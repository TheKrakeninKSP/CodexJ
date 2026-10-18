"""Data management API endpoints - export, import, backup operations"""

import json
import os
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend.constants import DUMPS_PATH
from backend.database.querying import (
    get_entries_by_journal_id,
    get_journals_by_workspace_id,
    get_media_by_user_id,
    get_tag_by_name,
    get_workspaces_by_user_id,
)
from backend.database.structural import EntryModel, UserModel
from backend.models.data_management import (
    DumpEntry,
    DumpJournal,
    DumpMedia,
    DumpTag,
    DumpUser,
    DumpWorkspace,
    ExportResponse,
    ExportStatistics,
    ImportEncryptedResponse,
    UserDataDump,
)
from backend.settings import ColorTheme
from backend.type_defs import (
    ExportStatus,
    ImportStatus,
    MediaStatus,
    MediaType,
    id_type,
    tag_type,
)
from backend.utils.auth import get_current_user, require_privileged_mode
from backend.utils.common import utcnow
from backend.utils.data_management import (
    derive_dump_key,
    encode_media_file,
    generate_dump_filename,
    import_dump_data,
    read_dump_meta,
    read_encrypted_dump,
    save_encrypted_dump,
    validate_dump_structure,
)
from backend.utils.media import trim_unreferenced_media_for_user

router = APIRouter(prefix="/data-management", tags=["data_management"])


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
    username = current_user.username
    dump_key = current_user.dump_key
    if not dump_key:
        raise HTTPException(500, "Dump key not set for this account.")

    workspaces_dump: list[DumpWorkspace] = []
    journals_dump: list[DumpJournal] = []
    entries_dump: list[DumpEntry] = []
    tags_dump: list[DumpTag] = []
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

    entries = [
        entry for journal in journals for entry in get_entries_by_journal_id(journal.id)
    ]
    entries_by_id: dict[id_type, EntryModel] = {entry.id: entry for entry in entries}

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

    # get tags from all entries belonging to the user
    tags_seen: set[tag_type] = set()
    for entry in entries_by_id.values():
        for tag in _json_value(entry.tags, []):
            if tag not in tags_seen:
                tags_seen.add(tag)
                tag_model = get_tag_by_name(tag)
                if not tag_model:
                    print(
                        f"Tag not found: {tag} associated with entry {entry.id} during export"
                    )
                    continue
                tags_dump.append(
                    DumpTag(
                        id=tag_model.id,
                        name=tag_model.name,
                        created_at=tag_model.created_at,
                    )
                )

    # Remove orphaned media before packaging files into the export.
    await trim_unreferenced_media_for_user(user_id)
    for media in get_media_by_user_id(user_id):
        content = encode_media_file(user_id, media.stored_filename)
        media_dump.append(
            DumpMedia(
                id=media.id,
                entry_id=media.entry_id,
                original_filename=media.original_filename,
                stored_filename=media.stored_filename,
                media_type=MediaType(media.media_type),
                file_size=media.file_size,
                created_at=media.created_at,
                custom_metadata=_json_value(media.custom_metadata, {}),
                content_base64=content,
                status=MediaStatus(media.status),
                error_message=media.error_message,
            )
        )

    user_dump = DumpUser(
        id=current_user.id,
        username=current_user.username,
        password_hash=current_user.password_hash,
        hashkey_hash=current_user.hashkey_hash,
        dump_key=current_user.dump_key,
        theme=ColorTheme(current_user.theme),
        created_at=current_user.created_at,
    )

    dump = UserDataDump(
        exported_at=utcnow(),
        user=user_dump,
        workspaces=workspaces_dump,
        journals=journals_dump,
        entries=entries_dump,
        tags=tags_dump,
        media=media_dump,
    )

    filename = generate_dump_filename(username)
    success, result = save_encrypted_dump(
        dump,
        dump_key,
        filename,
    )

    if not success:
        raise HTTPException(500, f"Failed to save dump: {result}")

    return ExportResponse(
        status=ExportStatus("completed"),
        statistics=ExportStatistics(
            workspaces_exported=len(dump.workspaces),
            journals_exported=len(dump.journals),
            entries_exported=len(dump.entries),
            tags_exported=len(dump.tags),
            media_exported=len(dump.media),
        ),
        filename=filename,
        message=(
            f"Exported {len(dump.workspaces)} workspaces, "
            f"{len(dump.journals)} journals, {len(dump.entries)} entries, "
            f"{len(dump.tags)} tags, {len(dump.media)} media"
        ),
        timestamp=utcnow(),
    )


@router.get("/export/download/{filename}")
async def download_dump(
    filename: str,
    current_user: UserModel = Depends(get_current_user),
):
    """Download a previously created dump file."""
    user_id = str(current_user.id)
    if not filename.startswith(f"codexj_dump_user[{current_user.username}]_"):
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

    source_username = str(meta.get("username") or "")
    if not source_username:
        raise HTTPException(400, "Dump meta is missing username.")

    fernet_key = derive_dump_key(hashkey, source_username)
    data = read_encrypted_dump(content, fernet_key)

    if data is None:
        raise HTTPException(
            400, "Failed to decrypt dump. Invalid hashkey or corrupted file."
        )

    valid, msg = validate_dump_structure(data)
    if not valid:
        raise HTTPException(400, f"Invalid dump structure: {msg}")

    data = UserDataDump(**data)
    import_result = await import_dump_data(
        data,
        source_username,
        conflict_resolution=conflict_resolution,
    )

    return ImportEncryptedResponse(
        status=ImportStatus(import_result.status),
        message="Import completed",
        workspaces_imported=import_result.workspaces_imported,
        journals_imported=import_result.journals_imported,
        entries_imported=import_result.entries_imported,
        tags_imported=import_result.tags_imported,
        skipped=import_result.skipped,
        errors=import_result.errors,
    )

