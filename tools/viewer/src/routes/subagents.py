"""Subagent log browser — reads structured JSON execution logs."""

import asyncio
import json
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
    SubagentUsage,
)

router = APIRouter(prefix="/api/subagents", tags=["subagents"])

# ── JSON parser ────────────────────────────────────────────────


def _parse_usage(raw: dict | None) -> SubagentUsage | None:
    """Parse usage dict into SubagentUsage model."""
    if not raw:
        return None
    return SubagentUsage(
        prompt_tokens=raw.get("prompt_tokens", 0),
        completion_tokens=raw.get("completion_tokens", 0),
        total_tokens=raw.get("total_tokens", 0),
        cached_tokens=raw.get("cached_tokens", 0),
        requests=raw.get("requests", 0),
    )


def _parse_subagent_json(filepath: Path) -> dict:
    """Parse a subagent JSON log into structured data."""
    data = json.loads(filepath.read_text(encoding="utf-8"))

    iterations = []
    for it in data.get("iterations", []):
        tool_calls = [
            SubagentToolCall(
                name=tc.get("name", ""),
                arguments=tc.get("arguments", ""),
                result=tc.get("result", ""),
            )
            for tc in it.get("tool_calls", [])
        ]
        iterations.append(SubagentIteration(
            number=it.get("number", 0),
            model_response=it.get("model_response"),
            tool_calls=tool_calls,
            usage=_parse_usage(it.get("usage")),
        ))

    return {
        "filename": filepath.name,
        "task_id": data.get("task_id", ""),
        "label": data.get("label", filepath.stem),
        "status": data.get("status", "unknown"),
        "started": data.get("started"),
        "finished": data.get("finished"),
        "duration": data.get("duration"),
        "task": data.get("task", ""),
        "iterations": iterations,
        "final_result": data.get("final_result", ""),
        "usage": _parse_usage(data.get("usage")),
    }


def _build_summary(filepath: Path) -> SubagentSummary | None:
    """Fast metadata extraction from a subagent JSON log."""
    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
        return SubagentSummary(
            filename=filepath.name,
            task_id=data.get("task_id", ""),
            label=data.get("label", filepath.stem),
            status=data.get("status", "unknown"),
            started=data.get("started"),
            finished=data.get("finished"),
            duration=data.get("duration"),
            usage=_parse_usage(data.get("usage")),
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
    for filepath in sorted(SUBAGENTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
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
                    for f in SUBAGENTS_DIR.glob("*.json"):
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
                        SUBAGENTS_DIR.glob("*.json"),
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

    data = _parse_subagent_json(filepath)
    return SubagentDetail(**data)
