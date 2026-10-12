import os

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.constants import MEDIA_PATH
from backend.database.querying import (
    get_media_by_id,
    media_belongs_to_user,
)
from backend.database.structural import UserModel
from backend.models.media import MediaOut
from backend.type_defs import id_type
from backend.utils.auth import get_current_user
from backend.utils.media import build_media_out
from backend.utils.music_media import (
    SETTLED_LOOKUP_STATUSES,
    get_lookup_status,
    start_music_lookup,
)

router = APIRouter(prefix="/media", tags=["media"])


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
