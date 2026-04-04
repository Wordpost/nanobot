"""Memory/History file viewer. Pool-mode aware. (fork-local)"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..config import resolve_workspace

router = APIRouter(prefix="/api/memory", tags=["memory"])
logger = logging.getLogger("session-viewer")

_FILE_MAP = {
    "history": "history.jsonl",
    "memory": "MEMORY.md",
}


def _resolve_path(file_type: str, agent: Optional[str] = None):
    """Resolve file_type + agent to absolute path."""
    name = _FILE_MAP.get(file_type)
    if not name:
        raise HTTPException(status_code=400, detail=f"Invalid file_type: {file_type}. Use 'history' or 'memory'.")
    ws = resolve_workspace(agent)
    return ws.memory_dir / name


@router.get("/{file_type}")
async def get_memory_file(file_type: str, agent: Optional[str] = Query(None)):
    """Read contents of history.jsonl or MEMORY.md."""
    if not agent or agent in ["", "all", "undefined"]:
        return {
            "file_type": file_type, 
            "filename": "", 
            "content": "Please select a specific agent to view history.", 
            "size_bytes": 0,
            "info": "selection_required"
        }

    try:
        filepath = _resolve_path(file_type, agent)
    except HTTPException as e:
        if e.status_code in [400, 404]:
             return {
                 "file_type": file_type, 
                 "filename": "", 
                 "content": "Please select a valid agent in the panel header.", 
                 "size_bytes": 0,
                 "info": "selection_required"
             }
        raise

    if not filepath.exists():
        return {"file_type": file_type, "filename": filepath.name, "content": "", "size_bytes": 0}

    content = filepath.read_text(encoding="utf-8")
    return {
        "file_type": file_type,
        "filename": filepath.name,
        "content": content,
        "size_bytes": filepath.stat().st_size,
    }


@router.delete("/{file_type}")
async def clear_memory_file(file_type: str, agent: Optional[str] = Query(None)):
    """Clear file contents without deleting the file."""
    if not agent and resolve_workspace.__module__.endswith(".config") and any(os.getenv("NANOBOT_POOL_DIR", "").strip() for _ in [1]):
        from ..config import POOL_MODE
        if POOL_MODE:
            raise HTTPException(status_code=400, detail="Cannot clear memory for 'All Agents'. Please select a specific agent.")

    try:
        filepath = _resolve_path(file_type, agent)
    except HTTPException as e:
        if e.status_code == 400 and "Agent parameter required" in str(e.detail):
             raise HTTPException(status_code=400, detail="Please select a specific agent.")
        raise

    filepath.write_text("", encoding="utf-8")
    logger.info(f"[memory] Cleared {filepath.name}")
    return {"status": "ok", "file_type": file_type, "message": f"{filepath.name} cleared"}
