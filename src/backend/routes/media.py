from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from backend.database.querying import (
    delete_media_by_id,
    entry_references_media,
    get_entry_by_id,
    get_media_by_id,
    get_media_by_user_id,
    media_belongs_to_user,
)
from backend.database.structural import UserModel
from backend.models.media import MediaOut
from backend.type_defs import MediaType, id_type
from backend.utils.auth import get_current_user, require_privileged_mode
from backend.utils.media import (
    build_media_out,
    build_media_url,
    delete_media_file,
    save_media_to_user_directory,
)

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
    "audio/opus",
    "audio/ogg",
    "application/pdf",
}


@router.post("/upload", response_model=MediaOut, status_code=201)
async def upload_media(
    entry_id: id_type = Form(...),
    file: UploadFile = File(...),
    user: UserModel = Depends(get_current_user),
):
    entry = get_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(404, "Entry not found")

    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(415, f"Unsupported media type: {file.content_type}")

    if file.content_type.startswith("image"):
        media_type = MediaType.image
    elif file.content_type.startswith("video"):
        media_type = MediaType.video
    elif file.content_type.startswith("audio"):
        media_type = MediaType.audio
    elif file.content_type == "application/pdf":
        media_type = MediaType.pdf
    else:
        raise HTTPException(415, f"Unsupported media type: {file.content_type}")

    try:
        result = await save_media_to_user_directory(
            user_id=user.id,
            entry_id=entry_id,
            media_type=media_type,
            file=file,
        )
        status = result.get("status", False)
        media = result.get("media")
    except Exception as exc:
        raise HTTPException(500, f"Upload failed: {exc}")

    if not status or not media:
        raise HTTPException(500, "Upload failed")

    # Music identification is not started automatically on upload; clients request
    # it via POST /media/{media_id}/identify-music (see routes/music.py).
    return MediaOut.model_validate(media)


@router.delete("/{media_id}", status_code=204)
async def delete_media(
    media_id: id_type,
    user: UserModel = Depends(get_current_user),
):
    media = get_media_by_id(media_id)
    if not media or not media_belongs_to_user(media_id, user.id):
        raise HTTPException(404, "Media not found")

    # Referential integrity check works for both regular files and webpage
    # archive directories, since entries reference media by resource URL.
    resource_path = build_media_url(user.id, media.stored_filename)

    # Check if any entries still reference this media
    if entry_references_media(resource_path):
        raise HTTPException(
            409,
            "Cannot delete media: still referenced by one or more entries",
        )

    delete_media_file(user.id, media.stored_filename)
    if not delete_media_by_id(media.id):
        raise HTTPException(404, "Media not found")


@router.post("/trim")
async def trim_media(
    current_user: UserModel = Depends(get_current_user),
    _=Depends(require_privileged_mode),
):
    deleted_count = 0
    scanned_count = 0
    for media in get_media_by_user_id(current_user.id):
        scanned_count += 1
        if entry_references_media(
            build_media_url(current_user.id, media.stored_filename)
        ):
            continue
        delete_media_file(current_user.id, media.stored_filename)
        print(f"Deleting unreferenced media: {media.original_filename}")
        if delete_media_by_id(media.id):
            deleted_count += 1
    return {
        "status": "success",
        "deleted_count": deleted_count,
        "scanned_count": scanned_count,
        "deleted_media_count": deleted_count,
        "scanned_media_count": scanned_count,
        # Tags are global (not per-workspace) and are never pruned by trim.
        "deleted_entry_type_count": 0,
        "scanned_entry_type_count": 0,
    }


@router.get("/{media_id}", response_model=MediaOut)
async def get_media(
    media_id: id_type,
    user: UserModel = Depends(get_current_user),
):
    media = get_media_by_id(media_id)
    if not media or not media_belongs_to_user(media_id, user.id):
        raise HTTPException(404, "Media not found")
    return build_media_out(media, user.id)
