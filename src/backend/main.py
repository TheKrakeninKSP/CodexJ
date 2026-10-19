import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.database.structural import run_migrations
from backend.utils.addressing import is_dev_env
from backend.utils.music_media import wait_for_music_lookup_tasks
from backend.utils.webpage_media import wait_for_webpage_archive_tasks

from .constants import APP_VERSION, MEDIA_PATH, STATIC_PATH
from .routes import (
    auth,
    data_management,
    entries,
    help,
    journals,
    media,
    music,
    tags,
    webpages,
    workspaces,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        run_migrations()
        yield
    except Exception as exc:
        print(f"Warning: Starting API without database connection: {exc}")
    finally:
        await wait_for_webpage_archive_tasks()
        await wait_for_music_lookup_tasks()


def app_factory() -> FastAPI:
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

    # Paths meant to be opened by a real browser navigation (not just fetched
    # by the SPA's own JS) - excluded from the SPA short-circuit below.
    _direct_nav_paths = (
        "/media/",
        "/assets/",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/health",
        "/version",
    )

    def _is_browser_navigation(request: Request) -> bool:
        """True for a real top-level browser navigation (typed URL, refresh,
        bookmark), false for the app's own fetch/XHR calls.

        `Sec-Fetch-Mode: navigate` is the standards-based signal, but some
        browsers/privacy settings strip Fetch Metadata headers entirely, so we
        also fall back to the `Accept` header: browsers have put `text/html`
        first in Accept on document navigations since long before Fetch
        Metadata existed, while axios' default Accept
        (`application/json, text/plain, */*`) never includes it.
        """
        if request.headers.get("sec-fetch-mode") == "navigate":
            return True
        return "text/html" in request.headers.get("accept", "")

    @app.middleware("http")
    async def spa_navigation_shortcut(request: Request, call_next):
        """Serve the SPA directly for real browser navigations, even on paths
        that collide with an API route (e.g. GET /entries/{id} vs. the
        /entries/:entryId reader page). Without this, refreshing the browser
        on such a page hits the API route first - with no Authorization
        header, since browsers never attach one to page loads - breaking the
        page even for an already-logged-in user.
        """
        if (
            request.method == "GET"
            and _is_browser_navigation(request)
            and not request.url.path.startswith(_direct_nav_paths)
        ):
            index_file = STATIC_PATH / "index.html"
            if index_file.exists():
                # Some of these paths (e.g. /entries/{id}) are *also* real API
                # endpoints the SPA's own JS calls right after this response is
                # served. FileResponse sets an ETag/Last-Modified by default
                # with no Vary: Accept, so without an explicit no-store the
                # browser's HTTP cache can transparently hand that axios call
                # this same cached HTML instead of hitting the network -
                # `entry` ends up as an HTML string, not JSON.
                return FileResponse(
                    str(index_file), headers={"Cache-Control": "no-store"}
                )
        return await call_next(request)

    @app.exception_handler(StarletteHTTPException)
    async def auth_redirect_on_navigation(request: Request, exc: StarletteHTTPException):
        # Fallback for when the SPA shortcut above didn't apply (e.g. the
        # static build is missing, or a route not in the exclusion list still
        # 401s) - send real browser navigations to login instead of showing
        # raw error JSON.
        if exc.status_code in (401, 403) and _is_browser_navigation(request):
            return RedirectResponse(url="/login")
        return await http_exception_handler(request, exc)

    app.include_router(auth.router)
    app.include_router(workspaces.router)
    app.include_router(journals.router)
    app.include_router(entries.router)
    app.include_router(tags.router)
    app.include_router(media.router)
    app.include_router(webpages.router)
    app.include_router(music.router)
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
                return FileResponse(
                    str(index_file), headers={"Cache-Control": "no-store"}
                )
            return {"detail": "Not Found"}

    return app


app = app_factory()
