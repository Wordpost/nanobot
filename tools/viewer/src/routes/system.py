import asyncio
import json
import logging
from typing import AsyncGenerator
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..config import SESSIONS_DIR, CONTAINER_NAME

router = APIRouter(prefix="/api/system", tags=["system"])
logger = logging.getLogger("session-viewer.system")

# Simple lock to preventing concurrent deployments
_deploy_lock = asyncio.Lock()


@router.get("/deploy/stream")
async def stream_deploy():
    """Stream deployment process in real-time via Server-Sent Events."""
    if _deploy_lock.locked():
        raise HTTPException(status_code=429, detail="A deployment is already in progress.")

    async def generate() -> AsyncGenerator[str, None]:
        async with _deploy_lock:
            # Calculate deployment root (/opt/nanobot) by going up from SESSIONS_DIR
            # SESSIONS_DIR is e.g. /opt/nanobot/.nanobot/workspace/sessions
            root_dir = SESSIONS_DIR.parent.parent.parent
            
            # The command: 
            # 1. Update submodule (cd nanobot && git pull origin main)
            # 2. Rebuild container (docker compose up --build -d)
            # Note: Using sh / bash explicitly to allow && chaining
            cmd = (
                "cd nanobot && "
                "git pull origin main && "
                "cd .. && "
                f"docker compose up --build -d {CONTAINER_NAME}"
            )

            logger.info(f"Starting deployment from {root_dir}")
            yield f"data: {json.dumps({'line': f'> Deploying from {root_dir}...'})}\n\n"
            yield f"data: {json.dumps({'line': f'> Executing: {cmd}'})}\n\n"

            process = None
            try:
                process = await asyncio.create_subprocess_shell(
                    cmd,
                    cwd=str(root_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )

                while True:
                    try:
                        line = await asyncio.wait_for(
                            process.stdout.readline(), timeout=15
                        )
                        if not line:
                            break
                        text = line.decode("utf-8", errors="replace").rstrip("\n\r")
                        yield f"data: {json.dumps({'line': text})}\n\n"
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"

                await process.wait()
                
                if process.returncode == 0:
                    yield f"data: {json.dumps({'line': '\\n\\n[SUCCESS] Deployment completed successfully!', 'done': True})}\n\n"
                else:
                    yield f"data: {json.dumps({'line': f'\\n\\n[ERROR] Process exited with code {process.returncode}', 'error': True, 'done': True})}\n\n"

            except asyncio.CancelledError:
                yield f"data: {json.dumps({'line': '[WARNING] Request cancelled but deployment might still be running locally.', 'error': True})}\n\n"
                pass
            except Exception as e:
                logger.error(f"Deployment error: {e}")
                yield f"data: {json.dumps({'line': f'[system-error] {e}', 'error': True, 'done': True})}\n\n"
            finally:
                if process and process.returncode is None:
                    try:
                        # process.kill() might be dangerous for docker compose, 
                        # but if we drop connection, we can choose to let it finish 
                        # or kill it. For now let it run in background.
                        pass
                    except Exception:
                        pass

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@router.get("/restart/stream")
async def stream_restart():
    """Stream restart process in real-time via Server-Sent Events."""
    if _deploy_lock.locked():
        raise HTTPException(status_code=429, detail="A task is already in progress.")

    async def generate() -> AsyncGenerator[str, None]:
        async with _deploy_lock:
            root_dir = SESSIONS_DIR.parent.parent.parent
            
            cmd = f"docker compose restart {CONTAINER_NAME}"

            logger.info(f"Starting restart from {root_dir}")
            yield f"data: {json.dumps({'line': f'> Restarting {CONTAINER_NAME} from {root_dir}...'})}\n\n"
            yield f"data: {json.dumps({'line': f'> Executing: {cmd}'})}\n\n"

            process = None
            try:
                process = await asyncio.create_subprocess_shell(
                    cmd,
                    cwd=str(root_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )

                while True:
                    try:
                        line = await asyncio.wait_for(
                            process.stdout.readline(), timeout=15
                        )
                        if not line:
                            break
                        text = line.decode("utf-8", errors="replace").rstrip("\n\r")
                        yield f"data: {json.dumps({'line': text})}\n\n"
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"

                await process.wait()
                
                if process.returncode == 0:
                    yield f"data: {json.dumps({'line': '\\n\\n[SUCCESS] Restart completed successfully!', 'done': True})}\n\n"
                else:
                    yield f"data: {json.dumps({'line': f'\\n\\n[ERROR] Process exited with code {process.returncode}', 'error': True, 'done': True})}\n\n"

            except asyncio.CancelledError:
                yield f"data: {json.dumps({'line': '[WARNING] Request cancelled but restart might still be running locally.', 'error': True})}\n\n"
                pass
            except Exception as e:
                logger.error(f"Restart error: {e}")
                yield f"data: {json.dumps({'line': f'[system-error] {e}', 'error': True, 'done': True})}\n\n"
            finally:
                if process and process.returncode is None:
                    try:
                        pass
                    except Exception:
                        pass

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
