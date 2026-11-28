# CodexJ

CodexJ is a self-hosted journaling application with a FastAPI + SQLite backend and a React + TypeScript + Vite frontend. Organize your writing into workspaces and journals, attach media, archive webpages, identify and tag music, link entries together, and export everything as an encrypted backup.

It ships two ways:

- **Desktop app** – a single PyInstaller bundle (`CodexJ.exe`) that opens in a native window (pywebview).
- **Headless server** – runs from source on a Linux box as a systemd service, reachable from a browser (including phones, via the responsive layout).

## Features

- **Workspaces & Journals** – Organize entries into workspaces, each containing multiple journals with optional descriptions. Journals can be moved between workspaces.
- **Rich-Text Editor** – TipTap-based editor with formatting, headers, lists, blockquotes, code blocks, links, and embedded media.
- **Media Uploads** – Attach images (JPEG, PNG, GIF, WebP), videos (MP4, WebM, Ogg), audio (MP3, AAC, FLAC, WAV, M4A, ALAC, Ogg, Opus), and PDFs to entries. Upload via the toolbar button or by dragging and dropping files into the editor.
- **Music Identification** – Audio uploads are fingerprinted via AcoustID (Chromaprint `fpcalc`) and looked up on MusicBrainz. Cover art, title, artist, album, and year are shown in the entry reader.
- **Song Tagging** – Don't have the audio file? Search MusicBrainz by title/artist and CodexJ downloads the song's audio from the top YouTube match (via yt-dlp), with its metadata and cover art.
- **Webpage Archiving** – Archive live webpages with the SingleFile CLI and a headless browser, or import previously saved SingleFile HTML archives. Archives run in the background.
- **Entry Linking** – Create internal links between entries. Links are clickable in the entry reader with history-aware back navigation.
- **Tags & Custom Metadata** – Tag entries and add unlimited key-value metadata fields to any entry. Entries can also have their own color theme.
- **Version History** – Previous versions of an entry can be browsed and compared from the entry reader.
- **Search & Filters** – Full-text search over entry bodies and metadata, plus filters by name, date range, and multiple tags (match all or any).
- **Bin & Recovery** – Deleted entries move to a Bin. Restore to the original location or a different journal, or purge permanently.
- **Encrypted Export & Import** – Encrypted data dumps include all workspaces, journals, entries (including binned), tags, and media. The dump key is derived from your account hashkey, so no separate passphrase is needed. Import into a new account (restoring from the dump) or into an existing account (merging data) with full ID remapping.
- **Sudo Mode** – Re-authenticate to unlock privileged actions (deleting workspaces/journals, rename, move, purge, export, trim, shred). Binning and restoring entries are reversible and need no Sudo mode.
- **Hashkey Recovery** – A one-time 64-character hex key generated at registration, which can be used to sign in if you lose your password.
- **Themes** – Light, Midnight, and Solarized Dark appearance themes, stored per user.
- **Admin Dashboard** – User count, per-user storage, and last login for admin accounts (see [Admin Accounts](#admin-accounts)).
- **Responsive Layout** – Usable on phones and narrow windows.
- **Fullscreen** – Toggle with Alt+Enter.

## Tech Stack

- Backend: FastAPI, Uvicorn, SQLAlchemy, Alembic, python-jose, Passlib (Argon2), Cryptography, pyacoustid, musicbrainzngs, yt-dlp
- Frontend: React, TypeScript, Vite, React Router, Axios, Zustand, TipTap
- Database: SQLite
- Desktop packaging: PyInstaller, pywebview
- Helper binaries: SingleFile CLI, Chromaprint `fpcalc`, ffmpeg/ffprobe, deno

## Repository Structure

```text
src/
  backend/     # FastAPI app: routes, models, database, utils, Alembic migrations
  frontend/    # React + Vite app
brand-common/  # git submodule: shared suite brand styles, theme tokens, style guide
tests/         # pytest test suite
packaging/     # systemd units + install script for the headless server
resources/     # build outputs bundled into the app (built frontend, build config)
deps/          # helper binaries fetched by build.py
build.py       # desktop / server build script
codexj.spec    # PyInstaller spec
```

At runtime the app keeps its data next to the project root: `codexj.db` (SQLite database), `media/` (uploads), and `dumps/` (encrypted exports). These are created automatically.

## Prerequisites

- Python 3.10+
- Node.js 18+ and npm 9+
- (Optional) Chrome, Edge, or Chromium for webpage archiving. Override the auto-detected browser with `CODEXJ_BROWSER_PATH`.
- Helper binaries: `python build.py` and `python build.py --server` download the SingleFile CLI, `fpcalc`, ffmpeg/ffprobe, and deno into `deps/` for the current platform. When running from a plain source checkout without running `build.py`, run it once with `--server` to fetch them, or have the tools on PATH (song tagging falls back to ffmpeg and deno on PATH).

## Environment Variables

### Backend

The backend reads its settings from a `.env` file. Copy `src/backend/.env.example` to `src/backend/.env` and fill in the JWT values.

| Variable | Default | Notes |
|---|---|---|
| `JWT_SECRET` | – | Required when running from source. Use a long random string. |
| `JWT_ALGORITHM` | `HS256` | |
| `JWT_EXPIRE_DAYS` | `7` | |
| `CODEXJ_BROWSER_PATH` | – | Optional path to Chrome/Edge/Chromium for webpage archiving. |
| `ACOUSTID_API_KEY` | built-in key | Optional AcoustID API key for music identification. |
| `CODEXJ_HOST` | `0.0.0.0` | Headless server only (`backend.serve`). |
| `CODEXJ_PORT` | `8128` | Headless server only (`backend.serve`). |

Example:

```env
JWT_SECRET=change-me-to-a-long-random-string
JWT_ALGORITHM=HS256
JWT_EXPIRE_DAYS=7
```

`DB_NAME` / `TEST_DB_NAME` in `.env.example` are leftovers from the old MongoDB backend and are not used. The database is always SQLite at `codexj.db` in the project root, and Alembic migrations are applied automatically at startup.

The desktop build does not need a `.env`: `build.py` embeds a freshly generated JWT secret into the bundle.

### Frontend

- `VITE_API_URL` (default: `http://localhost:8128`) – backend base URL used by the dev frontend. Production builds use same-origin requests.

Create `src/frontend/.env` only if you need to change it:

```env
VITE_API_URL=http://localhost:8128
```

## Local Development

The frontend's brand styles come from the [brand-common](https://github.com/TheKrakeninKSP/brand-common) git submodule. Clone with submodules:

```bash
git clone --recurse-submodules <codexj-url>
# already cloned? fetch the submodule:
git submodule update --init
```

Re-run `git submodule update --init` after a pull that changes `brand-common`, or set `git config --global submodule.recurse true` once so `git pull` does it automatically.

### 1. Backend Setup

From the repository root:

```powershell
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# Linux/macOS
source .venv/bin/activate

pip install -r requirements-dev.txt
```

`requirements-dev.txt` pulls in `requirements.txt` (runtime deps) plus the dev server CLI, test tools, and the desktop build tools (PyInstaller, pywebview).

Run the API (from the repository root):

```bash
fastapi dev src/backend/main.py --port 8128
```

API endpoints:

- Health: `GET /health`
- Version: `GET /version`
- OpenAPI docs: `http://localhost:8128/docs`

### 2. Frontend Setup

```bash
cd src/frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:5298`. In development the backend allows CORS from `http://localhost:5298` and `http://127.0.0.1:5298`.

Other frontend scripts:

```bash
npm run build     # type-check and compile to src/frontend/dist/
npm run lint      # ESLint (zero warnings allowed)
```

### Database Migrations

Migrations run automatically when the app starts. To manage them by hand, run Alembic from the repository root (where `alembic.ini` lives):

```bash
alembic upgrade head                                   # apply pending migrations
alembic revision --autogenerate -m "short description" # new migration from model changes
alembic downgrade -1                                   # roll back one migration
```

## Testing

From the repository root, with the venv active:

```bash
pytest                                          # all tests
pytest tests/test_entries.py                    # one file
pytest tests/test_entries.py -k "test_create_entry"  # one test
```

Tests use a separate `codexj-test.db` that is removed after the run.

## Building the Desktop App

Build a standalone executable that bundles the frontend and backend. Install the dev requirements first (they include PyInstaller and pywebview), then from the repository root:

```bash
python build.py
```

Or clean previous artifacts first:

```bash
python build.py --clean
```

The build compiles the frontend, generates an embedded config (with a random JWT secret), downloads the helper binaries into `deps/`, and runs PyInstaller.

### Output

The build creates `dist/CodexJ_v{VERSION}/` (the version comes from `APP_VERSION` in `src/backend/constants.py`) containing:

```text
CodexJ_v2.2.1/
├── CodexJ.exe    # Main executable (CodexJ on Linux/macOS)
├── media/        # User uploads directory
├── dumps/        # Data export directory
└── ...           # Supporting files
```

### Running the Built App

Run `CodexJ.exe`. It starts the server on `127.0.0.1:8128` and opens CodexJ in a fullscreen native window; closing the window stops the app. The database and media are stored inside the app folder, so the whole folder can be moved anywhere.

## Headless Server (Linux)

For running CodexJ as a background service on a Linux machine (no native window), served to browsers on your network. This runs from the source checkout rather than a PyInstaller bundle.

```bash
# Build the frontend and fetch the helper binaries for this platform (no PyInstaller)
python build.py --server

# Create the venv and install runtime dependencies
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Create the backend `.env` with `JWT_SECRET` / `JWT_ALGORITHM` / `JWT_EXPIRE_DAYS` as described in [Environment Variables](#backend). Optionally set `CODEXJ_HOST` / `CODEXJ_PORT` (default `0.0.0.0:8128`).

Run it directly:

```bash
cd src
../.venv/bin/python -m backend.serve
```

Or install it as a systemd service. First edit `packaging/codexj.service` (and `codexj-backup.service`) so `User`, `WorkingDirectory`, and `ExecStart` match your user and checkout path, then:

```bash
bash packaging/install_service.sh
```

The script (which re-runs itself with sudo) installs the units from `packaging/` into `/etc/systemd/system`, syncs the `brand-common` submodule, updates the Python dependencies, rebuilds the frontend, and enables and restarts the server and the backup timer. **Re-run it after every `git pull`** – the built frontend is not committed, so restarting the service alone keeps serving the old UI. Use `--no-build` to skip the frontend rebuild.

### Backups

`packaging/codexj-backup.timer` runs `python -m backend.snapshot` daily at midnight. It writes a consistent snapshot of the database to `backup/codexj.db` (only the latest is kept) without stopping the app. Back up `backup/` and `media/` with restic or a similar tool – not the live `codexj.db`. See [RESTIC-README.md](RESTIC-README.md) for details.

## Admin Accounts

Admins can open the admin dashboard (`/admin`, linked from the sidebar menu), which shows the
user count, storage used by each user, and each user's last login. Nobody is an admin by
default, and the role can only be granted from the command line on the machine running the
server, never through the app:

```bash
cd src
python -m backend.admin promote <username>   # grant admin
python -m backend.admin demote <username>    # revoke admin
python -m backend.admin list                 # list users, marking admins
```

Run it with the project's virtualenv active. It applies any pending database migrations
first, and is safe to run while the server is up. The change takes effect the next time the
user loads the app.
