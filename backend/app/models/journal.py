from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from backend.app.constants import (
    JOURNAL_DESCRIPTION_MAX_LENGTH,
    JOURNAL_NAME_MAX_LENGTH,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JournalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=JOURNAL_NAME_MAX_LENGTH)
    description: Optional[str] = Field(None, max_length=JOURNAL_DESCRIPTION_MAX_LENGTH)


class JournalUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=JOURNAL_NAME_MAX_LENGTH)
    description: Optional[str] = Field(None, max_length=JOURNAL_DESCRIPTION_MAX_LENGTH)


class JournalInDB(BaseModel):
    id: Optional[str] = None
    workspace_id: str
    name: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class JournalOut(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: Optional[str] = None
    created_at: datetime
