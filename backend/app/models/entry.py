from datetime import datetime, timezone
from typing import Any, Optional

from app.constants import ENTRY_NAME_MAX_LENGTH, ENTRY_TYPE_NAME_MAX_LENGTH
from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MetadataField(BaseModel):
    key: str
    value: str


class EntryCreate(BaseModel):
    type: str = Field(..., min_length=1, max_length=ENTRY_TYPE_NAME_MAX_LENGTH)
    body: Any = Field(default_factory=dict)  # Quill Delta JSON object
    custom_metadata: list[MetadataField] = Field(default_factory=list)
    date_created: Optional[datetime] = None  # defaults to utcnow server-side
    name: Optional[str] = ""


class EntryUpdate(BaseModel):
    type: Optional[str] = Field(
        None, min_length=1, max_length=ENTRY_TYPE_NAME_MAX_LENGTH
    )
    body: Optional[Any] = None
    name: Optional[str] = Field(None, min_length=1, max_length=ENTRY_NAME_MAX_LENGTH)
    custom_metadata: Optional[list[MetadataField]] = None


class DB_Entry(BaseModel):
    journal_id: str
    type: str = Field(..., min_length=1, max_length=ENTRY_TYPE_NAME_MAX_LENGTH)
    name: str = Field(..., min_length=1, max_length=ENTRY_NAME_MAX_LENGTH)
    body: Any = Field(default_factory=dict)
    custom_metadata: list[MetadataField] = Field(default_factory=list)
    media_refs: list[str] = Field(default_factory=list)
    date_created: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class EntryOut(BaseModel):
    id: str
    journal_id: str
    type: str
    name: str
    body: Any
    custom_metadata: list[MetadataField]
    media_refs: list[str]
    date_created: datetime
    updated_at: datetime
