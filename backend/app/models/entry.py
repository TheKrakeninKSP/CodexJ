from datetime import datetime, timezone
from typing import Optional, Any
from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MetadataField(BaseModel):
    key: str
    value: str


class EntryCreate(BaseModel):
    type: str = Field(..., min_length=1, max_length=100)
    body: Any = Field(default_factory=dict)  # Quill Delta JSON object
    custom_metadata: list[MetadataField] = Field(default_factory=list)
    date_created: Optional[datetime] = None  # defaults to utcnow server-side


class EntryUpdate(BaseModel):
    type: Optional[str] = Field(None, min_length=1, max_length=100)
    body: Optional[Any] = None
    custom_metadata: Optional[list[MetadataField]] = None


class EntryInDB(BaseModel):
    id: Optional[str] = None
    journal_id: str
    type: str
    body: Any = Field(default_factory=dict)
    custom_metadata: list[MetadataField] = Field(default_factory=list)
    media_refs: list[str] = Field(default_factory=list)
    date_created: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class EntryOut(BaseModel):
    id: str
    journal_id: str
    type: str
    body: Any
    custom_metadata: list[MetadataField]
    media_refs: list[str]
    date_created: datetime
    updated_at: datetime
