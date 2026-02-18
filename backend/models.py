from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class JournalCreate(BaseModel):
    title: str
    description: Optional[str] = None


class Journal(BaseModel):
    id: Optional[str] = None
    title: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EntryCreate(BaseModel):
    journal_id: str
    body_markdown: str
    entry_type: Optional[str] = "note"
    custom_fields: Optional[Dict[str, Any]] = None


class Entry(BaseModel):
    id: Optional[str] = None
    journal_id: str
    body_markdown: str
    entry_type: Optional[str] = "note"
    media_ids: Optional[List[str]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
