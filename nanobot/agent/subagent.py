"""Subagent manager for background task execution."""

import asyncio
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from loguru import logger

from nanobot.agent.hook import AgentHook, AgentHookContext
from nanobot.utils.prompt_templates import render_template
from nanobot.agent.runner import AgentRunSpec, AgentRunner
from nanobot.agent.skills import BUILTIN_SKILLS_DIR
from nanobot.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.search import GlobTool, GrepTool
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.web import WebFetchTool, WebSearchTool
from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.config.schema import ExecToolConfig, WebToolsConfig
from nanobot.providers.base import LLMProvider


def _slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug."""
    slug = re.sub(r'[^\w\s-]', '', text.lower())
    slug = re.sub(r'[-\s]+', '_', slug).strip('_')
    return slug[:50]

class _SubagentLogHook(AgentHook):
    """Lifecycle hook that logs subagent execution to a JSON file (fork-local).

    Creates a structured execution report at ``workspace/subagents/{task_id}_{slug}.json``
    containing task metadata, each iteration's tool calls with arguments and
    results, model responses, usage metrics, and the final outcome.
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

    def write_final(self, status: Literal["ok", "error"], result: str) -> None:
        """Write final outcome. Called explicitly from SubagentManager."""
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

    def _flush(self) -> None:
        """Write current state to disk."""
        try:
            self._log_file.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Failed to write subagent log {}: {}", self._log_file, e)


class SubagentManager:
    """Manages background subagent execution."""

    def __init__(
        self,
        provider: LLMProvider,
        workspace: Path,
        bus: MessageBus,
        max_tool_result_chars: int,
        model: str | None = None,
        web_config: "WebToolsConfig | None" = None,
        exec_config: "ExecToolConfig | None" = None,
        restrict_to_workspace: bool = False,
    ):
        from nanobot.config.schema import ExecToolConfig

        self.provider = provider
        self.workspace = workspace
        self.bus = bus
        self.model = model or provider.get_default_model()
        self.web_config = web_config or WebToolsConfig()
        self.max_tool_result_chars = max_tool_result_chars
        self.exec_config = exec_config or ExecToolConfig()
        self.restrict_to_workspace = restrict_to_workspace
        self.runner = AgentRunner(provider)
        self._running_tasks: dict[str, asyncio.Task[None]] = {}
        self._session_tasks: dict[str, set[str]] = {}  # session_key -> {task_id, ...}

    async def spawn(
        self,
        task: str,
        label: str | None = None,
        origin_channel: str = "cli",
        origin_chat_id: str = "direct",
        session_key: str | None = None,
    ) -> str:
        """Spawn a subagent to execute a task in the background."""
        task_id = str(uuid.uuid4())[:8]
        display_label = label or task[:30] + ("..." if len(task) > 30 else "")
        origin = {"channel": origin_channel, "chat_id": origin_chat_id}

        bg_task = asyncio.create_task(
            self._run_subagent(task_id, task, display_label, origin)
        )
        self._running_tasks[task_id] = bg_task
        if session_key:
            self._session_tasks.setdefault(session_key, set()).add(task_id)

        def _cleanup(_: asyncio.Task) -> None:
            self._running_tasks.pop(task_id, None)
            if session_key and (ids := self._session_tasks.get(session_key)):
                ids.discard(task_id)
                if not ids:
                    del self._session_tasks[session_key]

        bg_task.add_done_callback(_cleanup)

        logger.info("Spawned subagent [{}]: {}", task_id, display_label)
        return f"Subagent [{display_label}] started (id: {task_id}). I'll notify you when it completes."

    async def _run_subagent(
        self,
        task_id: str,
        task: str,
        label: str,
        origin: dict[str, str],
    ) -> None:
        """Execute the subagent task and announce the result."""
        logger.info("Subagent [{}] starting task: {}", task_id, label)
        hook: _SubagentLogHook | None = None

        try:
            # Build subagent tools (no message tool, no spawn tool)
            tools = ToolRegistry()
            allowed_dir = self.workspace if (self.restrict_to_workspace or self.exec_config.sandbox) else None
            extra_read = [BUILTIN_SKILLS_DIR] if allowed_dir else None
            tools.register(ReadFileTool(workspace=self.workspace, allowed_dir=allowed_dir, extra_allowed_dirs=extra_read))
            tools.register(WriteFileTool(workspace=self.workspace, allowed_dir=allowed_dir))
            tools.register(EditFileTool(workspace=self.workspace, allowed_dir=allowed_dir))
            tools.register(ListDirTool(workspace=self.workspace, allowed_dir=allowed_dir))
            tools.register(GlobTool(workspace=self.workspace, allowed_dir=allowed_dir))
            tools.register(GrepTool(workspace=self.workspace, allowed_dir=allowed_dir))
            if self.exec_config.enable:
                tools.register(ExecTool(
                    working_dir=str(self.workspace),
                    timeout=self.exec_config.timeout,
                    restrict_to_workspace=self.restrict_to_workspace,
                    sandbox=self.exec_config.sandbox,
                    path_append=self.exec_config.path_append,
                ))
            if self.web_config.enable:
                tools.register(WebSearchTool(config=self.web_config.search, proxy=self.web_config.proxy))
                tools.register(WebFetchTool(proxy=self.web_config.proxy))
            system_prompt = self._build_subagent_prompt()
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task},
            ]

            hook = _SubagentLogHook(task_id, label, task, self.workspace)

            result = await self.runner.run(AgentRunSpec(
                initial_messages=messages,
                tools=tools,
                model=self.model,
                max_iterations=15,
                max_tool_result_chars=self.max_tool_result_chars,
                hook=hook,
                max_iterations_message="Task completed but no final response was generated.",
                error_message=None,
                fail_on_tool_error=True,
            ))
            if result.stop_reason == "tool_error":
                partial = self._format_partial_progress(result)
                hook.write_final("error", partial)
                await self._announce_result(
                    task_id, label, task, partial, origin, "error",
                )
                return
            if result.stop_reason == "error":
                error_msg = result.error or "Error: subagent execution failed."
                hook.write_final("error", error_msg)
                await self._announce_result(
                    task_id, label, task, error_msg, origin, "error",
                )
                return
            final_result = result.final_content or "Task completed but no final response was generated."

            hook.write_final("ok", final_result)
            logger.info("Subagent [{}] completed successfully", task_id)
            await self._announce_result(task_id, label, task, final_result, origin, "ok")

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            if hook is not None:
                hook.write_final("error", error_msg)
            logger.error("Subagent [{}] failed: {}", task_id, e)
            await self._announce_result(task_id, label, task, error_msg, origin, "error")

    async def _announce_result(
        self,
        task_id: str,
        label: str,
        task: str,
        result: str,
        origin: dict[str, str],
        status: str,
    ) -> None:
        """Announce the subagent result to the main agent via the message bus."""
        status_text = "completed successfully" if status == "ok" else "failed"

        announce_content = render_template(
            "agent/subagent_announce.md",
            label=label,
            status_text=status_text,
            task=task,
            result=result,
        )

        # Inject as system message to trigger main agent
        msg = InboundMessage(
            channel="system",
            sender_id="subagent",
            chat_id=f"{origin['channel']}:{origin['chat_id']}",
            content=announce_content,
        )

        await self.bus.publish_inbound(msg)
        logger.debug("Subagent [{}] announced result to {}:{}", task_id, origin['channel'], origin['chat_id'])

    @staticmethod
    def _format_partial_progress(result) -> str:
        completed = [e for e in result.tool_events if e["status"] == "ok"]
        failure = next((e for e in reversed(result.tool_events) if e["status"] == "error"), None)
        lines: list[str] = []
        if completed:
            lines.append("Completed steps:")
            for event in completed[-3:]:
                lines.append(f"- {event['name']}: {event['detail']}")
        if failure:
            if lines:
                lines.append("")
            lines.append("Failure:")
            lines.append(f"- {failure['name']}: {failure['detail']}")
        if result.error and not failure:
            if lines:
                lines.append("")
            lines.append("Failure:")
            lines.append(f"- {result.error}")
        return "\n".join(lines) or (result.error or "Error: subagent execution failed.")

    def _build_subagent_prompt(self) -> str:
        """Build a focused system prompt for the subagent."""
        from nanobot.agent.context import ContextBuilder
        from nanobot.agent.skills import SkillsLoader

        time_ctx = ContextBuilder._build_runtime_context(None, None)
        skills_summary = SkillsLoader(self.workspace).build_skills_summary()
        return render_template(
            "agent/subagent_system.md",
            time_ctx=time_ctx,
            workspace=str(self.workspace),
            skills_summary=skills_summary or "",
        )

    async def cancel_by_session(self, session_key: str) -> int:
        """Cancel all subagents for the given session. Returns count cancelled."""
        tasks = [self._running_tasks[tid] for tid in self._session_tasks.get(session_key, [])
                 if tid in self._running_tasks and not self._running_tasks[tid].done()]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        return len(tasks)

    def get_running_count(self) -> int:
        """Return the number of currently running subagents."""
        return len(self._running_tasks)
