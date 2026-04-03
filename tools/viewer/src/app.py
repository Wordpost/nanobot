import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import PORT, HOST, SESSIONS_DIR, CONTAINER_NAME, STATIC_DIR, POOL_MODE, WORKSPACES, print_banner
from .routes import sessions, logs, system, config_manager, subagents, memory
from .schemas import AppConfig, AgentInfo

app = FastAPI(title="Nanobot Forensic Viewer", version="2.4.0")

# Static Files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Routes
app.include_router(sessions.router)
app.include_router(logs.router)
app.include_router(system.router)
app.include_router(config_manager.router)
app.include_router(subagents.router)
app.include_router(memory.router)


@app.get("/")
async def get_index():
    """Serve the SPA entry point."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config", response_model=AppConfig)
async def get_config():
    """Expose current environment config to the UI. (fork-local)"""
    agents = [
        AgentInfo(name=ws.name, container_name=ws.container_name)
        for ws in WORKSPACES.values()
    ] if POOL_MODE else []

    return AppConfig(
        sessions_dir=str(SESSIONS_DIR),
        container_name=CONTAINER_NAME,
        pool_mode=POOL_MODE,
        agents=agents,
    )


if __name__ == "__main__":
    print_banner()
    uvicorn.run(app, host=HOST, port=PORT)
