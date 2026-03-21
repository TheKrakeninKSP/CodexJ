from datetime import datetime, timezone

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MediaOut(BaseModel):
    id: str
    user_id: str
    original_filename: str
    stored_filename: str
    media_type: str
    file_size: int
    resource_path: str
    created_at: datetime = Field(default_factory=utcnow)
