"""Data management API endpoints - export, import, backup operations"""

import json
import os
from datetime import datetime, timezone
from typing import Any, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend.constants import DUMPS_PATH
from backend.database.querying import (
    create_entry,
    create_tag,
    get_all_tags,
    get_entries_by_journal_id,
    get_entries_for_user,
    get_journal_by_id,
    get_journals_by_workspace_id,
    get_media_by_user_id,
    get_tag_by_name,
    get_workspace_by_id,
    get_workspaces_by_user_id,
)
from backend.database.structural import EntryModel, TagModel, UserModel
from backend.models.data_management import (
    DumpEntry,
    DumpEntryType,
    DumpJournal,
    DumpMedia,
    DumpWorkspace,
    ExportResponse,
    ImportEncryptedResponse,
    PlaintextImportResponse,
    UserDataDump,
)
from backend.models.user import normalize_theme
from backend.type_defs import id_type
from backend.utils.auth import get_current_user, require_privileged_mode
from backend.utils.common import utcnow
from backend.utils.data_management import (
    convert_body_to_quill_delta,
    derive_dump_key,
    encode_media_file,
    generate_dump_filename,
    import_dump_data,
    parse_plaintext_entry,
    read_dump_meta,
    read_encrypted_dump,
    save_encrypted_dump,
    validate_dump_structure,
)
from backend.utils.entry_utils import extract_media_refs
from backend.utils.media import (
    save_media_to_user_directory,
    trim_unreferenced_media_for_user,
)

router = APIRouter(prefix="/data-management", tags=["data_management"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_value(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


# Export Endpoint


@router.post("/export", response_model=ExportResponse)
async def export_user_data(
    current_user: UserModel = Depends(get_current_user),
    _=Depends(require_privileged_mode),
):
    """Export all user data to an encrypted dump file."""
    user_id = current_user.id
    dump_key = current_user.dump_key
    if not dump_key:
        raise HTTPException(
            500, "Dump key not set for this account. Please contact support."
        )

    workspaces_dump: list[DumpWorkspace] = []
    journals_dump: list[DumpJournal] = []
    entries_dump: list[DumpEntry] = []
    entry_types_dump: list[DumpEntryType] = []
    media_dump: list[DumpMedia] = []

    workspaces = get_workspaces_by_user_id(user_id)
    for workspace in workspaces:
        workspaces_dump.append(
            DumpWorkspace(
                id=workspace.id,
                user_id=workspace.user_id,
                name=workspace.name,
                created_at=workspace.created_at,
            )
        )

    journals = [
        journal
        for workspace in workspaces
        for journal in get_journals_by_workspace_id(workspace.id)
    ]
    for journal in journals:
        journals_dump.append(
            DumpJournal(
                id=journal.id,
                workspace_id=journal.workspace_id,
                name=journal.name,
                description=journal.description,
                created_at=journal.created_at,
            )
        )

    active_entries = [
        entry for journal in journals for entry in get_entries_by_journal_id(journal.id)
    ]
    deleted_entries = get_entries_for_user(user_id, deleted=True)
    entries_by_id: dict[int, EntryModel] = {
        entry.id: entry for entry in active_entries + deleted_entries
    }

    for entry in entries_by_id.values():
        entries_dump.append(
            DumpEntry(
                id=entry.id,
                journal_id=entry.journal_id,
                tags=_json_value(entry.tags, []),
                name=entry.name,
                timezone=entry.timezone,
                body=_json_value(entry.body, {}),
                custom_metadata=_json_value(entry.custom_metadata, []),
                media_refs=_json_value(entry.media_refs, []),
                date_created=entry.date_created,
                updated_at=entry.updated_at,
                is_deleted=entry.is_deleted,
                deleted_at=entry.deleted_at,
                deleted_from_workspace_id=entry.deleted_from_workspace_id,
                deleted_from_journal_id=entry.deleted_from_journal_id,
            )
        )

    # The current SQL schema stores globally unique tags.
    for tag in get_all_tags():
        entry_types_dump.append(
            DumpEntryType(
                id=str(tag.id),
                workspace_id=0,
                name=tag.name,
                created_at=tag.created_at,
            )
        )

    # Remove orphaned media before packaging files into the export.
    await trim_unreferenced_media_for_user(user_id)

    for media in get_media_by_user_id(user_id):
        content = encode_media_file(str(user_id), media.stored_filename)
        media_dump.append(
            DumpMedia(
                id=media.id,
                user_id=media.user_id,
                entry_id=media.entry_id or 0,
                original_filename=media.original_filename,
                stored_filename=media.stored_filename,
                media_type=media.media_type,
                file_size=media.file_size,
                created_at=media.created_at,
                custom_metadata=_json_value(media.custom_metadata, {}),
                content_base64=content,
                resource_path=media.resource_path,
                status=media.status,
                error_message=media.error_message,
            )
        )

    dump = UserDataDump(
        exported_at=_now(),
        user_id=user_id,
        username=current_user.username,
        password_hash=current_user.password_hash,
        hashkey_hash=current_user.hashkey_hash,
        theme=normalize_theme(current_user.theme),
        workspaces=workspaces_dump,
        journals=journals_dump,
        entries=entries_dump,
        entry_types=entry_types_dump,
        media=media_dump,
    )

    filename = generate_dump_filename(str(user_id))
    success, result = save_encrypted_dump(
        dump.model_dump(mode="json"),
        dump_key,
        filename,
    )

    if not success:
        raise HTTPException(500, f"Failed to save dump: {result}")

    return ExportResponse(
        status="completed",
        filename=filename,
        message=(
            f"Exported {len(dump.workspaces)} workspaces, "
            f"{len(dump.journals)} journals, {len(dump.entries)} entries"
        ),
        timestamp=_now(),
    )


@router.get("/export/download/{filename}")
async def download_dump(
    filename: str,
    current_user: UserModel = Depends(get_current_user),
):
    """Download a previously created dump file."""
    user_id = str(current_user.id)
    if not filename.startswith(f"codexj_dump_{user_id[:8]}_"):
        raise HTTPException(403, "Access denied to this dump file")

    user_dir = os.path.join(DUMPS_PATH, user_id)
    file_path = os.path.join(user_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(404, "Dump file not found")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream",
    )


# Import from Encrypted Dump


@router.post("/import/encrypted", response_model=ImportEncryptedResponse)
async def import_encrypted_dump(
    hashkey: str = Form(...),
    conflict_resolution: str = Form("skip"),
    file: UploadFile = File(...),
    current_user: UserModel = Depends(get_current_user),
):
    """Import user data from an encrypted dump file."""
    user_id = current_user.id

    content = await file.read()

    meta = read_dump_meta(content)
    if meta is None:
        raise HTTPException(
            400,
            "Unrecognised dump format. This may be a legacy dump created before version 1.0.",
        )

    source_user_id = str(meta.get("user_id") or "")
    if not source_user_id:
        raise HTTPException(400, "Dump meta is missing user_id.")

    fernet_key = derive_dump_key(hashkey, source_user_id)
    data = read_encrypted_dump(content, fernet_key)

    if data is None:
        raise HTTPException(
            400, "Failed to decrypt dump. Invalid hashkey or corrupted file."
        )

    valid, msg = validate_dump_structure(data)
    if not valid:
        raise HTTPException(400, f"Invalid dump structure: {msg}")

    import_result = await import_dump_data(
        data,
        user_id,
        conflict_resolution=conflict_resolution,
    )

    return ImportEncryptedResponse(
        status=import_result.status,
        message="Import completed",
        workspaces_imported=import_result.workspaces_imported,
        journals_imported=import_result.journals_imported,
        entries_imported=import_result.entries_imported,
        tags_imported=import_result.entry_types_imported,
        errors=import_result.errors,
    )


# Import from Plaintext Format


@router.post("/import/plaintext", response_model=PlaintextImportResponse)
async def import_plaintext_entry(
    journal_id: id_type = Form(...),
    conflict_resolution: str = Form("create_new"),
    entry_file: UploadFile = File(...),
    media_files: List[UploadFile] = File(default=[]),
    current_user: UserModel = Depends(get_current_user),
):
    """
    Import a single entry from plaintext format with optional media files.

    Plaintext format:
    - Line 1: date
    - Line 2: journal name (for reference, uses journal_id parameter)
    - Line 3: entry type
    - Line 4: entry name
    - Lines starting with <<<>>>: custom_metadata [key |-| value]
    - Remaining lines: body
    - Within body: <<>>filename or <<>>"filename with spaces" = media reference
    """
    user_id = current_user.id

    journal = get_journal_by_id(journal_id)
    if not journal:
        raise HTTPException(404, "Journal not found")

    workspace = get_workspace_by_id(journal.workspace_id)
    if not workspace or workspace.user_id != user_id:
        raise HTTPException(403, "Access denied to this journal")

    errors: list[str] = []
    media_imported = 0

    try:
        content = (await entry_file.read()).decode("utf-8")
        parsed = parse_plaintext_entry(content)
    except Exception as exc:
        raise HTTPException(400, f"Failed to parse entry file: {exc}") from exc

    media_refs_map = {}
    media_files_dict = {f.filename: f for f in media_files if f.filename}

    for ref_filename in parsed.media_references:
        if ref_filename in media_files_dict:
            media_file = media_files_dict[ref_filename]

            content_type = media_file.content_type or "image/png"
            if content_type.startswith("image"):
                media_type = "image"
            elif content_type.startswith("video"):
                media_type = "video"
            elif content_type.startswith("audio"):
                media_type = "audio"
            else:
                media_type = "image"

            await media_file.seek(0)

            save_result = await save_media_to_user_directory(
                user_id=user_id,
                media_type=media_type,
                file=media_file,
                db=None,
            )

            if save_result.get("status"):
                media_doc = save_result.get("media")
                if media_doc:
                    media_refs_map[ref_filename] = media_doc["resource_path"]
                    media_imported += 1
            else:
                errors.append(f"Failed to save media: {ref_filename}")
        else:
            errors.append(f"Media file not provided: {ref_filename}")

    body = convert_body_to_quill_delta(parsed.body_text, media_refs_map)

    if conflict_resolution == "skip":
        existing_entries = get_entries_by_journal_id(journal_id)
        existing = next(
            (
                entry
                for entry in existing_entries
                if entry.name == parsed.entry_name and entry.date_created == parsed.date
            ),
            None,
        )
        if existing:
            return PlaintextImportResponse(
                status="skipped",
                message="Entry already exists",
                media_imported=media_imported,
                errors=errors,
            )

    if parsed.entry_type and not get_tag_by_name(parsed.entry_type):
        create_tag(TagModel(name=parsed.entry_type, created_at=utcnow()))

    entry = EntryModel(
        journal_id=journal_id,
        tags=json.dumps([parsed.entry_type] if parsed.entry_type else []),
        name=parsed.entry_name,
        body=json.dumps(body),
        custom_metadata=json.dumps(parsed.custom_metadata),
        media_refs=json.dumps(extract_media_refs(body)),
        date_created=parsed.date or utcnow(),
        updated_at=parsed.date or utcnow(),
        is_deleted=False,
    )

    create_entry(entry)
    return PlaintextImportResponse(
        status="success",
        message=f"Entry '{parsed.entry_name}' imported successfully",
        entry_id=str(entry.id),
        media_imported=media_imported,
        errors=errors,
    )
