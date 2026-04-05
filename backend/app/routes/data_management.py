"""Data management API endpoints - export, import, backup operations"""

import os
from datetime import datetime, timezone
from typing import List

from app.constants import DUMPS_PATH
from app.database import get_db
from app.models.data_management import (
    DumpEntry,
    DumpEntryType,
    DumpJournal,
    DumpMedia,
    DumpWorkspace,
    ExportRequest,
    ExportResponse,
    ImportEncryptedResponse,
    PlaintextImportResponse,
    UserDataDump,
)
from app.models.media import DB_Media
from app.models.user import normalize_theme
from app.utils.auth import get_current_user, require_privileged_mode
from app.utils.data_management import (
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
from app.utils.entry_utils import extract_media_refs
from app.utils.media import (
    save_media_to_user_directory,
    trim_unreferenced_media_for_user,
)
from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

router = APIRouter(prefix="/data-management", tags=["data_management"])


def _now():
    return datetime.now(timezone.utc)


# Export Endpoint


@router.post("/export", response_model=ExportResponse)
async def export_user_data(
    current_user: dict = Depends(require_privileged_mode),
    db=Depends(get_db),
):
    """Export all user data to an encrypted dump file."""
    user_id = current_user["id"]
    user_doc = None
    if ObjectId.is_valid(user_id):
        user_doc = await db["users"].find_one({"_id": ObjectId(user_id)})

    dump_key = (user_doc or {}).get("dump_key") or current_user.get("dump_key")
    if not dump_key:
        raise HTTPException(
            500, "Dump key not set for this account. Please contact support."
        )

    dump = UserDataDump(
        version="1.0",
        exported_at=_now(),
        user_id=user_id,
        username=(user_doc or {}).get("username") or current_user.get("username"),
        password_hash=(user_doc or {}).get("password_hash"),
        hashkey_hash=(user_doc or {}).get("hashkey_hash"),
        theme=normalize_theme(
            (user_doc or {}).get("theme") or current_user.get("theme")
        ),
    )

    # Export workspaces
    async for ws in db["workspaces"].find({"user_id": user_id}):
        dump.workspaces.append(
            DumpWorkspace(
                id=str(ws["_id"]),
                name=ws["name"],
                created_at=ws.get("created_at", _now()),
            )
        )

    ws_ids = [ws.id for ws in dump.workspaces]

    # Export journals
    async for jr in db["journals"].find({"workspace_id": {"$in": ws_ids}}):
        dump.journals.append(
            DumpJournal(
                id=str(jr["_id"]),
                workspace_id=jr["workspace_id"],
                name=jr["name"],
                description=jr.get("description"),
                created_at=jr.get("created_at", _now()),
            )
        )

    jr_ids = [jr.id for jr in dump.journals]

    entry_query: dict
    if jr_ids:
        entry_query = {
            "$or": [
                {"journal_id": {"$in": jr_ids}},
                {"user_id": user_id, "is_deleted": True},
            ]
        }
    else:
        entry_query = {"user_id": user_id, "is_deleted": True}

    # Export entries, including binned entries that may outlive their original journal/workspace.
    async for entry in db["entries"].find(entry_query):
        dump.entries.append(
            DumpEntry(
                id=str(entry["_id"]),
                journal_id=entry["journal_id"],
                user_id=entry.get("user_id"),
                type=entry["type"],
                name=entry["name"],
                timezone=entry.get("timezone"),
                body=entry.get("body", {}),
                custom_metadata=entry.get("custom_metadata", []),
                media_refs=entry.get("media_refs", []),
                date_created=entry.get("date_created", _now()),
                updated_at=entry.get("updated_at", _now()),
                is_deleted=entry.get("is_deleted", False),
                deleted_at=entry.get("deleted_at"),
                deleted_from_workspace_id=entry.get("deleted_from_workspace_id"),
                deleted_from_workspace_name=entry.get("deleted_from_workspace_name"),
                deleted_from_journal_id=entry.get("deleted_from_journal_id"),
                deleted_from_journal_name=entry.get("deleted_from_journal_name"),
            )
        )

    # Export entry types
    async for et in db["entry_types"].find({"user_id": user_id}):
        dump.entry_types.append(
            DumpEntryType(
                id=str(et["_id"]),
                workspace_id=et.get("workspace_id"),
                name=et["name"],
                created_at=et.get("created_at", _now()),
            )
        )

    # Remove orphaned media before packaging files into the export.
    await trim_unreferenced_media_for_user(user_id, db)

    # Export media (with file content)
    async for media in db["media"].find({"user_id": user_id}):
        content = encode_media_file(user_id, media["stored_filename"])
        dump.media.append(
            DumpMedia(
                id=str(media["_id"]),
                original_filename=media["original_filename"],
                stored_filename=media["stored_filename"],
                media_type=media["media_type"],
                file_size=media["file_size"],
                created_at=media.get("created_at", _now()),
                custom_metadata=media.get("custom_metadata", {}),
                content_base64=content,
                resource_path=media.get("resource_path"),
                status=media.get("status", "completed"),
                error_message=media.get("error_message"),
            )
        )

    # Encrypt and save dump
    filename = generate_dump_filename(user_id)
    success, result = save_encrypted_dump(
        dump.model_dump(mode="json"),
        dump_key,
        filename,
    )

    if not success:
        raise HTTPException(500, f"Failed to save dump: {result}")

    return ExportResponse(
        status="success",
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
    current_user: dict = Depends(get_current_user),
):
    """Download a previously created dump file."""
    if not filename.startswith(f"codexj_dump_{current_user['id'][:8]}_"):
        raise HTTPException(403, "Access denied to this dump file")

    user_dir = os.path.join(DUMPS_PATH, current_user["id"])
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
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Import user data from an encrypted dump file."""
    user_id = current_user["id"]

    content = await file.read()

    meta = read_dump_meta(content)
    if meta is None:
        raise HTTPException(
            400,
            "Unrecognised dump format. This may be a legacy dump created before version 1.0.",
        )

    source_user_id = meta.get("user_id")
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
        data, user_id, db, conflict_resolution=conflict_resolution
    )

    return ImportEncryptedResponse(
        status=import_result.status,
        message="Import completed",
        workspaces_imported=import_result.workspaces_imported,
        journals_imported=import_result.journals_imported,
        entries_imported=import_result.entries_imported,
        entry_types_imported=import_result.entry_types_imported,
        skipped=import_result.skipped,
        errors=import_result.errors,
    )


# Import from Plaintext Format


@router.post("/import/plaintext", response_model=PlaintextImportResponse)
async def import_plaintext_entry(
    journal_id: str = Form(...),
    conflict_resolution: str = Form("create_new"),
    entry_file: UploadFile = File(...),
    media_files: List[UploadFile] = File(default=[]),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
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
    user_id = current_user["id"]

    # Verify journal access
    journal = await db["journals"].find_one({"_id": ObjectId(journal_id)})
    if not journal:
        raise HTTPException(404, "Journal not found")

    ws = await db["workspaces"].find_one(
        {
            "_id": ObjectId(journal["workspace_id"]),
            "user_id": user_id,
        }
    )
    if not ws:
        raise HTTPException(403, "Access denied to this journal")

    result = PlaintextImportResponse(
        status="success",
        message="Import completed",
    )

    # Parse the plaintext file
    try:
        content = (await entry_file.read()).decode("utf-8")
        parsed = parse_plaintext_entry(content)
    except Exception as e:
        raise HTTPException(400, f"Failed to parse entry file: {e}")

    # Process media files
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

            # Reset file position for reading
            await media_file.seek(0)

            save_result = await save_media_to_user_directory(
                user_id=user_id,
                media_type=media_type,
                file=media_file,
                db=db,
            )

            if save_result.get("status"):
                media_doc = save_result.get("media")
                if DB_Media.model_validate(media_doc) and media_doc:
                    media_refs_map[ref_filename] = media_doc["resource_path"]
                    result.media_imported += 1
            else:
                result.errors.append(f"Failed to save media: {ref_filename}")
        else:
            result.errors.append(f"Media file not provided: {ref_filename}")

    # Convert body to Quill Delta format
    body = convert_body_to_quill_delta(parsed.body_text, media_refs_map)

    # Check for existing entry
    if conflict_resolution == "skip":
        existing = await db["entries"].find_one(
            {
                "journal_id": journal_id,
                "name": parsed.entry_name,
                "date_created": parsed.date,
            }
        )
        if existing:
            result.status = "skipped"
            result.message = "Entry already exists"
            return result

    # Ensure entry type exists
    et_existing = await db["entry_types"].find_one(
        {
            "user_id": user_id,
            "workspace_id": str(ws["_id"]),
            "name": parsed.entry_type,
        }
    )
    if not et_existing:
        await db["entry_types"].insert_one(
            {
                "user_id": user_id,
                "workspace_id": str(ws["_id"]),
                "name": parsed.entry_type,
                "created_at": _now(),
            }
        )

    # Create the entry
    new_entry_id = ObjectId()
    entry_doc = {
        "_id": new_entry_id,
        "id": str(new_entry_id),
        "user_id": user_id,
        "journal_id": journal_id,
        "type": parsed.entry_type,
        "name": parsed.entry_name,
        "body": body,
        "custom_metadata": parsed.custom_metadata,
        "media_refs": extract_media_refs(body),
        "date_created": parsed.date,
        "updated_at": parsed.date,
        "is_deleted": False,
    }

    await db["entries"].insert_one(entry_doc)
    result.entry_id = str(new_entry_id)
    result.message = f"Entry '{parsed.entry_name}' imported successfully"

    return result
