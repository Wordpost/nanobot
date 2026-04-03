"""
Centralized configuration with auto-discovery.

Priority for SESSIONS_DIR:
  1. NANOBOT_SESSIONS_DIR env var (absolute path)
  2. Auto-detect: walk up from CWD looking for .nanobot/workspace/sessions
  3. Auto-detect: walk up from this file's location
  4. Fallback: .nanobot/workspace/sessions relative to CWD

Pool Mode (multi-agent):
  Set NANOBOT_POOL_DIR to a root directory containing multiple workspaces.
  The viewer will scan all subdirectories for workspace/sessions/*.jsonl.

Container naming convention (fork-local):
  Agent workspace folder name → container = nanobot-{name}
  Example: .shantra → nanobot-shantra, .nanobot → nanobot-gateway (special case)
"""

import os
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Optional

from fastapi import HTTPException

try:
    from dotenv import load_dotenv

    _viewer_root = Path(__file__).resolve().parent.parent
    _env_file = _viewer_root / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
    else:
        load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("session-viewer")

# ── Container name convention ───────────────────────────────

_CONTAINER_OVERRIDES = {
    "nanobot": "nanobot-gateway",
}


def _derive_container_name(agent_name: str) -> str:
    """Convention: nanobot-{name}, with overrides for special cases."""
    return _CONTAINER_OVERRIDES.get(agent_name, f"nanobot-{agent_name}")


# ── Pool Mode: multi-workspace discovery ────────────────────

@dataclass
class WorkspaceInfo:
    """Describes a single agent workspace. (fork-local)"""
    name: str
    sessions_dir: Path
    subagents_dir: Path
    workspace_dir: Path
    container_name: str
    config_path: Path
    memory_dir: Path


def _discover_workspaces(pool_dir: Path) -> Dict[str, WorkspaceInfo]:
    """Scan pool_dir for subdirectories containing workspace/sessions."""
    workspaces: Dict[str, WorkspaceInfo] = {}

    if not pool_dir.exists():
        logger.warning(f"[config] Pool dir does not exist: {pool_dir}")
        return workspaces

    for child in sorted(pool_dir.iterdir()):
        if not child.is_dir():
            continue

        sessions_candidate = child / "workspace" / "sessions"
        if not sessions_candidate.exists():
            continue

        name = child.name.lstrip(".")  # .nanobot -> nanobot, .shantra -> shantra
        workspace_dir = child / "workspace"
        workspaces[name] = WorkspaceInfo(
            name=name,
            sessions_dir=sessions_candidate,
            subagents_dir=workspace_dir / "subagents",
            workspace_dir=workspace_dir,
            container_name=_derive_container_name(name),
            config_path=child / "config.json",
            memory_dir=workspace_dir / "memory",
        )
        logger.info(f"[config] Pool workspace discovered: {name} -> {sessions_candidate}")

    return workspaces


# ── Single-agent session dir discovery ──────────────────────

def _find_sessions_dir() -> Path:
    """Locate .nanobot/workspace/sessions automatically."""

    env_dir = os.getenv("NANOBOT_SESSIONS_DIR")
    if env_dir:
        resolved = Path(env_dir).resolve()
        logger.info(f"[config] SESSIONS_DIR from env: {resolved}")
        return resolved

    target = Path(".nanobot") / "workspace" / "sessions"

    # Walk up from CWD
    current = Path.cwd().resolve()
    for _ in range(10):
        candidate = current / target
        if candidate.exists():
            logger.info(f"[config] SESSIONS_DIR auto-detected (cwd): {candidate}")
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent

    # Walk up from this file's location
    current = Path(__file__).resolve().parent
    for _ in range(10):
        candidate = current / target
        if candidate.exists():
            logger.info(f"[config] SESSIONS_DIR auto-detected (file): {candidate}")
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent

    fallback = Path(".nanobot/workspace/sessions").resolve()
    logger.warning(f"[config] SESSIONS_DIR fallback (not found): {fallback}")
    return fallback


# ── Exported Config ─────────────────────────────────────────

PORT = int(os.getenv("NANOBOT_PORT", "2003"))
HOST = os.getenv("NANOBOT_HOST", "127.0.0.1")
CONTAINER_NAME = os.getenv("NANOBOT_CONTAINER", "nanobot-gateway")

# Pool mode
_pool_dir_env = os.getenv("NANOBOT_POOL_DIR", "")
POOL_MODE = bool(_pool_dir_env)
POOL_DIR = Path(_pool_dir_env).resolve() if _pool_dir_env else None
WORKSPACES = _discover_workspaces(POOL_DIR) if POOL_MODE and POOL_DIR else {}

# Single-agent fallback
SESSIONS_DIR = _find_sessions_dir() if not POOL_MODE else Path(".")
SUBAGENTS_DIR = SESSIONS_DIR.parent / "subagents" if not POOL_MODE else Path(".")

# Deploy root: where docker-compose.yml lives (fork-local)
DEPLOY_ROOT: Optional[Path] = None
if POOL_MODE and POOL_DIR:
    DEPLOY_ROOT = POOL_DIR
elif not POOL_MODE and SESSIONS_DIR.exists():
    # /opt/nanobot/.nanobot/workspace/sessions → /opt/nanobot
    DEPLOY_ROOT = SESSIONS_DIR.parent.parent.parent

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Default workspace for single mode — unified interface (fork-local)
DEFAULT_WORKSPACE: Optional[WorkspaceInfo] = None
if not POOL_MODE and SESSIONS_DIR != Path("."):
    DEFAULT_WORKSPACE = WorkspaceInfo(
        name="default",
        sessions_dir=SESSIONS_DIR,
        subagents_dir=SUBAGENTS_DIR,
        workspace_dir=SESSIONS_DIR.parent,
        container_name=CONTAINER_NAME,
        config_path=SESSIONS_DIR.parent.parent / "config.json",
        memory_dir=SESSIONS_DIR.parent / "memory",
    )


def resolve_workspace(agent: Optional[str]) -> WorkspaceInfo:
    """Resolve agent name to WorkspaceInfo. (fork-local)

    - Pool mode + agent name → lookup in WORKSPACES
    - Pool mode + no agent → HTTPException 400
    - Single mode → DEFAULT_WORKSPACE
    """
    if POOL_MODE:
        if not agent:
            raise HTTPException(status_code=400, detail="Agent parameter required in pool mode")
        ws = WORKSPACES.get(agent)
        if not ws:
            raise HTTPException(status_code=404, detail=f"Agent workspace not found: {agent}")
        return ws

    if DEFAULT_WORKSPACE:
        return DEFAULT_WORKSPACE

    raise HTTPException(status_code=500, detail="No workspace configured")


def print_banner():
    """Print startup info to stdout."""
    print(f"\n  +----------------------------------------------+")
    print(f"  |  Nanobot Forensic Viewer                     |")
    print(f"  +----------------------------------------------+")
    print(f"  |  URL:      http://{HOST}:{PORT:<5}                |")

    if POOL_MODE:
        print(f"  |  Mode:     POOL ({len(WORKSPACES)} agents)                  |")
        for name, ws in WORKSPACES.items():
            print(f"  |    - {name:<25} [{ws.container_name}] |")
    else:
        print(f"  |  Sessions: {str(SESSIONS_DIR)[:33]:<33} |")
        print(f"  |  Status:   {'Found' if SESSIONS_DIR.exists() else 'Not found':<33} |")

    print(f"  +----------------------------------------------+\n")
