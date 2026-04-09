"""Handoff tool for inter-agent communication across containers (fork-local).

Enables agents running in separate Docker containers to exchange information
via synchronous HTTP requests.  Each agent maintains its own isolated context;
the handoff tool provides the bridge by POSTing structured payloads to a peer's
WebhookChannel endpoint and **waiting** for the response.

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
    """Synchronous tool to exchange information with peer agents (fork-local)."""

    _SWARM_CONFIG_FILE = "swarm.json"
    _DEFAULT_PORT = 1987
    _DEFAULT_SLOT_PATH = "/webhook/swarm"
    _TIMEOUT_SECONDS = 120

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace
        self._config = self._load_config()
        self._peers = self._normalize_peers()

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
        """Send task to peer agent and WAIT for their response (fork-local)."""
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

        payload: dict[str, Any] = {
            "task": task,
            "data": data,
            "context_id": ctx_id,
            "origin": {"agent": identity},
        }

        try:
            async with aiohttp.ClientSession() as session:
                headers: dict[str, str] = {"Content-Type": "application/json"}
                if token:
                    headers["Authorization"] = f"Bearer {token}"

                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self._TIMEOUT_SECONDS),
                ) as resp:
                    body = await resp.json()

                    if resp.status == 200 and body.get("status") == "completed":
                        result = body.get("result", "")
                        self._log_handoff(ctx_id, target, "completed")
                        return (
                            f"Response from {target} (context: {ctx_id}):\n"
                            f"{result}"
                        )
                    else:
                        error = body.get("error", f"HTTP {resp.status}")
                        self._log_handoff(ctx_id, target, "error")
                        return f"Error from {target}: {error}"

        except asyncio.TimeoutError:
            self._log_handoff(ctx_id, target, "timeout")
            return (
                f"Error: {target} did not respond within "
                f"{self._TIMEOUT_SECONDS} seconds."
            )
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
