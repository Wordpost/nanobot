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
    if not agent and POOL_MODE:  # (fork-local) simplified pool mode check
        return {"message": "Please select a specific agent to view its config.json."}

    try:
        path = _get_config_path(agent)
    except HTTPException as e:
        if e.status_code == 400 and "Agent parameter required" in str(e.detail):
             return {"message": "Please select a specific agent to view its config.json."}
        raise

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"config.json not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error reading config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
async def save_full_config(request: Request, agent: Optional[str] = Query(None)):
    """Saves the provided JSON document back to config.json."""
    if not agent and POOL_MODE:  # (fork-local) simplified pool mode check
        raise HTTPException(status_code=400, detail="Cannot save config for 'All Agents'. Please select a specific agent.")

    try:
        data = await request.json()
        path = _get_config_path(agent)
    except HTTPException as e:
        if e.status_code == 400 and "Agent parameter required" in str(e.detail):
             raise HTTPException(status_code=400, detail="Please select a specific agent.")
        raise
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format provided")

    if not path.exists():
        raise HTTPException(status_code=404, detail="config.json not found on backend. Cannot overwrite.")

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return {"status": "success", "message": "Configuration saved successfully"}
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        raise HTTPException(status_code=500, detail=str(e))
