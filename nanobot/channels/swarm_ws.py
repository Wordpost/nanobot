"""Swarm WebSocket channel: inter-agent streaming communication (fork-local).

Provides a dedicated WebSocket server for Swarm agent-to-agent tasks.
When a peer agent connects and sends a JSON task, this channel:
1. Authenticates via Bearer token from query parameter
2. Creates an InboundMessage and publishes to the MessageBus
3. Intercepts OutboundMessage via send()/send_delta() and streams
   delta/progress/message events back over the WebSocket connection

Wire Protocol (Server → Client):
    {"event": "accepted",  "context_id": "..."}
    {"event": "delta",     "text": "..."}
    {"event": "progress",  "text": "..."}
    {"event": "message",   "text": "...", "context_id": "..."}
    {"event": "error",     "text": "..."}

Wire Protocol (Client → Server, single frame after connect):
    {"task": "...", "data": "", "context_id": "...", "origin": {"agent": "..."}}

Configuration:
    Enabled via ``config.json → channels.swarm_ws.enabled``.
    Runtime settings (port, token) read from ``workspace/swarm.json``.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import uuid
from pathlib import Path
from typing import Any

from loguru import logger
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from nanobot.bus.events import OutboundMessage
from nanobot.channels.base import BaseChannel


class SwarmWSChannel(BaseChannel):
    """WebSocket server for Swarm inter-agent communication (fork-local)."""

    name = "swarm_ws"
    display_name = "Swarm WebSocket"

    _DEFAULT_PORT = 1988
    _WS_PATH = "/swarm"

    def __init__(self, config: Any, bus: Any) -> None:
        super().__init__(config, bus)
        self._stop_event = asyncio.Event()
        self._server_task: asyncio.Task[None] | None = None
        # {request_id → (ws_connection, Future)}
        self._pending: dict[str, tuple[ServerConnection, asyncio.Future[str]]] = {}
        # {request_id → context_id}  for final message decoration
        self._context_ids: dict[str, str] = {}
        self._swarm_token: str = ""
        self._swarm_port: int = self._DEFAULT_PORT

    # ------------------------------------------------------------------ #
    # Lifecycle                                                           #
    # ------------------------------------------------------------------ #

    @classmethod
    def default_config(cls) -> dict[str, Any]:
        return {"enabled": False}

    async def start(self) -> None:
        """Start the Swarm WebSocket server."""
        self._running = True
        self._stop_event.clear()

        swarm_cfg = self._load_swarm_config()
        if not swarm_cfg:
            logger.warning("swarm_ws: no swarm.json found — channel idle")
            await self._stop_event.wait()
            return

        self._swarm_token = swarm_cfg.get("token", "")
        self._swarm_port = swarm_cfg.get("port", self._DEFAULT_PORT)

        if not self._swarm_token:
            logger.error(
                "swarm_ws: 'token' is empty in swarm.json — refusing to start "
                "(set a strong secret for inter-agent auth)"
            )
            await self._stop_event.wait()
            return

        async def _process_request(
            connection: ServerConnection,
            request: Any,
        ) -> Any:
            """Validate path and token before WebSocket upgrade."""
            from urllib.parse import parse_qs, urlparse

            parsed = urlparse("ws://x" + (request.path or "/"))
            path = parsed.path.rstrip("/") or "/"
            if path != self._WS_PATH:
                return connection.respond(404, "Not Found")

            query = parse_qs(parsed.query)
            supplied = (query.get("token") or [None])[0]
            if not supplied or not hmac.compare_digest(supplied, self._swarm_token):
                logger.warning("swarm_ws: auth failed from {}", getattr(connection, "remote_address", "?"))
                return connection.respond(401, "Unauthorized")
            return None

        async def _handler(connection: ServerConnection) -> None:
            await self._connection_loop(connection)

        logger.info("Swarm WS listening on 0.0.0.0:{}{}", self._swarm_port, self._WS_PATH)

        async def _runner() -> None:
            async with serve(
                _handler,
                "0.0.0.0",
                self._swarm_port,
                process_request=_process_request,
                max_size=4_194_304,  # 4 MB
                ping_interval=30.0,
                ping_timeout=30.0,
            ):
                await self._stop_event.wait()

        self._server_task = asyncio.create_task(_runner())
        await self._server_task

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._stop_event.set()
        # Cancel all pending futures
        for request_id, (ws, future) in list(self._pending.items()):
            if not future.done():
                future.cancel()
        self._pending.clear()
        self._context_ids.clear()
        if self._server_task:
            try:
                await self._server_task
            except Exception as e:
                logger.warning("swarm_ws: server task error during shutdown: {}", e)
            self._server_task = None

    # ------------------------------------------------------------------ #
    # Connection handling                                                 #
    # ------------------------------------------------------------------ #

    async def _connection_loop(self, connection: ServerConnection) -> None:
        """Handle one peer agent connection: receive task → stream response."""
        request_id = uuid.uuid4().hex

        try:
            # 1. Read the task payload (single JSON frame)
            raw = await asyncio.wait_for(connection.recv(), timeout=30.0)
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await self._send_event(connection, "error", "Invalid JSON payload")
                return

            task = payload.get("task", "")
            data = payload.get("data", "")
            context_id = payload.get("context_id") or uuid.uuid4().hex[:8]
            origin = payload.get("origin", {})
            sender = origin.get("agent", "swarm-peer")

            if not task:
                await self._send_event(connection, "error", "Missing 'task' field")
                return

            # 2. Acknowledge
            await connection.send(json.dumps(
                {"event": "accepted", "context_id": context_id},
                ensure_ascii=False,
            ))

            # 3. Register pending request
            future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
            self._pending[request_id] = (connection, future)
            self._context_ids[request_id] = context_id

            session_key = f"swarm:{context_id}"

            # 4. Build LLM-visible content
            content_parts: list[str] = [f"[Message from {sender}]", task]
            if data:
                if isinstance(data, str) and data.strip():
                    content_parts.append(f"\nData:\n{data}")
                elif isinstance(data, (dict, list)):
                    content_parts.append(
                        f"\nData:\n{json.dumps(data, ensure_ascii=False, indent=2)}"
                    )
            text = "\n".join(content_parts)

            logger.info(
                "[swarm_ws] task from '{}' (ctx={}): {}",
                sender, context_id, task[:80],
            )

            # 5. Publish to AgentLoop
            metadata = {"_request_id": request_id, "_wants_stream": True}
            await self._handle_message(
                sender_id=sender,
                chat_id=session_key,
                content=text,
                media=[],
                metadata=metadata,
            )

            # 6. Wait for AgentLoop to produce response
            try:
                result = await asyncio.wait_for(future, timeout=600)
                # Final message is sent by send() — nothing more to do here
                _ = result  # consumed by send()
            except asyncio.TimeoutError:
                logger.error("[swarm_ws] timeout waiting for AgentLoop (ctx={})", context_id)
                await self._send_event(connection, "error", "Agent did not respond within 600 seconds")
            except asyncio.CancelledError:
                await self._send_event(connection, "error", "Request cancelled")

        except ConnectionClosed:
            logger.debug("swarm_ws: peer disconnected during task (req={})", request_id)
        except Exception as e:
            logger.error("swarm_ws: connection error: {}", e)
            try:
                await self._send_event(connection, "error", str(e))
            except Exception:
                pass
        finally:
            self._pending.pop(request_id, None)
            self._context_ids.pop(request_id, None)

    # ------------------------------------------------------------------ #
    # Outbound: intercept AgentLoop responses                             #
    # ------------------------------------------------------------------ #

    async def send(self, msg: OutboundMessage) -> None:
        """Deliver final response or progress to the calling agent via WS."""
        meta = msg.metadata or {}
        request_id = meta.get("_request_id")
        if not request_id or request_id not in self._pending:
            return  # Not a swarm message — ignore

        ws, future = self._pending[request_id]
        context_id = self._context_ids.get(request_id, "")

        # Suppress progress if the connection is for swarm
        if meta.get("_progress"):
            text = msg.content or ""
            if text.strip():
                event_type = "progress" if meta.get("_tool_hint") else "delta"
                await self._safe_ws_send(ws, request_id, event_type, text)
            return

        # Final response
        try:
            await ws.send(json.dumps(
                {"event": "message", "text": msg.content or "", "context_id": context_id},
                ensure_ascii=False,
            ))
        except ConnectionClosed:
            logger.warning("swarm_ws: peer gone before final message (req={})", request_id)
        except Exception as e:
            logger.error("swarm_ws: send final failed: {}", e)

        if not future.done():
            future.set_result(msg.content or "")

    async def send_delta(
        self,
        chat_id: str,
        delta: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Stream text chunks back to the calling agent."""
        meta = metadata or {}
        request_id = meta.get("_request_id")
        if not request_id or request_id not in self._pending:
            return

        if meta.get("_stream_end"):
            return  # Internal event, don't forward

        ws, _ = self._pending[request_id]
        await self._safe_ws_send(ws, request_id, "delta", delta)

    # ------------------------------------------------------------------ #
    # Helpers                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _send_event(ws: ServerConnection, event: str, text: str) -> None:
        """Send a JSON event frame to the client."""
        try:
            await ws.send(json.dumps({"event": event, "text": text}, ensure_ascii=False))
        except Exception:
            pass

    async def _safe_ws_send(
        self, ws: ServerConnection, request_id: str, event: str, text: str,
    ) -> None:
        """Send a JSON event, cleaning up on ConnectionClosed."""
        try:
            await ws.send(json.dumps(
                {"event": event, "text": text}, ensure_ascii=False,
            ))
        except ConnectionClosed:
            self._pending.pop(request_id, None)
            self._context_ids.pop(request_id, None)
            logger.debug("swarm_ws: peer gone during {} (req={})", event, request_id)
        except Exception as e:
            logger.error("swarm_ws: send {} failed: {}", event, e)

    def _load_swarm_config(self) -> dict[str, Any] | None:
        """Load swarm.json from the workspace."""
        workspace = os.environ.get("NANOBOT_WORKSPACE", "")
        if workspace:
            path = Path(workspace) / "swarm.json"
        else:
            # Fallback: try common paths
            for candidate in [
                Path(".nanobot/workspace/swarm.json"),
                Path("/home/nanobot/.nanobot/workspace/swarm.json"),
            ]:
                if candidate.is_file():
                    path = candidate
                    break
            else:
                return None

        if not path.is_file():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            logger.info("swarm_ws: loaded config from {} (port={}, peers={})",
                        path, data.get("port", self._DEFAULT_PORT),
                        list(data.get("peers", {}).keys()))
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("swarm_ws: failed to load {}: {}", path, exc)
            return None
