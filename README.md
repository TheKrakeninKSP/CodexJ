# CodexJ

CodexJ is a full-stack journaling application with a FastAPI backend and a React + Vite frontend.

## Tech Stack

- Backend: FastAPI, Motor, PyMongo, python-jose, Passlib
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

## Environment Variables

### Backend

The backend reads environment variables from a `.env` file.

Required/optional variables:

- `MONGODB_URI` (default: `mongodb://localhost:27017/`)
- `DB_NAME` (default: `codexj`)

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
CodexJ_v0.2.4/
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