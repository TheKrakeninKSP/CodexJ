import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.constants import MEDIA_PATH
from app.models.media import DB_Media
from app.utils.entry_utils import extract_media_refs
from fastapi import UploadFile


async def save_media_to_user_directory(
    user_id: str, media_type: str, file: UploadFile, db
) -> dict:
    # Save the file to the media directory with a unique UUID-based filename
    try:
        user_directory = os.path.join(MEDIA_PATH, user_id)
        os.makedirs(user_directory, exist_ok=True)

        original_filename = file.filename or "unnamed"
        _, ext = os.path.splitext(original_filename)
        stored_filename = f"{uuid.uuid4().hex}{ext}"

        file_location = os.path.join(user_directory, stored_filename)
        url = f"http://localhost:8128/media/{user_id}/{stored_filename}"

        contents = await file.read()
        with open(file_location, "wb") as f:
            f.write(contents)

        # Insert media record into the database
        media = DB_Media(
            user_id=user_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            media_type=media_type,
            file_size=len(contents),
            resource_path=url,
            created_at=datetime.now(timezone.utc),
            custom_metadata={},
        )
        media_doc = media.model_dump()
        await db["media"].insert_one(media_doc)
        return {"status": True, "media": media_doc}

    except Exception as exc:
        print(f"Error occurred while uploading media: {exc}", file=sys.stderr)
        return {"status": False, "media": None}


def delete_media_file(user_id: str, stored_filename: str) -> None:
    try:
        file_location = os.path.join(MEDIA_PATH, user_id, stored_filename)
        if os.path.exists(file_location):
            if os.path.isdir(file_location):
                shutil.rmtree(file_location)
            else:
                os.remove(file_location)
    except Exception as exc:
        print(f"Error occurred while deleting media file: {exc}", file=sys.stderr)


async def _collect_user_workspace_ids(user_id: str, db) -> list[str]:
    return [
        str(workspace["_id"])
        async for workspace in db["workspaces"].find({"user_id": user_id}, {"_id": 1})
    ]


async def _collect_workspace_journals(
    workspace_ids: list[str], db
) -> tuple[dict[str, list[str]], dict[str, str]]:
    journal_ids_by_workspace: dict[str, list[str]] = {
        workspace_id: [] for workspace_id in workspace_ids
    }
    journal_workspace_map: dict[str, str] = {}

    if not workspace_ids:
        return journal_ids_by_workspace, journal_workspace_map

    async for journal in db["journals"].find(
        {"workspace_id": {"$in": workspace_ids}},
        {"_id": 1, "workspace_id": 1},
    ):
        journal_id = str(journal["_id"])
        workspace_id = journal["workspace_id"]
        journal_workspace_map[journal_id] = workspace_id
        journal_ids_by_workspace.setdefault(workspace_id, []).append(journal_id)

    return journal_ids_by_workspace, journal_workspace_map


async def trim_unreferenced_media_for_user(user_id: str, db) -> dict:
    """Delete media records/files that are no longer referenced by any of the user's entries."""
    workspace_ids = await _collect_user_workspace_ids(user_id, db)
    _, journal_workspace_map = await _collect_workspace_journals(workspace_ids, db)
    journal_ids = list(journal_workspace_map.keys())

    referenced_media_filenames: set[str] = set()
    entry_query: dict
    if journal_ids:
        entry_query = {
            "$or": [
                {"journal_id": {"$in": journal_ids}},
                {"user_id": user_id, "is_deleted": True},
            ]
        }
    else:
        entry_query = {"user_id": user_id, "is_deleted": True}

    async for entry in db["entries"].find(entry_query, {"media_refs": 1, "body": 1}):
        media_refs = entry.get("media_refs") or []
        for media_ref in media_refs:
            if isinstance(media_ref, str) and media_ref:
                ref_without_query = media_ref.split("?", 1)[0].rstrip("/")
                referenced_name = ref_without_query.rsplit("/", 1)[-1]
                if referenced_name:
                    referenced_media_filenames.add(referenced_name)

    deleted_count = 0
    scanned_count = 0

    async for media_doc in db["media"].find({"user_id": user_id}):
        scanned_count += 1
        stored_filename = media_doc.get("stored_filename")
        if (
            isinstance(stored_filename, str)
            and stored_filename in referenced_media_filenames
        ):
            continue

        if isinstance(stored_filename, str) and stored_filename:
            delete_media_file(user_id, stored_filename)
        await db["media"].delete_one({"_id": media_doc["_id"]})
        deleted_count += 1

    return {
        "status": "success",
        "deleted_count": deleted_count,
        "scanned_count": scanned_count,
    }


async def trim_unused_entry_types_for_user(user_id: str, db) -> dict:
    """Delete entry type records that are not referenced by any entry in their workspace."""
    workspace_ids = await _collect_user_workspace_ids(user_id, db)
    journal_ids_by_workspace, journal_workspace_map = await _collect_workspace_journals(
        workspace_ids, db
    )
    journal_ids = list(journal_workspace_map.keys())

    referenced_types_by_workspace: dict[str, set[str]] = {
        workspace_id: set() for workspace_id in workspace_ids
    }

    if journal_ids:
        async for entry in db["entries"].find(
            {"journal_id": {"$in": journal_ids}},
            {"journal_id": 1, "type": 1},
        ):
            journal_id = entry.get("journal_id")
            workspace_id = journal_workspace_map.get(journal_id)
            entry_type = entry.get("type")
            if workspace_id and isinstance(entry_type, str) and entry_type.strip():
                referenced_types_by_workspace.setdefault(workspace_id, set()).add(
                    entry_type
                )

    deleted_count = 0
    scanned_count = 0

    async for entry_type_doc in db["entry_types"].find({"user_id": user_id}):
        scanned_count += 1
        workspace_id = entry_type_doc.get("workspace_id")
        name = entry_type_doc.get("name")
        if (
            isinstance(workspace_id, str)
            and isinstance(name, str)
            and name in referenced_types_by_workspace.get(workspace_id, set())
        ):
            continue

        await db["entry_types"].delete_one({"_id": entry_type_doc["_id"]})
        deleted_count += 1

    return {
        "status": "success",
        "deleted_count": deleted_count,
        "scanned_count": scanned_count,
    }


async def trim_unused_resources_for_user(user_id: str, db) -> dict:
    media_result = await trim_unreferenced_media_for_user(user_id, db)
    entry_type_result = await trim_unused_entry_types_for_user(user_id, db)

    return {
        "status": "success",
        "deleted_count": media_result["deleted_count"]
        + entry_type_result["deleted_count"],
        "scanned_count": media_result["scanned_count"]
        + entry_type_result["scanned_count"],
        "deleted_media_count": media_result["deleted_count"],
        "scanned_media_count": media_result["scanned_count"],
        "deleted_entry_type_count": entry_type_result["deleted_count"],
        "scanned_entry_type_count": entry_type_result["scanned_count"],
    }
