"""OpenAI-compatible HTTP API server for a fixed nanobot session.

Provides /v1/chat/completions, /v1/models, and /v1/swarm/handoff endpoints.
All requests route to a single persistent API session.

The /v1/swarm/handoff endpoint (fork-local) enables async inter-agent
task delegation within the swarm network.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from aiohttp import web
from loguru import logger

from nanobot.utils.runtime import EMPTY_FINAL_RESPONSE_MESSAGE

API_SESSION_KEY = "api:default"
API_CHAT_ID = "default"


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _error_json(status: int, message: str, err_type: str = "invalid_request_error") -> web.Response:
    return web.json_response(
        {"error": {"message": message, "type": err_type, "code": status}},
        status=status,
    )


def _chat_completion_response(content: str, model: str) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _response_text(value: Any) -> str:
    """Normalize process_direct output to plain assistant text."""
    if value is None:
        return ""
    if hasattr(value, "content"):
        return str(getattr(value, "content") or "")
    return str(value)


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

async def handle_chat_completions(request: web.Request) -> web.Response:
    """POST /v1/chat/completions"""

    # --- Parse body ---
    try:
        body = await request.json()
    except Exception:
        return _error_json(400, "Invalid JSON body")

    messages = body.get("messages")
    if not isinstance(messages, list) or len(messages) != 1:
        return _error_json(400, "Only a single user message is supported")

    # Stream not yet supported
    if body.get("stream", False):
        return _error_json(400, "stream=true is not supported yet. Set stream=false or omit it.")

    message = messages[0]
    if not isinstance(message, dict) or message.get("role") != "user":
        return _error_json(400, "Only a single user message is supported")
    user_content = message.get("content", "")
    if isinstance(user_content, list):
        # Multi-modal content array — extract text parts
        user_content = " ".join(
            part.get("text", "") for part in user_content if part.get("type") == "text"
        )

    agent_loop = request.app["agent_loop"]
    timeout_s: float = request.app.get("request_timeout", 120.0)
    model_name: str = request.app.get("model_name", "nanobot")
    if (requested_model := body.get("model")) and requested_model != model_name:
        return _error_json(400, f"Only configured model '{model_name}' is available")

    session_key = f"api:{body['session_id']}" if body.get("session_id") else API_SESSION_KEY
    session_locks: dict[str, asyncio.Lock] = request.app["session_locks"]
    session_lock = session_locks.setdefault(session_key, asyncio.Lock())

    logger.info("API request session_key={} content={}", session_key, user_content[:80])

    _FALLBACK = EMPTY_FINAL_RESPONSE_MESSAGE

    try:
        async with session_lock:
            try:
                response = await asyncio.wait_for(
                    agent_loop.process_direct(
                        content=user_content,
                        session_key=session_key,
                        channel="api",
                        chat_id=API_CHAT_ID,
                    ),
                    timeout=timeout_s,
                )
                response_text = _response_text(response)

                if not response_text or not response_text.strip():
                    logger.warning(
                        "Empty response for session {}, retrying",
                        session_key,
                    )
                    retry_response = await asyncio.wait_for(
                        agent_loop.process_direct(
                            content=user_content,
                            session_key=session_key,
                            channel="api",
                            chat_id=API_CHAT_ID,
                        ),
                        timeout=timeout_s,
                    )
                    response_text = _response_text(retry_response)
                    if not response_text or not response_text.strip():
                        logger.warning(
                            "Empty response after retry for session {}, using fallback",
                            session_key,
                        )
                        response_text = _FALLBACK

            except asyncio.TimeoutError:
                return _error_json(504, f"Request timed out after {timeout_s}s")
            except Exception:
                logger.exception("Error processing request for session {}", session_key)
                return _error_json(500, "Internal server error", err_type="server_error")
    except Exception:
        logger.exception("Unexpected API lock error for session {}", session_key)
        return _error_json(500, "Internal server error", err_type="server_error")

    return web.json_response(_chat_completion_response(response_text, model_name))


async def handle_models(request: web.Request) -> web.Response:
    """GET /v1/models"""
    model_name = request.app.get("model_name", "nanobot")
    return web.json_response({
        "object": "list",
        "data": [
            {
                "id": model_name,
                "object": "model",
                "created": 0,
                "owned_by": "nanobot",
            }
        ],
    })


async def handle_health(request: web.Request) -> web.Response:
    """GET /health"""
    return web.json_response({"status": "ok"})


# ---------------------------------------------------------------------------
# Swarm handoff (fork-local)
# ---------------------------------------------------------------------------

async def handle_swarm_handoff(request: web.Request) -> web.Response:
    """POST /v1/swarm/handoff — async inter-agent task delegation (fork-local).

    Accepts a swarm task payload, queues it for background processing via
    the agent loop, and returns 202 Accepted immediately.  The receiving
    agent processes the task asynchronously; when finished it calls back
    the origin agent's ``/v1/swarm/handoff`` with ``type: "result"``.
    """
    try:
        body = await request.json()
    except Exception:
        return _error_json(400, "Invalid JSON body")

    task = body.get("task", "")
    data = body.get("data", "")
    chain_id = body.get("chain_id") or uuid.uuid4().hex[:8]
    hop_count = body.get("hop_count", 0)
    max_hops = body.get("max_hops", 5)
    msg_type = body.get("type", "task")
    origin = body.get("origin", {})
    human = body.get("human", {})

    if not task:
        return _error_json(400, "Missing 'task' field")

    # Build LLM-visible content with embedded swarm metadata
    sender = origin.get("agent", "unknown")
    content_parts: list[str] = [
        f"[Swarm chain={chain_id} hop={hop_count}/{max_hops} "
        f"from={sender} type={msg_type}]",
        "---",
        task,
    ]
    if data:
        content_parts.append(f"\nДанные:\n{data}")
    content = "\n".join(content_parts)

    session_key = f"swarm:{chain_id}"
    agent_loop = request.app["agent_loop"]

    # Machine metadata — passed to AgentLoop via InboundMessage.metadata
    metadata = {
        "_swarm": True,
        "_chain_id": chain_id,
        "_hop_count": hop_count,
        "_max_hops": max_hops,
        "_origin": origin,
        "_human": human,
        "_type": msg_type,
    }

    logger.info(
        "Swarm handoff {} from '{}' (chain={}, hop={}/{}): {}",
        msg_type, sender, chain_id, hop_count, max_hops, task[:80],
    )

    # Fire-and-forget: process in background
    async def _process_handoff() -> None:
        try:
            from nanobot.bus.events import InboundMessage

            msg = InboundMessage(
                channel="swarm",
                sender_id=sender,
                chat_id=chain_id,
                content=content,
                metadata=metadata,
            )
            await agent_loop._process_message(msg, session_key=session_key)
        except Exception:
            logger.exception(
                "Swarm handoff processing failed for chain {}", chain_id,
            )

    asyncio.create_task(_process_handoff())

    return web.json_response(
        {"ok": True, "chain_id": chain_id, "session_key": session_key},
        status=202,
    )


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(agent_loop, model_name: str = "nanobot", request_timeout: float = 120.0) -> web.Application:
    """Create the aiohttp application.

    Args:
        agent_loop: An initialized AgentLoop instance.
        model_name: Model name reported in responses.
        request_timeout: Per-request timeout in seconds.
    """
    app = web.Application()
    app["agent_loop"] = agent_loop
    app["model_name"] = model_name
    app["request_timeout"] = request_timeout
    app["session_locks"] = {}  # per-user locks, keyed by session_key

    app.router.add_post("/v1/chat/completions", handle_chat_completions)
    app.router.add_post("/v1/swarm/handoff", handle_swarm_handoff)  # (fork-local)
    app.router.add_get("/v1/models", handle_models)
    app.router.add_get("/health", handle_health)
    return app
