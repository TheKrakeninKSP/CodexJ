from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["help"])

HELP_DOC_PATH = Path(__file__).resolve().parents[1] / "help.md"


@router.get("/help", summary="Get CodexJ usage help")
async def get_help():
    return FileResponse(HELP_DOC_PATH, media_type="text/markdown")
