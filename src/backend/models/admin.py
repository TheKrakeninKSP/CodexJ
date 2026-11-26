from datetime import datetime, timezone

from pydantic import BaseModel, field_validator

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

    @field_validator("created_at", "last_login_at")
    @classmethod
    def _assume_utc(cls, value: datetime | None) -> datetime | None:
        # SQLite drops tzinfo, so stored UTC timestamps come back naive; without an
        # offset in the JSON the browser would parse them as local time.
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class AdminOverviewResponse(BaseModel):
    user_count: int
    total_media_bytes: int
    total_text_bytes: int
    total_bytes: int
    users: list[AdminUserStats]
