"""Data management utilities - encryption, export, import operations"""

import base64
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from backend.constants import DUMPS_PATH, MEDIA_PATH
from backend.database.querying import (
    create_entry,
    create_journal,
    create_media,
    create_tag,
    create_workspace,
    get_all_tags,
    get_entries_by_journal_id,
    get_journals_by_workspace_id,
    get_workspaces_by_user_id,
)
from backend.database.structural import (
    EntryModel,
    JournalModel,
    MediaModel,
    TagModel,
    WorkspaceModel,
)
from backend.type_defs import id_type
from backend.utils.entry_utils import extract_media_refs

MEDIA_MARKER_PATTERN = r"<<>>(?:\"([^\"]+)\"|(\S+))"
MEDIA_MARKER_SPLIT_PATTERN = r"<<>>(?:\"[^\"]+\"|\S+)"


def _extract_media_marker_filename(marker: str) -> Optional[str]:
    """Extract media filename from <<>> marker, supporting quoted names with spaces."""
    match = re.match(MEDIA_MARKER_PATTERN, marker)
    if not match:
        return None
    quoted = match.group(1)
    bare = match.group(2)
    return quoted if quoted is not None else bare


# Key Derivation


def derive_dump_key(hashkey: str, username: str) -> str:
    """Derive a Fernet-compatible key from the user's plaintext hashkey and username using HKDF."""
    kdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=username.encode("utf-8"),
        info=b"codexj-export-v1",
    )
    key_bytes = kdf.derive(hashkey.encode("utf-8"))
    return base64.urlsafe_b64encode(key_bytes).decode("utf-8")


# Encryption Functions (following Arkiver pattern)


def get_fernet(secret_key: str) -> Optional[Fernet]:
    """Generate a Fernet cipher from the secret key."""
    try:
        key_bytes = secret_key.encode("utf-8").ljust(32, b"0")[:32]
        key = base64.urlsafe_b64encode(key_bytes)
        return Fernet(key)
    except Exception as e:
        sys.stderr.write(f"Error generating Fernet object: {e}\n")
        return None


def encrypt_data(data: str, secret_key: str) -> bytes:
    """Encrypt a string using the provided secret key."""
    f = get_fernet(secret_key)
    if f is None:
        raise ValueError("Failed to create encryption cipher")
    return f.encrypt(data.encode("utf-8"))


def decrypt_data(token: bytes, secret_key: str) -> Optional[str]:
    """Decrypt data using the provided secret key."""
    try:
        f = get_fernet(secret_key)
        if f is None:
            return None
        return f.decrypt(token).decode("utf-8")
    except InvalidToken:
        sys.stderr.write("Error: Invalid encryption key or corrupted file.\n")
        return None
    except Exception as e:
        sys.stderr.write(f"Error decrypting data: {e}\n")
        return None


# Dump File Management


def generate_dump_filename(user_id: str) -> str:
    """Generate a dump filename with timestamp."""
    now = datetime.now(timezone.utc)
    return f"codexj_dump_{user_id[:8]}_{now.strftime('%Y%m%d_%H%M%S')}.bin"


def save_encrypted_dump(data: dict, fernet_key: str, filename: str) -> Tuple[bool, str]:
    """Save data as encrypted JSON to DUMPS_PATH.

    Writes a JSON wrapper: {"meta": {"user_id": ..., "version": ...}, "payload": <fernet token>}
    The meta section is unencrypted and contains the user_id needed to re-derive the key at import.
    """
    try:
        os.makedirs(DUMPS_PATH, exist_ok=True)
        user_id = data.get("user_id", "unknown")
        user_dir = os.path.join(DUMPS_PATH, user_id)
        os.makedirs(user_dir, exist_ok=True)
        file_path = os.path.join(user_dir, filename)
        json_str = json.dumps(data, ensure_ascii=False, default=str)
        f = Fernet(fernet_key.encode("utf-8"))
        payload_token = f.encrypt(json_str.encode("utf-8")).decode("utf-8")
        wrapper = {
            "meta": {"user_id": user_id, "version": data.get("version", "1.0")},
            "payload": payload_token,
        }
        with open(file_path, "wb") as fp:
            fp.write(json.dumps(wrapper, ensure_ascii=False).encode("utf-8"))
        return True, file_path
    except Exception as e:
        sys.stderr.write(f"Error saving encrypted dump: {e}\n")
        return False, str(e)


def read_dump_meta(file_content: bytes) -> Optional[dict]:
    """Read the unencrypted meta section from a new-format dump without decrypting.

    Returns the meta dict (e.g. {"user_id": ..., "version": ...}) or None for old-format dumps.
    """
    try:
        wrapper = json.loads(file_content.decode("utf-8"))
        if isinstance(wrapper, dict) and "meta" in wrapper and "payload" in wrapper:
            return wrapper["meta"]
    except Exception:
        pass
    return None


def read_encrypted_dump(file_content: bytes, fernet_key: str) -> Optional[dict]:
    """Read and decrypt data from encrypted dump bytes.

    Supports the new JSON-wrapper format (post-1.0) where 'fernet_key' is a
    base64url-encoded 32-byte key derived via derive_dump_key().
    Falls back to the legacy raw-bytes format for older dumps.
    """
    try:
        # --- New format: JSON wrapper with unencrypted meta and encrypted payload ---
        try:
            wrapper = json.loads(file_content.decode("utf-8"))
            if isinstance(wrapper, dict) and "payload" in wrapper:
                payload_bytes = wrapper["payload"].encode("utf-8")
                f = Fernet(fernet_key.encode("utf-8"))
                decrypted = f.decrypt(payload_bytes).decode("utf-8")
                return json.loads(decrypted)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        # --- Legacy format: raw Fernet token (pre-1.0 dumps with user-chosen key) ---
        decrypted = decrypt_data(file_content, fernet_key)
        if not decrypted:
            return None
        return json.loads(decrypted)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"Error parsing JSON from dump: {e}\n")
        return None
    except Exception as e:
        sys.stderr.write(f"Error reading dump: {e}\n")
        return None


# Media Handling


def encode_media_file(user_id: str, stored_filename: str) -> Optional[str]:
    """Read and base64-encode a media file."""
    try:
        file_path = os.path.join(MEDIA_PATH, user_id, stored_filename)
        if not os.path.exists(file_path):
            return None
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        sys.stderr.write(f"Error encoding media file: {e}\n")
        return None


def decode_and_save_media(
    user_id: str,
    content_base64: str,
    original_filename: str,
    *,
    fallback_ext: str = "",
) -> Tuple[bool, str, str]:
    """
    Decode base64 content and save to user's media directory.

    Returns (success, stored_filename, resource_url).
    """
    try:
        user_dir = os.path.join(MEDIA_PATH, user_id)
        os.makedirs(user_dir, exist_ok=True)

        content = base64.b64decode(content_base64)
        # Always prefer fallback_ext (derived from stored_filename in the dump) so that
        # files like webpages (whose original_filename is a page title with no extension)
        # are saved with the correct extension (.html etc.).
        if fallback_ext:
            ext = fallback_ext
        else:
            _, ext = os.path.splitext(original_filename)
        stored_filename = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.join(user_dir, stored_filename)
        with open(file_path, "wb") as f:
            f.write(content)
        url = f"http://localhost:8128/media/{user_id}/{stored_filename}"
        return True, stored_filename, url
    except Exception as e:
        sys.stderr.write(f"Error saving media file: {e}\n")
        return False, "", str(e)


# Plaintext Entry Parser


@dataclass
class ParsedPlaintextEntry:
    """Parsed data from plaintext entry file"""

    date: Optional[datetime] = None
    journal_name: str = ""
    entry_type: str = ""
    entry_name: str = ""
    custom_metadata: List[dict] = field(default_factory=list)
    body_text: str = ""
    media_references: List[str] = field(default_factory=list)


def parse_date_string(date_str: str) -> datetime:
    """Parse various date formats into datetime."""
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%d/%m/%Y",
        "%Y/%m/%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Unable to parse date: {date_str}")


def parse_plaintext_entry(content: str) -> ParsedPlaintextEntry:
    """
    Parse plaintext entry file format:
    - Line 1: date (ISO format or common formats)
    - Line 2: journal name
    - Line 3: entry type
    - Line 4: entry name
    - Lines starting with <<<>>>: custom_metadata [key |-| value]
    - Remaining lines: body
    - Within body: <<>>filename or <<>>"filename with spaces" = media reference
    """
    result = ParsedPlaintextEntry()
    lines = content.strip().split("\n")

    if len(lines) < 4:
        raise ValueError(
            "Plaintext file must have at least 4 lines (date, journal, type, name)"
        )

    # Line 1: Date
    date_str = lines[0].strip()
    result.date = parse_date_string(date_str)

    # Line 2: Journal name
    result.journal_name = lines[1].strip()

    # Line 3: Entry type
    result.entry_type = lines[2].strip()

    # Line 4: Entry name
    result.entry_name = lines[3].strip()

    # Process remaining lines
    body_lines = []
    for line in lines[4:]:
        if line.startswith("<<<>>>"):
            # Custom metadata line
            metadata_content = line[6:].strip()
            match = re.match(r"\[(.+?)\s*\|-\|\s*(.+?)\]", metadata_content)
            if match:
                result.custom_metadata.append(
                    {
                        "key": match.group(1).strip(),
                        "value": match.group(2).strip(),
                    }
                )
        else:
            body_lines.append(line)

    # Join body and extract media references
    body_text = "\n".join(body_lines)

    # Find media references. Quoted markers allow spaces in filenames.
    result.media_references = [
        filename
        for quoted, bare in re.findall(MEDIA_MARKER_PATTERN, body_text)
        for filename in [quoted or bare]
        if filename
    ]

    # Store the raw body text for conversion to Quill Delta
    result.body_text = body_text

    return result


def convert_body_to_quill_delta(
    body_text: str,
    media_refs: dict,
) -> dict:
    """
    Convert plaintext body to Quill Delta format.
    Replace <<>>filename (or <<>>"filename with spaces") with embeds.
    """
    ops = []
    video_exts = {".mp4", ".webm", ".ogg"}
    audio_exts = {".mp3", ".aac", ".flac", ".wav", ".m4a", ".alac", ".oga", ".opus"}
    pdf_exts = {".pdf"}

    # Split by media markers
    parts = re.split(rf"({MEDIA_MARKER_SPLIT_PATTERN})", body_text)

    for part in parts:
        if part.startswith("<<>>"):
            filename = _extract_media_marker_filename(part)
            if not filename:
                ops.append({"insert": part})
                continue
            if filename in media_refs:
                url = media_refs[filename]
                ext = os.path.splitext(filename)[1].lower()
                if ext in video_exts:
                    ops.append({"insert": {"video": url}})
                elif ext in audio_exts:
                    ops.append({"insert": {"audio": url}})
                elif ext in pdf_exts:
                    ops.append({"insert": {"pdf": url}})
                else:
                    ops.append({"insert": {"image": url}})
            else:
                # Media not found, keep as text
                ops.append({"insert": part})
        elif part:
            # Regular text
            ops.append({"insert": part})

    # Ensure document ends with newline for Quill
    if ops:
        last_insert = ops[-1].get("insert")
        if isinstance(last_insert, str) and not last_insert.endswith("\n"):
            ops[-1]["insert"] = last_insert + "\n"
    else:
        ops.append({"insert": "\n"})

    return {"ops": ops}


# Validation


def validate_dump_structure(data: dict) -> Tuple[bool, str]:
    """Validate the structure of an imported dump."""
    required_keys = ["version", "user_id", "workspaces", "journals", "entries"]
    for key in required_keys:
        if key not in data:
            return False, f"Missing required key: {key}"

    version = data.get("version", "")
    if not version or version.split(".")[0] != "1":
        return False, f"Unsupported dump version: {version}"

    return True, "Valid"


def update_media_refs_in_body(body: dict, url_map: dict) -> dict:
    """Update media URLs in Quill Delta body to new URLs."""
    if not body or "ops" not in body:
        return body

    new_ops = []
    for op in body.get("ops", []):
        if isinstance(op.get("insert"), dict):
            insert = op["insert"].copy()
            for key in ["image", "video", "audio", "webpage", "pdf"]:
                if key not in insert:
                    continue

                value = insert[key]
                if isinstance(value, str) and value in url_map:
                    insert[key] = url_map[value]
                elif isinstance(value, dict):
                    # Audio embeds can be objects (e.g. {"src": "...", ...}).
                    media_url = value.get("src") or value.get("url")
                    if isinstance(media_url, str) and media_url in url_map:
                        remapped = value.copy()
                        if "src" in remapped:
                            remapped["src"] = url_map[media_url]
                        if "url" in remapped:
                            remapped["url"] = url_map[media_url]
                        # If neither key is present, normalize to src.
                        if "src" not in remapped and "url" not in remapped:
                            remapped["src"] = url_map[media_url]
                        insert[key] = remapped
            new_ops.append(
                {"insert": insert, **{k: v for k, v in op.items() if k != "insert"}}
            )
        else:
            new_ops.append(op)

    return {"ops": new_ops}


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ImportResult:
    status: str = "completed"
    workspaces_imported: int = 0
    journals_imported: int = 0
    entries_imported: int = 0
    entry_types_imported: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)


def _to_int(value) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


async def import_dump_data(
    data: dict,
    user_id: id_type,
    db=None,
    conflict_resolution: str = "create_new",
) -> ImportResult:
    """
    Import workspaces, journals, entries, media and entry types from a decrypted dump dict.

    conflict_resolution controls what happens when a workspace/journal/entry already exists:
      - "skip"        : keep existing, map IDs so children are still imported
      - "overwrite"   : keep existing but continue (same as skip for now)
      - "create_new"  : always insert a new record (default; used by register-with-import)
    """
    _ = db
    result = ImportResult()

    ws_id_map: dict[str, int] = {}
    jr_id_map: dict[str, int] = {}
    entry_id_map: dict[str, int] = {}
    jr_workspace_map: dict[int, int] = {}
    media_url_map: dict[str, str] = {}
    imported_entry_types_by_workspace: dict[int, dict[str, datetime]] = {}

    # ── Workspaces ────────────────────────────────────────────────────────────
    existing_workspaces_by_name = {
        workspace.name: workspace for workspace in get_workspaces_by_user_id(user_id)
    }
    for ws_data in data.get("workspaces", []):
        source_ws_id = str(ws_data.get("id"))
        if conflict_resolution != "create_new":
            existing = existing_workspaces_by_name.get(ws_data["name"])
            if existing:
                ws_id_map[source_ws_id] = existing.id
                result.skipped += 1
                continue

        workspace = WorkspaceModel(
            user_id=user_id,
            name=ws_data["name"],
            created_at=ws_data.get("created_at", _now()),
        )
        workspace_id = create_workspace(workspace)
        ws_id_map[source_ws_id] = workspace_id
        existing_workspaces_by_name[workspace.name] = workspace
        result.workspaces_imported += 1

    # ── Journals ──────────────────────────────────────────────────────────────
    for jr_data in data.get("journals", []):
        source_journal_id = str(jr_data.get("id"))
        new_ws_id = ws_id_map.get(str(jr_data.get("workspace_id")))
        if not new_ws_id:
            result.errors.append(f"Journal '{jr_data['name']}': workspace not found")
            continue

        existing_journals_by_name = {
            journal.name: journal for journal in get_journals_by_workspace_id(new_ws_id)
        }
        if conflict_resolution != "create_new":
            existing = existing_journals_by_name.get(jr_data["name"])
            if existing:
                jr_id_map[source_journal_id] = existing.id
                jr_workspace_map[existing.id] = new_ws_id
                result.skipped += 1
                continue

        journal = JournalModel(
            workspace_id=new_ws_id,
            name=jr_data["name"],
            description=jr_data.get("description"),
            created_at=jr_data.get("created_at", _now()),
        )
        journal_id = create_journal(journal)
        jr_id_map[source_journal_id] = journal_id
        jr_workspace_map[journal_id] = new_ws_id
        result.journals_imported += 1

    # ── Entries ───────────────────────────────────────────────────────────────
    for entry_data in data.get("entries", []):
        new_jr_id = jr_id_map.get(str(entry_data.get("journal_id")))
        is_deleted = bool(entry_data.get("is_deleted", False))
        if not new_jr_id:
            result.errors.append(f"Entry '{entry_data['name']}': journal not found")
            continue

        new_ws_id = jr_workspace_map.get(new_jr_id)
        # Support both new format (tags list) and old format (type string)
        raw_tags = entry_data.get("tags")
        if raw_tags is None:
            old_type = entry_data.get("type", "")
            raw_tags = (
                [old_type] if isinstance(old_type, str) and old_type.strip() else []
            )
        entry_tags = [t for t in raw_tags if isinstance(t, str) and t.strip()]
        if new_ws_id:
            for tag in entry_tags:
                imported_entry_types_by_workspace.setdefault(new_ws_id, {}).setdefault(
                    tag, _now()
                )

        body = entry_data.get("body", {})
        # Temporarily use placeholder URL map until media is processed
        updated_body = update_media_refs_in_body(body, media_url_map)

        if conflict_resolution == "skip":
            existing_entries = get_entries_by_journal_id(new_jr_id)
            found_conflict = any(
                existing_entry.name == entry_data.get("name")
                and existing_entry.date_created == entry_data.get("date_created")
                and existing_entry.is_deleted == is_deleted
                for existing_entry in existing_entries
            )
            if found_conflict:
                result.skipped += 1
                continue

        deleted_workspace_id = ws_id_map.get(
            str(entry_data.get("deleted_from_workspace_id"))
        )
        if deleted_workspace_id is None:
            deleted_workspace_id = _to_int(entry_data.get("deleted_from_workspace_id"))

        deleted_journal_id = jr_id_map.get(
            str(entry_data.get("deleted_from_journal_id"))
        )
        if deleted_journal_id is None:
            deleted_journal_id = _to_int(entry_data.get("deleted_from_journal_id"))

        entry = EntryModel(
            journal_id=new_jr_id,
            tags=json.dumps(entry_tags),
            name=entry_data.get("name"),
            timezone=entry_data.get("timezone"),
            body=json.dumps(updated_body),
            custom_metadata=json.dumps(entry_data.get("custom_metadata", [])),
            media_refs=json.dumps(extract_media_refs(updated_body)),
            date_created=entry_data.get("date_created", _now()),
            updated_at=entry_data.get("updated_at", _now()),
            is_deleted=is_deleted,
            deleted_at=entry_data.get("deleted_at"),
            deleted_from_workspace_id=deleted_workspace_id,
            deleted_from_journal_id=deleted_journal_id,
        )
        entry_id = create_entry(entry)
        source_entry_id = str(entry_data.get("id"))
        entry_id_map[source_entry_id] = entry_id
        result.entries_imported += 1

    # ── Media ─────────────────────────────────────────────────────────────────
    for media_data in data.get("media", []):
        if not media_data.get("content_base64"):
            result.errors.append(
                f"Media '{media_data['original_filename']}': no content"
            )
            continue

        # Map source entry_id to new entry_id (media requires entry_id)
        source_entry_id = str(media_data.get("entry_id", 0))
        new_entry_id = entry_id_map.get(source_entry_id)
        if not new_entry_id:
            result.errors.append(
                f"Media '{media_data['original_filename']}': entry not found (source entry_id: {source_entry_id})"
            )
            continue

        _, _fallback_ext = os.path.splitext(media_data.get("stored_filename", ""))
        success, stored_filename, new_url = decode_and_save_media(
            str(user_id),
            media_data["content_base64"],
            media_data["original_filename"],
            fallback_ext=_fallback_ext,
        )

        if success:
            media_doc = MediaModel(
                entry_id=new_entry_id,
                original_filename=media_data["original_filename"],
                stored_filename=stored_filename,
                media_type=media_data["media_type"],
                file_size=media_data["file_size"],
                resource_path=new_url,
                created_at=_now(),
                custom_metadata=json.dumps(media_data.get("custom_metadata", {})),
                status=media_data.get("status", "completed"),
                error_message=media_data.get("error_message"),
            )
            create_media(media_doc)

            old_url = (
                media_data.get("resource_path")
                or f"http://localhost:8128/media/{data['user_id']}/{media_data['stored_filename']}"
            )
            media_url_map[old_url] = new_url
        else:
            result.errors.append(
                f"Media '{media_data['original_filename']}': failed to save file"
            )

    # ── Entry types ───────────────────────────────────────────────────────────

    # ── Entry types ───────────────────────────────────────────────────────────
    for et_data in data.get("entry_types", []):
        old_ws_id = et_data.get("workspace_id")
        if not old_ws_id:
            continue
        new_ws_id = ws_id_map.get(str(old_ws_id))
        if not new_ws_id:
            continue
        imported_entry_types_by_workspace.setdefault(new_ws_id, {}).setdefault(
            et_data["name"], et_data.get("created_at", _now())
        )

    existing_tags = {tag.name for tag in get_all_tags()}
    for _, entry_types in imported_entry_types_by_workspace.items():
        for name, created_at in entry_types.items():
            if name in existing_tags:
                result.skipped += 1
                continue
            create_tag(
                TagModel(
                    name=name,
                    created_at=created_at,
                )
            )
            existing_tags.add(name)
            result.entry_types_imported += 1

    result.status = "completed" if not result.errors else "failed"
    return result
