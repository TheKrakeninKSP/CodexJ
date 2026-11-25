"""Music for audio media, run as background tasks: song identification for uploads, and
fetching a song's audio from YouTube for song tagging."""

import asyncio
import json
import os
import shutil
import uuid
from datetime import datetime, timezone

from backend.constants import MEDIA_PATH
from backend.database.querying import create_media, get_media_by_id, update_media
from backend.database.structural import MediaModel
from backend.type_defs import MediaStatus, MediaType, id_type
from backend.utils import music_lookup, youtube_audio
from backend.utils.background_tasks import BackgroundTaskRegistry

# Statuses that mean a lookup already ran (or is running) and needn't be repeated
# unless the caller forces it.
SETTLED_LOOKUP_STATUSES = {"completed", "not_found", "pending"}

# Shared by lookups and downloads, so one wait covers both (shutdown, tests).
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


# -- Song tagging: fetch a song's audio from YouTube in the background ---------


def _fail_download(media_id: id_type, message: str) -> None:
    update_media(media_id, status=MediaStatus.failed.value, error_message=message)


async def _finalize_music_download(
    *,
    media_id: id_type,
    query: str,
    output_path: str,
    release_mbid: str | None,
    identify: bool,
) -> None:
    # The cover doesn't depend on the audio, so fetch both at once.
    download = asyncio.to_thread(youtube_audio.download_top_audio, query)
    try:
        if release_mbid:
            audio, cover = await asyncio.gather(
                download,
                asyncio.to_thread(music_lookup.fetch_cover_art_base64, release_mbid),
            )
        else:
            audio, cover = await download, None
    except youtube_audio.YoutubeAudioError as exc:
        _fail_download(media_id, str(exc))
        return
    except Exception as exc:
        _fail_download(media_id, f"Download failed: {exc}")
        return

    try:
        shutil.move(audio["path"], output_path)
    except Exception as exc:
        _fail_download(media_id, f"Could not save the downloaded audio: {exc}")
        return
    finally:
        shutil.rmtree(os.path.dirname(audio["path"]), ignore_errors=True)

    media = get_media_by_id(media_id)
    if media is None:  # deleted while downloading
        os.remove(output_path)
        return
    metadata = json.loads(media.custom_metadata or "{}")
    metadata["youtube"] = {
        "video_id": audio["video_id"],
        "title": audio["title"],
        "channel": audio["channel"],
        "duration": audio["duration"],
    }
    if cover and isinstance(metadata.get("music_info"), dict):
        metadata["music_info"]["cover_art_base64"] = cover
    update_media(
        media_id,
        status=MediaStatus.completed.value,
        error_message=None,
        file_size=os.path.getsize(output_path),
        custom_metadata=json.dumps(metadata),
    )
    if identify:
        start_music_lookup(media_id=media_id, file_path=output_path)


def queue_music_download(
    *,
    entry_id: id_type,
    user_id: id_type,
    title: str,
    artist: str = "",
    album: str = "",
    year: str = "",
    mbid: str | None = None,
    release_mbid: str | None = None,
) -> MediaModel:
    """Create a pending audio media record and fetch the song from YouTube in the background.

    The file name is fixed up front (downloads are always Opus), so the media URL can go
    into the entry immediately. Songs picked from a MusicBrainz search get their metadata
    now and their cover art alongside the download; songs typed by hand are fingerprinted
    once the audio arrives.
    """
    stored_filename = f"{uuid.uuid4().hex}.{youtube_audio.AUDIO_EXT}"
    user_media_dir = os.path.join(MEDIA_PATH, str(user_id))
    os.makedirs(user_media_dir, exist_ok=True)

    label = " - ".join(p for p in (artist, title) if p)
    metadata: dict = {}
    if mbid:
        metadata["music_lookup_status"] = "completed"
        metadata["music_info"] = {
            "title": title,
            "artist": artist,
            "album": album,
            "year": year,
            "mbid": mbid,
        }
    media = MediaModel(
        entry_id=entry_id,
        original_filename=f"{label}.{youtube_audio.AUDIO_EXT}",
        stored_filename=stored_filename,
        media_type=MediaType.audio.value,
        file_size=0,
        status=MediaStatus.pending.value,
        custom_metadata=json.dumps(metadata),
        created_at=datetime.now(timezone.utc),
    )
    create_media(media)
    _lookup_tasks.schedule(
        _finalize_music_download(
            media_id=media.id,
            query=" ".join(p for p in (artist, title) if p),
            output_path=os.path.join(user_media_dir, stored_filename),
            release_mbid=release_mbid if mbid else None,
            identify=not mbid,
        )
    )
    return media
