"""Webpage archiver utility for CodexJ — delegates to SingleFile CLI."""

import asyncio
import html as _html
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

from app.constants import SINGLEFILE_EXE

# ---------------------------------------------------------------------------
# Browser discovery
# ---------------------------------------------------------------------------

_BROWSER_CANDIDATES: tuple[str, ...] = (
    # Windows – Chrome
    os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    # Windows – Edge
    os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
    # Linux
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
    # macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)


def _find_browser() -> str | None:
    """Return the path to the first Chrome/Chromium/Edge binary found, or None."""
    # Allow explicit override via environment variable
    override = os.environ.get("CODEXJ_BROWSER_PATH", "").strip()
    if override and os.path.isfile(override):
        return override
    for candidate in _BROWSER_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate
    return None


# Hosts / prefixes that must not be fetched (SSRF prevention)
_PRIVATE_HOSTS: tuple[str, ...] = (
    "localhost",
    "0.0.0.0",
    "127.",
    "10.",
    "192.168.",
    "169.254.",
    "172.16.",
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
    "::1",
)

_ARCHIVE_TIMEOUT = 60.0
_RE_TITLE = re.compile(r"<title[^>]*>([^<]*)</title>", re.IGNORECASE)
_RE_SINGLEFILE_URL = re.compile(
    r"Page saved with SingleFile\s+url:\s*(.+?)\s+saved date:",
    re.IGNORECASE | re.DOTALL,
)
_RE_SINGLEFILE_SAVED_DATE = re.compile(
    r"saved date:\s*(.+?)\s*-->",
    re.IGNORECASE | re.DOTALL,
)
_RE_CANONICAL_URL = re.compile(
    r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_RE_OG_URL = re.compile(
    r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)


def _validate_url(url: str) -> None:
    """Raise ValueError if the URL is not a safe public http/https address."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL must use http or https, got: {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    for prefix in _PRIVATE_HOSTS:
        stripped = prefix.rstrip(".")
        if host == stripped or host.startswith(prefix):
            raise ValueError(f"URL points to a private or reserved address: {host!r}")


def _normalize_public_url(value: str | None) -> str:
    candidate = (value or "").strip()
    if not candidate:
        return ""
    try:
        _validate_url(candidate)
    except ValueError:
        return ""
    return candidate


def _extract_title(raw_html: str, fallback: str = "") -> str:
    match = _RE_TITLE.search(raw_html)
    if not match:
        return fallback
    return _html.unescape(match.group(1)).strip() or fallback


def _extract_source_url(raw_html: str) -> str:
    for pattern in (_RE_SINGLEFILE_URL, _RE_CANONICAL_URL, _RE_OG_URL):
        match = pattern.search(raw_html)
        if not match:
            continue
        candidate = _normalize_public_url(match.group(1))
        if candidate:
            return candidate
    return ""


def _extract_archived_at(raw_html: str) -> str:
    match = _RE_SINGLEFILE_SAVED_DATE.search(raw_html)
    if match:
        raw_value = re.sub(r"\s*\([^)]*\)\s*$", "", match.group(1).strip())
        try:
            parsed = datetime.strptime(raw_value, "%a %b %d %Y %H:%M:%S GMT%z")
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
        try:
            parsed = parsedate_to_datetime(raw_value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc).isoformat()


def extract_archived_webpage_metadata(raw_html: str) -> dict[str, str]:
    source_url = _extract_source_url(raw_html)
    page_title = _extract_title(raw_html, source_url or "Imported webpage archive")
    return {
        "page_title": page_title,
        "source_url": source_url,
        "archived_at": _extract_archived_at(raw_html),
    }


async def archive_webpage(url: str, output_path: str) -> dict:
    """
    Archive a webpage to a single self-contained HTML file using SingleFile CLI.

    Args:
        url:         The URL to archive. Must be http/https and not a private address.
        output_path: Destination file path (e.g. /media/user_id/archive_id.html).
                     The parent directory is created if it does not exist.

    Returns:
        dict with keys:
            "page_title"  (str) -- extracted from <title>
            "archived_at" (str) -- ISO 8601 UTC timestamp

    Raises:
        ValueError:   URL is invalid or points to a private address.
        RuntimeError: SingleFile CLI failed or timed out.
    """
    _validate_url(url)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        SINGLEFILE_EXE,
        url,
        output_path,
        "--browser-headless=true",
        "--browser-arg=--no-sandbox",
        "--browser-arg=--disable-gpu",
        "--browser-wait-until=load",
    ]
    browser = _find_browser()
    if browser:
        cmd.append(f"--browser-executable-path={browser}")

    def _run_singlefile() -> tuple[int, str]:
        """Run SingleFile CLI synchronously (called via asyncio.to_thread)."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=_ARCHIVE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"SingleFile timed out after {_ARCHIVE_TIMEOUT}s")
        return result.returncode, result.stderr.decode(errors="replace")

    returncode, stderr_text = await asyncio.to_thread(_run_singlefile)

    if returncode != 0:
        raise RuntimeError(
            f"SingleFile failed (exit {returncode}): {stderr_text[:500]}"
        )

    out = Path(output_path)
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError(
            "SingleFile exited successfully but produced no output. "
            "Check that a supported browser (Chrome/Edge/Chromium) is installed."
        )

    raw = out.read_text(encoding="utf-8", errors="replace")
    parsed = extract_archived_webpage_metadata(raw)
    page_title = parsed["page_title"] or url

    return {
        "page_title": page_title,
        "archived_at": datetime.now(timezone.utc).isoformat(),
    }
