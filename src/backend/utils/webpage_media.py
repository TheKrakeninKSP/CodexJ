"""Webpage archive media: record creation, background archiving and file import."""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.constants import MEDIA_PATH
from backend.database.querying import create_media, update_media
from backend.database.structural import MediaModel
from backend.type_defs import MediaStatus, id_type
from backend.utils.background_tasks import BackgroundTaskRegistry
from backend.utils.webpage_archiver import archive_webpage

_archive_tasks = BackgroundTaskRegistry()


async def wait_for_webpage_archive_tasks() -> None:
    await _archive_tasks.wait()


def _build_webpage_media_document(
    *,
    entry_id: id_type,
    stored_filename: str,
    file_size: int,
    source_url: str,
    page_title: str = "",
    archived_at: str | None = None,
    status: MediaStatus = MediaStatus.completed,
    error_message: str | None = None,
) -> MediaModel:
    return MediaModel(
        entry_id=entry_id,
        original_filename=page_title or source_url or stored_filename,
        stored_filename=stored_filename,
        media_type="webpage",
        file_size=file_size,
        status=status.value,
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


async def _finalize_webpage_archive(
    *,
    media_id: id_type,
    source_url: str,
    output_path: str,
    stored_filename: str,
) -> None:
    try:
        meta = await archive_webpage(source_url, output_path)
        update_media(
            media_id,
            original_filename=meta["page_title"] or source_url or stored_filename,
            file_size=Path(output_path).stat().st_size,
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


def queue_webpage_archive(
    *, entry_id: id_type, user_id: id_type, url: str
) -> MediaModel:
    """Create a pending webpage media record and archive the page in the background."""
    stored_filename = f"{uuid.uuid4().hex}.html"
    user_media_dir = os.path.join(MEDIA_PATH, str(user_id))
    os.makedirs(user_media_dir, exist_ok=True)
    output_path = os.path.join(user_media_dir, stored_filename)

    media = _build_webpage_media_document(
        entry_id=entry_id,
        stored_filename=stored_filename,
        file_size=0,
        source_url=url,
        status=MediaStatus.pending,
    )
    create_media(media)
    _archive_tasks.schedule(
        _finalize_webpage_archive(
            media_id=media.id,
            source_url=url,
            output_path=output_path,
            stored_filename=stored_filename,
        )
    )
    return media


def save_uploaded_webpage_archive(
    *, entry_id: id_type, user_id: id_type, contents: bytes, metadata: dict[str, str]
) -> MediaModel:
    """Store an already-archived HTML file as webpage media. Raises OSError on write failure."""
    stored_filename = f"{uuid.uuid4().hex}.html"
    user_media_dir = os.path.join(MEDIA_PATH, str(user_id))
    os.makedirs(user_media_dir, exist_ok=True)
    with open(os.path.join(user_media_dir, stored_filename), "wb") as archive_file:
        archive_file.write(contents)

    media = _build_webpage_media_document(
        entry_id=entry_id,
        stored_filename=stored_filename,
        file_size=len(contents),
        source_url=metadata["source_url"],
        page_title=metadata["page_title"],
        archived_at=metadata["archived_at"],
    )
    create_media(media)
    return media
