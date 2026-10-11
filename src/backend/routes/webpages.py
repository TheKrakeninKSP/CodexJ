import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.database.querying import get_entry_by_id
from backend.database.structural import UserModel
from backend.models.media import MediaOut
from backend.type_defs import id_type
from backend.utils.auth import get_current_user
from backend.utils.media import build_media_out
from backend.utils.webpage_archiver import (
    _validate_url,
    extract_archived_webpage_metadata,
)
from backend.utils.webpage_media import (
    queue_webpage_archive,
    save_uploaded_webpage_archive,
)

router = APIRouter(prefix="/media", tags=["media"])

ALLOWED_WEBPAGE_ARCHIVE_MIME = {
    "text/html",
    "application/xhtml+xml",
    "application/octet-stream",
    "",
}
WEBPAGE_ARCHIVE_EXTENSIONS = {".html", ".htm"}


class SaveWebpageRequest(BaseModel):
    url: str


@router.post("/save-webpage", response_model=MediaOut, status_code=201)
async def save_webpage(
    entry_id: int,
    payload: SaveWebpageRequest,
    current_user: UserModel = Depends(get_current_user),
):
    """Archive a webpage and save it to the user's media directory."""
    if not get_entry_by_id(entry_id):
        raise HTTPException(404, "Entry not found")

    try:
        _validate_url(payload.url)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    media = queue_webpage_archive(
        entry_id=entry_id, user_id=current_user.id, url=payload.url
    )
    return build_media_out(media, current_user.id)


@router.post("/upload-webpage-archive", response_model=MediaOut, status_code=201)
async def upload_webpage_archive(
    entry_id: id_type = Form(...),
    file: UploadFile = File(...),
    current_user: UserModel = Depends(get_current_user),
):
    if not get_entry_by_id(entry_id):
        raise HTTPException(404, "Entry not found")

    content_type = (file.content_type or "").lower()
    _, extension = os.path.splitext(file.filename or "archive.html")
    if (
        content_type not in ALLOWED_WEBPAGE_ARCHIVE_MIME
        and extension.lower() not in WEBPAGE_ARCHIVE_EXTENSIONS
    ):
        raise HTTPException(415, "Unsupported archive type. Upload a saved HTML file.")

    contents = await file.read()
    if not contents:
        raise HTTPException(400, "Uploaded archive is empty")

    raw_html = contents.decode("utf-8", errors="replace")
    if "<html" not in raw_html.lower():
        raise HTTPException(422, "Uploaded file is not a valid HTML archive")

    try:
        media = save_uploaded_webpage_archive(
            entry_id=entry_id,
            user_id=current_user.id,
            contents=contents,
            metadata=extract_archived_webpage_metadata(raw_html),
        )
    except OSError as exc:
        raise HTTPException(500, f"Archive import failed: {exc}")
    return build_media_out(media, current_user.id)
