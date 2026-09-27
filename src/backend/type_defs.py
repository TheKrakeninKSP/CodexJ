from enum import Enum

id_type = int
tag_type = str
theme_type = str


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
