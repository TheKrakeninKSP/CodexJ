from pydantic import BaseModel, Field

from backend.type_defs import id_type

_MAX_FIELD_LEN = 200


class MusicSearchResult(BaseModel):
    title: str
    artist: str = ""
    album: str = ""
    year: str = ""
    mbid: str = ""
    release_mbid: str | None = None


class MusicDownloadRequest(BaseModel):
    """A song to fetch from YouTube; the MusicBrainz fields are set when it came from search."""

    entry_id: id_type
    title: str = Field(..., min_length=1, max_length=_MAX_FIELD_LEN)
    artist: str = Field("", max_length=_MAX_FIELD_LEN)
    album: str = Field("", max_length=_MAX_FIELD_LEN)
    year: str = Field("", max_length=16)
    mbid: str | None = Field(None, max_length=64)
    release_mbid: str | None = Field(None, max_length=64)
