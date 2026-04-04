import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(tags=["help"])


def _resolve_help_doc_path() -> Path | None:
    source_path = Path(__file__).resolve().parents[1] / "help.md"

    if getattr(sys, "frozen", False):
        base_path = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        frozen_candidates = [
            base_path / "help.md",
            base_path / "app" / "help.md",
        ]
        for candidate in frozen_candidates:
            if candidate.exists():
                return candidate

    if source_path.exists():
        return source_path

    return None


@router.get("/help", summary="Get CodexJ usage help")
async def get_help():
    help_doc_path = _resolve_help_doc_path()
    if not help_doc_path:
        raise HTTPException(status_code=404, detail="Help documentation not found")

    return FileResponse(help_doc_path, media_type="text/markdown")
