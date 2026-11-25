import asyncio
import os

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.constants import MEDIA_PATH
from backend.database.querying import (
    get_entry_by_id,
    get_media_by_id,
    media_belongs_to_user,
)
from backend.database.structural import UserModel
from backend.models.media import MediaOut
from backend.models.music import MusicDownloadRequest, MusicSearchResult
from backend.type_defs import id_type
from backend.utils import music_lookup, youtube_audio
from backend.utils.auth import assert_journal_access, get_current_user
from backend.utils.media import build_media_out
from backend.utils.music_media import (
    SETTLED_LOOKUP_STATUSES,
    get_lookup_status,
    queue_music_download,
    start_music_lookup,
)

router = APIRouter(prefix="/media", tags=["media"])
search_router = APIRouter(prefix="/music", tags=["music"])

_MAX_QUERY_LEN = 200


@search_router.get("/search", response_model=list[MusicSearchResult])
async def search_music(
    q: str = Query(..., min_length=1, max_length=_MAX_QUERY_LEN),
    artist: str | None = Query(None, max_length=_MAX_QUERY_LEN),
    limit: int = Query(10, ge=1, le=25),
    current_user: UserModel = Depends(get_current_user),
):
    """Search MusicBrainz by song title (+ optional artist), for tagging a song with no audio file."""
    try:
        return await asyncio.to_thread(
            music_lookup.search_recordings,
            q.strip(),
            (artist or "").strip() or None,
            limit,
        )
    except Exception:
        raise HTTPException(502, "Music search is unavailable right now")


@search_router.post("/download", response_model=MediaOut, status_code=202)
async def download_music(
    body: MusicDownloadRequest,
    current_user: UserModel = Depends(get_current_user),
):
    """Queue a download of the song's audio from the top YouTube result.

    Returns the pending audio media straight away; poll GET /media/{id} until its status
    is completed (or failed, with error_message set).
    """
    entry = get_entry_by_id(body.entry_id)
    if not entry:
        raise HTTPException(404, "Entry not found")
    assert_journal_access(entry.journal_id, current_user.id)

    # Fail fast on a missing prerequisite rather than queueing a doomed download.
    if not youtube_audio.find_ffmpeg():
        raise HTTPException(
            503, "ffmpeg was not found - install it or place it in deps/ to download audio"
        )

    media = queue_music_download(
        entry_id=body.entry_id,
        user_id=current_user.id,
        title=body.title.strip(),
        artist=body.artist.strip(),
        album=body.album,
        year=body.year,
        mbid=body.mbid,
        release_mbid=body.release_mbid,
    )
    return build_media_out(media, current_user.id)


@router.post("/{media_id}/identify-music", response_model=MediaOut)
async def identify_music(
    media_id: id_type,
    force: bool = Query(False),
    current_user: UserModel = Depends(get_current_user),
):
    media = get_media_by_id(media_id)
    if not media or not media_belongs_to_user(media_id, current_user.id):
        raise HTTPException(404, "Media not found")
    if media.media_type != "audio":
        raise HTTPException(
            422, "Music identification is only available for audio media"
        )

    if (
        not force
        and get_lookup_status(media.custom_metadata) in SETTLED_LOOKUP_STATUSES
    ):
        return build_media_out(media, current_user.id)

    file_path = os.path.join(MEDIA_PATH, str(current_user.id), media.stored_filename)
    if not os.path.isfile(file_path):
        raise HTTPException(404, "Audio file not found on disk")

    start_music_lookup(media_id=media_id, file_path=file_path)

    updated = get_media_by_id(media_id)
    return build_media_out(updated or media, current_user.id)
