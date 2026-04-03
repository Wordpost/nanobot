"""Config.json editor. Pool-mode aware. (fork-local)"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from ..config import POOL_MODE, resolve_workspace

router = APIRouter(prefix="/api/config-manager", tags=["config-manager"])
logger = logging.getLogger("session-viewer.config")


def _get_config_path(agent: Optional[str] = None):
    """Resolve config.json path for agent."""
    ws = resolve_workspace(agent)
    return ws.config_path


@router.get("/")
async def get_full_config(agent: Optional[str] = Query(None)):
    """Returns the full nanobot configuration as JSON."""
    try:
        path = _get_config_path(agent)
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"config.json not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
async def save_full_config(request: Request, agent: Optional[str] = Query(None)):
    """Saves the provided JSON document back to config.json."""
    try:
        data = await request.json()
        path = _get_config_path(agent)

        if not path.exists():
            raise HTTPException(status_code=404, detail="config.json not found on backend. Cannot overwrite.")

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return {"status": "success", "message": "Configuration saved successfully"}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format provided")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        raise HTTPException(status_code=500, detail=str(e))
