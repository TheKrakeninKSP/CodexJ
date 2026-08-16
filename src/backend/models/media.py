from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


MediaStatus = Literal["pending", "completed", "failed"]


class MediaOut(BaseModel):
    original_filename: str
    media_type: str
    file_size: int
    resource_path: str
    status: MediaStatus = "completed"
    error_message: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    custom_metadata: dict = Field(default_factory=dict)


class DB_Media(BaseModel):
    user_id: str
    original_filename: str
    stored_filename: str
    media_type: str
    file_size: int
    resource_path: str
    status: MediaStatus = "completed"
    error_message: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    custom_metadata: dict = Field(default_factory=dict)
