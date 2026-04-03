import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app.constants import APP_VERSION, MEDIA_PATH
from app.database import close_db, connect_db
from app.routes import (
    auth,
    data_management,
    entries,
    entry_types,
    help,
    journals,
    media,
    workspaces,
)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Determine if running in production (frozen executable)
IS_FROZEN = getattr(sys, "frozen", False)


def get_static_dir() -> Path:
    """Get the static files directory for embedded frontend"""
    if IS_FROZEN:
        # PyInstaller extracts data files to _MEIPASS
        return Path(sys._MEIPASS) / "static"  # type: ignore[attr-defined]
    else:
        # Development: static dir alongside main.py (created during build)
        return Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await connect_db(app)
    except Exception as exc:
        print(f"Warning: Starting API without database connection: {exc}")
    yield
    await media.wait_for_webpage_archive_tasks()
    await close_db(app)


app = FastAPI(
    title="CodexJ API",
    description="Backend for the CodexJ journaling application",
    version=APP_VERSION,
    lifespan=lifespan,
)

# CORS only needed in development (frontend on different port)
if not IS_FROZEN:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5298", "http://127.0.0.1:5298"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(journals.router)
app.include_router(entries.router)
app.include_router(entry_types.router)
app.include_router(media.router)
app.include_router(data_management.router)
app.include_router(help.router)
app.mount("/media", StaticFiles(directory=MEDIA_PATH), name="media")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/version")
async def version():
    return {"version": APP_VERSION}


# ── Static file serving for production ───────────────────────────────────────

static_dir = get_static_dir()

if static_dir.exists():
    # Mount static assets (JS, CSS, images)
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # SPA fallback - serve index.html for all non-API routes
    @app.get("/{path:path}")
    async def serve_spa(path: str):
        # Don't intercept API routes or media
        api_prefixes = (
            "api/",
            "auth/",
            "workspaces/",
            "journals/",
            "entries/",
            "entry-types/",
            "media/",
            "data-management/",
            "help",
            "health",
            "version",
            "docs",
            "openapi.json",
            "redoc",
        )
        if path.startswith(api_prefixes):
            return {"detail": "Not Found"}

        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"detail": "Not Found"}
