"""Music identification utility — AcoustID fingerprint → MusicBrainz metadata → Cover Art Archive."""

import base64
import io
import os
import sys
from typing import TypedDict

import acoustid
import musicbrainzngs

_ACOUSTID_API_KEY_ENV = "ACOUSTID_API_KEY"
_DEFAULT_ACOUSTID_API_KEY = "bBGgsa4P2d"  # registered for CodexJ

_COVER_ART_THUMB_SIZE = 250

musicbrainzngs.set_useragent("CodexJ", "0.4", "https://github.com/codexj")


class MusicInfo(TypedDict, total=False):
    title: str
    artist: str
    album: str
    year: str
    mbid: str
    cover_art_base64: str


def _get_acoustid_api_key() -> str:
    return os.environ.get(_ACOUSTID_API_KEY_ENV, _DEFAULT_ACOUSTID_API_KEY)


def _resolve_fpcalc_path() -> str | None:
    exe_name = "fpcalc.exe" if sys.platform == "win32" else "fpcalc"
    if getattr(sys, "frozen", False):
        bundled = os.path.join(getattr(sys, "_MEIPASS", ""), exe_name)
        if os.path.isfile(bundled):
            return bundled
    vendor_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "vendor")
    )
    vendor_path = os.path.join(vendor_dir, exe_name)
    if os.path.isfile(vendor_path):
        return vendor_path
    return None


def fingerprint_audio(file_path: str) -> tuple[float, str] | None:
    fpcalc = _resolve_fpcalc_path()
    try:
        if fpcalc:
            duration, fingerprint = acoustid.fingerprint_file(
                file_path, force_fpcalc=fpcalc
            )
        else:
            duration, fingerprint = acoustid.fingerprint_file(file_path)
        return (duration, fingerprint)
    except Exception:
        return None


def lookup_acoustid(
    duration: float, fingerprint: str, api_key: str | None = None
) -> str | None:
    key = api_key or _get_acoustid_api_key()
    try:
        results = acoustid.lookup(key, fingerprint, duration, meta="recordingids")
        for result in results:
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
