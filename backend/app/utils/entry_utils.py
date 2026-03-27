from typing import Any


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
            for key in ["image", "video", "audio"]:
                if key not in insert:
                    continue
                media_url = _extract_embed_url(insert[key])
                if media_url:
                    media_refs.append(media_url)
                    break

    return media_refs
