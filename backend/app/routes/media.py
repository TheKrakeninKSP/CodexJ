import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.constants import MEDIA_PATH
from app.database import get_db
from app.models.media import DB_Media, MediaOut
from app.utils.auth import get_current_user, require_privileged_mode
from app.utils.media import (
    delete_media_file,
    save_media_to_user_directory,
    trim_unreferenced_media_for_user,
)
from bson import ObjectId
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

    # Use the stored resource_path for referential integrity check (works for
    # both regular files and webpage archive directories).
    resource_path = doc.get("resource_path", "")

    # Check if any entries still reference this media
    entry_with_ref = await db["entries"].find_one({"media_refs": resource_path})
    if entry_with_ref:
        raise HTTPException(
            409,
            "Cannot delete media: still referenced by one or more entries",
        )

    delete_media_file(doc["user_id"], doc["stored_filename"])
    await db["media"].delete_one({"_id": doc["_id"]})


@router.post("/trim")
async def trim_media(
    current_user: dict = Depends(require_privileged_mode),
    db=Depends(get_db),
):
    return await trim_unreferenced_media_for_user(current_user["id"], db)


class SaveWebpageRequest(BaseModel):
    url: str


@router.post("/save-webpage", response_model=MediaOut, status_code=201)
async def save_webpage(
    payload: SaveWebpageRequest,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Archive a webpage and save it to the user's media directory."""
    from app.utils.webpage_archiver import _validate_url, archive_webpage

    try:
        _validate_url(payload.url)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    user_id = current_user.get("id", "")
    archive_id = uuid.uuid4().hex
    stored_filename = f"{archive_id}.html"
    user_media_dir = os.path.join(MEDIA_PATH, user_id)
    os.makedirs(user_media_dir, exist_ok=True)
    output_path = os.path.join(user_media_dir, stored_filename)

    try:
        meta = await archive_webpage(payload.url, output_path)
    except RuntimeError as exc:
        if os.path.exists(output_path):
            os.remove(output_path)
        raise HTTPException(502, str(exc))
    except ValueError as exc:
        if os.path.exists(output_path):
            os.remove(output_path)
        raise HTTPException(422, str(exc))
    except Exception as exc:
        if os.path.exists(output_path):
            os.remove(output_path)
        raise HTTPException(500, f"Archive failed: {exc}")

    total_size = Path(output_path).stat().st_size

    resource_path = f"http://localhost:8128/media/{user_id}/{stored_filename}"

    media_doc = DB_Media(
        user_id=user_id,
        original_filename=meta["page_title"] or payload.url,
        stored_filename=stored_filename,
        media_type="webpage",
        file_size=total_size,
        resource_path=resource_path,
        created_at=datetime.now(timezone.utc),
        custom_metadata={
            "source_url": payload.url,
            "page_title": meta["page_title"],
            "archived_at": meta["archived_at"],
        },
    ).model_dump()

    await db["media"].insert_one(media_doc)
    return MediaOut.model_validate(media_doc)
