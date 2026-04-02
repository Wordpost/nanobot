import asyncio
import json
import re
from typing import Any

from aiohttp import web
from loguru import logger

from nanobot.channels.base import BaseChannel
from nanobot.bus.events import OutboundMessage

class WebhookChannel(BaseChannel):
    name = "webhook"
    display_name = "Webhook"

    def __init__(self, config: Any, bus: Any):
        super().__init__(config, bus)
        self.raw_mappings = self.config.get("mappings", {}) if isinstance(self.config, dict) else getattr(self.config, "mappings", {})
        self._stop_event = asyncio.Event()

    @classmethod
    def default_config(cls) -> dict[str, Any]:
        return {
            "enabled": False,
            "port": 1987,
            "token": "",
            "allowFrom": ["*"],
            "mappings": {
                "messageTemplate": "",
                "senderTemplate": "webhook",
                "sessionKey": "webhook",
            }
        }

    def is_allowed(self, sender_id: str) -> bool:
        """
        Overriding is_allowed directly in our plugin to fix the dictionary configuration bug
        in nanobots core BaseChannel without needing to modify the core itself.
        """
        # The core does getattr(self.config, 'allow_from'), which fails when self.config is a dict
        allow_list = self.config.get("allowFrom", self.config.get("allow_from", []))
        if not allow_list:
            logger.warning("{}: allowFrom is empty — all access denied", self.name)
            return False
        if "*" in allow_list:
            return True
        return str(sender_id) in allow_list

    async def start(self) -> None:
        """Start an HTTP server that listens for incoming JSON events."""
        self._running = True
        port = self.config.get("port", 1987) if isinstance(self.config, dict) else getattr(self.config, "port", 1987)

        app = web.Application()
        # Endpoints matching OpenClaw's approach
        app.router.add_post("/webhook", self._on_request)
        app.router.add_post("/webhook/{agent}", self._on_request) 

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info("Webhook listening on :{}", port)

        # Block until stopped
        self._stop_event.clear()
        await self._stop_event.wait()

        await runner.cleanup()

    async def stop(self) -> None:
        self._running = False
        self._stop_event.set()

    async def send(self, msg: OutboundMessage) -> None:
        """Deliver an outbound message.
        Webhooks typically are one-way (inbound), unless an explicit callback URL is set.
        For now, we just log it.
        """
        logger.info("[webhook] -> {}: {}", msg.chat_id, msg.content[:80])

    def _verify_token(self, request: web.Request) -> web.Response | None:
        """Verify request authorization. Returns error Response if invalid, else None."""
        import hmac
        expected_token = self.config.get("token") if isinstance(self.config, dict) else getattr(self.config, "token", None)
        
        if not expected_token:
            logger.error("Security Alert: Webhook channel running without a 'token'.")
            return web.json_response({"error": "Internal Server Error - Security Misconfiguration"}, status=500)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            logger.warning("Webhook auth failed: Missing Bearer token.")
            return web.json_response({"error": "Unauthorized"}, status=401)
            
        if not hmac.compare_digest(auth_header[7:], expected_token):
            logger.warning("Webhook auth failed: Invalid token.")
            return web.json_response({"error": "Unauthorized"}, status=401)
            
        return None

    def _extract_payload(self, body: dict) -> tuple[str, str, str]:
        """Extract text, sender, and chat_id from JSON body via mapped templates."""
        text = self._render_template(self.raw_mappings.get("messageTemplate"), body)
        sender = self._render_template(self.raw_mappings.get("senderTemplate", "webhook"), body)
        chat_id = self._render_template(self.raw_mappings.get("sessionKey", "webhook"), body)

        if not text:
            # Fallback for arbitrary payloads with no templates
            text = json.dumps(body, indent=2, ensure_ascii=False)
            
        return text, sender, chat_id

    async def _on_request(self, request: web.Request) -> web.Response:
        """Handle incoming HTTP POST routing and dispatching."""
        auth_err = self._verify_token(request)
        if auth_err:
            return auth_err
        
        try:
            body = await request.json()
        except json.JSONDecodeError:
            logger.error("Received non-JSON content on webhook")
            return web.json_response({"error": "Invalid JSON"}, status=400)

        text, sender, chat_id = self._extract_payload(body)

        await self._handle_message(
            sender_id=sender,
            chat_id=chat_id,
            content=text,
            media=[],
        )

        return web.json_response({"ok": True, "sender_id": sender})

    def _render_template(self, template_str: str | None, data: dict) -> str:
        """
        Lightweight custom template parser that supports dot.notation and array index access
        e.g., {{ messages.0.text }} extracts from {"messages": [{"text": "Hello"}]}
        """
        if not template_str:
            return ""
        
        def replace(match):
            keys = match.group(1).strip().split('.')
            val = data
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
            return re.sub(r'\{\{(.*?)\}\}', replace, str(template_str))
        except Exception as e:
            logger.error("Failed to parse template '{}': {}", template_str, e)
            return ""
