from typing import Any


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
            # Check for image embed
            if "image" in insert and isinstance(insert["image"], str):
                media_refs.append(insert["image"])
            # Check for video embed
            elif "video" in insert and isinstance(insert["video"], str):
                media_refs.append(insert["video"])
            # Check for audio embed
            elif "audio" in insert and isinstance(insert["audio"], str):
                media_refs.append(insert["audio"])

    return media_refs
