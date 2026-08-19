from datetime import datetime

from pydantic import BaseModel, Field

from backend.constants import TAG_NAME_MAX_LENGTH
from backend.types import id_type, tag_type
from backend.utils.common import utcnow


class Tag(BaseModel):
    id: id_type
    name: tag_type = Field(..., min_length=1, max_length=TAG_NAME_MAX_LENGTH)
    created_at: datetime = Field(default_factory=utcnow)


class TagCreate(BaseModel):
    name: tag_type = Field(..., min_length=1, max_length=TAG_NAME_MAX_LENGTH)


class TagOut(BaseModel):
    name: tag_type
