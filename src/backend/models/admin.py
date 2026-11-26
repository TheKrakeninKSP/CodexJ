from datetime import datetime

from pydantic import BaseModel

from backend.type_defs import id_type


class AdminUserStats(BaseModel):
    id: id_type
    username: str
    is_admin: bool
    created_at: datetime
    last_login_at: datetime | None
    entry_count: int
    media_files: int
    media_bytes: int  # on-disk size of media/<user_id>/, orphans included
    text_bytes: int  # entry body/metadata/tags + saved versions, in the DB
    total_bytes: int


class AdminOverviewResponse(BaseModel):
    user_count: int
    total_media_bytes: int
    total_text_bytes: int
    total_bytes: int
    users: list[AdminUserStats]
