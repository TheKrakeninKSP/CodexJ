from datetime import datetime, timezone
from typing import Any, Optional

from app.constants import ENTRY_NAME_MAX_LENGTH, ENTRY_TYPE_NAME_MAX_LENGTH
from pydantic import BaseModel, Field, field_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MetadataField(BaseModel):
    key: str
    value: str


class EntryCreate(BaseModel):
    tags: list[str] = Field(..., min_length=1)
    body: Any = Field(default_factory=dict)  # Quill Delta JSON object
    custom_metadata: list[MetadataField] = Field(default_factory=list)
    date_created: Optional[datetime] = None  # defaults to utcnow server-side
    name: Optional[str] = None
    timezone: Optional[str] = Field(None, min_length=1, max_length=64)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        cleaned = [t.strip() for t in v if t.strip()]
        if not cleaned:
            raise ValueError("At least one tag is required")
        for tag in cleaned:
            if len(tag) > ENTRY_TYPE_NAME_MAX_LENGTH:
                raise ValueError(
                    f"Tag exceeds maximum length of {ENTRY_TYPE_NAME_MAX_LENGTH}"
                )
        return cleaned


class EntryUpdate(BaseModel):
    tags: Optional[list[str]] = None
    body: Optional[Any] = None
    name: Optional[str] = Field(None, min_length=1, max_length=ENTRY_NAME_MAX_LENGTH)
    custom_metadata: Optional[list[MetadataField]] = None
    timezone: Optional[str] = Field(None, min_length=1, max_length=64)
    date_created: Optional[datetime] = None

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return v
        cleaned = [t.strip() for t in v if t.strip()]
        if not cleaned:
            raise ValueError("At least one tag is required")
        for tag in cleaned:
            if len(tag) > ENTRY_TYPE_NAME_MAX_LENGTH:
                raise ValueError(
                    f"Tag exceeds maximum length of {ENTRY_TYPE_NAME_MAX_LENGTH}"
                )
        return cleaned


class EntryMove(BaseModel):
    journal_id: str


class EntryRestoreRequest(BaseModel):
    workspace_id: str
    journal_id: str


class BinCountOut(BaseModel):
    count: int


class DB_Entry(BaseModel):
    user_id: Optional[str] = None
    journal_id: str
    tags: list[str] = Field(default_factory=list)
    name: Optional[str] = None
    timezone: Optional[str] = None
    body: Any = Field(default_factory=dict)
    custom_metadata: list[MetadataField] = Field(default_factory=list)
    media_refs: list[str] = Field(default_factory=list)
    date_created: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_from_workspace_id: Optional[str] = None
    deleted_from_workspace_name: Optional[str] = None
    deleted_from_journal_id: Optional[str] = None
    deleted_from_journal_name: Optional[str] = None


class EntryOut(BaseModel):
    id: str
    journal_id: str
    tags: list[str]
    name: Optional[str]
    timezone: Optional[str]
    body: Any
    custom_metadata: list[MetadataField]
    media_refs: list[str]
    date_created: datetime
    updated_at: datetime
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_from_workspace_id: Optional[str] = None
    deleted_from_workspace_name: Optional[str] = None
    deleted_from_journal_id: Optional[str] = None
    deleted_from_journal_name: Optional[str] = None
