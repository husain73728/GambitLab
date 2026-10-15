"""FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import ROOT
from .db import session_scope
from .engine.manager import ensure_default_config, manager
from .jobs import worker
from .models import Base
from .db import engine as db_engine
from .routers import core, games, insights

WEB_DIST = ROOT / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(db_engine)
    session = session_scope()
    try:
        from .deps import get_current_user
        get_current_user(session)
        ensure_default_config(session)
    finally:
        session.close()
    worker.start()
    yield
    worker.stop()
    manager.shutdown()


app = FastAPI(title="GambitLab", version=__version__, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(core.router)
app.include_router(games.router)
app.include_router(insights.router)


@app.get("/api/version")
def version():
    return {"name": "GambitLab", "version": __version__}


# Serve the built frontend when present (single-origin production mode).
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(WEB_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        index = WEB_DIST / "index.html"
        candidate = WEB_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)
