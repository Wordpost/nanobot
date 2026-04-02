#!/bin/bash
# ─────────────────────────────────────────────────────────
#  Nanobot Forensic Viewer — Launcher (Linux/macOS)
#  Config is loaded from .env file or auto-detected.
# ─────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    echo "[Error] Virtual environment not found. Run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

source venv/bin/activate
python3 -m src.app
