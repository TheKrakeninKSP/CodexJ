"""Fetch a song's audio from YouTube with yt-dlp, for tagging music without an audio file.

Equivalent to `yt-dlp -x --audio-format opus "ytsearch1:<query>"`: search YouTube, take
the top result, and extract just its audio track. YouTube's best audio stream is almost
always Opus already, so this is a stream copy, not a re-encode - and fixing the format
lets callers know the final file name (and so its URL) before the download finishes.

Needs ffmpeg + ffprobe (for -x) and deno (for YouTube's JS challenges). Both are taken
from the bundled helper binaries (deps/ from source, or inside the desktop build) when
build.py fetched them, otherwise from PATH.
"""

import os
import shutil
import tempfile
from typing import TypedDict

import yt_dlp
from yt_dlp.utils import DownloadError, match_filter_func

from backend.constants import DENO, FFMPEG

# Guard against the top hit being a 10-hour loop or a full-album upload.
MAX_DURATION_SECONDS = 20 * 60
MAX_FILESIZE_BYTES = 100 * 1024 * 1024
AUDIO_EXT = "opus"


class YoutubeAudioError(Exception):
    """A user-presentable reason the download failed."""


class YoutubeAudio(TypedDict):
    path: str  # temp file; caller moves it into place
    ext: str
    video_id: str
    title: str
    channel: str
    duration: int | None


def find_ffmpeg() -> str | None:
    """Directory containing ffmpeg/ffprobe: the bundled copy first, then PATH."""
    if os.path.isfile(FFMPEG):
        return os.path.dirname(FFMPEG)
    found = shutil.which("ffmpeg")
    return os.path.dirname(found) if found else None


def find_deno() -> str | None:
    """The bundled deno, if present. (Without it yt-dlp searches PATH itself.)"""
    return str(DENO) if os.path.isfile(DENO) else None


def _ydl_options(out_dir: str, ffmpeg_dir: str) -> dict:
    return {
        "format": "bestaudio[acodec=opus]/bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"),
        "ffmpeg_location": ffmpeg_dir,
        # -x --audio-format opus (copies the stream when the source is already Opus)
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": AUDIO_EXT}],
        "max_filesize": MAX_FILESIZE_BYTES,
        "match_filter": match_filter_func(f"duration < {MAX_DURATION_SECONDS}"),
        # Point yt-dlp at the bundled deno; {} means "find deno on PATH" (its default).
        "js_runtimes": {"deno": {"path": deno} if (deno := find_deno()) else {}},
    }


def download_top_audio(query: str) -> YoutubeAudio:
    """Download the audio of the top YouTube search result for `query`.

    Blocking (run it in a thread). On success the file lives in a fresh temp dir that
    the caller owns - move the file out, then remove `os.path.dirname(result["path"])`.
    """
    ffmpeg_dir = find_ffmpeg()
    if not ffmpeg_dir:
        raise YoutubeAudioError(
            "ffmpeg was not found - install it or place it in deps/ to download audio"
        )

    out_dir = tempfile.mkdtemp(prefix="codexj-ytdlp-")
    try:
        with yt_dlp.YoutubeDL(_ydl_options(out_dir, ffmpeg_dir)) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=True)
    except DownloadError as exc:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise YoutubeAudioError(f"YouTube download failed: {_short_error(exc)}") from exc
    except Exception:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise

    entries = (info or {}).get("entries") or []
    if not entries:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise YoutubeAudioError("No YouTube results for that song")
    entry = entries[0]

    downloads = entry.get("requested_downloads") or []
    path = downloads[0].get("filepath") if downloads else None
    if not path or not os.path.isfile(path):
        shutil.rmtree(out_dir, ignore_errors=True)
        # yt-dlp skips (rather than fails) entries rejected by match_filter/max_filesize.
        raise YoutubeAudioError(
            f"The top YouTube result ({entry.get('title') or 'unknown'}) was too long "
            "or too large to download"
        )

    return {
        "path": path,
        "ext": os.path.splitext(path)[1].lstrip(".").lower(),
        "video_id": entry.get("id", ""),
        "title": entry.get("title", ""),
        "channel": entry.get("channel") or entry.get("uploader") or "",
        "duration": entry.get("duration"),
    }


def _short_error(exc: Exception) -> str:
    msg = str(exc).removeprefix("ERROR: ").strip()
    return msg.splitlines()[0][:300] if msg else "unknown error"
