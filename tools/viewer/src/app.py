import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import PORT, HOST, SESSIONS_DIR, CONTAINER_NAME, STATIC_DIR, print_banner
from .routes import sessions, logs, system
from .schemas import AppConfig

app = FastAPI(title="Nanobot Forensic Viewer", version="2.1.0")

# Static Files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Routes
app.include_router(sessions.router)
app.include_router(logs.router)
app.include_router(system.router)


@app.get("/")
async def get_index():
    """Serve the SPA entry point."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config", response_model=AppConfig)
async def get_config():
    """Expose current environment config to the UI."""
    return AppConfig(
        sessions_dir=str(SESSIONS_DIR),
        container_name=CONTAINER_NAME,
    )


if __name__ == "__main__":
    print_banner()
    uvicorn.run(app, host=HOST, port=PORT)
