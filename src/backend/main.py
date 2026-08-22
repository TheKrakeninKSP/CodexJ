import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.database.structural import init_db
from backend.utils.addressing import is_dev_env

from .constants import APP_VERSION, MEDIA_PATH, STATIC_PATH
from .database.database import close_db, connect_db, get_db_direct
from .routes import (
    auth,
    data_management,
    entries,
    help,
    journals,
    media,
    tags,
    workspaces,
)

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await connect_db(app)
        await _run_migrations(app)
        init_db()
        yield
    except Exception as exc:
        print(f"Warning: Starting API without database connection: {exc}")
    finally:
        await media.wait_for_webpage_archive_tasks()
        await close_db(app)


async def _run_migrations(app: FastAPI):
    """Run one-time DB migrations on startup."""

    db = await get_db_direct(app)
    if db is None:
        return
    # Release 1.2: migrate 'type' string field -> 'tags' list field
    result = await db["entries"].update_many(
        {"type": {"$exists": True}, "tags": {"$exists": False}},
        [{"$set": {"tags": ["$type"]}}, {"$unset": "type"}],
    )
    if result.modified_count:
        print(f"Migration: converted {result.modified_count} entries from type→tags")


app = FastAPI(
    title="CodexJ API",
    description="Backend for the CodexJ journaling application",
    version=APP_VERSION,
    lifespan=lifespan,
)

# CORS only needed in development (frontend on different port)
if is_dev_env():
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
app.include_router(tags.router)
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

static_dir = STATIC_PATH
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
