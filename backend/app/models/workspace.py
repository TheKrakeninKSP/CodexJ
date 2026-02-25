from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)


class WorkspaceInDB(BaseModel):
    id: Optional[str] = None
    user_id: str
    name: str
    created_at: datetime = Field(default_factory=utcnow)


class WorkspaceOut(BaseModel):
    id: str
    name: str
    created_at: datetime
