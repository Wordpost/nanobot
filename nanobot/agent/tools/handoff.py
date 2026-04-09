"""Handoff tool for inter-agent communication via WebSocket (fork-local).

Enables agents running in separate Docker containers to exchange information
via streaming WebSocket connections.  Each agent maintains its own isolated
context; the handoff tool provides the bridge by connecting to a peer's
SwarmWSChannel endpoint and **listening** for delta/progress/message events.

Configuration lives in ``workspace/swarm.json`` (never in core config.json).

Minimal config example::

    {
        "peers": {
            "aggregator": "secret-token"
        }
    }

The peer URL is auto-resolved as ``ws://{peer_name}:{port}/swarm``
unless explicitly overridden.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.tools.base import Tool
from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus


class HandoffTool(Tool):
    """Streaming tool to exchange information with peer agents via WebSocket (fork-local)."""

    _SWARM_CONFIG_FILE = "swarm.json"
    _DEFAULT_PORT = 1988
    _DEFAULT_SLOT_PATH = "/swarm"
    _IDLE_TIMEOUT = 300  # seconds without any event → peer considered dead

    def __init__(self, workspace: Path, bus: MessageBus) -> None:
        self._workspace = workspace
        self._bus = bus
        self._config = self._load_config()
        self._peers = self._normalize_peers()
        self._origin_channel = "cli"
        self._origin_chat_id = "direct"

    # ------------------------------------------------------------------
    # Context for UI forwarding (set by AgentLoop._set_tool_context)
    # ------------------------------------------------------------------

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the origin context for forwarding peer delta/progress to user."""
        self._origin_channel = channel
        self._origin_chat_id = chat_id

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "handoff"

    @property
    def description(self) -> str:
        peers = list(self._peers.keys())
        peer_list = ", ".join(peers) if peers else "none configured"
        return (
            "Send a message or task to a peer agent and get their response. "
            "Use context_id to continue a previous conversation with the same peer. "
            f"Available peers: [{peer_list}]."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        peers = list(self._peers.keys())
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": f"Name of the target peer agent. One of: {peers}",
                },
                "task": {
                    "type": "string",
                    "description": "Task or message for the peer agent",
                },
                "data": {
                    "type": "string",
                    "description": (
                        "Optional structured data (JSON string) to include. "
                        "Use for contacts, code, reports, etc."
                    ),
                },
                "context_id": {
                    "type": "string",
                    "description": (
                        "Optional. Pass the context ID from a previous handoff "
                        "to continue the same conversation with the peer."
                    ),
                },
            },
            "required": ["target", "task"],
        }

    async def execute(
        self,
        target: str,
        task: str,
        data: str = "",
        context_id: str = "",
        **kwargs: Any,
    ) -> str:
        """Connect to peer agent via WebSocket, stream events, return result (fork-local)."""
        if target not in self._peers:
            available = list(self._peers.keys())
            return (
                f"Error: Unknown peer '{target}'. "
                f"Available peers: {available}"
            )

        peer = self._peers[target]
        url = peer["url"]
        token = peer["token"]

        ctx_id = context_id or uuid.uuid4().hex[:8]
        identity = self._get_identity()

        # Build WS URL with token
        separator = "&" if "?" in url else "?"
        ws_url = f"{url}{separator}token={token}"

        payload = json.dumps({
            "task": task,
            "data": data,
            "context_id": ctx_id,
            "origin": {"agent": identity},
        }, ensure_ascii=False)

        try:
            import websockets

            async with websockets.connect(
                ws_url,
                max_size=4_194_304,
                ping_interval=30.0,
                ping_timeout=30.0,
            ) as ws:
                # Send task
                await ws.send(payload)

                # Listen for events
                last_activity = time.monotonic()

                async for raw in ws:
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")

                    last_activity = time.monotonic()

                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning("[handoff] non-JSON frame from {}: {}", target, raw[:100])
                        continue

                    event = msg.get("event", "")

                    if event == "accepted":
                        logger.info("[handoff] accepted by {} (ctx={})", target, ctx_id)

                    elif event == "delta":
                        await self._forward_progress(msg.get("text", ""), tool_hint=False)

                    elif event == "progress":
                        await self._forward_progress(msg.get("text", ""), tool_hint=True)

                    elif event == "message":
                        result = msg.get("text", "")
                        self._log_handoff(ctx_id, target, "completed")
                        return (
                            f"Response from {target} (context: {ctx_id}):\n"
                            f"{result}"
                        )

                    elif event == "error":
                        self._log_handoff(ctx_id, target, "error")
                        return f"Error from {target}: {msg.get('text', 'unknown error')}"

                    # Check idle timeout
                    if time.monotonic() - last_activity > self._IDLE_TIMEOUT:
                        self._log_handoff(ctx_id, target, "idle_timeout")
                        return (
                            f"Error: {target} stopped sending events after "
                            f"{self._IDLE_TIMEOUT} seconds of inactivity."
                        )

                # Connection closed without a "message" event
                self._log_handoff(ctx_id, target, "closed_without_result")
                return f"Error: {target} closed connection without sending a result."

        except asyncio.TimeoutError:
            self._log_handoff(ctx_id, target, "timeout")
            return f"Error: Connection to {target} timed out."
        except Exception as exc:
            logger.error("Handoff WS error to '{}': {}", target, exc)
            self._log_handoff(ctx_id, target, "error")
            return f"Error: Could not connect to '{target}' — {exc}"

    # ------------------------------------------------------------------
    # UI forwarding
    # ------------------------------------------------------------------

    async def _forward_progress(self, text: str, *, tool_hint: bool = False) -> None:
        """Forward peer's delta/progress to the calling user's channel via bus."""
        if not self._bus or not text.strip():
            return
        meta: dict[str, Any] = {"_progress": True, "_tool_hint": tool_hint}
        await self._bus.publish_outbound(OutboundMessage(
            channel=self._origin_channel,
            chat_id=self._origin_chat_id,
            content=text,
            metadata=meta,
        ))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_identity(self) -> str:
        """Determine this agent's name.

        Priority: explicit ``name`` in swarm.json → HOSTNAME env var → fallback.
        """
        explicit = self._config.get("name") or self._config.get("role")
        if explicit:
            return explicit
        return os.environ.get("HOSTNAME", "unknown-agent")

    def _build_peer_url(self, peer_name: str) -> str:
        """Construct a peer's WebSocket URL using convention.

        Uses ``url_template`` from config if available, otherwise defaults to
        ``ws://{target}:{port}/swarm``.
        """
        port = self._config.get("port", self._DEFAULT_PORT)
        template = self._config.get(
            "url_template",
            f"ws://{{target}}:{port}{self._DEFAULT_SLOT_PATH}",
        )
        return template.replace("{target}", peer_name)

    def _normalize_peers(self) -> dict[str, dict[str, str]]:
        """Normalize peers to full format.

        Supports two formats in swarm.json::

            # Short: just a token string
            "peers": { "aggregator": "secret-token" }

            # Full: object with token and optional url
            "peers": { "aggregator": { "token": "secret-token", "url": "ws://..." } }

        Returns a dict of ``{ name: { "token": str, "url": str } }``.
        """
        raw_peers = self._config.get("peers", {})
        normalized: dict[str, dict[str, str]] = {}

        for name, value in raw_peers.items():
            if isinstance(value, str):
                normalized[name] = {
                    "token": value,
                    "url": self._build_peer_url(name),
                }
            elif isinstance(value, dict):
                token = value.get("token", "")
                url = value.get("url") or self._build_peer_url(name)
                normalized[name] = {"token": token, "url": url}
            else:
                logger.warning("Swarm: invalid peer config for '{}', skipping", name)

        return normalized

    def _load_config(self) -> dict[str, Any]:
        """Load swarm.json from the agent's workspace."""
        path = self._workspace / self._SWARM_CONFIG_FILE
        if not path.exists():
            logger.debug("No swarm.json found at {}", path)
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            peers = list(data.get("peers", {}).keys())
            identity = data.get("name") or data.get("role") or os.environ.get("HOSTNAME", "?")
            logger.info("Swarm config loaded: identity='{}', peers={}", identity, peers)
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load swarm.json: {}", exc)
            return {}

    def _log_handoff(
        self,
        context_id: str,
        target: str,
        status: str,
    ) -> None:
        """Log handoff event to workspace/swarm/chains/{context_id}.jsonl."""
        from datetime import datetime

        log_dir = self._workspace / "swarm" / "chains"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{context_id}.jsonl"

        entry = {
            "timestamp": datetime.now().isoformat(),
            "from": self._get_identity(),
            "to": target,
            "status": status,
        }
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Failed to write swarm chain log: {}", exc)
