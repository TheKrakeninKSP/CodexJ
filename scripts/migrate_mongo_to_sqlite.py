"""Migrate CodexJ data from MongoDB into the SQLite database.

Usage (from the project root):

    python scripts/migrate_mongo_to_sqlite.py --dry-run
    python scripts/migrate_mongo_to_sqlite.py

You are asked for the old media folder unless --media-source is given.
What it does
  * users, workspaces, journals, entries and media get fresh UUIDv4 ids
  * `entry_types` become global tags (plus any tag used by an entry)
  * media files are copied from <media-source>/<old user id>/ to
    <media-dest>/<new user id>/, and every media URL inside entry bodies is
    rewritten to the new user id
  * audio/webpage embeds get the `media_id` the frontend needs
  * `media_refs` are recomputed from the rewritten bodies

Mongo media documents carry no entry id, so each one is attached to the first
entry that references its URL. Media no entry references cannot be stored (the
SQLite schema requires an entry) and are reported and skipped.

The script never modifies MongoDB or the original media files. It refuses to run
if a Mongo username already exists in SQLite.
"""

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

MEDIA_URL_PREFIX = "http://localhost:8128/media"
URL_EMBED_KEYS = ("image", "video", "audio", "webpage", "pdf")
ID_EMBED_KEYS = ("audio", "webpage")


class MigrationError(Exception):
    pass


@dataclass
class Report:
    users: int = 0
    workspaces: int = 0
    journals: int = 0
    tags: int = 0
    entries: int = 0
    media: int = 0
    media_files_copied: int = 0
    media_files_missing: int = 0
    missing_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _dt(value: Any, default: datetime | None = None) -> datetime:
    """Mongo holds a mix of naive datetimes and ISO strings; normalise to aware UTC."""
    if value is None or value == "":
        return default or datetime.now(timezone.utc)
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _rewrite_strings(node: Any, old_prefix: str, new_prefix: str) -> Any:
    if isinstance(node, str):
        return node.replace(old_prefix, new_prefix)
    if isinstance(node, list):
        return [_rewrite_strings(item, old_prefix, new_prefix) for item in node]
    if isinstance(node, dict):
        return {k: _rewrite_strings(v, old_prefix, new_prefix) for k, v in node.items()}
    return node


def _embed_url(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        candidate = value.get("src") or value.get("url")
        return candidate if isinstance(candidate, str) else None
    return None


def _attach_media_ids(body: Any, media_id_by_url: dict[str, str]) -> Any:
    """Add `media_id` to audio/webpage object embeds whose URL is a migrated media."""
    if not isinstance(body, dict) or not isinstance(body.get("ops"), list):
        return body
    for op in body["ops"]:
        insert = op.get("insert") if isinstance(op, dict) else None
        if not isinstance(insert, dict):
            continue
        for key in ID_EMBED_KEYS:
            embed = insert.get(key)
            if isinstance(embed, dict):
                media_id = media_id_by_url.get(_embed_url(embed) or "")
                if media_id:
                    embed["media_id"] = media_id
            elif isinstance(embed, str) and embed in media_id_by_url:
                # Plain-URL embeds become object embeds so they can carry the id.
                insert[key] = {"src": embed, "media_id": media_id_by_url[embed]}
    return body


def _collect_urls(body: Any) -> list[str]:
    urls: list[str] = []
    if not isinstance(body, dict) or not isinstance(body.get("ops"), list):
        return urls
    for op in body["ops"]:
        insert = op.get("insert") if isinstance(op, dict) else None
        if isinstance(insert, dict):
            for key in URL_EMBED_KEYS:
                url = _embed_url(insert.get(key))
                if url:
                    urls.append(url)
    return urls


def migrate(
    mongo_db: Any,
    session: Any,
    *,
    media_source: Path,
    media_dest: Path,
    dry_run: bool = False,
    skip_missing_media: bool = False,
) -> Report:
    """Copy everything from `mongo_db` into `session`. The caller commits (or not)."""
    from backend.database.structural import (
        EntryModel,
        JournalModel,
        MediaModel,
        TagModel,
        UserModel,
        WorkspaceModel,
    )
    from backend.type_defs import new_id
    from backend.utils.entry_utils import extract_media_refs, remap_entry_links

    report = Report()
    mongo_users = list(mongo_db["users"].find())

    for user in mongo_users:
        if session.query(UserModel).filter_by(username=user["username"]).first():
            raise MigrationError(
                f"User '{user['username']}' already exists in SQLite; refusing to merge."
            )

    user_ids = {str(u["_id"]): new_id() for u in mongo_users}
    workspace_docs = list(mongo_db["workspaces"].find())
    journal_docs = list(mongo_db["journals"].find())
    entry_docs = list(mongo_db["entries"].find())
    media_docs = list(mongo_db["media"].find())
    entry_type_docs = list(mongo_db["entry_types"].find())

    workspace_ids = {str(w["_id"]): new_id() for w in workspace_docs}
    journal_ids = {str(j["_id"]): new_id() for j in journal_docs}

    # ── Users ────────────────────────────────────────────────────────────────
    for user in mongo_users:
        old_id = str(user["_id"])
        owned = [w for w in workspace_docs if w.get("user_id") == old_id]
        created_at = _dt(
            user.get("created_at"),
            default=min((_dt(w.get("created_at")) for w in owned), default=None),
        )
        session.add(
            UserModel(
                id=user_ids[old_id],
                username=user["username"],
                password_hash=user["password_hash"],
                hashkey_hash=user["hashkey_hash"],
                dump_key=user["dump_key"],
                theme=user.get("theme") or "light",
                created_at=created_at,
            )
        )
        report.users += 1

    # ── Workspaces / journals ────────────────────────────────────────────────
    for ws in workspace_docs:
        if ws.get("user_id") not in user_ids:
            report.warnings.append(f"Workspace '{ws['name']}': unknown user, skipped")
            workspace_ids.pop(str(ws["_id"]), None)
            continue
        session.add(
            WorkspaceModel(
                id=workspace_ids[str(ws["_id"])],
                user_id=user_ids[ws["user_id"]],
                name=ws["name"],
                created_at=_dt(ws.get("created_at")),
            )
        )
        report.workspaces += 1

    for jr in journal_docs:
        if jr.get("workspace_id") not in workspace_ids:
            report.warnings.append(f"Journal '{jr['name']}': unknown workspace, skipped")
            journal_ids.pop(str(jr["_id"]), None)
            continue
        session.add(
            JournalModel(
                id=journal_ids[str(jr["_id"])],
                workspace_id=workspace_ids[jr["workspace_id"]],
                name=jr["name"],
                description=jr.get("description"),
                created_at=_dt(jr.get("created_at")),
            )
        )
        report.journals += 1

    # ── Tags (global, unique by name) ────────────────────────────────────────
    tag_created: dict[str, datetime] = {}
    for et in entry_type_docs:
        created = _dt(et.get("created_at"))
        name = et["name"]
        tag_created[name] = min(created, tag_created.get(name, created))
    for entry in entry_docs:
        for name in entry.get("tags") or []:
            tag_created.setdefault(name, _dt(entry.get("date_created")))
    for name, created in sorted(tag_created.items()):
        if session.query(TagModel).filter_by(name=name).first():
            continue
        session.add(TagModel(id=new_id(), name=name, created_at=created))
        report.tags += 1

    # ── Media planning (needed before entries, to embed media ids) ───────────
    media_plan: dict[str, dict[str, Any]] = {}
    for media in media_docs:
        old_uid = media.get("user_id")
        if old_uid not in user_ids:
            report.warnings.append(
                f"Media '{media.get('original_filename')}': unknown user, skipped"
            )
            continue
        new_uid = user_ids[old_uid]
        old_url = media["resource_path"]
        new_url = old_url.replace(
            f"{MEDIA_URL_PREFIX}/{old_uid}/", f"{MEDIA_URL_PREFIX}/{new_uid}/"
        )
        source = media_source / old_uid / media["stored_filename"]
        media_plan[old_url] = {
            "doc": media,
            "id": new_id(),
            "new_url": new_url,
            "new_uid": new_uid,
            "source": source,
            "exists": source.exists(),
            "entry_id": None,
        }

    # ── Entries ──────────────────────────────────────────────────────────────
    # Decide up front which entries migrate so links can be remapped consistently.
    entry_ids = {
        str(e["_id"]): new_id()
        for e in entry_docs
        if e.get("user_id") in user_ids and e.get("journal_id") in journal_ids
    }
    media_id_by_new_url = {p["new_url"]: p["id"] for p in media_plan.values()}
    for entry in entry_docs:
        old_uid = entry.get("user_id")
        journal_id = journal_ids.get(entry.get("journal_id"))
        if str(entry["_id"]) not in entry_ids:
            report.warnings.append(
                f"Entry '{entry.get('name')}' ({entry['_id']}): unknown journal/user, skipped"
            )
            continue

        new_entry_id = entry_ids[str(entry["_id"])]
        old_body = entry.get("body") or {}
        referenced = set(entry.get("media_refs") or []) | set(_collect_urls(old_body))
        for url in referenced:
            plan = media_plan.get(url)
            if plan and plan["entry_id"] is None:
                plan["entry_id"] = new_entry_id

        body = _rewrite_strings(
            old_body,
            f"{MEDIA_URL_PREFIX}/{old_uid}/",
            f"{MEDIA_URL_PREFIX}/{user_ids[old_uid]}/",
        )
        body = _attach_media_ids(body, media_id_by_new_url)
        body = remap_entry_links(body, entry_ids)

        deleted_ws = workspace_ids.get(entry.get("deleted_from_workspace_id") or "")
        deleted_jr = journal_ids.get(entry.get("deleted_from_journal_id") or "")
        created = _dt(entry.get("date_created"))
        session.add(
            EntryModel(
                id=new_entry_id,
                journal_id=journal_id,
                tags=json.dumps(entry.get("tags") or []),
                name=entry.get("name"),
                timezone=entry.get("timezone"),
                body=json.dumps(body),
                custom_metadata=json.dumps(entry.get("custom_metadata") or []),
                media_refs=json.dumps(extract_media_refs(body)),
                date_created=created,
                updated_at=_dt(entry.get("updated_at"), default=created),
                is_deleted=bool(entry.get("is_deleted")),
                deleted_at=_dt(entry["deleted_at"]) if entry.get("deleted_at") else None,
                deleted_from_workspace_id=deleted_ws,
                deleted_from_journal_id=deleted_jr,
            )
        )
        report.entries += 1

    # ── Media records and files ──────────────────────────────────────────────
    session.flush()
    copies: list[tuple[Path, Path]] = []
    for plan in media_plan.values():
        media = plan["doc"]
        name = media.get("original_filename")
        if plan["entry_id"] is None:
            report.warnings.append(f"Media '{name}': no entry references it, skipped")
            continue
        if not plan["exists"]:
            report.media_files_missing += 1
            report.missing_files.append(str(plan["source"]))
            if skip_missing_media:
                report.warnings.append(f"Media '{name}': file missing, skipped")
                continue
        else:
            copies.append(
                (plan["source"], media_dest / plan["new_uid"] / media["stored_filename"])
            )

        session.add(
            MediaModel(
                id=plan["id"],
                entry_id=plan["entry_id"],
                original_filename=media["original_filename"],
                stored_filename=media["stored_filename"],
                media_type=media["media_type"],
                file_size=media.get("file_size") or 0,
                status=media.get("status") or "completed",
                error_message=media.get("error_message"),
                custom_metadata=json.dumps(media.get("custom_metadata") or {}),
                created_at=_dt(media.get("created_at")),
            )
        )
        report.media += 1

    session.flush()
    if dry_run:
        report.media_files_copied = len(copies)
    else:
        for source, dest in copies:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(source, dest)
            report.media_files_copied += 1
    return report


def _print_report(report: Report, dry_run: bool) -> None:
    verb = "Would migrate" if dry_run else "Migrated"
    print(f"\n{verb}:")
    for label, count in (
        ("users", report.users),
        ("workspaces", report.workspaces),
        ("journals", report.journals),
        ("tags", report.tags),
        ("entries", report.entries),
        ("media records", report.media),
    ):
        print(f"  {label:<14}{count}")
    copied = "to copy" if dry_run else "copied"
    print(
        f"  media files   {report.media_files_copied} {copied}, "
        f"{report.media_files_missing} missing"
    )
    if report.missing_files:
        print(
            f"\n{len(report.missing_files)} media file(s) were not found, e.g.\n"
            f"  {report.missing_files[0]}\n"
            "Their records were still migrated (use --media-source to point at the old "
            "media folder, or --skip-missing-media to drop them)."
        )
    if report.warnings:
        print(f"\n{len(report.warnings)} warning(s):")
        for warning in report.warnings[:25]:
            print(f"  - {warning}")
        if len(report.warnings) > 25:
            print(f"  ... and {len(report.warnings) - 25} more")


def _prompt_media_source(default: Path) -> Path:
    """Ask where the old media folders are; non-interactive runs use the default."""
    if not sys.stdin.isatty():
        return default
    while True:
        answer = input(
            "Absolute path to the old media folder (contains one subfolder per old user id)\n"
            f"[{default}]: "
        )
        # Windows "Copy as path" wraps the path in quotes.
        path = Path(answer.strip().strip('"').strip("'") or default).expanduser()
        if not path.is_absolute():
            print(f"  '{path}' is not an absolute path.")
            continue
        if path.is_dir():
            return path
        print(f"  '{path}' is not a folder.")
        if input("  Continue without media files from there? [y/N]: ").strip().lower() == "y":
            return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--mongo-uri", default=os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
    )
    parser.add_argument("--mongo-db", default=os.getenv("DB_NAME", "codexj"))
    parser.add_argument(
        "--sqlite",
        default=str(PROJECT_ROOT / "src" / "codexj.db"),
        help="SQLite file to migrate into (default: src/codexj.db)",
    )
    parser.add_argument(
        "--media-source",
        default=None,
        help="Absolute path of the folder holding the old <user id>/ media directories "
        "(prompted for when omitted in an interactive terminal; default: media/)",
    )
    parser.add_argument(
        "--media-dest",
        default=str(PROJECT_ROOT / "media"),
        help="Folder the app serves media from",
    )
    parser.add_argument(
        "--skip-missing-media",
        action="store_true",
        help="Do not create media records whose file cannot be found",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do everything except write to SQLite or copy files",
    )
    args = parser.parse_args()
    default_media = PROJECT_ROOT / "media"
    if args.media_source and not Path(args.media_source).expanduser().is_absolute():
        parser.error(f"--media-source must be an absolute path, got '{args.media_source}'")
    media_source = (
        Path(args.media_source).expanduser()
        if args.media_source
        else _prompt_media_source(default_media)
    )
    # The engine reads this URL at import time, so set it before importing structural.
    import backend.constants

    backend.constants.SQLITE_DB_URL = (
        f"sqlite:///{Path(args.sqlite).resolve().as_posix()}"
    )
    from pymongo import MongoClient

    from backend.database.structural import Session, init_db

    client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except Exception as exc:
        print(f"Cannot connect to MongoDB at {args.mongo_uri}: {exc}", file=sys.stderr)
        return 1

    init_db()
    with Session() as session:
        try:
            report = migrate(
                client[args.mongo_db],
                session,
                media_source=media_source,
                media_dest=Path(args.media_dest),
                dry_run=args.dry_run,
                skip_missing_media=args.skip_missing_media,
            )
            if args.dry_run:
                session.rollback()
            else:
                session.commit()
        except MigrationError as exc:
            session.rollback()
            print(f"Aborted: {exc}", file=sys.stderr)
            return 1
        except Exception:
            session.rollback()
            raise
    _print_report(report, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
