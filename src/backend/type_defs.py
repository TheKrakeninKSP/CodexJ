import uuid
from enum import Enum

# Entity ids are UUIDv4 strings (36 chars, hyphenated).
id_type = str
tag_type = str
theme_type = str


def new_id() -> id_type:
    return str(uuid.uuid4())


class MediaStatus(str, Enum):
    """Status of media processing. Values match the enum member name."""

    pending = "pending"
    completed = "completed"
    failed = "failed"


class MediaType(str, Enum):
    """Type of media file. Values match the enum member name."""

    image = "image"
    video = "video"
    audio = "audio"
    pdf = "pdf"
    webpage = "webpage"
    other = "other"


class ExportStatus(str, Enum):
    """Status of export processing. Values match the enum member name."""

    pending = "pending"
    completed = "completed"
    failed = "failed"


class ImportStatus(str, Enum):
    """Status of import processing. Values match the enum member name."""

    pending = "pending"
    completed = "completed"
    failed = "failed"
