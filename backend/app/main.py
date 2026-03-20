from app.constants import MEDIA_PATH
from dotenv import load_dotenv

load_dotenv()

from contextlib import asynccontextmanager

from app.database import close_db, connect_db
from app.routes import auth, entries, entry_types, journals, media, workspaces
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await connect_db(app)
    except Exception as exc:
        print(f"Warning: Starting API without database connection: {exc}")
    yield
    await close_db(app)


app = FastAPI(
    title="CodexJ API",
    description="Backend for the CodexJ journaling application",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
app.mount("/media", StaticFiles(directory=MEDIA_PATH), name="media")


@app.get("/health")
async def health():
    return {"status": "ok"}
