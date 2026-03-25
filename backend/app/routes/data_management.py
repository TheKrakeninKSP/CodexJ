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
from app.utils.auth import get_current_user
from app.utils.data_management import (
    convert_body_to_quill_delta,
    decode_and_save_media,
    encode_media_file,
    generate_dump_filename,
    parse_plaintext_entry,
    read_encrypted_dump,
    save_encrypted_dump,
    update_media_refs_in_body,
    validate_dump_structure,
)
from app.utils.entry_utils import extract_media_refs
from app.utils.media import save_media_to_user_directory
from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

router = APIRouter(prefix="/data-management", tags=["data_management"])


def _now():
    return datetime.now(timezone.utc)


# Export Endpoint


@router.post("/export", response_model=ExportResponse)
async def export_user_data(
    payload: ExportRequest,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Export all user data to an encrypted dump file."""
    user_id = current_user["id"]
    user_doc = None
    if ObjectId.is_valid(user_id):
        user_doc = await db["users"].find_one({"_id": ObjectId(user_id)})

    dump = UserDataDump(
        version="1.0",
        exported_at=_now(),
        user_id=user_id,
        username=(user_doc or {}).get("username") or current_user.get("username"),
        password_hash=(user_doc or {}).get("password_hash"),
        hashkey_hash=(user_doc or {}).get("hashkey_hash"),
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

    # Export entries
    async for entry in db["entries"].find({"journal_id": {"$in": jr_ids}}):
        dump.entries.append(
            DumpEntry(
                id=str(entry["_id"]),
                journal_id=entry["journal_id"],
                type=entry["type"],
                name=entry["name"],
                timezone=entry.get("timezone"),
                body=entry.get("body", {}),
                custom_metadata=entry.get("custom_metadata", []),
                media_refs=entry.get("media_refs", []),
                date_created=entry.get("date_created", _now()),
                updated_at=entry.get("updated_at", _now()),
            )
        )

    # Export entry types
    async for et in db["entry_types"].find({"user_id": user_id}):
        dump.entry_types.append(
            DumpEntryType(
                id=str(et["_id"]),
                name=et["name"],
                created_at=et.get("created_at", _now()),
            )
        )

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
            )
        )

    # Encrypt and save dump
    filename = generate_dump_filename(user_id)
    success, result = save_encrypted_dump(
        dump.model_dump(mode="json"),
        payload.encryption_key,
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
    encryption_key: str = Form(...),
    conflict_resolution: str = Form("skip"),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Import user data from an encrypted dump file."""
    user_id = current_user["id"]

    content = await file.read()
    data = read_encrypted_dump(content, encryption_key)

    if data is None:
        raise HTTPException(
            400, "Failed to decrypt dump. Invalid key or corrupted file."
        )

    valid, msg = validate_dump_structure(data)
    if not valid:
        raise HTTPException(400, f"Invalid dump structure: {msg}")

    result = ImportEncryptedResponse(
        status="success",
        message="Import completed",
    )

    # ID mapping: old_id -> new_id
    ws_id_map = {}
    jr_id_map = {}
    media_url_map = {}

    # Import workspaces
    for ws_data in data.get("workspaces", []):
        existing = await db["workspaces"].find_one(
            {
                "user_id": user_id,
                "name": ws_data["name"],
            }
        )

        if existing:
            if conflict_resolution == "skip":
                ws_id_map[ws_data["id"]] = str(existing["_id"])
                result.skipped += 1
                continue
            elif conflict_resolution == "overwrite":
                ws_id_map[ws_data["id"]] = str(existing["_id"])
                continue

        doc = {
            "user_id": user_id,
            "name": ws_data["name"],
            "created_at": ws_data.get("created_at", _now()),
        }
        res = await db["workspaces"].insert_one(doc)
        ws_id_map[ws_data["id"]] = str(res.inserted_id)
        result.workspaces_imported += 1

    # Import journals
    for jr_data in data.get("journals", []):
        new_ws_id = ws_id_map.get(jr_data["workspace_id"])
        if not new_ws_id:
            result.errors.append(f"Journal '{jr_data['name']}': workspace not found")
            continue

        existing = await db["journals"].find_one(
            {
                "workspace_id": new_ws_id,
                "name": jr_data["name"],
            }
        )

        if existing:
            if conflict_resolution == "skip":
                jr_id_map[jr_data["id"]] = str(existing["_id"])
                result.skipped += 1
                continue
            elif conflict_resolution == "overwrite":
                jr_id_map[jr_data["id"]] = str(existing["_id"])
                continue

        doc = {
            "workspace_id": new_ws_id,
            "name": jr_data["name"],
            "description": jr_data.get("description"),
            "created_at": jr_data.get("created_at", _now()),
        }
        res = await db["journals"].insert_one(doc)
        jr_id_map[jr_data["id"]] = str(res.inserted_id)
        result.journals_imported += 1

    # Import media first (to update entry references)
    for media_data in data.get("media", []):
        if not media_data.get("content_base64"):
            result.errors.append(
                f"Media '{media_data['original_filename']}': no content"
            )
            continue

        success, stored_filename, new_url = decode_and_save_media(
            user_id,
            media_data["content_base64"],
            media_data["original_filename"],
        )

        if success:
            media_doc = DB_Media(
                user_id=user_id,
                original_filename=media_data["original_filename"],
                stored_filename=stored_filename,
                media_type=media_data["media_type"],
                file_size=media_data["file_size"],
                resource_path=new_url,
                created_at=_now(),
                custom_metadata=media_data.get("custom_metadata", {}),
            )
            await db["media"].insert_one(media_doc.model_dump())

            old_url = (
                f"http://localhost:8000/media/{data['user_id']}/"
                f"{media_data['stored_filename']}"
            )
            media_url_map[old_url] = new_url

    # Import entries
    for entry_data in data.get("entries", []):
        new_jr_id = jr_id_map.get(entry_data["journal_id"])
        if not new_jr_id:
            result.errors.append(f"Entry '{entry_data['name']}': journal not found")
            continue

        body = entry_data.get("body", {})
        updated_body = update_media_refs_in_body(body, media_url_map)

        existing = await db["entries"].find_one(
            {
                "journal_id": new_jr_id,
                "name": entry_data["name"],
                "date_created": entry_data.get("date_created"),
            }
        )

        if existing and conflict_resolution == "skip":
            result.skipped += 1
            continue

        # Generate a new ObjectId for this entry
        new_entry_id = ObjectId()
        doc = {
            "_id": new_entry_id,
            "id": str(new_entry_id),
            "journal_id": new_jr_id,
            "type": entry_data["type"],
            "name": entry_data["name"],
            "timezone": entry_data.get("timezone"),
            "body": updated_body,
            "custom_metadata": entry_data.get("custom_metadata", []),
            "media_refs": extract_media_refs(updated_body),
            "date_created": entry_data.get("date_created", _now()),
            "updated_at": _now(),
        }
        await db["entries"].insert_one(doc)
        result.entries_imported += 1

    # Import entry types
    for et_data in data.get("entry_types", []):
        existing = await db["entry_types"].find_one(
            {
                "user_id": user_id,
                "name": et_data["name"],
            }
        )

        if existing:
            result.skipped += 1
            continue

        doc = {
            "user_id": user_id,
            "name": et_data["name"],
            "created_at": et_data.get("created_at", _now()),
        }
        await db["entry_types"].insert_one(doc)
        result.entry_types_imported += 1

    return result


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
    - Within body: <<>>filename = media reference
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
            "name": parsed.entry_type,
        }
    )
    if not et_existing:
        await db["entry_types"].insert_one(
            {
                "user_id": user_id,
                "name": parsed.entry_type,
                "created_at": _now(),
            }
        )

    # Create the entry
    new_entry_id = ObjectId()
    entry_doc = {
        "_id": new_entry_id,
        "id": str(new_entry_id),
        "journal_id": journal_id,
        "type": parsed.entry_type,
        "name": parsed.entry_name,
        "body": body,
        "custom_metadata": parsed.custom_metadata,
        "media_refs": extract_media_refs(body),
        "date_created": parsed.date,
        "updated_at": parsed.date,
    }

    await db["entries"].insert_one(entry_doc)
    result.entry_id = str(new_entry_id)
    result.message = f"Entry '{parsed.entry_name}' imported successfully"

    return result
