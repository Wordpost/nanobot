"""Persist per-iteration token usage into session history (fork-local).

Plugs into the upstream AgentHook lifecycle via ``after_iteration`` so that
Vivir (and any other consumer) can display granular cost/token data per LLM
call rather than only per-turn totals.

Usage records are appended as special ``{"_type": "usage", ...}`` entries
that sit alongside regular messages but are ignored by the LLM context
builder.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from nanobot.agent.hook import AgentHook, AgentHookContext

if TYPE_CHECKING:
    from nanobot.session.manager import Session


class UsageTrackerHook(AgentHook):
    """Record token usage after every LLM iteration (fork-local).

    Bind a session via :meth:`bind_session` before the agent loop starts.
    The hook is a no-op when no session is bound (e.g. ``process_direct``
    without persistence).
    """

    __slots__ = ("_session",)

    def __init__(self) -> None:
        self._session: Session | None = None

    def bind_session(self, session: Session | None) -> None:
        """Attach (or detach) the target session for usage recording."""
        self._session = session

    async def after_iteration(self, context: AgentHookContext) -> None:
        if self._session is None or not context.usage:
            return
        self._session.messages.append({
            "_type": "usage",
            "prompt_tokens": context.usage.get("prompt_tokens", 0),
            "completion_tokens": context.usage.get("completion_tokens", 0),
            "total_tokens": context.usage.get("total_tokens", 0),
            "cached_tokens": context.usage.get("cached_tokens", 0),
            "timestamp": datetime.now().isoformat(),
        })
