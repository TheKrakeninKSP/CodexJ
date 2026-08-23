import asyncio
import json
import os
import uuid
from collections.abc import Coroutine
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from backend.constants import MEDIA_PATH
from backend.database.querying import (
    create_media,
    delete_media_by_id,
    entry_references_media,
    get_entry_by_id,
    get_media_by_id,
    get_media_by_resource_path,
    get_media_by_user_id,
    media_belongs_to_user,
    update_media,
)
from backend.database.structural import MediaModel, UserModel
from backend.models.media import MediaOut
from backend.type_defs import MediaStatus, MediaType, id_type
from backend.utils.auth import get_current_user, require_privileged_mode
from backend.utils.media import (
    delete_media_file,
    save_media_to_user_directory,
)
from backend.utils.music_lookup import identify_song
from backend.utils.webpage_archiver import (
    _validate_url,
    archive_webpage,
    extract_archived_webpage_metadata,
)

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
    entry_id: id_type,
    user_id: id_type,
    stored_filename: str,
    file_size: int,
    source_url: str,
    page_title: str = "",
    archived_at: str | None = None,
    status: MediaStatus = MediaStatus.completed,
    error_message: str | None = None,
):
    resource_path = f"http://localhost:8128/media/{user_id}/{stored_filename}"
    return MediaModel(
        entry_id=entry_id,
        original_filename=page_title or source_url or stored_filename,
        stored_filename=stored_filename,
        media_type="webpage",
        file_size=file_size,
        resource_path=resource_path,
        status=status,
        error_message=error_message,
        created_at=datetime.now(timezone.utc),
        custom_metadata=json.dumps(
            {
                "source_url": source_url,
                "page_title": page_title,
                "archived_at": archived_at,
            }
        ),
    )


def _cleanup_archive_file(output_path: str) -> None:
    if os.path.exists(output_path):
        os.remove(output_path)


def _media_out(media: MediaModel) -> MediaOut:
    media_type = MediaType(media.media_type)
    status = MediaStatus(media.status)
    return MediaOut(
        id=media.id,
        original_filename=media.original_filename,
        stored_filename=media.stored_filename,
        media_type=media_type,
        file_size=media.file_size,
        resource_path=media.resource_path,
        status=status,
        custom_metadata=json.loads(media.custom_metadata or "{}"),
        error_message=media.error_message,
        created_at=media.created_at,
    )


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
    db=None,
    media_id: int,
    file_path: str,
) -> None:

    try:
        info = await asyncio.to_thread(identify_song, file_path)
        if info is None:
            media = get_media_by_id(media_id)
            if media:
                metadata = json.loads(media.custom_metadata or "{}")
                metadata["music_lookup_status"] = "not_found"
                update_media(media_id, custom_metadata=json.dumps(metadata))
            return

        update_fields: dict[str, Any] = {
            "custom_metadata.music_lookup_status": "completed",
            "custom_metadata.music_info": info,
        }
        media = update_media(media_id)
        if media:
            metadata = json.loads(media.custom_metadata or "{}")
            metadata.update(
                {
                    key.removeprefix("custom_metadata."): value
                    for key, value in update_fields.items()
                }
            )
            update_media(media_id, custom_metadata=json.dumps(metadata))
    except Exception:
        media = update_media(media_id)
        if media:
            metadata = json.loads(media.custom_metadata or "{}")
            metadata["music_lookup_status"] = "failed"
            update_media(media_id, custom_metadata=json.dumps(metadata))


async def _finalize_webpage_archive(
    *,
    media_id: int,
    user_id: int,
    source_url: str,
    output_path: str,
    stored_filename: str,
) -> None:

    try:
        meta = await archive_webpage(source_url, output_path)
        total_size = Path(output_path).stat().st_size
        media = update_media(
            media_id,
            original_filename=meta["page_title"] or source_url or stored_filename,
            file_size=total_size,
            status="completed",
            error_message=None,
            custom_metadata=json.dumps(
                {
                    "source_url": source_url,
                    "page_title": meta["page_title"],
                    "archived_at": meta["archived_at"],
                }
            ),
        )
    except (RuntimeError, ValueError) as exc:
        _cleanup_archive_file(output_path)
        update_media(media_id, status="failed", error_message=str(exc), file_size=0)
    except Exception as exc:
        _cleanup_archive_file(output_path)
        update_media(
            media_id,
            status="failed",
            error_message=f"Archive failed: {exc}",
            file_size=0,
        )


@router.post("/upload", response_model=MediaOut, status_code=201)
async def upload_media(
    entry_id: int,
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
        media_type = MediaType.document
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
        file_path = result.get("file_path")
    except Exception as exc:
        raise HTTPException(500, f"Upload failed: {exc}")

    if not status or not media:
        raise HTTPException(500, "Upload failed")

    # Schedule background music identification for audio uploads
    if media_type == MediaType.audio and file_path:
        media_id = media.get("id")
        if media_id:
            metadata = media.get("custom_metadata", {})
            metadata["music_lookup_status"] = "pending"
            update_media(media_id, custom_metadata=json.dumps(metadata))
            media["custom_metadata"] = metadata
            _schedule_music_lookup_task(
                _finalize_music_lookup(
                    media_id=media_id,
                    file_path=file_path,
                )
            )

    return MediaOut.model_validate(media)


@router.delete("/{media_id}", status_code=204)
async def delete_media(
    media_id: str,
    current_user: UserModel = Depends(get_current_user),
):
    try:
        media_id_int = int(media_id)
    except ValueError as exc:
        raise HTTPException(400, "Invalid media ID") from exc

    doc = get_media_by_id(media_id_int)
    if not doc or not media_belongs_to_user(media_id_int, current_user.id):
        raise HTTPException(404, "Media not found")

    # Use the stored resource_path for referential integrity check (works for
    # both regular files and webpage archive directories).
    resource_path = doc.resource_path

    # Check if any entries still reference this media
    if entry_references_media(resource_path):
        raise HTTPException(
            409,
            "Cannot delete media: still referenced by one or more entries",
        )

    delete_media_file(str(current_user.id), doc.stored_filename)
    if not delete_media_by_id(doc.id):
        raise HTTPException(404, "Media not found")


@router.post("/trim")
async def trim_media(
    current_user: UserModel = Depends(require_privileged_mode),
):
    deleted_count = 0
    scanned_count = 0
    for media in get_media_by_user_id(current_user.id):
        scanned_count += 1
        if entry_references_media(media.resource_path):
            continue
        delete_media_file(str(media.user_id), media.stored_filename)
        if delete_media_by_id(media.id):
            deleted_count += 1
    return {
        "status": "success",
        "deleted_count": deleted_count,
        "scanned_count": scanned_count,
    }


@router.post("/identify-music", response_model=MediaOut)
async def identify_music(
    resource_path: str = Query(..., min_length=1),
    force: bool = Query(False),
    current_user: UserModel = Depends(get_current_user),
):
    doc = get_media_by_resource_path(resource_path, current_user.id)
    if not doc:
        raise HTTPException(404, "Media not found")
    if doc.media_type != "audio":
        raise HTTPException(
            422, "Music identification is only available for audio media"
        )

    # If already identified (or in progress / not found) and not forced, return early.
    skip_statuses = {"completed", "not_found", "pending"}
    if (
        not force
        and json.loads(doc.custom_metadata or "{}").get("music_lookup_status")
        in skip_statuses
    ):
        return _media_out(doc)

    stored_filename = doc.stored_filename
    user_id = current_user.id
    file_path = os.path.join(MEDIA_PATH, str(user_id), stored_filename)
    if not os.path.isfile(file_path):
        raise HTTPException(404, "Audio file not found on disk")

    media_id = doc.id
    metadata = json.loads(doc.custom_metadata or "{}")
    metadata["music_lookup_status"] = "pending"
    update_media(media_id, user_id, custom_metadata=json.dumps(metadata))
    _schedule_music_lookup_task(
        _finalize_music_lookup(
            media_id=media_id,
            user_id=user_id,
            file_path=file_path,
        )
    )

    updated = get_media_by_id(media_id)
    return _media_out(updated or doc)


class SaveWebpageRequest(BaseModel):
    url: str


@router.get("/status", response_model=MediaOut)
async def get_media_status(
    resource_path: str = Query(..., min_length=1),
    current_user: UserModel = Depends(get_current_user),
):
    doc = get_media_by_resource_path(resource_path)
    if not doc or not media_belongs_to_user(doc.id, current_user.id):
        raise HTTPException(404, "Media not found")
    return _media_out(doc)


@router.post("/save-webpage", response_model=MediaOut, status_code=201)
async def save_webpage(
    entry_id: int,
    payload: SaveWebpageRequest,
    current_user: UserModel = Depends(get_current_user),
):
    """Archive a webpage and save it to the user's media directory."""

    entry = get_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(404, "Entry not found")

    try:
        _validate_url(payload.url)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    user_id = current_user.id
    archive_id = uuid.uuid4().hex
    stored_filename = f"{archive_id}.html"
    user_media_dir = os.path.join(MEDIA_PATH, str(user_id))
    os.makedirs(user_media_dir, exist_ok=True)
    output_path = os.path.join(user_media_dir, stored_filename)

    media_doc = _build_webpage_media_document(
        entry_id=entry_id,
        user_id=user_id,
        stored_filename=stored_filename,
        file_size=0,
        source_url=payload.url,
        status=MediaStatus.pending,
    )

    create_media(media_doc)
    _schedule_webpage_archive_task(
        _finalize_webpage_archive(
            media_id=media_doc.id,
            user_id=user_id,
            source_url=payload.url,
            output_path=output_path,
            stored_filename=stored_filename,
        )
    )
    return _media_out(media_doc)


@router.post("/upload-webpage-archive", response_model=MediaOut, status_code=201)
async def upload_webpage_archive(
    entry_id: int,
    file: UploadFile = File(...),
    current_user: UserModel = Depends(get_current_user),
):
    entry = get_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(404, "Entry not found")

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

    metadata = extract_archived_webpage_metadata(raw_html)

    user_id = current_user.id
    stored_filename = f"{uuid.uuid4().hex}.html"
    user_media_dir = os.path.join(MEDIA_PATH, str(user_id))
    os.makedirs(user_media_dir, exist_ok=True)
    output_path = os.path.join(user_media_dir, stored_filename)

    try:
        with open(output_path, "wb") as archive_file:
            archive_file.write(contents)
    except Exception as exc:
        raise HTTPException(500, f"Archive import failed: {exc}")

    media_doc = _build_webpage_media_document(
        entry_id=entry_id,
        user_id=user_id,
        stored_filename=stored_filename,
        file_size=len(contents),
        source_url=metadata["source_url"],
        page_title=metadata["page_title"],
        archived_at=metadata["archived_at"],
    )

    create_media(media_doc)
    return _media_out(media_doc)
