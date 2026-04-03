"""Handoff tool for inter-agent task delegation across containers (fork-local).

Enables agents running in separate Docker containers to communicate via HTTP
webhooks.  Each agent maintains its own isolated context; the handoff tool
provides the bridge by POSTing structured payloads to a peer's WebhookChannel
endpoint.

Configuration lives in ``workspace/swarm.json`` (never in core config.json).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import aiohttp
from loguru import logger

from nanobot.agent.tools.base import Tool


class HandoffTool(Tool):
    """Tool to hand off tasks to peer agents in the swarm (fork-local)."""

    _SWARM_CONFIG_FILE = "swarm.json"

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace
        self._config = self._load_config()
        self._origin_channel = "cli"
        self._origin_chat_id = "direct"
        # Swarm context inherited from incoming swarm messages
        self._swarm_ctx: dict[str, Any] = {}

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

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "handoff"

    @property
    def description(self) -> str:
        peers = list(self._config.get("peers", {}).keys())
        peer_list = ", ".join(peers) if peers else "none configured"
        return (
            "Hand off a task to another agent in the swarm. "
            "Use this when a task requires a different specialist agent "
            "(e.g. parser → aggregator, coder → tester). "
            "The target agent will process the task independently and can "
            "send results back via its own handoff. "
            f"Available peers: [{peer_list}]. "
            "Types: 'task' (new work), 'result' (return findings), "
            "'notification' (lightweight status update)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        peers = list(self._config.get("peers", {}).keys())
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
        type: str = "task",
        **kwargs: Any,
    ) -> str:
        """Execute handoff: POST payload to target agent's webhook."""
        peers = self._config.get("peers", {})
        if target not in peers:
            available = list(peers.keys())
            return (
                f"Error: Unknown peer '{target}'. "
                f"Available peers: {available}"
            )

        peer = peers[target]
        url = peer.get("url", "")
        token = peer.get("token", "")

        if not url:
            return f"Error: No URL configured for peer '{target}'"

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
        role = self._config.get("role", "unknown")

        payload: dict[str, Any] = {
            "task": task,
            "data": data,
            "origin": {
                "agent": role,
                "url": self._build_self_url(),
            },
            "chain_id": chain_id,
            "hop_count": hop_count,
            "human": self._swarm_ctx.get("_human") or {
                "channel": self._origin_channel,
                "chat_id": self._origin_chat_id,
            },
            "type": type,
        }

        # ---- Send ----
        try:
            async with aiohttp.ClientSession() as session:
                headers: dict[str, str] = {"Content-Type": "application/json"}
                if token:
                    headers["Authorization"] = f"Bearer {token}"

                async with session.post(
                    url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        self._log_handoff(chain_id, target, hop_count, type)
                        return (
                            f"✓ Task handed off to '{target}' "
                            f"(chain: {chain_id}, hop: {hop_count}/{max_hops})"
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

    def _load_config(self) -> dict[str, Any]:
        """Load swarm.json from the agent's workspace."""
        path = self._workspace / self._SWARM_CONFIG_FILE
        if not path.exists():
            logger.debug("No swarm.json found at {}", path)
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            role = data.get("role", "?")
            peers = list(data.get("peers", {}).keys())
            logger.info("Swarm config loaded: role='{}', peers={}", role, peers)
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load swarm.json: {}", exc)
            return {}

    def _build_self_url(self) -> str:
        """Construct this agent's own webhook URL for callbacks."""
        self_url = self._config.get("self_url")
        if self_url:
            return self_url

        import os

        # Use HOSTNAME (auto-set by Docker) or fallback to role-based name
        host = os.environ.get("HOSTNAME", f"nanobot-{self._config.get('role', 'unknown')}")
        url = f"http://{host}:1987/webhook"

        logger.debug("Swarm: using {} as self_url (from HOSTNAME or role)", url)
        return url

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
            "from": self._config.get("role", "unknown"),
            "to": target,
            "hop": hop_count,
            "type": msg_type,
        }
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Failed to write swarm chain log: {}", exc)
