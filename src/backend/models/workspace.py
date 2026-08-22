from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from backend.constants import WORKSPACE_NAME_MAX_LENGTH
from backend.types import id_type
from backend.utils.common import utcnow


class Workspace(BaseModel):
    id: id_type
    user_id: id_type
    name: str
    created_at: datetime = Field(default_factory=utcnow)


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=WORKSPACE_NAME_MAX_LENGTH)


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(
        None, min_length=1, max_length=WORKSPACE_NAME_MAX_LENGTH
    )


class WorkspaceOut(BaseModel):
    id: id_type
    name: str
    created_at: datetime
