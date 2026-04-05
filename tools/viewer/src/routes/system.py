"""System operations: deploy, restart. Pool-mode aware. (fork-local)"""

import asyncio
import json
import logging
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..utils import sse_response as _sse_response, sse_line as _sse_line

from ..config import CONTAINER_NAME, DEPLOY_ROOT, POOL_MODE, WORKSPACES, resolve_workspace

router = APIRouter(prefix="/api/system", tags=["system"])
logger = logging.getLogger("session-viewer.system")

_deploy_lock = asyncio.Lock()


def _sse_keepalive() -> str:
    return ": keepalive\n\n"


async def _run_streamed_command(cmd: str, cwd: str) -> AsyncGenerator[str, None]:
    import subprocess
    import threading
    """Execute a shell command and yield SSE lines."""
    logger.info(f"Executing from {cwd}: {cmd}")
    yield _sse_line({"line": f"> Working directory: {cwd}"})
    yield _sse_line({"line": f"> Executing: {cmd}"})

    process = None
    try:
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()

        def reader():
            try:
                for line in iter(process.stdout.readline, b""):
                    asyncio.run_coroutine_threadsafe(queue.put(line), loop)
            except Exception:
                pass
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()

        while True:
            try:
                line = await asyncio.wait_for(queue.get(), timeout=15)
                if line is None:
                    break
                text = line.decode("utf-8", errors="replace").rstrip("\n\r")
                yield _sse_line({"line": text})
            except asyncio.TimeoutError:
                yield _sse_keepalive()

        # thread will finish because stdout is closed or EOF
        # wait for process to cleanly exit
        await asyncio.to_thread(process.wait)

        if process.returncode == 0:
            yield _sse_line({"line": "[SUCCESS] Completed successfully!", "done": True})
        else:
            yield _sse_line({"line": f"[ERROR] Process exited with code {process.returncode}", "error": True, "done": True})

    except asyncio.CancelledError:
        yield _sse_line({"line": "[WARNING] Request cancelled.", "error": True})
    except Exception as e:
        logger.error(f"Command error: {e}")
        yield _sse_line({"line": f"[system-error] {type(e).__name__}: {str(e)}", "error": True, "done": True})
    finally:
        if process and process.returncode is None:
            try:
                process.kill()
                process.wait()
            except Exception:
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


@router.post("/restart")
async def trigger_restart(agent: Optional[str] = Query(None)):
    """Trigger a container restart and return immediately on success."""
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

    async with _deploy_lock:
        root = str(DEPLOY_ROOT)
        cmd = f"docker compose restart {container}"
        logger.info(f"Triggering quick restart: {cmd}")
        
        import subprocess
        process = await asyncio.to_thread(
            subprocess.run,
            cmd,
            shell=True,
            cwd=root,
            capture_output=True
        )
        
        if process.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Restart failed: {process.stdout.decode()} {process.stderr.decode()}")
            
    return {"status": "success", "message": f"Container {container} restarted"}
