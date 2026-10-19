# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CodexJ is a self-hosted journaling app packaged as a standalone desktop executable. The backend is a FastAPI + SQLite app; the frontend is React + TypeScript + Vite. In production, PyInstaller bundles both into a single `CodexJ.exe` that uses pywebview for the native window. In development they run as separate processes.

## Commands

All commands assume the project root is `D:\projects\CodexJ` (or repo root on other systems).

### Backend

```powershell
# Activate the venv (PowerShell)
.\.venv\Scripts\Activate.ps1

# Run the dev server (hot-reload via fastapi dev)
fastapi dev src/backend/main.py --port 8128

# Run all tests
pytest

# Run a single test file
pytest tests/test_entries.py

# Run a single test by name
pytest tests/test_entries.py -k "test_create_entry"
```

`pytest` is configured in `pyproject.toml` with `pythonpath = ["src"]`, so imports resolve from `src/`.

### Database migrations (Alembic)

`alembic.ini` is in the repo root; run all commands from there.

```powershell
# Apply all pending migrations
alembic upgrade head

# Stamp an existing DB that pre-dates Alembic (run once, then upgrade head)
alembic stamp b1e3c8d2a9f1

# Generate a new migration from ORM model changes
alembic revision --autogenerate -m "short description"

# Roll back one migration
alembic downgrade -1
```

`render_as_batch=True` is set in `env.py` because SQLite does not support `ALTER TABLE … ADD COLUMN` in all cases.

### Frontend

```powershell
cd src/frontend
npm install       # first time only
npm run dev       # dev server at http://localhost:5298
npm run build     # compile to src/frontend/dist/
npm run lint      # ESLint (zero max-warnings)
```

### Distribution build

```powershell
# From repo root — builds frontend, then PyInstaller bundle
python build.py

# Clean previous artifacts first
python build.py --clean
```

Output: `dist/CodexJ_v{VERSION}/CodexJ.exe`

### Headless server deployment (Linux daemon)

For running CodexJ on a Linux box as a background service (no native window), rather than
the pywebview-wrapped desktop build:

```bash
# Build the frontend and fetch helper binaries (singlefile, fpcalc) for this platform -
# skips build_config.py and PyInstaller entirely
python build.py --server

# Set up the venv (on the target Linux host)
python -m venv .venv
.venv/bin/pip install -r requirements.txt

# Configure secrets the same way as dev: a .env at the repo root with
# JWT_SECRET / JWT_ALGORITHM / JWT_EXPIRE_DAYS (see env var table below).
# Optionally set CODEXJ_HOST / CODEXJ_PORT (default 0.0.0.0:8128).

# Run directly:
cd src && python -m backend.serve

# Or install packaging/codexj.service as a systemd unit for daemonized, auto-restarting operation.
```

`src/backend/serve.py` reuses the same FastAPI app as the desktop build (same routes, same
`run_migrations()` startup, same SQLite DB/media/dumps layout next to wherever the process
runs from) - it just runs uvicorn directly instead of wrapping it in a pywebview window.
`requirements.txt` lists only the runtime deps needed to run from source (no pywebview,
PyInstaller, or other desktop-only packages).

## Architecture

### Dev vs. production mode

`src/backend/utils/addressing.py:is_dev_env()` returns `True` when not running as a frozen PyInstaller bundle. This gates:
- CORS middleware (only added in dev, because prod serves the built frontend from the same origin)
- JWT config source (`.env` in dev vs. embedded `build_config` module in prod)
- Resource path resolution (`get_resource_path` uses `sys._MEIPASS` in prod)

The frontend at `src/frontend/src/services/api.ts` reads `VITE_API_URL` (defaults to `http://localhost:8128`).

### Backend layers

```
src/backend/
  main.py            — FastAPI app factory; mounts routers and static files
  constants.py       — All file paths (MEDIA_PATH, DUMPS_PATH, SQLITE_DB_URL), table names, and length limits
  type_defs.py       — Shared types: id_type (UUID str), MediaStatus, MediaType, ExportStatus, ImportStatus
  globalvar.py       — IS_SESSION_PRIVILEGED (module-level singleton flag for sudo mode)
  settings.py        — ColorTheme enum
  database/
    structural.py    — SQLAlchemy ORM models + engine + init_db(); also defines Session
    querying.py      — All DB queries as plain functions (one session per call, expire_on_commit=False)
  models/            — Pydantic request/response schemas (separate from ORM models)
  routes/            — One file per resource (auth, workspaces, journals, entries, tags, media, webpages, music, data_management, help)
  utils/
    auth.py          — JWT helpers, get_current_user dependency, assert_workspace_owner / assert_journal_access
    data_management.py — Encrypted export/import, recursive delete helpers (recursive_delete_*)
    entry_utils.py   — Quill Delta parsing: extract_media_refs, remap_entry_links
    addressing.py    — Path resolution (dev vs. frozen)
    music_media.py / music_lookup.py — AcoustID fingerprinting + MusicBrainz lookup (async background tasks)
    webpage_media.py / webpage_archiver.py — SingleFile-based webpage archiving (async background tasks)
```

### Database

SQLite. The DB file lives at `<project_root>/codexj.db` (resolved by `constants.SQLITE_DB_URL`). Schema is created by `init_db()` (called at app startup via `lifespan`).

**JSON-in-columns pattern:** several `EntryModel` columns store JSON strings — `tags` (`list[str]`), `body` (Quill Delta object), `custom_metadata` (`list[MetadataField]`), `theme` (`EntryTheme`), and `media_refs` (`list[str]`). The `querying.py` functions handle serialisation/deserialisation. Full-text search over `body` and `custom_metadata` uses SQLite `ILIKE` on the raw JSON string.

**Ownership chain:** `Media → Entry → Journal → Workspace → User`. Auth helpers in `utils/auth.py` enforce this chain by walking it and returning 403/404 as appropriate.

### Authentication & privileged mode

JWT Bearer tokens. `get_current_user` is a FastAPI dependency injected into every protected route. "Sudo mode" is a process-level flag (`globalvar.IS_SESSION_PRIVILEGED`) toggled via `/auth/privileged` — not per-request state. Routes that require it call `require_privileged_mode()` as a dependency.

### Frontend

React Router v7 SPA. Route layout:
- `/login`, `/register` — public
- `/*` — wrapped in `RequireAuth` → `AppLayout` (sidebar + outlet)
  - `/` → `WorkspaceOverview`
  - `/journals/:journalId` → `JournalView`
  - `/entries/:entryId` → `EntryReader`
  - `/entries/:entryId/edit` → `EntryEditor`
  - `/bin`, `/help`

State is managed with Zustand stores (`authStore`, `themeStore`, `workspaceStore`, `editorPrefsStore`). `authStore` persists token/username to `localStorage` (key `codexj-auth`) but excludes `isPrivilegedMode`. All API calls go through the single Axios instance in `services/api.ts`, which attaches the Bearer token and auto-logs out on 401.

### Media

Uploaded files are stored under `media/<user_id>/<uuid>.<ext>`. The path is served as a static mount at `/media` by FastAPI. `MediaModel.stored_filename` is the bare `<uuid>.<ext>`; the full URL is reconstructed from the user's id. Orphaned media cleanup uses `entry_references_media()` to check whether an entry's `media_refs` JSON still contains a URL before deleting the file.

### Export / import

Encrypted with `cryptography.fernet`. The encryption key is derived from the user's `hashkey` via HKDF (see `utils/data_management.derive_dump_key`). Dumps bundle all workspaces, journals, entries, media files, and tags. Import supports merging into an existing account with full ID remapping (`remap_entry_links` rewrites Quill Delta link attributes).

## Testing

Tests use `pytest-asyncio` with an in-process `httpx.AsyncClient` (ASGI transport). The test DB is a separate SQLite file (`codexj-test.db`) created by overriding `backend.constants.SQLITE_DB_URL` before any import of the database modules. `conftest.py` tears the file down after the session.

Key fixtures in `tests/conftest.py`:
- `client` / `alternate_user_client` — bypass auth via `dependency_overrides[get_current_user]`
- `make_workspace`, `make_journal`, `make_entry` — composable, each cleans up after itself
- `enable_privileged_mode` — sets the global flag for the duration of the test
- `stub_music_lookup` (autouse) — patches `identify_song` to `None` to keep tests offline

## Environment variables (backend `.env`)

| Variable | Default | Notes |
|---|---|---|
| `JWT_SECRET` | — | Required in dev |
| `JWT_ALGORITHM` | `HS256` | |
| `JWT_EXPIRE_DAYS` | `7` | |
| `CODEXJ_BROWSER_PATH` | — | Path to Chrome/Edge for webpage archiving |

The `DB_NAME` and `MONGODB_URI` variables in `.env.example` are leftover from the old MongoDB era and are not used — the database is now SQLite, configured entirely by `constants.SQLITE_DB_URL`.
