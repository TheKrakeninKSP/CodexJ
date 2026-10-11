import re
from typing import Any

# Entry links are stored as Quill `link` attributes: "/entries/<id>", optionally with
# the app's own origin. Links to other sites are never touched.
_ENTRY_LINK_RE = re.compile(
    r"^((?:https?://(?:localhost|127\.0\.0\.1)(?::\d+)?)?/entries/)([^/?#]+)(.*)$"
)


def remap_entry_links(body: Any, id_map: dict) -> Any:
    """Rewrite links to other entries using `id_map` (old entry id -> new entry id).

    Links to entries that aren't in the map are left as they are.
    """
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


def _extract_embed_url(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict):
        candidate = value.get("src") or value.get("url")
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def extract_media_refs(body: Any) -> list[str]:
    """
    Extract media references (image/video URLs) from a Quill Delta body.

    Args:
        body: Quill Delta object with structure {"ops": [{"insert": ...}, ...]}

    Returns:
        List of media resource paths found in the body
    """
    media_refs = []

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
