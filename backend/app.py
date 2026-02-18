from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import connect_db, close_db
from .routers import journals
from .media import router as media_router

app = FastAPI(title="CodexJ Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    connect_db()


@app.on_event("shutdown")
async def shutdown_event():
    close_db()


@app.get("/")
async def health():
    return {"ok": True}


app.include_router(journals.router, prefix="/api")
app.include_router(media_router, prefix="/api")
