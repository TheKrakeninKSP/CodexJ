from datetime import datetime, timezone
from typing import Optional

from app.constants import WORKSPACE_NAME_MAX_LENGTH
from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=WORKSPACE_NAME_MAX_LENGTH)


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(
        None, min_length=1, max_length=WORKSPACE_NAME_MAX_LENGTH
    )


class DB_Workspace(BaseModel):
    user_id: str
    name: str
    created_at: datetime = Field(default_factory=utcnow)


class WorkspaceOut(BaseModel):
    id: str
    name: str
    created_at: datetime
