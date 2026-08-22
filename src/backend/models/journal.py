from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from backend.constants import JOURNAL_DESCRIPTION_MAX_LENGTH, JOURNAL_NAME_MAX_LENGTH
from backend.types import id_type
from backend.utils.common import utcnow


class Journal(BaseModel):
    id: id_type
    workspace_id: id_type
    name: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class JournalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=JOURNAL_NAME_MAX_LENGTH)
    description: Optional[str] = Field(None, max_length=JOURNAL_DESCRIPTION_MAX_LENGTH)


class JournalUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=JOURNAL_NAME_MAX_LENGTH)
    description: Optional[str] = Field(None, max_length=JOURNAL_DESCRIPTION_MAX_LENGTH)


class JournalMove(BaseModel):
    workspace_id: id_type


class JournalOut(BaseModel):
    id: id_type
    workspace_id: id_type
    name: str
    description: Optional[str] = None
    workspace_name: str
    created_at: datetime
