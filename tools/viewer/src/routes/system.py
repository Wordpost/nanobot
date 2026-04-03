"""System operations: deploy, restart. Pool-mode aware. (fork-local)"""

import asyncio
import json
import logging
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..config import CONTAINER_NAME, DEPLOY_ROOT, POOL_MODE, WORKSPACES, resolve_workspace

router = APIRouter(prefix="/api/system", tags=["system"])
logger = logging.getLogger("session-viewer.system")

_deploy_lock = asyncio.Lock()


def _sse_response(generator):
    """Wrap SSE generator in StreamingResponse with correct headers."""
    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_line(payload: dict) -> str:
    """Format a single SSE data line."""
    return f"data: {json.dumps(payload)}\n\n"


def _sse_keepalive() -> str:
    return ": keepalive\n\n"


async def _run_streamed_command(cmd: str, cwd: str) -> AsyncGenerator[str, None]:
    """Execute a shell command and yield SSE lines."""
    logger.info(f"Executing from {cwd}: {cmd}")
    yield _sse_line({"line": f"> Working directory: {cwd}"})
    yield _sse_line({"line": f"> Executing: {cmd}"})

    process = None
    try:
        process = await asyncio.create_subprocess_shell(
            cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        while True:
            try:
                line = await asyncio.wait_for(process.stdout.readline(), timeout=15)
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip("\n\r")
                yield _sse_line({"line": text})
            except asyncio.TimeoutError:
                yield _sse_keepalive()

        await process.wait()

        if process.returncode == 0:
            yield _sse_line({"line": "[SUCCESS] Completed successfully!", "done": True})
        else:
            yield _sse_line({"line": f"[ERROR] Process exited with code {process.returncode}", "error": True, "done": True})

    except asyncio.CancelledError:
        yield _sse_line({"line": "[WARNING] Request cancelled.", "error": True})
    except Exception as e:
        logger.error(f"Command error: {e}")
        yield _sse_line({"line": f"[system-error] {e}", "error": True, "done": True})
    finally:
        if process and process.returncode is None:
            pass


@router.get("/deploy/stream")
async def stream_deploy():
    """Stream deployment: git pull + rebuild all containers."""
    if _deploy_lock.locked():
        raise HTTPException(status_code=429, detail="A deployment is already in progress.")

    if not DEPLOY_ROOT:
        raise HTTPException(status_code=500, detail="Deploy root not configured")

    async def generate() -> AsyncGenerator[str, None]:
        async with _deploy_lock:
            root = str(DEPLOY_ROOT)

            if POOL_MODE:
                services = " ".join(ws.container_name for ws in WORKSPACES.values())
                cmd = (
                    "cd nanobot && "
                    "git pull origin main && "
                    "cd .. && "
                    f"docker compose up --build -d {services}"
                )
            else:
                cmd = (
                    "cd nanobot && "
                    "git pull origin main && "
                    "cd .. && "
                    f"docker compose up --build -d {CONTAINER_NAME}"
                )

            yield _sse_line({"line": f"> Deploying from {root}..."})
            async for chunk in _run_streamed_command(cmd, root):
                yield chunk

    return _sse_response(generate)


@router.get("/restart/stream")
async def stream_restart(agent: Optional[str] = Query(None)):
    """Stream restart for a specific agent container."""
    if _deploy_lock.locked():
        raise HTTPException(status_code=429, detail="A task is already in progress.")

    if not DEPLOY_ROOT:
        raise HTTPException(status_code=500, detail="Deploy root not configured")

    if POOL_MODE:
        if not agent:
            raise HTTPException(status_code=400, detail="Agent parameter required in pool mode")
        ws = resolve_workspace(agent)
        container = ws.container_name
    else:
        container = CONTAINER_NAME

    async def generate() -> AsyncGenerator[str, None]:
        async with _deploy_lock:
            root = str(DEPLOY_ROOT)
            cmd = f"docker compose restart {container}"

            yield _sse_line({"line": f"> Restarting {container}..."})
            async for chunk in _run_streamed_command(cmd, root):
                yield chunk

    return _sse_response(generate)
