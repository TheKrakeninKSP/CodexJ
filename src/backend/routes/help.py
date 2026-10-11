from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.constants import RESOURCES_PATH
from backend.utils.addressing import get_resource_path

router = APIRouter(tags=["help"])


def _resolve_help_doc_path() -> Path | None:
    source_path = get_resource_path(RESOURCES_PATH, "help.md")
    if source_path.exists():
        return source_path
    return None


@router.get("/help", summary="Get CodexJ usage help")
async def get_help():
    help_doc_path = _resolve_help_doc_path()
    if not help_doc_path:
        raise HTTPException(status_code=404, detail="Help documentation not found")
    return FileResponse(help_doc_path, media_type="text/markdown")
