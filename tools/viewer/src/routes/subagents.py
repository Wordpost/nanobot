"""Subagent log browser — reads structured JSON execution logs. Pool-mode aware. (fork-local)"""

import asyncio
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..config import SUBAGENTS_DIR, POOL_MODE, WORKSPACES, resolve_workspace
from ..utils import sse_response
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


def _build_summary(filepath: Path, agent_name: str | None = None) -> SubagentSummary | None:
    """Fast metadata extraction from a subagent JSON log."""
    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
        filename = f"{agent_name}/{filepath.name}" if agent_name else filepath.name
        return SubagentSummary(
            filename=filename,
            task_id=data.get("task_id", ""),
            label=data.get("label", filepath.stem),
            status=data.get("status", "unknown"),
            started=data.get("started"),
            finished=data.get("finished"),
            duration=data.get("duration"),
            usage=_parse_usage(data.get("usage")),
            agent=agent_name,
        )
    except Exception:
        return None


def _resolve_subagent_filepath(filename: str) -> Path:
    """Resolve subagent filename to path. In pool mode: 'agent/file.json'."""
    if POOL_MODE and "/" in filename:
        agent, base = filename.split("/", 1)
        ws = WORKSPACES.get(agent)
        if not ws:
            raise HTTPException(status_code=404, detail=f"Agent workspace not found: {agent}")
        return ws.subagents_dir / base

    return SUBAGENTS_DIR / filename


def _get_scan_dirs() -> list[tuple[Path, str | None]]:
    """Get directories to scan for subagent logs."""
    if POOL_MODE:
        return [(ws.subagents_dir, name) for name, ws in WORKSPACES.items()]
    return [(SUBAGENTS_DIR, None)]


# ── API Endpoints ──────────────────────────────────────────────


@router.get("", response_model=SubagentListResponse)
async def list_subagents(agent: Optional[str] = Query(None)):
    """List subagent execution logs. Supports pool-mode filtering."""
    subagents: list[SubagentSummary] = []

    if agent and POOL_MODE:
        ws = resolve_workspace(agent)
        scan_dirs = [(ws.subagents_dir, agent)]
    else:
        scan_dirs = _get_scan_dirs()

    for scan_dir, agent_name in scan_dirs:
        if not scan_dir.exists():
            continue
        for filepath in sorted(scan_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            summary = _build_summary(filepath, agent_name)
            if summary:
                subagents.append(summary)

    return SubagentListResponse(subagents=subagents, total=len(subagents))


@router.get("/watch")
async def watch_subagents(agent: Optional[str] = Query(None)):
    """SSE endpoint — emits subagent list on directory changes."""
    from ..utils import watch_directories

    if agent and POOL_MODE:
        ws = resolve_workspace(agent)
        scan_dirs = [(ws.subagents_dir, agent)]
    else:
        scan_dirs = _get_scan_dirs()

    async def generate():
        dirs_to_scan = [d for d, _ in scan_dirs]

        async for changed in watch_directories(dirs_to_scan, ".json"):
            if changed:
                subagents = []
                for scan_dir, agent_name in scan_dirs:
                    if not scan_dir.exists():
                        continue
                    for filepath in sorted(
                        scan_dir.glob("*.json"),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True,
                    ):
                        s = _build_summary(filepath, agent_name)
                        if s:
                            subagents.append(s.model_dump())

                payload = json.dumps({"subagents": subagents, "total": len(subagents)})
                yield f"data: {payload}\n\n"
            else:
                yield ": keepalive\n\n"

    return sse_response(generate)


@router.get("/{filename:path}", response_model=SubagentDetail)
async def get_subagent_detail(filename: str):
    """Get full parsed execution log for a subagent."""
    if ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = _resolve_subagent_filepath(filename)
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Subagent log not found")

    data = _parse_subagent_json(filepath)
    data["filename"] = filename  # Keep agent-prefixed name
    return SubagentDetail(**data)
