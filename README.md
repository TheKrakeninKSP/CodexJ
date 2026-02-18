# CodexJ — Backend scaffold

This folder contains a minimal FastAPI backend scaffold for CodexJ.

Setup (Windows):

1. Install MongoDB Community Server and ensure it is running on `mongodb://localhost:27017`.
2. Create a virtualenv and install dependencies:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

3. Copy `.env.template` to `.env` and adjust if needed.

Run the dev server:

```powershell
uvicorn backend.app:app --reload --port 8000
```

API highlights:
- `GET /` health
- `POST /api/journals` create a journal
- `GET /api/journals` list journals
- `POST /api/journals/{journal_id}/entries` create an entry
- `GET /api/journals/{journal_id}/entries` list entries
- `POST /api/media/upload` upload media (stored in GridFS)
- `GET /api/media/{id}` download media
# CodexJ
A lightweight journaling application 
