"""Docker log streaming. Pool-mode aware. (fork-local)"""

import asyncio
import json
import subprocess
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..config import CONTAINER_NAME, POOL_MODE, resolve_workspace
from ..utils import sse_response
from ..schemas import DockerLogsResponse

router = APIRouter(prefix="/api/logs", tags=["logs"])


def _resolve_container(agent: Optional[str]) -> str:
    """Resolve agent name to Docker container name."""
    if POOL_MODE and agent:
        ws = resolve_workspace(agent)
        return ws.container_name
    return CONTAINER_NAME


@router.get("/", response_model=DockerLogsResponse)
async def get_logs(
    agent: Optional[str] = Query(None),
    container: Optional[str] = Query(None),
    tail: int = 300,
):
    """Fetch Docker logs snapshot (fallback)."""
    target = container or _resolve_container(agent)
    try:
        result = subprocess.run(
            ["docker", "logs", target, "--tail", str(tail), "--timestamps"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if result.returncode != 0:
            return DockerLogsResponse(logs=f"[system-error] {result.stderr}", container=target)

        return DockerLogsResponse(logs=result.stdout + result.stderr, container=target)
    except FileNotFoundError:
        return DockerLogsResponse(logs="[system-error] Docker CLI not found", container=target)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Docker log timeout")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stream")
async def stream_logs(
    agent: Optional[str] = Query(None),
    container: Optional[str] = Query(None),
    tail: int = 300,
):
    """Stream Docker logs in real-time via SSE."""
    target = container or _resolve_container(agent)

    async def generate():
        import subprocess
        import threading
        
        process = None
        try:
            process = subprocess.Popen(
                ["docker", "logs", target, "--follow", "--tail", str(tail), "--timestamps"],
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
                    yield f"data: {json.dumps({'line': text})}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    
            await asyncio.to_thread(process.wait)
            
        except asyncio.CancelledError:
            pass
        except FileNotFoundError:
            yield f"data: {json.dumps({'line': '[system-error] Docker CLI not found', 'error': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'line': f'[system-error] {type(e).__name__}: {str(e)}', 'error': True})}\n\n"
        finally:
            if process and process.returncode is None:
                try:
                    process.kill()
                    process.wait()
                except Exception:
                    pass

    return sse_response(generate)
