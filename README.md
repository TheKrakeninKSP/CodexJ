# CodexJ

CodexJ is a full-stack journaling application with a FastAPI backend and a React + Vite frontend. Organize your writing into workspaces and journals, attach media, archive webpages, identify music in audio uploads, link entries together, and export everything as an encrypted backup.

## Features

- **Workspaces & Journals** – Organize entries into workspaces, each containing multiple journals with optional descriptions.
- **Rich-Text Editor** – Quill-based editor with formatting, headers, lists, blockquotes, and code blocks.
- **Media Uploads** – Attach images (JPEG, PNG, GIF, WebP), videos (MP4, WebM, Ogg), and audio (MP3, AAC, FLAC, WAV, M4A, OGG, Opus) to entries. Upload via the toolbar button or by dragging and dropping files directly into the editor.
- **Music Identification** – Audio uploads are automatically fingerprinted via AcoustID and looked up on MusicBrainz. Cover art, title, artist, album, and year are displayed in the entry reader.
- **Webpage Archiving** – Archive live webpages using the SingleFile engine with a headless browser, or import previously saved SingleFile HTML archives. Archives run in the background.
- **Entry Linking** – Create internal links between entries. Links are clickable in the entry reader with history-aware back navigation.
- **Custom Metadata** – Add unlimited key-value fields to any entry.
- **Entry Types** – Per-workspace entry type system with usage counts and management from the workspace overview.
- **Search & Filters** – Full-text search (MongoDB Atlas Search with regex fallback), plus filters by entry name, type, and date range with pagination.
- **Bin & Recovery** – Deleted entries move to a Bin. Restore to the original location or a different journal. Bulk purge supported.
- **Encrypted Export & Import** – AES-encrypted data dumps include all workspaces, journals, entries (including binned), entry types, and media. The dump is encrypted with a key derived from your account hashkey — no separate passphrase needed. Import into a new account (restoring from the dump) or into an existing account (merging data) with full ID remapping.
- **Plaintext Import** – Import structured `.txt` files with optional media attachments.
- **Sudo Mode** – Re-authenticate to unlock privileged actions (delete, rename, purge, export, trim, shred).
- **Themes** – Light and Dark appearance themes, stored per user.
- **Hashkey Recovery** – A one-time 64-character hex key generated at registration for account recovery.
- **Fullscreen** – Toggle with Alt+Enter.

## Tech Stack

- Backend: FastAPI, Motor, PyMongo, python-jose, Passlib, Cryptography
- Frontend: React, TypeScript, Vite, Axios, Zustand, Quill
- Database: MongoDB

## Repository Structure

```text
backend/
  app/       # FastAPI app, routes, models, utilities
  tests/     # pytest test suite
frontend/
  src/       # React app source code
```

## Prerequisites

- Python 3.10+
- Node.js 18+
- npm 9+
- MongoDB local instance
- (Optional) Chrome, Edge, or Chromium for webpage archiving. Override with `CODEXJ_BROWSER_PATH`.

## Environment Variables

### Backend

The backend reads environment variables from a `.env` file.

Required/optional variables:

- `MONGODB_URI` (default: `mongodb://localhost:27017/`)
- `DB_NAME` (default: `codexj`)
- `CODEXJ_BROWSER_PATH` (optional) – Path to Chrome/Edge/Chromium for webpage archiving.

Example:

```env
MONGODB_URI=mongodb://localhost:27017/
DB_NAME=codexj
```

### Frontend

Frontend API base URL:

- `VITE_API_URL` (default: `http://localhost:8128`)

Create `frontend/.env` if needed:

```env
VITE_API_URL=http://localhost:8128
```

## Local Development

### 1. Backend Setup

From the repository root:

```bash
cd backend
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Run the API:

```bash
fastapi dev app/main.py --port 8128
```

API endpoints:

- Health: `GET /health`
- Version: `GET /version`
- OpenAPI docs: `http://localhost:8128/docs`

### 2. Frontend Setup

From the repository root:

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5298` by default.

## Testing

Run backend tests:

```bash
cd backend
pytest
```

## Build Frontend

```bash
cd frontend
npm run build
npm run preview
```

## Notes

- Backend CORS allows `http://localhost:5298` and `http://127.0.0.1:5298` in development.
- Media and data dump directories are created automatically.

## Building for Distribution

Build a standalone executable that bundles the frontend and backend:

### Prerequisites

```bash
cd backend
pip install pyinstaller
```

### Build

From the repository root:

```bash
python build.py
```

Or clean previous artifacts first:

```bash
python build.py --clean
```

### Output

The build creates `dist/CodexJ_v{VERSION}/` containing:

```text
CodexJ_v0.4.3/
├── CodexJ.exe    # Main executable (or CodexJ on Linux/Mac)
├── media/        # User uploads directory
├── dumps/        # Data export directory
└── ...           # Supporting files
```

### Running the Built App

1. Ensure MongoDB is running locally
2. Run `CodexJ.exe` (or `./CodexJ` on Linux/Mac)
3. Open `http://localhost:8128` in your browser

The built app is fully portable - move the entire folder anywhere and it will work.