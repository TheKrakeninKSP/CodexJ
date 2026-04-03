"""Data management models - schemas for export/import operations"""

from datetime import datetime
from typing import Any, List, Optional

from app.models.user import DEFAULT_THEME, ThemeName
from pydantic import BaseModel, Field

# Export Schemas


class ExportRequest(BaseModel):
    """Request to export user data to encrypted dump"""

    encryption_key: str = Field(..., min_length=8, max_length=64)


class ExportResponse(BaseModel):
    """Response from export operation"""

    status: str
    filename: str
    message: Optional[str] = None
    timestamp: datetime


# Import from Encrypted Dump Schemas


class ImportEncryptedResponse(BaseModel):
    """Response from encrypted import operation"""

    status: str
    message: str
    workspaces_imported: int = 0
    journals_imported: int = 0
    entries_imported: int = 0
    entry_types_imported: int = 0
    skipped: int = 0
    errors: List[str] = Field(default_factory=list)


# Import from Plaintext Schemas


class PlaintextImportResponse(BaseModel):
    """Response from plaintext import operation"""

    status: str
    message: str
    entry_id: Optional[str] = None
    media_imported: int = 0
    errors: List[str] = Field(default_factory=list)


# Dump Structure Models (internal representation)


class DumpWorkspace(BaseModel):
    """Workspace data in dump format"""

    id: str
    name: str
    created_at: datetime


class DumpJournal(BaseModel):
    """Journal data in dump format"""

    id: str
    workspace_id: str
    name: str
    description: Optional[str] = None
    created_at: datetime


class DumpEntry(BaseModel):
    """Entry data in dump format"""

    id: str
    journal_id: str
    user_id: Optional[str] = None
    type: str
    name: Optional[str] = None
    timezone: Optional[str] = None
    body: Any
    custom_metadata: List[dict]
    media_refs: List[str]
    date_created: datetime
    updated_at: datetime
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_from_workspace_id: Optional[str] = None
    deleted_from_workspace_name: Optional[str] = None
    deleted_from_journal_id: Optional[str] = None
    deleted_from_journal_name: Optional[str] = None


class DumpEntryType(BaseModel):
    """Entry type data in dump format"""

    id: str
    workspace_id: Optional[str] = None
    name: str
    created_at: datetime


class DumpMedia(BaseModel):
    """Media metadata in dump format"""

    id: str
    original_filename: str
    stored_filename: str
    media_type: str
    file_size: int
    created_at: datetime
    custom_metadata: dict
    content_base64: Optional[str] = None
    resource_path: Optional[str] = (
        None  # stored resource URL; used for import URL remapping
    )


class UserDataDump(BaseModel):
    """Complete user data dump structure"""

    version: str = "1.0"
    exported_at: datetime
    user_id: str
    username: Optional[str] = None
    password_hash: Optional[str] = None
    hashkey_hash: Optional[str] = None
    theme: ThemeName = DEFAULT_THEME
    workspaces: List[DumpWorkspace] = Field(default_factory=list)
    journals: List[DumpJournal] = Field(default_factory=list)
    entries: List[DumpEntry] = Field(default_factory=list)
    entry_types: List[DumpEntryType] = Field(default_factory=list)
    media: List[DumpMedia] = Field(default_factory=list)
