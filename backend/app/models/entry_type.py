from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EntryTypeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class EntryTypeInDB(BaseModel):
    id: Optional[str] = None
    user_id: str
    name: str
    created_at: datetime = Field(default_factory=utcnow)


class EntryTypeOut(BaseModel):
    id: str
    name: str
