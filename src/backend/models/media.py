from datetime import datetime

from pydantic import BaseModel, Field

from backend.types import MediaStatus, MediaType, id_type
from backend.utils.common import utcnow


class Media(BaseModel):
    entry_id: id_type
    filename: str
    media_type: MediaType
    file_size: int
    resource_path: str
    status: MediaStatus
    error_message: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class MediaOut(BaseModel):
    filename: str
    media_type: MediaType
    file_size: int
    status: MediaStatus
    error_message: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
