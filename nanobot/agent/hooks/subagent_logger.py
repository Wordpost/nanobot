"""Structured JSON logger for subagent executions (fork-local).

Captures every iteration — tool calls with arguments and results, model
responses, cumulative usage metrics — into a per-task JSON file at
``workspace/subagents/{task_id}_{slug}.json``.  The Forensic Viewer
(Vivir) reads these files to render subagent session replays.

Design notes
~~~~~~~~~~~~

* This hook is **fork-local** and must never be merged upstream.
* It plugs into the upstream ``AgentHook`` lifecycle so that no core
  code needs modification beyond a single ``CompositeHook`` assembly
  point in ``subagent.py``.
* ``write_final`` is called *outside* the hook lifecycle, directly from
  ``SubagentManager._run_subagent``, to record the terminal outcome.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from loguru import logger

from nanobot.agent.hook import AgentHook, AgentHookContext


def _slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug."""
    slug = re.sub(r'[^\w\s-]', '', text.lower())
    slug = re.sub(r'[-\s]+', '_', slug).strip('_')
    return slug[:50]


class SubagentLogHook(AgentHook):
    """Lifecycle hook that logs subagent execution to a JSON file (fork-local).

    Creates a structured execution report containing task metadata, each
    iteration's tool calls with arguments and results, model responses,
    usage metrics, and the final outcome.
    """

    _MAX_RESULT_CHARS = 2000
    _MAX_THINKING_CHARS = 3000

    def __init__(
        self,
        task_id: str,
        label: str,
        task: str,
        workspace: Path,
    ) -> None:
        super().__init__(reraise=True)
        self._task_id = task_id
        self._label = label
        self._log_dir = workspace / "subagents"
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self._log_dir / f"{task_id}_{_slugify(label)}.json"
        self._started = datetime.now()
        self._requests_count = 0
        self._total_usage: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cached_tokens": 0,
        }
        self._data: dict[str, Any] = {
            "task_id": task_id,
            "label": label,
            "task": task,
            "started": self._started.isoformat(),
            "status": "running",
            "finished": None,
            "duration": None,
            "usage": {},
            "iterations": [],
            "final_result": "",
        }
        self._flush()

    # -- Hook callbacks -------------------------------------------------------

    async def before_execute_tools(self, context: AgentHookContext) -> None:
        for tc in context.tool_calls:
            args_str = json.dumps(tc.arguments, ensure_ascii=False)
            logger.debug(
                "Subagent [{}] executing: {} with arguments: {}",
                self._task_id, tc.name, args_str,
            )

    async def after_iteration(self, context: AgentHookContext) -> None:
        self._requests_count += 1

        # Accumulate usage from this iteration
        iter_usage = context.usage or {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens"):
            self._total_usage[key] = self._total_usage.get(key, 0) + iter_usage.get(key, 0)

        # Build iteration record
        iteration_data: dict[str, Any] = {
            "number": context.iteration,
            "model_response": None,
            "usage": dict(iter_usage) if iter_usage else {},
            "tool_calls": [],
        }

        if context.response and context.response.content:
            thinking = context.response.content
            if len(thinking) > self._MAX_THINKING_CHARS:
                thinking = thinking[: self._MAX_THINKING_CHARS] + "\n\n... (truncated)"
            iteration_data["model_response"] = thinking

        for i, tc in enumerate(context.tool_calls):
            tc_data = self._format_tool_call(tc, context.tool_results, i)
            iteration_data["tool_calls"].append(tc_data)

        self._data["iterations"].append(iteration_data)
        self._data["usage"] = {
            **self._total_usage,
            "requests": self._requests_count,
        }
        self._flush()

    # -- Public API -----------------------------------------------------------

    def write_final(self, status: Literal["ok", "error"], result: str) -> None:
        """Write final outcome.  Called explicitly from SubagentManager."""
        elapsed = datetime.now() - self._started
        self._data["status"] = status
        self._data["finished"] = datetime.now().isoformat()
        self._data["duration"] = f"{elapsed.total_seconds():.1f}s"
        self._data["final_result"] = result
        self._data["usage"] = {
            **self._total_usage,
            "requests": self._requests_count,
        }
        self._flush()

    # -- Internal helpers -----------------------------------------------------

    def _format_tool_call(self, tc: Any, results: list[Any], index: int) -> dict[str, str]:
        """Format a single tool call with its arguments and result."""
        args_str = json.dumps(tc.arguments, ensure_ascii=False, indent=2)
        tc_data: dict[str, str] = {
            "name": tc.name,
            "arguments": args_str,
            "result": "",
        }
        if index < len(results):
            result_str = str(results[index])
            if len(result_str) > self._MAX_RESULT_CHARS:
                result_str = result_str[: self._MAX_RESULT_CHARS] + "\n... (truncated)"
            tc_data["result"] = result_str
        return tc_data

    def _flush(self) -> None:
        """Write current state to disk."""
        try:
            self._log_file.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Failed to write subagent log {}: {}", self._log_file, e)
