import asyncio
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from ..config import SESSIONS_DIR, POOL_MODE, WORKSPACES
from ..parser import SessionParser
from ..schemas import SessionListResponse, SessionDetail, SessionMetadata
from ..utils import sse_response

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
logger = logging.getLogger("session-viewer")


def _validate_filename(filename: str):
    """Guard against path traversal."""
    if ".." in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")


def _resolve_filepath(filename: str):
    """Resolve a filename (possibly agent-prefixed) to an absolute path.

    Returns (filepath, agent_name).
    In pool mode filename looks like 'shantra/session_xyz.jsonl'.
    In single mode it's just 'session_xyz.jsonl'.
    """
    if POOL_MODE and "/" in filename:
        agent, base = filename.split("/", 1)
        ws = WORKSPACES.get(agent)
        if not ws:
            raise HTTPException(status_code=404, detail=f"Agent workspace not found: {agent}")
        return ws.sessions_dir / base, agent

    return SESSIONS_DIR / filename, None


def _build_session_list():
    """Build session list from filesystem. Supports both single and pool modes."""
    sessions = []

    if POOL_MODE:
        for agent_name, ws in WORKSPACES.items():
            if not ws.sessions_dir.exists():
                continue
            for filepath in sorted(ws.sessions_dir.glob("*.jsonl")):
                meta = SessionParser.get_metadata_only(filepath)
                if not meta:
                    continue
                # Prefix filename with agent for unique identification
                meta["filename"] = f"{agent_name}/{filepath.name}"
                meta["agent"] = agent_name
                meta["channel"] = _detect_channel(meta.get("key", ""))
                sessions.append(meta)
    else:
        if not SESSIONS_DIR.exists():
            return sessions
        for filepath in sorted(SESSIONS_DIR.glob("*.jsonl")):
            meta = SessionParser.get_metadata_only(filepath)
            if meta:
                meta["channel"] = _detect_channel(meta.get("key", ""))
                sessions.append(meta)

    sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
    return sessions


def _detect_channel(key: str) -> str:
    """Extract channel type from session key."""
    lower = key.lower()
    for prefix in ("telegram", "webhook", "api", "heartbeat"):
        if prefix in lower:
            return prefix
    return "default"


@router.get("", response_model=SessionListResponse)
async def list_sessions():
    """List all available chat sessions with metadata."""
    if not POOL_MODE and not SESSIONS_DIR.exists():
        raise HTTPException(status_code=404, detail=f"Sessions directory not found: {SESSIONS_DIR}")

    raw = _build_session_list()
    sessions = [SessionMetadata(**s) for s in raw]
    return SessionListResponse(sessions=sessions, total=len(sessions))


@router.get("/watch")
async def watch_sessions():
    """SSE endpoint — emits full session list whenever directory contents change."""
    from ..utils import watch_directories

    async def generate():
        dirs_to_scan = (
            [ws.sessions_dir for name, ws in WORKSPACES.items()]
            if POOL_MODE
            else [SESSIONS_DIR]
        )

        async for changed in watch_directories(dirs_to_scan, ".jsonl"):
            if changed:
                sessions = _build_session_list()
                payload = json.dumps({"sessions": sessions, "total": len(sessions)})
                yield f"data: {payload}\n\n"
            else:
                yield ": keepalive\n\n"

    return sse_response(generate)


@router.get("/{filename:path}")
async def get_session_detail(
    filename: str,
    page: Optional[int] = Query(None, ge=1, description="Page number (1-based)"),
    limit: Optional[int] = Query(None, ge=1, le=500, description="Messages per page"),
):
    """Get message history for a session. Supports optional pagination. (fork-local)"""
    _validate_filename(filename)

    filepath, _ = _resolve_filepath(filename)
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    parser = SessionParser(filepath)
    result = parser.load_full()

    # Pagination: if page & limit provided, return a slice
    if page is not None and limit is not None:
        total = len(result["messages"])
        offset = (page - 1) * limit
        result["messages"] = result["messages"][offset:offset + limit]
        result["total"] = total
        result["page"] = page
        result["limit"] = limit
        result["pages"] = (total + limit - 1) // limit

    return result


# ── DELETE endpoints ────────────────────────────────────────


@router.delete("/{filename:path}")
async def delete_session(filename: str):
    """Delete an entire session file."""
    _validate_filename(filename)

    filepath, _ = _resolve_filepath(filename)
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    filepath.unlink()
    logger.info(f"[sessions] Deleted session file: {filename}")
    return {"status": "ok", "message": f"Session {filename} deleted"}


class DeleteMessagesRequest(BaseModel):
    indices: List[int]


@router.delete("/{filename:path}/messages")
async def delete_messages(filename: str, body: DeleteMessagesRequest):
    """Delete specific messages by their indices (0-based, among messages only)."""
    _validate_filename(filename)

    filepath, _ = _resolve_filepath(filename)
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    indices_set = set(body.indices)
    if not indices_set:
        raise HTTPException(status_code=400, detail="No indices provided")

    parser = SessionParser(filepath)
    metadata_obj = None
    rows: list = []

    for obj in parser.stream_objects():
        if not isinstance(obj, dict):
            continue
        if obj.get("_type") == "metadata":
            metadata_obj = obj
        elif "role" in obj:
            rows.append(obj)
        elif obj.get("_type"):
            rows.append(obj)
        elif "messages" in obj:
            metadata_obj = {k: v for k, v in obj.items() if k != "messages"}
            rows.extend(obj["messages"])

    msg_indices = [i for i, r in enumerate(rows) if "role" in r]
    max_idx = len(msg_indices) - 1
    invalid = [i for i in indices_set if i < 0 or i > max_idx]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid indices: {invalid}. Max index: {max_idx}")

    delete_row_indices = {msg_indices[i] for i in indices_set}
    kept = [r for i, r in enumerate(rows) if i not in delete_row_indices]
    deleted_count = len(delete_row_indices)

    if metadata_obj:
        metadata_obj["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    with open(filepath, "w", encoding="utf-8") as f:
        if metadata_obj:
            f.write(json.dumps(metadata_obj, ensure_ascii=False) + "\n")
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    logger.info(f"[sessions] Deleted {deleted_count} message(s) from {filename}")
    return {"status": "ok", "deleted": deleted_count, "remaining": len(kept) - sum(1 for r in kept if r.get("_type"))}
