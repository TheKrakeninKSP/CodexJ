"""
One-time migration: convert all Quill Delta entry bodies to TipTap HTML.

Run from the repo root:
    python scripts/migrate_bodies_to_html.py [--db PATH] [--dry-run]

The body column stores each value as json.dumps(body), so:
  - Old Delta:  '{"ops": [...]}'
  - New HTML:   '"<p>...</p>"'   (json.dumps of a plain string)

After conversion the frontend's deltaToHtml shim is no longer needed for those
entries; they load as HTML strings directly.
"""

import argparse
import html as html_module
import json
import sqlite3
import sys
from pathlib import Path


# ── Delta → HTML converter (mirrors src/frontend/src/utils/deltaToHtml.ts) ────

def _esc(text: str) -> str:
    return html_module.escape(str(text))


def _extract_str(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("src") or value.get("url") or "")
    return ""


def _wrap_inline(text: str, attrs: dict) -> str:
    if not text:
        return ""
    result = _esc(text)
    if attrs.get("link"):
        href = _esc(str(attrs["link"]))
        result = f'<a href="{href}">{result}</a>'
    if attrs.get("code"):
        result = f"<code>{result}</code>"
    if attrs.get("bold"):
        result = f"<strong>{result}</strong>"
    if attrs.get("italic"):
        result = f"<em>{result}</em>"
    if attrs.get("underline"):
        result = f"<u>{result}</u>"
    if attrs.get("strike"):
        result = f"<s>{result}</s>"
    return result


def _open_block(attrs: dict) -> tuple[str, str]:
    h = attrs.get("header")
    if h == 1:
        return "<h1>", "</h1>"
    if h == 2:
        return "<h2>", "</h2>"
    if h == 3:
        return "<h3>", "</h3>"
    if attrs.get("blockquote"):
        return "<blockquote><p>", "</p></blockquote>"
    if attrs.get("code-block"):
        return "<pre><code>", "</code></pre>"
    if attrs.get("list") in ("ordered", "bullet"):
        return "<li>", "</li>"
    return "<p>", "</p>"


def _render_embed(key: str, value: object) -> str:
    if key == "image":
        src = _extract_str(value)
        return f'<img src="{_esc(src)}">' if src else ""

    if key == "video":
        src = _extract_str(value)
        return (
            f'<iframe src="{_esc(src)}" frameborder="0" allowfullscreen="true"></iframe>'
            if src
            else ""
        )

    if key == "audio":
        if isinstance(value, str):
            return f'<audio src="{_esc(value)}" controls preload="metadata"></audio>'
        if isinstance(value, dict):
            src = str(value.get("src") or value.get("url") or "")
            if not src:
                return ""
            parts = [f'src="{_esc(src)}" controls preload="metadata"']
            if value.get("original_filename"):
                parts.append(f'data-original-filename="{_esc(value["original_filename"])}"')
            if value.get("media_id"):
                parts.append(f'data-media-id="{_esc(value["media_id"])}"')
            return f'<audio {" ".join(parts)}></audio>'
        return ""

    if key == "pdf":
        src = _extract_str(value)
        return f'<div data-type="pdf" data-src="{_esc(src)}"></div>' if src else ""

    if key == "webpage":
        if not isinstance(value, dict):
            return ""
        src = str(value.get("src") or "")
        source_url = str(value.get("source_url") or src)
        title = str(value.get("title") or "")
        media_id = str(value.get("media_id") or "")
        status = value.get("status", "completed")
        if status not in ("pending", "failed"):
            status = "completed"
        error_msg = str(value.get("error_message") or "")
        attr_parts = [
            f'data-type="webpage"',
            f'data-src="{_esc(src)}"',
            f'data-source-url="{_esc(source_url)}"',
            f'data-title="{_esc(title)}"',
            f'data-status="{status}"',
            f'data-error-message="{_esc(error_msg)}"',
        ]
        if media_id:
            attr_parts.append(f'data-media-id="{_esc(media_id)}"')
        return f'<div {" ".join(attr_parts)}></div>'

    return ""


def delta_to_html(body: object) -> str:
    """Convert a Quill Delta dict to TipTap HTML. Returns '' for unrecognised input."""
    if isinstance(body, str):
        return body  # already HTML
    if not isinstance(body, dict) or not isinstance(body.get("ops"), list):
        return ""

    ops: list = body["ops"]
    parts: list[str] = []
    inline_buffer = ""
    current_list_type: str | None = None

    def flush_list() -> None:
        nonlocal current_list_type
        if current_list_type is None:
            return
        parts.append("</ol>" if current_list_type == "ordered" else "</ul>")
        current_list_type = None

    def ensure_list(list_type: str) -> None:
        nonlocal current_list_type
        if current_list_type == list_type:
            return
        if current_list_type is not None:
            flush_list()
        parts.append("<ol>" if list_type == "ordered" else "<ul>")
        current_list_type = list_type

    def flush_inline_as_block(attrs: dict) -> None:
        nonlocal inline_buffer
        content = inline_buffer
        inline_buffer = ""
        list_type = attrs.get("list")
        if list_type in ("ordered", "bullet"):
            ensure_list(list_type)
        else:
            flush_list()
        open_, close = _open_block(attrs)
        parts.append(f"{open_}{content or ('' if list_type else '<br>')}{close}")

    for op in ops:
        if not isinstance(op, dict):
            continue
        insert = op.get("insert")
        attrs: dict = op.get("attributes") or {}

        # Block embed
        if isinstance(insert, dict):
            for key in ("image", "video", "audio", "pdf", "webpage"):
                if key in insert:
                    if inline_buffer:
                        flush_list()
                        parts.append(f"<p>{inline_buffer}</p>")
                        inline_buffer = ""
                    flush_list()
                    embed_html = _render_embed(key, insert[key])
                    if embed_html:
                        parts.append(embed_html)
                    break
            continue

        if not isinstance(insert, str):
            continue

        segments = insert.split("\n")
        for i, segment in enumerate(segments):
            if i < len(segments) - 1:
                inline_buffer += _wrap_inline(segment, attrs)
                if i == len(segments) - 2:
                    flush_inline_as_block(attrs)
                else:
                    flush_list()
                    parts.append(f"<p>{inline_buffer or '<br>'}</p>")
                    inline_buffer = ""
            else:
                inline_buffer += _wrap_inline(segment, attrs)

    if inline_buffer:
        flush_list()
        parts.append(f"<p>{inline_buffer}</p>")
    flush_list()

    return "".join(parts)


# ── media_refs re-extraction for HTML ──────────────────────────────────────────

from html.parser import HTMLParser  # noqa: E402

class _MediaRefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.refs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = dict(attrs)
        if tag in ("img", "video", "audio", "iframe"):
            if src := d.get("src"):
                self.refs.append(src)
        elif tag == "div":
            if d.get("data-type") in ("pdf", "webpage"):
                if src := d.get("data-src"):
                    self.refs.append(src)


def _extract_media_refs_html(html: str) -> list[str]:
    p = _MediaRefParser()
    p.feed(html)
    return p.refs


# ── Migration ──────────────────────────────────────────────────────────────────

def migrate(db_path: Path, dry_run: bool) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT id, body, media_refs FROM entry")
    rows = cur.fetchall()

    converted = skipped = errors = 0

    for entry_id, body_raw, media_refs_raw in rows:
        # Deserialise the stored JSON string
        try:
            body = json.loads(body_raw) if body_raw else {}
        except (json.JSONDecodeError, TypeError):
            print(f"  SKIP {entry_id}: body is not valid JSON")
            skipped += 1
            continue

        # Skip entries that are already HTML strings
        if isinstance(body, str):
            skipped += 1
            continue

        # Skip entries that don't look like a Delta
        if not isinstance(body, dict) or "ops" not in body:
            print(f"  SKIP {entry_id}: unrecognised body shape")
            skipped += 1
            continue

        try:
            html = delta_to_html(body)
        except Exception as exc:
            print(f"  ERROR {entry_id}: {exc}")
            errors += 1
            continue

        new_media_refs = _extract_media_refs_html(html)

        if not dry_run:
            cur.execute(
                "UPDATE entry SET body = ?, media_refs = ? WHERE id = ?",
                (json.dumps(html), json.dumps(new_media_refs), entry_id),
            )

        converted += 1
        print(f"  OK    {entry_id}  ({len(html)} chars, {len(new_media_refs)} media refs)")

    if not dry_run:
        conn.commit()
    conn.close()

    mode = "[DRY RUN] " if dry_run else ""
    print(f"\n{mode}{converted} converted, {skipped} skipped (already HTML or empty), {errors} errors")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    repo_root = Path(__file__).resolve().parent.parent
    parser.add_argument("--db", default=str(repo_root / "codexj.db"), help="Path to the SQLite DB file")
    parser.add_argument("--dry-run", action="store_true", help="Convert and print but do not write to the DB")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    print(f"{'DRY RUN — ' if args.dry_run else ''}Migrating {db_path}")
    migrate(db_path, args.dry_run)


if __name__ == "__main__":
    main()
