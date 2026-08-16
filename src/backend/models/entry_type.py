from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from backend.constants import ENTRY_TYPE_NAME_MAX_LENGTH


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EntryTypeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=ENTRY_TYPE_NAME_MAX_LENGTH)


class DB_EntryType(BaseModel):
    user_id: str
    workspace_id: str
    name: str
    created_at: datetime = Field(default_factory=utcnow)


class EntryTypeOut(BaseModel):
    id: str
    name: str
    entry_count: int = 0
