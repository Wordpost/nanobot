"""Memory/History file viewer. Pool-mode aware. (fork-local)"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..config import resolve_workspace

router = APIRouter(prefix="/api/memory", tags=["memory"])
logger = logging.getLogger("session-viewer")

_FILE_MAP = {
    "history": "HISTORY.md",
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
    """Read contents of HISTORY.md or MEMORY.md."""
    filepath = _resolve_path(file_type, agent)
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
    filepath = _resolve_path(file_type, agent)
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filepath.name}")

    filepath.write_text("", encoding="utf-8")
    logger.info(f"[memory] Cleared {filepath.name}")
    return {"status": "ok", "file_type": file_type, "message": f"{filepath.name} cleared"}
