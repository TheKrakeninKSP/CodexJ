from enum import Enum

id_type = int
tag_type = str
theme_type = str

# Functional Enum with (name, value) pairs so .value matches the member name string —
# these values are stored in the DB and serialized directly in API responses.
MediaStatus = Enum("MediaStatus", [(s, s) for s in ["pending", "completed", "failed"]])
MediaType = Enum(
    "MediaType",
    [(s, s) for s in ["image", "video", "audio", "pdf", "webpage", "other"]],
)

ExportStatus = Enum("ExportStatus", [(s, s) for s in ["pending", "completed", "failed"]])
ImportStatus = Enum("ImportStatus", [(s, s) for s in ["pending", "completed", "failed"]])
