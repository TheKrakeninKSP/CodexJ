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

- `VITE_API_URL` (default: `http://localhost:8000`)

Create `frontend/.env` if needed:

```env
VITE_API_URL=http://localhost:8000
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
fastapi dev app/main.py
```

API endpoints:

- Health: `GET /health`
- Version: `GET /version`
- OpenAPI docs: `http://localhost:8000/docs`

### 2. Frontend Setup

From the repository root:

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173` by default.

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

- Backend CORS allows `http://localhost:5173` and `http://127.0.0.1:5173`.
- Media and data dump directories are created automatically under `backend/app/`.