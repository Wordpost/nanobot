import asyncio
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from ..config import SESSIONS_DIR
from ..parser import SessionParser
from ..schemas import SessionListResponse, SessionDetail, SessionMetadata

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


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
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = SESSIONS_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    parser = SessionParser(filepath)
    return parser.load_full()
