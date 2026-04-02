import json
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from ..config import SESSIONS_DIR

router = APIRouter(prefix="/api/config-manager", tags=["config-manager"])
logger = logging.getLogger("session-viewer.config")

def get_config_path() -> Path:
    return SESSIONS_DIR.parent.parent / "config.json"

@router.get("/")
async def get_full_config():
    """Returns the full nanobot configuration as JSON."""
    try:
        path = get_config_path()
        if not path.exists():
            raise HTTPException(status_code=404, detail="config.json not found")
        
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/")
async def save_full_config(request: Request):
    """Saves the provided JSON document back to config.json"""
    try:
        # Validate that the incoming request is valid JSON
        data = await request.json()
        path = get_config_path()
        
        if not path.exists():
            raise HTTPException(status_code=404, detail="config.json not found on backend. Cannot overwrite.")
        
        # Write format with beautiful indentation
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        return {"status": "success", "message": "Configuration saved successfully"}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format provided")
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        raise HTTPException(status_code=500, detail=str(e))
