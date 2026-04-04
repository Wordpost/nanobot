"""Handoff tool for inter-agent task delegation across containers (fork-local).

Enables agents running in separate Docker containers to communicate via HTTP
webhooks.  Each agent maintains its own isolated context; the handoff tool
provides the bridge by POSTing structured payloads to a peer's WebhookChannel
endpoint.

Configuration lives in ``workspace/swarm.json`` (never in core config.json).

Minimal config example::

    {
        "peers": {
            "aggregator": "secret-token"
        }
    }

The peer URL is auto-resolved as ``http://{peer_name}:{port}/webhook/swarm``
unless explicitly overridden.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Any

import aiohttp
from loguru import logger

from nanobot.agent.tools.base import Tool


class HandoffTool(Tool):
    """Tool to hand off tasks to peer agents in the swarm (fork-local)."""

    _SWARM_CONFIG_FILE = "swarm.json"
    _DEFAULT_PORT = 1987
    _DEFAULT_SLOT_PATH = "/webhook/swarm"

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace
        self._config = self._load_config()
        self._peers = self._normalize_peers()
        self._origin_channel = "cli"
        self._origin_chat_id = "direct"
        # Swarm context inherited from incoming swarm messages
        self._swarm_ctx: dict[str, Any] = {}
        # Session key for reply routing
        self._session_key: str = ""
        # Reusable HTTP session
        self._http_session: aiohttp.ClientSession | None = None

    # ------------------------------------------------------------------
    # Context management
    # ------------------------------------------------------------------

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the origin channel/chat for human-facing callbacks."""
        self._origin_channel = channel
        self._origin_chat_id = chat_id

    def set_swarm_context(self, metadata: dict[str, Any]) -> None:
        """Inject incoming swarm metadata so outgoing handoffs preserve the chain."""
        self._swarm_ctx = metadata if metadata.get("_swarm") else {}

    def set_session_key(self, session_key: str) -> None:
        """Set the current session key for reply routing."""
        self._session_key = session_key

    async def close(self) -> None:
        """Cleanup reusable HTTP session."""
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
            self._http_session = None

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
            "Communication channel between swarm agents. "
            "MANDATORY: Use this tool with type='peer-response' or type='result' to reply to incoming Swarm tasks. "
            "Use type='task' to delegate new sub-tasks to specialists. "
            "NEVER use plain text to communicate with peer agents; always use THIS tool. "
            f"Available target peers: [{peer_list}]. "
            "Types: 'task' (delegation), 'result' (returning answer to origin), 'notification' (status)."
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
                    "description": "Task description for the target agent",
                },
                "data": {
                    "type": "string",
                    "description": (
                        "Optional structured data (JSON string) to include. "
                        "Use for contacts, code, reports, etc."
                    ),
                },
                "type": {
                    "type": "string",
                    "description": (
                        "Message type: 'task' (default), 'result', or 'notification'"
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
        msg_type: str = "task",
        **kwargs: Any,
    ) -> str:
        """Execute handoff: POST payload to target agent's webhook."""
        if target not in self._peers:
            available = list(self._peers.keys())
            return (
                f"Error: Unknown peer '{target}'. "
                f"Available peers: {available}"
            )

        peer = self._peers[target]
        url = peer["url"]
        token = peer["token"]

        # ---- Anti-loop protection ----
        hop_count = self._swarm_ctx.get("_hop_count", 0) + 1
        max_hops = self._config.get("max_hops", 5)

        if hop_count > max_hops:
            logger.warning(
                "Swarm anti-loop: hop_count {} exceeds max_hops {} for chain {}",
                hop_count, max_hops, self._swarm_ctx.get("_chain_id", "?"),
            )
            return (
                f"Error: Maximum chain depth ({max_hops}) reached. "
                "Cannot hand off — summarize results and report to the user instead."
            )

        # ---- Build payload ----
        chain_id = self._swarm_ctx.get("_chain_id") or uuid.uuid4().hex[:8]
        identity = self._get_identity()

        payload: dict[str, Any] = {
            "task": task,
            "data": data,
            "origin": {
                "agent": identity,
                "url": self._build_self_url(),
            },
            "chain_id": chain_id,
            "hop_count": hop_count,
            "human": self._swarm_ctx.get("_human") or {
                "channel": self._origin_channel,
                "chat_id": self._origin_chat_id,
            },
            "type": msg_type,
            "reply_to_session": self._session_key,
        }

        # ---- Send ----
        try:
            session = await self._get_http_session()
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = f"Bearer {token}"

            async with session.post(
                url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    asyncio.create_task(
                        self._log_handoff_async(chain_id, target, hop_count, msg_type),
                    )
                    return (
                        f"✓ Task handed off to '{target}' "
                        f"(chain: {chain_id}, hop: {hop_count}/{max_hops}). "
                        "SUCCESS. Do NOT output any conversational text or 'continue' messages. End your turn immediately."
                    )
                body_text = await resp.text()
                logger.error(
                    "Handoff to '{}' failed: HTTP {} — {}",
                    target, resp.status, body_text[:200],
                )
                return f"Error: Handoff to '{target}' failed (HTTP {resp.status})"

        except aiohttp.ClientError as exc:
            logger.error("Handoff connection error to '{}': {}", target, exc)
            return f"Error: Could not connect to '{target}' — {exc}"
        except Exception as exc:
            logger.error("Handoff unexpected error to '{}': {}", target, exc)
            return f"Error: Unexpected error during handoff — {exc}"

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

    def _build_self_url(self) -> str:
        """Construct this agent's own webhook URL for callbacks (fork-local)."""
        explicit = self._config.get("self_url")
        if explicit:
            return explicit

        port = self._config.get("port", self._DEFAULT_PORT)
        host = self._get_identity()
        return f"http://{host}:{port}{self._DEFAULT_SLOT_PATH}"

    def _build_peer_url(self, peer_name: str) -> str:
        """Construct a peer's webhook URL using convention.

        Uses ``url_template`` from config if available, otherwise defaults to
        ``http://{target}:{port}/webhook/swarm``.
        """
        port = self._config.get("port", self._DEFAULT_PORT)
        template = self._config.get(
            "url_template",
            f"http://{{target}}:{port}{self._DEFAULT_SLOT_PATH}",
        )
        return template.replace("{target}", peer_name)

    async def _get_http_session(self) -> aiohttp.ClientSession:
        """Get or create a reusable HTTP session."""
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    def _normalize_peers(self) -> dict[str, dict[str, str]]:
        """Normalize peers to full format.

        Supports two formats in swarm.json::

            # Short: just a token string
            "peers": { "aggregator": "secret-token" }

            # Full: object with token and optional url
            "peers": { "aggregator": { "token": "secret-token", "url": "http://..." } }

        Returns a dict of ``{ name: { "token": str, "url": str } }``.
        """
        raw_peers = self._config.get("peers", {})
        normalized: dict[str, dict[str, str]] = {}

        for name, value in raw_peers.items():
            if isinstance(value, str):
                # Short format: value is the token
                normalized[name] = {
                    "token": value,
                    "url": self._build_peer_url(name),
                }
            elif isinstance(value, dict):
                # Full format: object with explicit fields
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
        chain_id: str,
        target: str,
        hop_count: int,
        msg_type: str,
    ) -> None:
        """Log handoff event to workspace/swarm/chains/{chain_id}.jsonl."""
        from datetime import datetime

        log_dir = self._workspace / "swarm" / "chains"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{chain_id}.jsonl"

        entry = {
            "timestamp": datetime.now().isoformat(),
            "from": self._get_identity(),
            "to": target,
            "hop": hop_count,
            "type": msg_type,
        }
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Failed to write swarm chain log: {}", exc)

    async def _log_handoff_async(
        self,
        chain_id: str,
        target: str,
        hop_count: int,
        msg_type: str,
    ) -> None:
        """Non-blocking log write via asyncio.to_thread."""
        await asyncio.to_thread(self._log_handoff, chain_id, target, hop_count, msg_type)
