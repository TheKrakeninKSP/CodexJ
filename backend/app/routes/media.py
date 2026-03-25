from app.database import get_db
from app.models.media import MediaOut
from app.utils.auth import get_current_user
from app.utils.media import delete_media_file, save_media_to_user_directory
from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

router = APIRouter(prefix="/media", tags=["media"])

ALLOWED_MIME = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "video/mp4",
    "video/webm",
    "video/ogg",
    "audio/mpeg",
    "audio/aac",
    "audio/flac",
    "audio/wav",
    "audio/mp4",
    "audio/x-m4a",
    "audio/alac",
}


@router.post("/upload", response_model=MediaOut, status_code=201)
async def upload_media(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(415, f"Unsupported media type: {file.content_type}")

    if file.content_type.startswith("image"):
        resource_type = "image"
    elif file.content_type.startswith("video"):
        resource_type = "video"
    elif file.content_type.startswith("audio"):
        resource_type = "audio"
    else:
        raise HTTPException(415, f"Unsupported media type: {file.content_type}")

    try:
        result = await save_media_to_user_directory(
            user_id=current_user.get("id", ""),
            media_type=resource_type,
            file=file,
            db=db,
        )
        status = result.get("status", False)
        media = result.get("media")
    except Exception as exc:
        raise HTTPException(500, f"Upload failed: {exc}")

    if not status or not media:
        raise HTTPException(500, "Upload failed")

    return MediaOut.model_validate(media)


@router.delete("/{media_id}", status_code=204)
async def delete_media(
    media_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    doc = await db["media"].find_one(
        {"_id": ObjectId(media_id), "user_id": current_user["id"]}
    )
    if not doc:
        raise HTTPException(404, "Media not found")

    # Construct the resource path to check if it's still referenced
    resource_path = (
        f"http://localhost:8000/media/{doc['user_id']}/{doc['stored_filename']}"
    )

    # Check if any entries still reference this media
    entry_with_ref = await db["entries"].find_one({"media_refs": resource_path})
    if entry_with_ref:
        raise HTTPException(
            409,
            "Cannot delete media: still referenced by one or more entries",
        )

    delete_media_file(doc["user_id"], doc["stored_filename"])
    await db["media"].delete_one({"_id": doc["_id"]})
