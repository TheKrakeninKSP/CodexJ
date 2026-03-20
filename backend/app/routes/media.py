from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from app.utils.auth import get_current_user
from app.utils.media import save_media_to_user_directory

router = APIRouter(prefix="/media", tags=["media"])

ALLOWED_MIME = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "video/mp4", "video/webm", "video/ogg",
}
MAX_SIZE_MB = 20


class UploadResponse(BaseModel):
    status: str = "success"
    resource_type: str


@router.post("/upload", response_model=UploadResponse)
async def upload_media(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(415, f"Unsupported media type: {file.content_type}")

    data = await file.read()
    if len(data) > MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(413, f"File exceeds {MAX_SIZE_MB} MB limit")

    if file.content_type.startswith("image"):
        resource_type = "image"
    elif file.content_type.startswith("video"):
        resource_type = "video"
    else:
        raise HTTPException(415, f"Unsupported media type: {file.content_type}")

    try:
        result = save_media_to_user_directory(
            user_id=current_user.get('id', ""),
            media_type=resource_type,
            file=file
        )
    except Exception as exc:
        raise HTTPException(500, f"Upload failed: {exc}")

    return UploadResponse(
        status="success",
        resource_type=resource_type,
    )
