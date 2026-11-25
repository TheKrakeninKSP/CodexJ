"""Music identification utility — AcoustID fingerprint → MusicBrainz metadata → Cover Art Archive."""

import base64
import io
import json
import os
import subprocess
import sys
from typing import TypedDict

import acoustid
import musicbrainzngs

from backend.constants import FPCALC

_ACOUSTID_API_KEY_ENV = "ACOUSTID_API_KEY"
_DEFAULT_ACOUSTID_API_KEY = "ruQrV0I2Yi"

_COVER_ART_THUMB_SIZE = 250

musicbrainzngs.set_useragent("CodexJ", "0.4", "https://github.com/codexj")


class MusicInfo(TypedDict, total=False):
    title: str
    artist: str
    album: str
    year: str
    mbid: str
    cover_art_base64: str


def _get_acoustid_api_key() -> str | None:
    return os.environ.get(_ACOUSTID_API_KEY_ENV, _DEFAULT_ACOUSTID_API_KEY)


def fingerprint_audio(file_path: str) -> tuple[float, str] | None:
    fpcalc = FPCALC
    if not fpcalc:
        return None
    try:
        # Run fpcalc directly so we can suppress the console window on Windows.
        kwargs: dict = {
            "capture_output": True,
            "timeout": 60,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run([fpcalc, "-json", file_path], **kwargs)
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout.decode("utf-8", errors="replace"))
        duration = float(data["duration"])
        fingerprint = str(data["fingerprint"])
        return (duration, fingerprint)
    except Exception:
        return None


def lookup_acoustid(
    duration: float, fingerprint: str | bytes, api_key: str | None = None
) -> str | None:
    key = api_key or _get_acoustid_api_key()
    if not key:
        return None
    fp = fingerprint.decode() if isinstance(fingerprint, bytes) else fingerprint
    try:
        response = acoustid.lookup(key, fp, duration, meta="recordingids")
        for result in response.get("results", []):
            score = result.get("score", 0)
            if score < 0.5:
                continue
            recordings = result.get("recordings", [])
            if recordings:
                return recordings[0].get("id")
    except Exception:
        return None
    return None


def lookup_musicbrainz(recording_mbid: str) -> dict | None:
    try:
        result = musicbrainzngs.get_recording_by_id(
            recording_mbid,
            includes=["artists", "releases"],
        )
        recording = result.get("recording", {})
        title = recording.get("title", "")
        artists = recording.get("artist-credit", [])
        artist_name = ""
        if artists:
            parts = []
            for credit in artists:
                if isinstance(credit, dict):
                    a = credit.get("artist", {})
                    parts.append(a.get("name", ""))
                    join_phrase = credit.get("joinphrase", "")
                    if join_phrase:
                        parts.append(join_phrase)
                elif isinstance(credit, str):
                    parts.append(credit)
            artist_name = "".join(parts)

        album = ""
        year = ""
        release_mbid = None
        releases = recording.get("release-list", [])
        if releases:
            release = releases[0]
            album = release.get("title", "")
            date = release.get("date", "")
            if date:
                year = date[:4]
            release_mbid = release.get("id")

        return {
            "title": title,
            "artist": artist_name,
            "album": album,
            "year": year,
            "mbid": recording_mbid,
            "release_mbid": release_mbid,
        }
    except Exception:
        return None


def fetch_cover_art_base64(release_mbid: str) -> str | None:
    try:
        from PIL import Image

        image_data = musicbrainzngs.get_image_front(release_mbid, size="250")
        if not image_data:
            return None
        img = Image.open(io.BytesIO(image_data))
        img.thumbnail((_COVER_ART_THUMB_SIZE, _COVER_ART_THUMB_SIZE))
        if img.mode != "RGB":
            img = img.convert("RGB")
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=80)
        return base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception:
        return None


def identify_song(file_path: str, api_key: str | None = None) -> MusicInfo | None:
    fp_result = fingerprint_audio(file_path)
    if fp_result is None:
        return None
    duration, fingerprint = fp_result

    recording_mbid = lookup_acoustid(duration, fingerprint, api_key)
    if recording_mbid is None:
        return None

    mb_data = lookup_musicbrainz(recording_mbid)
    if mb_data is None:
        return None

    info: MusicInfo = {
        "title": mb_data.get("title", ""),
        "artist": mb_data.get("artist", ""),
        "album": mb_data.get("album", ""),
        "year": mb_data.get("year", ""),
        "mbid": mb_data.get("mbid", ""),
    }

    release_mbid = mb_data.get("release_mbid")
    if release_mbid:
        cover = fetch_cover_art_base64(release_mbid)
        if cover:
            info["cover_art_base64"] = cover

    return info


def _artist_credit_phrase(credits: list) -> str:
    parts: list[str] = []
    for credit in credits or []:
        if isinstance(credit, dict):
            parts.append(credit.get("artist", {}).get("name", "") or credit.get("name", ""))
            parts.append(credit.get("joinphrase", ""))
        elif isinstance(credit, str):
            parts.append(credit)
    return "".join(parts)


def search_recordings(
    title: str, artist: str | None = None, limit: int = 10
) -> list[dict]:
    """MusicBrainz recording search, for tagging a song without an audio file.

    Searching the title and artist as separate fields ranks the original recording far
    above the covers a plain free-text query surfaces. Returns up to `limit` distinct
    songs as dicts: title, artist, album, year, mbid, release_mbid. Raises on
    network/API errors so the caller can report them.
    """
    # Over-fetch: many hits are duplicate recordings of one song that get collapsed below.
    fetch = min(100, limit * 4)
    if artist:
        result = musicbrainzngs.search_recordings(
            recording=title, artist=artist, limit=fetch
        )
    else:
        result = musicbrainzngs.search_recordings(query=title, limit=fetch)
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for rec in result.get("recording-list", []):
        title = rec.get("title", "")
        artist = rec.get("artist-credit-phrase") or _artist_credit_phrase(
            rec.get("artist-credit", [])
        )
        # MusicBrainz returns many near-identical recordings (live/remaster/compilation
        # duplicates) - collapse on title + artist, keeping the best-scored one.
        key = (title.casefold(), artist.casefold())
        if key in seen:
            continue
        seen.add(key)

        releases = rec.get("release-list", [])
        # Prefer an official album release over singles/compilations when there is one.
        release = next(
            (
                r
                for r in releases
                if r.get("status") == "Official"
                and r.get("release-group", {}).get("primary-type") == "Album"
            ),
            releases[0] if releases else None,
        )
        date = (release or {}).get("date", "")
        out.append(
            {
                "title": title,
                "artist": artist,
                "album": (release or {}).get("title", ""),
                "year": date[:4] if date else "",
                "mbid": rec.get("id", ""),
                "release_mbid": (release or {}).get("id"),
            }
        )
        if len(out) >= limit:
            break
    return out
