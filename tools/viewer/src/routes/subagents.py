"""Subagent log browser — parses Markdown execution logs into structured JSON."""

import asyncio
import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..config import SUBAGENTS_DIR
from ..schemas import (
    SubagentDetail,
    SubagentIteration,
    SubagentListResponse,
    SubagentSummary,
    SubagentToolCall,
)

router = APIRouter(prefix="/api/subagents", tags=["subagents"])

# ── Markdown parser ────────────────────────────────────────────


def _parse_header(text: str) -> dict:
    """Extract metadata from the header portion of a subagent log."""
    info: dict = {}

    m = re.search(r"# Subagent:\s*(.+)", text)
    if m:
        info["label"] = m.group(1).strip()

    m = re.search(r"\*\*Task ID:\*\*\s*`([^`]+)`", text)
    if m:
        info["task_id"] = m.group(1).strip()

    m = re.search(r"\*\*Started:\*\*\s*`([^`]+)`", text)
    if m:
        info["started"] = m.group(1).strip()

    return info


def _parse_result(text: str) -> dict:
    """Extract final result block from the log."""
    info: dict = {}

    m = re.search(r"\*\*Status:\*\*\s*(.+)", text)
    if m:
        raw = m.group(1).strip()
        info["status"] = "ok" if "COMPLETED" in raw else "error"

    m = re.search(r"\*\*Finished:\*\*\s*`([^`]+)`", text)
    if m:
        info["finished"] = m.group(1).strip()

    m = re.search(r"\*\*Duration:\*\*\s*`([^`]+)`", text)
    if m:
        info["duration"] = m.group(1).strip()

    return info


def _parse_iterations(text: str) -> list[SubagentIteration]:
    """Parse iteration blocks from the execution log section."""
    iterations: list[SubagentIteration] = []

    # Split by ### Iteration N
    parts = re.split(r"### Iteration (\d+)", text)
    # parts = [preamble, "1", content1, "2", content2, ...]
    i = 1
    while i < len(parts) - 1:
        num = int(parts[i])
        content = parts[i + 1]
        i += 2

        iteration = SubagentIteration(number=num)

        # Model response
        resp_match = re.search(
            r"\*\*Model Response:\*\*\s*\n\n(.*?)(?=####|\*\*|---|\Z)",
            content,
            re.DOTALL,
        )
        if resp_match:
            iteration.model_response = resp_match.group(1).strip()

        # Tool calls: #### 🔧 `tool_name`
        tool_blocks = re.split(r"####\s*🔧\s*`([^`]+)`", content)
        # tool_blocks = [preamble, name1, body1, name2, body2, ...]
        t = 1
        while t < len(tool_blocks) - 1:
            tc_name = tool_blocks[t].strip()
            tc_body = tool_blocks[t + 1]
            t += 2

            tc = SubagentToolCall(name=tc_name)

            # Arguments
            args_match = re.search(
                r"\*\*Arguments:\*\*\s*```(?:json)?\s*(.*?)```",
                tc_body,
                re.DOTALL,
            )
            if args_match:
                tc.arguments = args_match.group(1).strip()

            # Result
            result_match = re.search(
                r"\*\*Result:\*\*\s*```\s*(.*?)```",
                tc_body,
                re.DOTALL,
            )
            if result_match:
                tc.result = result_match.group(1).strip()

            iteration.tool_calls.append(tc)

        iterations.append(iteration)

    return iterations


def _parse_subagent_md(filepath: Path) -> dict:
    """Parse a complete subagent Markdown log into structured data."""
    text = filepath.read_text(encoding="utf-8")

    data: dict = {"filename": filepath.name}
    data.update(_parse_header(text))

    # Task section
    task_match = re.search(r"## Task\s*\n\n(.*?)(?=\n---)", text, re.DOTALL)
    if task_match:
        data["task"] = task_match.group(1).strip()

    # Execution log section
    exec_match = re.search(r"## Execution Log\s*\n\n(.*?)(?=\n## Result|\Z)", text, re.DOTALL)
    if exec_match:
        data["iterations"] = _parse_iterations(exec_match.group(1))

    # Result section
    result_match = re.search(r"## Result\s*\n\n(.*)", text, re.DOTALL)
    if result_match:
        result_text = result_match.group(1)
        data.update(_parse_result(result_text))

        # Final result text (everything after the metadata bullets)
        final_lines = []
        past_meta = False
        for line in result_text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("- **") and not past_meta:
                continue
            if stripped == "" and not past_meta:
                past_meta = True
                continue
            past_meta = True
            final_lines.append(line)
        data["final_result"] = "\n".join(final_lines).strip()

    return data


def _build_summary(filepath: Path) -> SubagentSummary | None:
    """Fast metadata extraction from a subagent log."""
    try:
        # Read only the first ~2KB for speed
        with open(filepath, encoding="utf-8") as f:
            header = f.read(2048)

        info = _parse_header(header)

        # Quick status check — need to read tail
        tail = ""
        size = filepath.stat().st_size
        if size > 2048:
            with open(filepath, encoding="utf-8") as f:
                f.seek(max(0, size - 512))
                tail = f.read()
        else:
            tail = header

        result_info = _parse_result(tail)

        return SubagentSummary(
            filename=filepath.name,
            task_id=info.get("task_id", ""),
            label=info.get("label", filepath.stem),
            status=result_info.get("status", "running"),
            started=info.get("started"),
            finished=result_info.get("finished"),
            duration=result_info.get("duration"),
        )
    except Exception:
        return None


# ── API Endpoints ──────────────────────────────────────────────


@router.get("", response_model=SubagentListResponse)
async def list_subagents():
    """List all subagent execution logs."""
    if not SUBAGENTS_DIR.exists():
        return SubagentListResponse(subagents=[], total=0)

    subagents: list[SubagentSummary] = []
    for filepath in sorted(SUBAGENTS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        summary = _build_summary(filepath)
        if summary:
            subagents.append(summary)

    return SubagentListResponse(subagents=subagents, total=len(subagents))


@router.get("/watch")
async def watch_subagents():
    """SSE endpoint — emits subagent list on directory changes."""

    async def generate():
        last_fingerprint = None
        keepalive_counter = 0

        while True:
            try:
                fingerprint = {}
                if SUBAGENTS_DIR.exists():
                    for f in SUBAGENTS_DIR.glob("*.md"):
                        try:
                            st = f.stat()
                            fingerprint[f.name] = (st.st_mtime, st.st_size)
                        except OSError:
                            continue

                fp_key = str(sorted(fingerprint.items()))

                if fp_key != last_fingerprint:
                    last_fingerprint = fp_key

                    subagents = []
                    for filepath in sorted(
                        SUBAGENTS_DIR.glob("*.md"),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True,
                    ):
                        s = _build_summary(filepath)
                        if s:
                            subagents.append(s.model_dump())

                    payload = json.dumps({"subagents": subagents, "total": len(subagents)})
                    yield f"data: {payload}\n\n"
                    keepalive_counter = 0
                else:
                    keepalive_counter += 1
                    if keepalive_counter >= 5:
                        yield ": keepalive\n\n"
                        keepalive_counter = 0

                await asyncio.sleep(3)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(5)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{filename}", response_model=SubagentDetail)
async def get_subagent_detail(filename: str):
    """Get full parsed execution log for a subagent."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = SUBAGENTS_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Subagent log not found")

    data = _parse_subagent_md(filepath)
    return SubagentDetail(**data)
