import asyncio
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List
from ..config import SESSIONS_DIR
from ..parser import SessionParser
from ..schemas import SessionListResponse, SessionDetail, SessionMetadata

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
logger = logging.getLogger("session-viewer")


def _validate_filename(filename: str):
    """Guard against path traversal."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")


def _build_session_list():
    """Build session list from filesystem. Shared by REST and SSE."""
    sessions = []
    if not SESSIONS_DIR.exists():
        return sessions

    for filepath in sorted(SESSIONS_DIR.glob("*.jsonl")):
        meta = SessionParser.get_metadata_only(filepath)
        if meta:
            filename_key = meta.get("key", "").lower()
            channel = "default"
            for prefix in ["telegram", "webhook", "api", "heartbeat"]:
                if prefix in filename_key:
                    channel = prefix
                    break
            sessions.append({**meta, "channel": channel})

    sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
    return sessions


@router.get("", response_model=SessionListResponse)
async def list_sessions():
    """List all available chat sessions with metadata."""
    if not SESSIONS_DIR.exists():
        raise HTTPException(status_code=404, detail=f"Sessions directory not found: {SESSIONS_DIR}")

    raw = _build_session_list()
    sessions = [SessionMetadata(**s) for s in raw]
    return SessionListResponse(sessions=sessions, total=len(sessions))


@router.get("/watch")
async def watch_sessions():
    """SSE endpoint — emits full session list whenever directory contents change."""

    async def generate():
        last_fingerprint = None
        keepalive_counter = 0

        while True:
            try:
                fingerprint = {}
                if SESSIONS_DIR.exists():
                    for f in SESSIONS_DIR.glob("*.jsonl"):
                        try:
                            st = f.stat()
                            fingerprint[f.name] = (st.st_mtime, st.st_size)
                        except OSError:
                            continue

                fp_key = str(sorted(fingerprint.items()))

                if fp_key != last_fingerprint:
                    last_fingerprint = fp_key
                    sessions = _build_session_list()
                    payload = json.dumps(
                        {"sessions": sessions, "total": len(sessions)}
                    )
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


@router.get("/{filename}", response_model=SessionDetail)
async def get_session_detail(filename: str):
    """Get full message history for a single session."""
    _validate_filename(filename)

    filepath = SESSIONS_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    parser = SessionParser(filepath)
    return parser.load_full()


# ── DELETE endpoints ────────────────────────────────────────


@router.delete("/{filename}")
async def delete_session(filename: str):
    """Delete an entire session file."""
    _validate_filename(filename)

    filepath = SESSIONS_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    filepath.unlink()
    logger.info(f"[sessions] Deleted session file: {filename}")
    return {"status": "ok", "message": f"Session {filename} deleted"}


class DeleteMessagesRequest(BaseModel):
    indices: List[int]


@router.delete("/{filename}/messages")
async def delete_messages(filename: str, body: DeleteMessagesRequest):
    """Delete specific messages by their indices (0-based, among messages only)."""
    _validate_filename(filename)

    filepath = SESSIONS_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    indices_set = set(body.indices)
    if not indices_set:
        raise HTTPException(status_code=400, detail="No indices provided")

    parser = SessionParser(filepath)
    metadata_obj = None
    # Collect all rows preserving order: messages and non-metadata special records
    rows: list = []

    for obj in parser.stream_objects():
        if not isinstance(obj, dict):
            continue
        if obj.get("_type") == "metadata":
            metadata_obj = obj
        elif "role" in obj:
            rows.append(obj)
        elif obj.get("_type"):
            # Preserve special records (_type: "usage", etc.)
            rows.append(obj)
        elif "messages" in obj:
            metadata_obj = {k: v for k, v in obj.items() if k != "messages"}
            rows.extend(obj["messages"])

    # Build index mapping only for actual messages (have "role")
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
