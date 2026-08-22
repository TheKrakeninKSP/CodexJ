from datetime import datetime

from pydantic import BaseModel, Field

from backend.types import MediaStatus, MediaType, id_type
from backend.utils.common import utcnow


class Media(BaseModel):
    id: id_type
    user_id: id_type
    entry_id: id_type
    original_filename: str
    stored_filename: str
    media_type: MediaType
    file_size: int
    resource_path: str
    status: MediaStatus
    custom_metadata: dict = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class MediaOut(BaseModel):
    id: id_type
    original_filename: str
    stored_filename: str
    media_type: MediaType
    file_size: int
    resource_path: str
    status: MediaStatus
    custom_metadata: dict = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
