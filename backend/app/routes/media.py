import os
import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from app.utils.auth import get_current_user

router = APIRouter(prefix="/media", tags=["media"])

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

ALLOWED_MIME = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "video/mp4", "video/webm", "video/ogg",
}
MAX_SIZE_MB = 20


class UploadResponse(BaseModel):
    url: str
    public_id: str
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

    resource_type = "video" if file.content_type.startswith("video") else "image"

    try:
        result = cloudinary.uploader.upload(
            data,
            folder=f"codexj/{current_user['id']}",
            resource_type=resource_type,
        )
    except Exception as exc:
        raise HTTPException(500, f"Upload failed: {exc}")

    return UploadResponse(
        url=result["secure_url"],
        public_id=result["public_id"],
        resource_type=resource_type,
    )
