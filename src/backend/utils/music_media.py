"""Music identification for audio media, run as a background task."""

import asyncio
import json

from backend.database.querying import get_media_by_id, update_media
from backend.type_defs import id_type
from backend.utils import music_lookup
from backend.utils.background_tasks import BackgroundTaskRegistry

# Statuses that mean a lookup already ran (or is running) and needn't be repeated
# unless the caller forces it.
SETTLED_LOOKUP_STATUSES = {"completed", "not_found", "pending"}

_lookup_tasks = BackgroundTaskRegistry()


async def wait_for_music_lookup_tasks() -> None:
    await _lookup_tasks.wait()


def _set_lookup_metadata(media_id: id_type, **fields: object) -> None:
    media = get_media_by_id(media_id)
    if not media:
        return
    metadata = json.loads(media.custom_metadata or "{}")
    metadata.update(fields)
    update_media(media_id, custom_metadata=json.dumps(metadata))


async def _finalize_music_lookup(*, media_id: id_type, file_path: str) -> None:
    try:
        info = await asyncio.to_thread(music_lookup.identify_song, file_path)
        if info is None:
            _set_lookup_metadata(media_id, music_lookup_status="not_found")
        else:
            _set_lookup_metadata(
                media_id, music_lookup_status="completed", music_info=info
            )
    except Exception:
        _set_lookup_metadata(media_id, music_lookup_status="failed")


def get_lookup_status(custom_metadata: str | None) -> str | None:
    return json.loads(custom_metadata or "{}").get("music_lookup_status")


def start_music_lookup(*, media_id: id_type, file_path: str) -> None:
    """Mark the media's lookup as pending and identify the song in the background."""
    _set_lookup_metadata(media_id, music_lookup_status="pending")
    _lookup_tasks.schedule(
        _finalize_music_lookup(media_id=media_id, file_path=file_path)
    )
