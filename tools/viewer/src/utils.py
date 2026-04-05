"""Shared SSE utilities for Forensic Viewer routes. (fork-local)"""

import json
from fastapi.responses import StreamingResponse


def sse_response(generator):
    """Wrap an async SSE generator in StreamingResponse with standard headers."""
    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def sse_line(payload: dict) -> str:
    """Format a single SSE data line."""
    return f"data: {json.dumps(payload)}\n\n"


async def watch_directories_fallback(scan_dirs: list, extension: str, yield_interval: int = 3):
    """Fallback polling watcher for directories if watchfiles is unavailable."""
    import asyncio
    last_fingerprint = None
    keepalive_counter = 0

    while True:
        try:
            fingerprint = {}
            for d in scan_dirs:
                if not d.exists():
                    continue
                for f in d.glob(f"*{extension}"):
                    try:
                        st = f.stat()
                        fingerprint[str(f)] = (st.st_mtime, st.st_size)
                    except OSError:
                        continue

            fp_key = str(sorted(fingerprint.items()))

            if fp_key != last_fingerprint:
                last_fingerprint = fp_key
                yield True  # Signal that a change occurred
                keepalive_counter = 0
            else:
                keepalive_counter += 1
                if keepalive_counter >= 5:
                    yield False  # Signal keepalive (no change)
                    keepalive_counter = 0

            await asyncio.sleep(yield_interval)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(5)


async def watch_directories(scan_dirs: list, extension: str):
    """
    Watch directories for changes, yielding True on change, False on keepalive.
    Uses 'watchfiles' for instant updates, falls back to polling if not installed.
    """
    import asyncio
    try:
        from watchfiles import awatch, Change
        have_watchfiles = True
    except ImportError:
        have_watchfiles = False
        import logging
        logging.getLogger("session-viewer").warning("watchfiles not installed, using polling fallback")

    if not have_watchfiles:
        async for change in watch_directories_fallback(scan_dirs, extension):
            yield change
        return

    # Using watchfiles
    dirs_to_watch = [str(d) for d in scan_dirs if d.exists()]
    
    if not dirs_to_watch:
        # Fallback if no directories exist yet (wait until they are created)
        async for change in watch_directories_fallback(scan_dirs, extension):
            yield change
        return

    # Yield initially (always "changed" at startup)
    yield True

    try:
        async for changes in awatch(*dirs_to_watch, step=500):
            # Check if any changed file matches our extension
            has_relevant_change = any(
                p.endswith(extension) for _, p in changes
            )
            if has_relevant_change:
                yield True
    except asyncio.CancelledError:
        pass
    except Exception as e:
        import logging
        logging.getLogger("session-viewer").error(f"watchfiles error: {e}, falling back to polling")
        async for change in watch_directories_fallback(scan_dirs, extension):
            yield change
