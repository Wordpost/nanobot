"""Webhook channel with slot-based routing (fork-local).

Each *slot* is a named webhook receiver with its own:
- HTTP path (e.g. ``/webhook/swarm``, ``/webhook/crm``)
- Bearer token for authentication
- Handler type (``standard``, ``swarm``, ``raw``)
- Mapping templates for payload extraction
- Optional fixed session key

Slots are configured in ``channels.webhook.slots`` in ``config.json``.
"""

import asyncio
import json
import re
from typing import Any

from aiohttp import web
from loguru import logger

from nanobot.channels.base import BaseChannel
from nanobot.bus.events import OutboundMessage


# ------------------------------------------------------------------ #
# Slot definition                                                     #
# ------------------------------------------------------------------ #

class WebhookSlot:
    """A single named webhook receiver configuration.

    Handler type is derived from the slot name for built-in types
    (``swarm``, ``raw``).  All other names default to ``standard``.
    Path defaults to ``/webhook/{name}`` (or ``/webhook`` for "default").
    """

    __slots__ = ("name", "path", "token", "handler", "mappings", "session_key", "allow_from")

    # Built-in handler types that auto-resolve from slot name
    _BUILTIN_HANDLERS = frozenset({"swarm", "raw"})

    def __init__(self, name: str, cfg: dict[str, Any]) -> None:
        self.name = name
        self.path: str = cfg.get("path", f"/webhook/{name}" if name != "default" else "/webhook")
        self.token: str = cfg.get("token", "")
        # Handler: explicit > derived from name > "standard"
        self.handler: str = cfg.get(
            "handler", name if name in self._BUILTIN_HANDLERS else "standard",
        )
        self.mappings: dict[str, str] = cfg.get("mappings", {})
        self.session_key: str | None = cfg.get("sessionKey") or cfg.get("session_key")
        self.allow_from: list[str] = cfg.get("allowFrom", cfg.get("allow_from", ["*"]))

    def __repr__(self) -> str:
        return f"<Slot '{self.name}' path={self.path} handler={self.handler}>"


# ------------------------------------------------------------------ #
# WebhookChannel                                                      #
# ------------------------------------------------------------------ #

class WebhookChannel(BaseChannel):
    """HTTP webhook channel with slot-based multi-endpoint routing (fork-local)."""

    name = "webhook"
    display_name = "Webhook"

    def __init__(self, config: Any, bus: Any) -> None:
        super().__init__(config, bus)
        self._stop_event = asyncio.Event()
        self._slots: dict[str, WebhookSlot] = {}  # path → slot
        self._build_slots()

    # ------------------------------------------------------------------ #
    # Slot registry                                                       #
    # ------------------------------------------------------------------ #

    def _cfg(self, key: str, default: Any = None) -> Any:
        """Read from config regardless of dict or pydantic model."""
        if isinstance(self.config, dict):
            return self.config.get(key, default)
        return getattr(self.config, key, default)

    def _build_slots(self) -> None:
        """Build slot registry from config.slots."""
        slots_cfg = self._cfg("slots")

        if not slots_cfg or not isinstance(slots_cfg, dict):
            logger.error(
                "WebhookChannel: 'slots' not configured. "
                "Add 'slots' section to channels.webhook in config.json"
            )
            return

        for slot_name, slot_data in slots_cfg.items():
            slot = WebhookSlot(slot_name, slot_data)
            self._slots[slot.path] = slot
            logger.debug("Webhook slot registered: {}", slot)

        if not self._slots:
            logger.warning("WebhookChannel: no slots configured")

    def _match_slot(self, path: str) -> WebhookSlot | None:
        """Find the slot that matches the request path."""
        # Exact match
        if path in self._slots:
            return self._slots[path]

        # Without trailing slash
        clean = path.rstrip("/")
        if clean in self._slots:
            return self._slots[clean]

        return None

    # ------------------------------------------------------------------ #
    # Lifecycle                                                           #
    # ------------------------------------------------------------------ #

    @classmethod
    def default_config(cls) -> dict[str, Any]:
        return {
            "enabled": False,
            "port": 1987,
            "slots": {
                "default": {
                    "token": "",
                    "allowFrom": ["*"],
                    "mappings": {
                        "messageTemplate": "",
                        "senderTemplate": "webhook",
                        "sessionKey": "webhook",
                    },
                },
            },
        }

    def _is_allowed_by_slot(self, slot: WebhookSlot, sender_id: str) -> bool:
        """Check per-slot allow list."""
        if not slot.allow_from:
            return True  # slot inherits channel-level check
        if "*" in slot.allow_from:
            return True
        return str(sender_id) in slot.allow_from

    async def start(self) -> None:
        """Start HTTP server with routes for each configured slot."""
        self._running = True
        port = self._cfg("port", 1987)

        app = web.Application()

        # Register route for each slot path
        for path in self._slots:
            app.router.add_post(path, self._on_request)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()

        slot_names = [s.name for s in self._slots.values()]
        logger.info("Webhook listening on :{}, slots: {}", port, slot_names)

        self._stop_event.clear()
        await self._stop_event.wait()
        await runner.cleanup()

    async def stop(self) -> None:
        self._running = False
        self._stop_event.set()

    async def send(self, msg: OutboundMessage) -> None:
        """Deliver outbound (log-only for webhooks unless callback configured)."""
        logger.info("[webhook] -> {}: {}", msg.chat_id, msg.content[:80])

    # ------------------------------------------------------------------ #
    # Request handling — slot dispatcher                                  #
    # ------------------------------------------------------------------ #

    async def _on_request(self, request: web.Request) -> web.Response:
        """Route incoming POST to the matching slot handler."""
        path = request.path

        slot = self._match_slot(path)
        if not slot:
            logger.warning("No slot matches path: {}", path)
            return web.json_response({"error": f"No handler for {path}"}, status=404)

        # Per-slot auth
        auth_err = self._verify_slot_token(request, slot)
        if auth_err:
            return auth_err

        # Parse body
        try:
            body = await request.json()
        except json.JSONDecodeError:
            logger.error("Received non-JSON content on {}", path)
            return web.json_response({"error": "Invalid JSON"}, status=400)

        # Dispatch by handler type
        if slot.handler == "swarm":
            return await self._handle_swarm(slot, body)
        elif slot.handler == "raw":
            return await self._handle_raw(slot, body)
        else:
            return await self._handle_standard(slot, body)

    # ------------------------------------------------------------------ #
    # Auth                                                                #
    # ------------------------------------------------------------------ #

    def _verify_slot_token(self, request: web.Request, slot: WebhookSlot) -> web.Response | None:
        """Verify Bearer token for a specific slot. Returns error Response or None."""
        import hmac

        token = slot.token
        if not token:
            logger.error("Security Alert: slot '{}' has no token configured.", slot.name)
            return web.json_response(
                {"error": "Internal Server Error - Security Misconfiguration"}, status=500,
            )

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            logger.warning("Auth failed on slot '{}': Missing Bearer token.", slot.name)
            return web.json_response({"error": "Unauthorized"}, status=401)

        if not hmac.compare_digest(auth_header[7:], token):
            logger.warning("Auth failed on slot '{}': Invalid token.", slot.name)
            return web.json_response({"error": "Unauthorized"}, status=401)

        return None

    # ------------------------------------------------------------------ #
    # Handler: standard (template-based extraction)                       #
    # ------------------------------------------------------------------ #

    async def _handle_standard(self, slot: WebhookSlot, body: dict) -> web.Response:
        """Process via template mappings (same logic as legacy _extract_payload)."""
        mappings = slot.mappings
        text = self._render_template(mappings.get("messageTemplate"), body)
        sender = self._render_template(mappings.get("senderTemplate", "webhook"), body)
        chat_id = slot.session_key or self._render_template(
            mappings.get("sessionKey", "webhook"), body,
        )

        if not text:
            text = json.dumps(body, indent=2, ensure_ascii=False)

        if not self._is_allowed_by_slot(slot, sender):
            logger.warning("Access denied for sender {} on slot '{}'", sender, slot.name)
            return web.json_response({"error": "Forbidden"}, status=403)

        await self._handle_message(
            sender_id=sender,
            chat_id=chat_id,
            content=text,
            media=[],
        )
        return web.json_response({"ok": True, "slot": slot.name, "sender_id": sender})

    # ------------------------------------------------------------------ #
    # Handler: swarm (inter-agent handoff)                                #
    # ------------------------------------------------------------------ #

    async def _handle_swarm(self, slot: WebhookSlot, body: dict) -> web.Response:
        """Process swarm handoff payload.

        Extracts machine metadata into InboundMessage.metadata (invisible to
        the LLM) and formats the task + data as clean text for the agent.
        """
        task = body.get("task", "")
        data = body.get("data")
        msg_type = body.get("type", "task")
        origin = body.get("origin", {})
        chain_id = body.get("chain_id", "default")

        # Validate required swarm fields
        if not task:
            return web.json_response({"error": "Missing 'task' field"}, status=400)

        # Build LLM-visible content
        content_parts: list[str] = [task]
        if data:
            if isinstance(data, str) and data.strip():
                content_parts.append(f"\nДанные:\n{data}")
            elif isinstance(data, (dict, list)):
                content_parts.append(
                    f"\nДанные:\n{json.dumps(data, ensure_ascii=False, indent=2)}"
                )
        text = "\n".join(content_parts)

        # Machine metadata — accessible to HandoffTool, hidden from LLM
        metadata = {
            "_swarm": True,
            "_chain_id": chain_id,
            "_hop_count": body.get("hop_count", 0),
            "_origin": origin,
            "_human": body.get("human", {}),
            "_type": msg_type,
            "_slot": slot.name,
        }

        sender = origin.get("agent", "swarm")
        session_key = f"swarm:{chain_id}"

        logger.info(
            "Swarm {} from '{}' via slot '{}' (chain={}, hop={}): {}",
            msg_type, sender, slot.name, chain_id,
            body.get("hop_count", 0), task[:80],
        )

        await self._handle_message(
            sender_id=sender,
            chat_id=session_key,
            content=text,
            media=[],
            metadata=metadata,
        )

        return web.json_response({"ok": True, "swarm": True, "chain_id": chain_id})

    # ------------------------------------------------------------------ #
    # Handler: raw (pass full body as JSON)                               #
    # ------------------------------------------------------------------ #

    async def _handle_raw(self, slot: WebhookSlot, body: dict) -> web.Response:
        """Pass the full JSON body as text to the agent."""
        text = json.dumps(body, indent=2, ensure_ascii=False)
        chat_id = slot.session_key or f"webhook:{slot.name}"
        sender = f"webhook:{slot.name}"

        await self._handle_message(
            sender_id=sender,
            chat_id=chat_id,
            content=text,
            media=[],
            metadata={"_slot": slot.name, "_raw": True},
        )

        return web.json_response({"ok": True, "slot": slot.name})

    # ------------------------------------------------------------------ #
    # Template engine (unchanged)                                         #
    # ------------------------------------------------------------------ #

    def _render_template(self, template_str: str | None, data: dict) -> str:
        """Lightweight template parser: ``{{ messages.0.text }}`` dot-notation."""
        if not template_str:
            return ""

        def replace(match: re.Match) -> str:
            keys = match.group(1).strip().split(".")
            val: Any = data
            for k in keys:
                if isinstance(val, dict):
                    val = val.get(k, "")
                elif isinstance(val, list) and k.isdigit():
                    idx = int(k)
                    val = val[idx] if 0 <= idx < len(val) else ""
                else:
                    return ""
                if val == "":
                    return ""
            return str(val) if val is not None else ""

        try:
            return re.sub(r"\{\{(.*?)\}\}", replace, str(template_str))
        except Exception as e:
            logger.error("Failed to parse template '{}': {}", template_str, e)
            return ""
