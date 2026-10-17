import re
from html.parser import HTMLParser
from typing import Any

# Entry links stored as href="/entries/<id>" or with the app's own origin.
_ENTRY_LINK_RE = re.compile(
    r"^((?:https?://(?:localhost|127\.0\.0\.1)(?::\d+)?)?/entries/)([^/?#]+)(.*)$"
)


# ── HTML helpers ───────────────────────────────────────────────────────────────

class _MediaRefHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.refs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        if tag == "img":
            src = attr_dict.get("src")
            if src:
                self.refs.append(src)
        elif tag == "video":
            src = attr_dict.get("src")
            if src:
                self.refs.append(src)
        elif tag == "audio":
            src = attr_dict.get("src")
            if src:
                self.refs.append(src)
        elif tag == "iframe":
            src = attr_dict.get("src")
            if src:
                self.refs.append(src)
        elif tag == "div":
            data_type = attr_dict.get("data-type")
            if data_type in ("pdf", "webpage"):
                src = attr_dict.get("data-src")
                if src:
                    self.refs.append(src)


class _EntryLinkHTMLParser(HTMLParser):
    """Collects <a href="..."> values that look like internal entry links."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr_dict = dict(attrs)
        href = attr_dict.get("href", "")
        if href and _ENTRY_LINK_RE.match(href):
            self.links.append(href)


def _remap_html_links(html: str, id_map: dict) -> str:
    """Rewrite /entries/<old-id> hrefs in the HTML using id_map."""

    def _replace(m: re.Match) -> str:
        prefix, old_id, suffix = m.group(1), m.group(2), m.group(3)
        new_id = id_map.get(old_id, old_id)
        return f"{prefix}{new_id}{suffix}"

    # Match href="..." containing an entry link
    def _href_replace(m: re.Match) -> str:
        href = m.group(1)
        link_match = _ENTRY_LINK_RE.match(href)
        if link_match and link_match.group(2) in id_map:
            new_href = _replace(link_match)
            return f'href="{new_href}"'
        return m.group(0)

    return re.sub(r'href="([^"]*)"', _href_replace, html)


# ── Delta helpers (legacy format) ─────────────────────────────────────────────

def _extract_embed_url(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict):
        candidate = value.get("src") or value.get("url")
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


# ── Public API ─────────────────────────────────────────────────────────────────

def remap_entry_links(body: Any, id_map: dict) -> Any:
    """Rewrite links to other entries using id_map (old entry id -> new entry id).

    Handles both HTML strings (new format) and Quill Delta dicts (legacy format).
    """
    if isinstance(body, str):
        return _remap_html_links(body, id_map)

    # Legacy Quill Delta
    if not isinstance(body, dict) or not isinstance(body.get("ops"), list):
        return body

    new_ops = []
    for op in body["ops"]:
        attributes = op.get("attributes") if isinstance(op, dict) else None
        link = attributes.get("link") if isinstance(attributes, dict) else None
        match = _ENTRY_LINK_RE.match(link) if isinstance(link, str) else None
        if match and match.group(2) in id_map:
            prefix, old_id, suffix = match.groups()
            op = {
                **op,
                "attributes": {**attributes, "link": f"{prefix}{id_map[old_id]}{suffix}"},
            }
        new_ops.append(op)
    return {**body, "ops": new_ops}


def extract_media_refs(body: Any) -> list[str]:
    """Extract media URLs from an entry body.

    Handles both HTML strings (new format) and Quill Delta dicts (legacy format).
    """
    if isinstance(body, str):
        parser = _MediaRefHTMLParser()
        parser.feed(body)
        return parser.refs

    # Legacy Quill Delta
    media_refs: list[str] = []
    if not isinstance(body, dict):
        return media_refs

    ops = body.get("ops", [])
    if not isinstance(ops, list):
        return media_refs

    for op in ops:
        if not isinstance(op, dict):
            continue
        insert = op.get("insert")
        if isinstance(insert, dict):
            for key in ["image", "video", "audio", "webpage", "pdf"]:
                if key not in insert:
                    continue
                media_url = _extract_embed_url(insert[key])
                if media_url:
                    media_refs.append(media_url)
                    break

    return media_refs
