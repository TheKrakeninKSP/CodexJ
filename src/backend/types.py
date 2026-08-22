id_type = int
tag_type = str
theme_type = str

from enum import Enum

MediaStatus = Enum("MediaStatus", ["pending", "completed", "failed"])
MediaType = Enum("MediaType", ["image", "video", "audio", "document", "other"])

ExportStatus = Enum("ExportStatus", ["pending", "completed", "failed"])
ImportStatus = Enum("ImportStatus", ["pending", "completed", "failed"])
