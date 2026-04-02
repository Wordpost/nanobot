"""
Centralized configuration with auto-discovery.

Priority for SESSIONS_DIR:
  1. NANOBOT_SESSIONS_DIR env var (absolute path)
  2. Auto-detect: walk up from CWD looking for .nanobot/workspace/sessions
  3. Auto-detect: walk up from this file's location
  4. Fallback: .nanobot/workspace/sessions relative to CWD
"""

import os
import sys
import logging
from pathlib import Path

try:
    from dotenv import load_dotenv

    # Look for .env in viewer root (two levels up from this file)
    _viewer_root = Path(__file__).resolve().parent.parent
    _env_file = _viewer_root / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
    else:
        # Also check CWD
        load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("session-viewer")


def _find_sessions_dir() -> Path:
    """Locate .nanobot/workspace/sessions automatically."""

    # 1. Explicit env var — highest priority
    env_dir = os.getenv("NANOBOT_SESSIONS_DIR")
    if env_dir:
        resolved = Path(env_dir).resolve()
        logger.info(f"[config] SESSIONS_DIR from env: {resolved}")
        return resolved

    target = Path(".nanobot") / "workspace" / "sessions"

    # 2. Walk up from CWD
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

    # 3. Walk up from this file's location
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

    # 4. Fallback
    fallback = Path(".nanobot/workspace/sessions").resolve()
    logger.warning(f"[config] SESSIONS_DIR fallback (not found): {fallback}")
    return fallback


# ── Exported Config ─────────────────────────────────────────

PORT = int(os.getenv("NANOBOT_PORT", "2003"))
HOST = os.getenv("NANOBOT_HOST", "127.0.0.1")
SESSIONS_DIR = _find_sessions_dir()
CONTAINER_NAME = os.getenv("NANOBOT_CONTAINER", "nanobot-gateway")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def print_banner():
    """Print startup info to stdout."""
    print(f"\n  +----------------------------------------------+")
    print(f"  |  Nanobot Forensic Viewer                     |")
    print(f"  +----------------------------------------------+")
    print(f"  |  URL:      http://{HOST}:{PORT:<5}                |")
    print(f"  |  Sessions: {str(SESSIONS_DIR)[:33]:<33} |")
    print(f"  |  Status:   {'Found' if SESSIONS_DIR.exists() else 'Not found':<33} |")
    print(f"  +----------------------------------------------+\n")
