from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from backend.constants import (
    ENTRY_NAME_MAX_LENGTH,
    TAG_NAME_MAX_LENGTH,
)
from backend.types import id_type, tag_type
from backend.utils.common import utcnow


class MetadataField(BaseModel):
    key: str
    value: str


class Entry(BaseModel):
    id: id_type
    journal_id: id_type
    tags: list[tag_type] = Field(default_factory=list)
    name: Optional[str] = None
    timezone: Optional[str] = None
    body: Any = Field(default_factory=dict)
    custom_metadata: list[MetadataField] = Field(default_factory=list)
    media_refs: list[str] = Field(default_factory=list)
    date_created: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_from_workspace_id: Optional[id_type] = None
    deleted_from_journal_id: Optional[id_type] = None


class EntryCreate(BaseModel):
    tags: list[tag_type] = Field(..., min_length=0)
    body: Any = Field(default_factory=dict)  # Quill Delta JSON object
    custom_metadata: list[MetadataField] = Field(default_factory=list)
    date_created: Optional[datetime] = None  # defaults to utcnow server-side
    name: Optional[str] = None
    timezone: Optional[str] = Field(None, min_length=1, max_length=64)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[tag_type]) -> list[tag_type]:
        cleaned = [t.strip() for t in v if t.strip()]
        if not cleaned:
            return []
        for tag in cleaned:
            if len(tag) > TAG_NAME_MAX_LENGTH:
                raise ValueError(f"Tag exceeds maximum length of {TAG_NAME_MAX_LENGTH}")
        return cleaned


class EntryUpdate(BaseModel):
    tags: Optional[list[tag_type]] = None
    body: Optional[Any] = None
    name: Optional[str] = Field(None, min_length=1, max_length=ENTRY_NAME_MAX_LENGTH)
    custom_metadata: Optional[list[MetadataField]] = None
    timezone: Optional[str] = Field(None, min_length=1, max_length=64)
    date_created: Optional[datetime] = None

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[list[tag_type]]) -> Optional[list[tag_type]]:
        if v is None:
            return v
        cleaned = [t.strip() for t in v if t.strip()]
        if not cleaned:
            return []
        for tag in cleaned:
            if len(tag) > TAG_NAME_MAX_LENGTH:
                raise ValueError(f"Tag exceeds maximum length of {TAG_NAME_MAX_LENGTH}")
        return cleaned


class EntryMove(BaseModel):
    journal_id: id_type


class EntryRestoreRequest(BaseModel):
    workspace_id: id_type
    journal_id: id_type


class BinCountOut(BaseModel):
    count: int


class EntryOut(BaseModel):
    id: id_type
    journal_id: id_type
    tags: list[tag_type]
    name: Optional[str]
    timezone: Optional[str]
    body: Any
    custom_metadata: list[MetadataField]
    media_refs: list[str]
    date_created: datetime
    updated_at: datetime
