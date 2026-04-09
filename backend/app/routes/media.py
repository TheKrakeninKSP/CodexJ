import asyncio
import os
import uuid
from collections.abc import Coroutine
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.constants import MEDIA_PATH
from app.database import get_db
from app.models.media import DB_Media, MediaOut, MediaStatus
from app.utils.auth import get_current_user, require_privileged_mode
from app.utils.media import (
    delete_media_file,
    save_media_to_user_directory,
    trim_unused_resources_for_user,
)
from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

router = APIRouter(prefix="/media", tags=["media"])

_webpage_archive_tasks: set[asyncio.Task[None]] = set()
_music_lookup_tasks: set[asyncio.Task[None]] = set()

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
ALLOWED_WEBPAGE_ARCHIVE_MIME = {
    "text/html",
    "application/xhtml+xml",
    "application/octet-stream",
    "",
}


def _build_webpage_media_document(
    *,
    user_id: str,
    stored_filename: str,
    file_size: int,
    source_url: str,
    page_title: str = "",
    archived_at: str | None = None,
    status: MediaStatus = "completed",
    error_message: str | None = None,
):
    resource_path = f"http://localhost:8128/media/{user_id}/{stored_filename}"
    return DB_Media(
        user_id=user_id,
        original_filename=page_title or source_url or stored_filename,
        stored_filename=stored_filename,
        media_type="webpage",
        file_size=file_size,
        resource_path=resource_path,
        status=status,
        error_message=error_message,
        created_at=datetime.now(timezone.utc),
        custom_metadata={
            "source_url": source_url,
            "page_title": page_title,
            "archived_at": archived_at,
        },
    ).model_dump()


def _cleanup_archive_file(output_path: str) -> None:
    if os.path.exists(output_path):
        os.remove(output_path)


def _schedule_webpage_archive_task(coro: Coroutine[Any, Any, None]) -> None:
    task = asyncio.create_task(coro)
    _webpage_archive_tasks.add(task)
    task.add_done_callback(_webpage_archive_tasks.discard)


async def wait_for_webpage_archive_tasks() -> None:
    if not _webpage_archive_tasks:
        return
    await asyncio.gather(*list(_webpage_archive_tasks), return_exceptions=True)


def _schedule_music_lookup_task(coro: Coroutine[Any, Any, None]) -> None:
    task = asyncio.create_task(coro)
    _music_lookup_tasks.add(task)
    task.add_done_callback(_music_lookup_tasks.discard)


async def wait_for_music_lookup_tasks() -> None:
    if not _music_lookup_tasks:
        return
    await asyncio.gather(*list(_music_lookup_tasks), return_exceptions=True)


async def _finalize_music_lookup(
    *,
    db,
    media_id: ObjectId,
    user_id: str,
    file_path: str,
) -> None:
    from app.utils.music_lookup import identify_song

    try:
        info = await asyncio.to_thread(identify_song, file_path)
        if info is None:
            await db["media"].update_one(
                {"_id": media_id, "user_id": user_id},
                {"$set": {"custom_metadata.music_lookup_status": "not_found"}},
            )
            return

        update_fields: dict[str, Any] = {
            "custom_metadata.music_lookup_status": "completed",
            "custom_metadata.music_info": info,
        }
        await db["media"].update_one(
            {"_id": media_id, "user_id": user_id},
            {"$set": update_fields},
        )
    except Exception:
        await db["media"].update_one(
            {"_id": media_id, "user_id": user_id},
            {"$set": {"custom_metadata.music_lookup_status": "failed"}},
        )


async def _finalize_webpage_archive(
    *,
    db,
    media_id: ObjectId,
    user_id: str,
    source_url: str,
    output_path: str,
    stored_filename: str,
) -> None:
    from app.utils.webpage_archiver import archive_webpage

    try:
        meta = await archive_webpage(source_url, output_path)
        total_size = Path(output_path).stat().st_size
        await db["media"].update_one(
            {"_id": media_id, "user_id": user_id},
            {
                "$set": {
                    "original_filename": meta["page_title"]
                    or source_url
                    or stored_filename,
                    "file_size": total_size,
                    "status": "completed",
                    "error_message": None,
                    "custom_metadata.source_url": source_url,
                    "custom_metadata.page_title": meta["page_title"],
                    "custom_metadata.archived_at": meta["archived_at"],
                }
            },
        )
    except (RuntimeError, ValueError) as exc:
        _cleanup_archive_file(output_path)
        await db["media"].update_one(
            {"_id": media_id, "user_id": user_id},
            {
                "$set": {
                    "status": "failed",
                    "error_message": str(exc),
                    "file_size": 0,
                }
            },
        )
    except Exception as exc:
        _cleanup_archive_file(output_path)
        await db["media"].update_one(
            {"_id": media_id, "user_id": user_id},
            {
                "$set": {
                    "status": "failed",
                    "error_message": f"Archive failed: {exc}",
                    "file_size": 0,
                }
            },
        )


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
    elif file.content_type == "application/pdf":
        resource_type = "pdf"
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
        file_path = result.get("file_path")
    except Exception as exc:
        raise HTTPException(500, f"Upload failed: {exc}")

    if not status or not media:
        raise HTTPException(500, "Upload failed")

    # Schedule background music identification for audio uploads
    if resource_type == "audio" and file_path:
        media_id = media.get("_id")
        if media_id:
            await db["media"].update_one(
                {"_id": media_id},
                {"$set": {"custom_metadata.music_lookup_status": "pending"}},
            )
            media["custom_metadata"]["music_lookup_status"] = "pending"
            _schedule_music_lookup_task(
                _finalize_music_lookup(
                    db=db,
                    media_id=media_id,
                    user_id=current_user.get("id", ""),
                    file_path=file_path,
                )
            )

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
    return await trim_unused_resources_for_user(current_user["id"], db)


@router.post("/identify-music", response_model=MediaOut)
async def identify_music(
    resource_path: str = Query(..., min_length=1),
    force: bool = Query(False),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    doc = await db["media"].find_one(
        {"resource_path": resource_path, "user_id": current_user["id"]}
    )
    if not doc:
        raise HTTPException(404, "Media not found")
    if doc.get("media_type") != "audio":
        raise HTTPException(
            422, "Music identification is only available for audio media"
        )

    # If already identified (or in progress / not found) and not forced, return early.
    skip_statuses = {"completed", "not_found", "pending"}
    if (
        not force
        and doc.get("custom_metadata", {}).get("music_lookup_status") in skip_statuses
    ):
        return MediaOut.model_validate(doc)

    stored_filename = doc.get("stored_filename", "")
    user_id = current_user["id"]
    file_path = os.path.join(MEDIA_PATH, user_id, stored_filename)
    if not os.path.isfile(file_path):
        raise HTTPException(404, "Audio file not found on disk")

    media_id = doc["_id"]
    await db["media"].update_one(
        {"_id": media_id},
        {"$set": {"custom_metadata.music_lookup_status": "pending"}},
    )
    _schedule_music_lookup_task(
        _finalize_music_lookup(
            db=db,
            media_id=media_id,
            user_id=user_id,
            file_path=file_path,
        )
    )

    updated = await db["media"].find_one({"_id": media_id})
    return MediaOut.model_validate(updated)


class SaveWebpageRequest(BaseModel):
    url: str


@router.get("/status", response_model=MediaOut)
async def get_media_status(
    resource_path: str = Query(..., min_length=1),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    doc = await db["media"].find_one(
        {"resource_path": resource_path, "user_id": current_user["id"]}
    )
    if not doc:
        raise HTTPException(404, "Media not found")
    return MediaOut.model_validate(doc)


@router.post("/save-webpage", response_model=MediaOut, status_code=201)
async def save_webpage(
    payload: SaveWebpageRequest,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Archive a webpage and save it to the user's media directory."""
    from app.utils.webpage_archiver import _validate_url

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

    media_doc = _build_webpage_media_document(
        user_id=user_id,
        stored_filename=stored_filename,
        file_size=0,
        source_url=payload.url,
        status="pending",
    )

    result = await db["media"].insert_one(media_doc)
    _schedule_webpage_archive_task(
        _finalize_webpage_archive(
            db=db,
            media_id=result.inserted_id,
            user_id=user_id,
            source_url=payload.url,
            output_path=output_path,
            stored_filename=stored_filename,
        )
    )
    return MediaOut.model_validate(media_doc)


@router.post("/upload-webpage-archive", response_model=MediaOut, status_code=201)
async def upload_webpage_archive(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    content_type = (file.content_type or "").lower()
    filename = file.filename or "archive.html"
    _, extension = os.path.splitext(filename)
    if content_type not in ALLOWED_WEBPAGE_ARCHIVE_MIME and extension.lower() not in {
        ".html",
        ".htm",
    }:
        raise HTTPException(415, "Unsupported archive type. Upload a saved HTML file.")

    contents = await file.read()
    if not contents:
        raise HTTPException(400, "Uploaded archive is empty")

    raw_html = contents.decode("utf-8", errors="replace")
    if "<html" not in raw_html.lower():
        raise HTTPException(422, "Uploaded file is not a valid HTML archive")

    from app.utils.webpage_archiver import extract_archived_webpage_metadata

    metadata = extract_archived_webpage_metadata(raw_html)

    user_id = current_user.get("id", "")
    stored_filename = f"{uuid.uuid4().hex}.html"
    user_media_dir = os.path.join(MEDIA_PATH, user_id)
    os.makedirs(user_media_dir, exist_ok=True)
    output_path = os.path.join(user_media_dir, stored_filename)

    try:
        with open(output_path, "wb") as archive_file:
            archive_file.write(contents)
    except Exception as exc:
        raise HTTPException(500, f"Archive import failed: {exc}")

    media_doc = _build_webpage_media_document(
        user_id=user_id,
        stored_filename=stored_filename,
        file_size=len(contents),
        source_url=metadata["source_url"],
        page_title=metadata["page_title"],
        archived_at=metadata["archived_at"],
    )

    await db["media"].insert_one(media_doc)
    return MediaOut.model_validate(media_doc)
