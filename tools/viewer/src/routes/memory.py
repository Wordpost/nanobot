import logging
from fastapi import APIRouter, HTTPException
from ..config import SESSIONS_DIR

router = APIRouter(prefix="/api/memory", tags=["memory"])
logger = logging.getLogger("session-viewer")

MEMORY_DIR = SESSIONS_DIR.parent / "memory"

_FILE_MAP = {
    "history": "HISTORY.md",
    "memory": "MEMORY.md",
}


def _resolve_path(file_type: str):
    """Resolve file_type to absolute path, raise 400 on invalid type."""
    name = _FILE_MAP.get(file_type)
    if not name:
        raise HTTPException(status_code=400, detail=f"Invalid file_type: {file_type}. Use 'history' or 'memory'.")
    return MEMORY_DIR / name


@router.get("/{file_type}")
async def get_memory_file(file_type: str):
    """Read contents of HISTORY.md or MEMORY.md."""
    filepath = _resolve_path(file_type)
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
async def clear_memory_file(file_type: str):
    """Clear file contents without deleting the file."""
    filepath = _resolve_path(file_type)
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filepath.name}")

    filepath.write_text("", encoding="utf-8")
    logger.info(f"[memory] Cleared {filepath.name}")
    return {"status": "ok", "file_type": file_type, "message": f"{filepath.name} cleared"}
