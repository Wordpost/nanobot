import subprocess
import asyncio
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from ..schemas import DockerLogsResponse

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/", response_model=DockerLogsResponse)
async def get_logs(container: str = "nanobot-gateway", tail: int = 300):
    """Fetch Docker logs snapshot (fallback)."""
    try:
        result = subprocess.run(
            ["docker", "logs", container, "--tail", str(tail), "--timestamps"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if result.returncode != 0:
            return DockerLogsResponse(logs=f"[system-error] {result.stderr}", container=container)

        return DockerLogsResponse(
            logs=result.stdout + result.stderr,
            container=container,
        )
    except FileNotFoundError:
        return DockerLogsResponse(logs="[system-error] Docker CLI not found", container=container)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Docker log timeout")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stream")
async def stream_logs(container: str = "nanobot-gateway", tail: int = 300):
    """Stream Docker logs in real-time via Server-Sent Events."""

    async def generate():
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                "docker", "logs", container,
                "--follow", "--tail", str(tail), "--timestamps",
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
        except asyncio.CancelledError:
            pass
        except FileNotFoundError:
            yield f"data: {json.dumps({'line': '[system-error] Docker CLI not found', 'error': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'line': f'[system-error] {e}', 'error': True})}\n\n"
        finally:
            if process and process.returncode is None:
                try:
                    process.kill()
                    await process.wait()
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
