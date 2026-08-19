from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field, model_validator

from backend.constants import APP_VERSION
from backend.models.entry import Entry
from backend.models.journal import Journal
from backend.models.media import Media
from backend.models.tag import Tag
from backend.models.user import User
from backend.models.workspace import Workspace
from backend.types import ExportStatus, ImportStatus
from backend.utils.common import utcnow

# Export Schemas


class ExportResponse(BaseModel):
    """Response from export operation"""

    status: ExportStatus
    filename: str
    message: Optional[str] = None
    timestamp: datetime


# Import from Encrypted Dump Schemas


class ImportEncryptedResponse(BaseModel):
    """Response from encrypted import operation"""

    status: ImportStatus
    message: str
    workspaces_imported: int = 0
    journals_imported: int = 0
    entries_imported: int = 0
    tags_imported: int = 0
    errors: List[str] = Field(default_factory=list)


# Dump Structure Models (internal representation)


class DumpWorkspace(Workspace):
    """Workspace data in dump format"""


class DumpJournal(Journal):
    """Journal data in dump format"""


class DumpEntry(Entry):
    """Entry data in dump format"""


class DumpTag(Tag):
    """Tag data in dump format"""


class DumpMedia(Media):
    """Media metadata in dump format"""

    content_base64: Optional[str] = None


class DumpUser(User):
    """Complete user data dump structure"""


class DumpMeta(BaseModel):
    """Metadata for the dump"""

    version: str = APP_VERSION
    exported_at: datetime = Field(default_factory=utcnow)
    user_id: str
    username: Optional[str] = None
    workspaces_count: int = 0
    journals_count: int = 0
    entries_count: int = 0
    tags_count: int = 0
    media_count: int = 0
