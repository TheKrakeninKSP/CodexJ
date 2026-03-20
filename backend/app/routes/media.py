from app.utils.auth import get_current_user
from app.utils.media import save_media_to_user_directory
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

router = APIRouter(prefix="/media", tags=["media"])

ALLOWED_MIME = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "video/mp4",
    "video/webm",
    "video/ogg",
}


class UploadResponse(BaseModel):
    status: str = "success"
    resource_path: str
    resource_type: str


@router.post("/upload", response_model=UploadResponse)
async def upload_media(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(415, f"Unsupported media type: {file.content_type}")

    if file.content_type.startswith("image"):
        resource_type = "image"
    elif file.content_type.startswith("video"):
        resource_type = "video"
    else:
        raise HTTPException(415, f"Unsupported media type: {file.content_type}")

    try:
        result = await save_media_to_user_directory(
            user_id=current_user.get("id", ""), media_type=resource_type, file=file
        )
        status = result.get("status", False)
        url = result.get("url", "")
    except Exception as exc:
        raise HTTPException(500, f"Upload failed: {exc}")

    return UploadResponse(
        status="success" if status else "error",
        resource_path=url,
        resource_type=resource_type,
    )
