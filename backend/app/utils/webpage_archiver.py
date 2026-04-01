"""Webpage archiver utility for CodexJ."""

import asyncio
import os
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Response, async_playwright

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

ASSET_SUBDIR = "_assets"
_PAGE_TIMEOUT = 30.0
_ASSET_TIMEOUT = 10.0
_NETWORK_IDLE_TIMEOUT_MS = 5000

# CSS url() references — skip data: URIs
_RE_CSS_URL = re.compile(
    r"""url\(\s*(['"]?)(?!data:)([^'"\)\s]+)\1\s*\)""",
    re.IGNORECASE,
)
# CSS @import references
_RE_CSS_IMPORT = re.compile(
    r"""@import\s+(?:url\(\s*['"]?|'|")([^'"\)\s]+)""",
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


def _safe_filename(url_path: str, idx: int) -> str:
    """Derive a short, filesystem-safe filename from a URL path segment."""
    clean = urllib.parse.unquote(url_path.split("?", 1)[0])
    base = os.path.basename(clean.rstrip("/")) or f"asset_{idx}"
    safe = re.sub(r"[^A-Za-z0-9._\-]", "_", base)[:80]
    if not safe or safe.startswith("."):
        safe = f"asset_{idx}"
    return safe


def _unique_path(assets_path: Path, filename: str) -> str:
    """Return a filename that does not already exist in assets_path."""
    stem, ext = os.path.splitext(filename)
    candidate = filename
    n = 1
    while (assets_path / candidate).exists():
        candidate = f"{stem}_{n}{ext}"
        n += 1
    return candidate


async def _launch_browser(playwright):
    launch_attempts: list[str] = []

    for channel in ("msedge", "chrome", None):
        try:
            if channel is None:
                return await playwright.chromium.launch(headless=True)
            return await playwright.chromium.launch(channel=channel, headless=True)
        except Exception as exc:
            launch_attempts.append(f"{channel or 'chromium'}: {exc}")

    detail = "; ".join(launch_attempts)
    raise RuntimeError(
        "Unable to launch a compatible Chromium browser. "
        "Install Microsoft Edge or Chrome, or install Playwright Chromium. "
        f"Attempts: {detail}"
    )


async def _ssrf_route_handler(route):
    request_url = str(route.request.url)
    if _is_safe_asset_url(request_url):
        await route.continue_()
        return
    await route.abort()


async def _cache_response_body(
    response: Response, response_cache: dict[str, bytes]
) -> None:
    request = response.request
    if request.method.upper() != "GET":
        return

    request_url = str(request.url)
    response_url = str(response.url)
    if not _is_safe_asset_url(request_url) or not _is_safe_asset_url(response_url):
        return

    try:
        body = await response.body()
    except Exception:
        return

    response_cache[request_url] = body
    response_cache[response_url] = body


async def _render_page(url: str) -> tuple[str, str, int, dict[str, bytes]]:
    response_cache: dict[str, bytes] = {}

    async with async_playwright() as playwright:
        browser = await _launch_browser(playwright)
        context = await browser.new_context(
            service_workers="block",
            viewport={"width": 1440, "height": 2400},
        )
        page = await context.new_page()
        response_tasks: set[asyncio.Task] = set()

        def on_response(response: Response) -> None:
            task = asyncio.create_task(_cache_response_body(response, response_cache))
            response_tasks.add(task)
            task.add_done_callback(response_tasks.discard)

        page.on("response", on_response)
        page.on("dialog", lambda dialog: asyncio.create_task(dialog.dismiss()))

        await context.route("**/*", _ssrf_route_handler)

        try:
            response = await page.goto(
                url,
                wait_until="load",
                timeout=int(_PAGE_TIMEOUT * 1000),
            )
            try:
                await page.wait_for_load_state(
                    "networkidle",
                    timeout=_NETWORK_IDLE_TIMEOUT_MS,
                )
            except PlaywrightError:
                pass

            if response_tasks:
                await asyncio.gather(*list(response_tasks), return_exceptions=True)

            html = await page.content()
            final_url = page.url
            http_status = response.status if response is not None else 200
        except PlaywrightError as exc:
            raise RuntimeError(f"Failed to render page: {exc}")
        finally:
            await context.close()
            await browser.close()

    return html, final_url, http_status, response_cache


async def _download(
    client: httpx.AsyncClient,
    response_cache: dict[str, bytes],
    url: str,
    timeout: float = _ASSET_TIMEOUT,
) -> Optional[bytes]:
    cached = response_cache.get(url)
    if cached is not None:
        return cached

    try:
        resp = await client.get(url, follow_redirects=True, timeout=timeout)
        resp.raise_for_status()
        return resp.content
    except Exception as exc:
        sys.stderr.write(f"[archiver] skipping {url}: {exc}\n")
        return None


def _is_safe_asset_url(abs_url: str) -> bool:
    try:
        parsed = urlparse(abs_url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").lower()
        for prefix in _PRIVATE_HOSTS:
            stripped = prefix.rstrip(".")
            if host == stripped or host.startswith(prefix):
                return False
    except Exception:
        return False
    return True


async def _save_asset(
    client: httpx.AsyncClient,
    response_cache: dict[str, bytes],
    url_map: dict,
    assets_path: Path,
    counter: list,
    asset_ref: str,
    base_url: str,
    process_css: bool = False,
) -> Optional[str]:
    """
    Download one asset, save it under assets_path, and return its relative path
    from the index.html (e.g. "_assets/style.abc.css"). Returns None on failure.
    """
    if not asset_ref or asset_ref.startswith("data:") or asset_ref.startswith("#"):
        return None

    abs_url = urljoin(base_url, asset_ref)
    if not _is_safe_asset_url(abs_url):
        return None

    if abs_url in url_map:
        return url_map[abs_url]

    idx = counter[0]
    counter[0] += 1

    parsed_abs = urlparse(abs_url)
    filename = _safe_filename(parsed_abs.path, idx)
    filename = _unique_path(assets_path, filename)

    content = await _download(client, response_cache, abs_url)
    if content is None:
        return None

    ext_lower = os.path.splitext(filename)[1].lower()
    if process_css and ext_lower == ".css":
        try:
            css_text = content.decode("utf-8", errors="replace")
            css_text = await _rewrite_css(
                client,
                response_cache,
                url_map,
                assets_path,
                counter,
                css_text,
                abs_url,
            )
            (assets_path / filename).write_text(css_text, encoding="utf-8")
        except Exception as exc:
            sys.stderr.write(f"[archiver] CSS rewrite error for {abs_url}: {exc}\n")
            (assets_path / filename).write_bytes(content)
    else:
        (assets_path / filename).write_bytes(content)

    rel_path = f"{ASSET_SUBDIR}/{filename}"
    url_map[abs_url] = rel_path
    return rel_path


async def _rewrite_css(
    client: httpx.AsyncClient,
    response_cache: dict[str, bytes],
    url_map: dict,
    assets_path: Path,
    counter: list,
    css_text: str,
    css_url: str,
) -> str:
    """
    Parse url() and @import references in CSS, download each sub-asset, and
    rewrite paths to point to the local _assets/ directory.
    CSS is saved into _assets/, so sub-assets are referenced by filename alone.
    """
    replacements: dict[str, str] = {}
    refs: list[tuple[str, str]] = []

    for match in _RE_CSS_URL.finditer(css_text):
        refs.append((match.group(0), match.group(2)))
    for match in _RE_CSS_IMPORT.finditer(css_text):
        refs.append((match.group(0), match.group(1)))

    for original, ref in refs:
        if original in replacements:
            continue
        if not ref or ref.startswith("data:") or ref.startswith("#"):
            continue
        rel = await _save_asset(
            client,
            response_cache,
            url_map,
            assets_path,
            counter,
            ref,
            css_url,
            process_css=False,
        )
        if rel:
            # CSS lives in _assets/ — sub-assets are in the same directory,
            # so just use the bare filename (strip "_assets/" prefix).
            asset_filename = rel[len(ASSET_SUBDIR) + 1 :]
            replacements[original] = original.replace(ref, asset_filename, 1)

    for old, new in replacements.items():
        css_text = css_text.replace(old, new, 1)

    return css_text


async def archive_webpage(url: str, dest_dir: str) -> dict:
    """
    Archive a webpage to dest_dir/index.html with assets in dest_dir/_assets/.

    Downloads the HTML page and its immediate linked assets (stylesheets, scripts,
    images). CSS files are processed one level deep: their own url() and @import
    references are also downloaded.

    Args:
        url:      The URL to archive. Must be http/https and not a private address.
        dest_dir: Destination directory (created if it does not exist).

    Returns:
        dict with keys:
            "page_title"  (str) — extracted from <title>
            "archived_at" (str) — ISO 8601 UTC timestamp
            "asset_count" (int) — number of assets downloaded

    Raises:
        ValueError:   URL is invalid or points to a private address.
        RuntimeError: Main page could not be downloaded.
    """
    _validate_url(url)

    dest_path = Path(dest_dir)
    assets_path = dest_path / ASSET_SUBDIR
    assets_path.mkdir(parents=True, exist_ok=True)

    counter = [0]
    url_map: dict[str, str] = {}
    html, final_url, http_status, response_cache = await _render_page(url)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        soup = BeautifulSoup(html, "lxml")

        title_tag = soup.find("title")
        page_title = title_tag.get_text(strip=True) if title_tag else url

        # Remove <base> tags so relative paths stay relative to index.html
        for base_tag in soup.find_all("base"):
            base_tag.decompose()

        # ── <link href> — stylesheets, icons ─────────────────────────────
        for tag in soup.find_all("link"):
            href = str(tag.get("href") or "")
            if not href:
                continue
            rel_raw = tag.get("rel")
            rel_list: list = (
                rel_raw if isinstance(rel_raw, list) else [rel_raw] if rel_raw else []
            )
            is_css = any(str(r).lower() == "stylesheet" for r in rel_list)
            new_href = await _save_asset(
                client,
                response_cache,
                url_map,
                assets_path,
                counter,
                href,
                final_url,
                process_css=is_css,
            )
            if new_href:
                tag["href"] = new_href

        # ── <script src> ─────────────────────────────────────────────────
        for tag in soup.find_all("script", src=True):
            src = str(tag.get("src") or "")
            new_src = await _save_asset(
                client,
                response_cache,
                url_map,
                assets_path,
                counter,
                src,
                final_url,
            )
            if new_src:
                tag["src"] = new_src

        # ── <img src> and srcset ──────────────────────────────────────────
        for tag in soup.find_all("img"):
            src = str(tag.get("src") or "")
            if src:
                new_src = await _save_asset(
                    client,
                    response_cache,
                    url_map,
                    assets_path,
                    counter,
                    src,
                    final_url,
                )
                if new_src:
                    tag["src"] = new_src

            srcset = str(tag.get("srcset") or "")
            if srcset:
                new_parts: list[str] = []
                for part in srcset.split(","):
                    part = part.strip()
                    if not part:
                        continue
                    pieces = part.split(None, 1)
                    asset_ref = pieces[0]
                    descriptor = pieces[1] if len(pieces) > 1 else ""
                    new_u = await _save_asset(
                        client,
                        response_cache,
                        url_map,
                        assets_path,
                        counter,
                        asset_ref,
                        final_url,
                    )
                    new_parts.append(f"{new_u or asset_ref} {descriptor}".strip())
                tag["srcset"] = ", ".join(new_parts)

        # ── <source src> ─────────────────────────────────────────────────
        for tag in soup.find_all("source", src=True):
            src = str(tag.get("src") or "")
            new_src = await _save_asset(
                client,
                response_cache,
                url_map,
                assets_path,
                counter,
                src,
                final_url,
            )
            if new_src:
                tag["src"] = new_src

        # ── Inline <style> blocks ─────────────────────────────────────────
        for style_tag in soup.find_all("style"):
            css_text = style_tag.string or ""
            if css_text.strip():
                processed = await _rewrite_css(
                    client,
                    response_cache,
                    url_map,
                    assets_path,
                    counter,
                    css_text,
                    final_url,
                )
                style_tag.string = processed

        # ── Inline style= attributes ──────────────────────────────────────
        for tag in soup.find_all(style=True):
            inline = str(tag.get("style") or "")
            if inline.strip():
                processed_inline = await _rewrite_css(
                    client,
                    response_cache,
                    url_map,
                    assets_path,
                    counter,
                    inline,
                    final_url,
                )
                tag["style"] = processed_inline

        (dest_path / "index.html").write_text(str(soup), encoding="utf-8")

    return {
        "page_title": page_title,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "asset_count": counter[0],
        "http_status": http_status,
    }
