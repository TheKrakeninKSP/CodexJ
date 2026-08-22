import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone

from fastapi import UploadFile

from backend.constants import MEDIA_PATH
from backend.database.querying import (
    create_media,
    delete_media_by_id,
    get_entries_by_journal_id,
    get_entries_for_user,
    get_journals_by_workspace_id,
    get_media_by_user_id,
    get_workspaces_by_user_id,
)
from backend.database.structural import MediaModel
from backend.type_defs import id_type


async def save_media_to_user_directory(
    user_id: id_type, media_type: str, file: UploadFile, db
) -> dict:
    # Save the file to the media directory with a unique UUID-based filename
    try:
        user_directory = os.path.join(MEDIA_PATH, str(user_id))
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
        media = MediaModel(
            user_id=user_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            media_type=media_type,
            file_size=len(contents),
            resource_path=url,
            status="completed",
            custom_metadata=json.dumps({}),
            created_at=datetime.now(timezone.utc),
        )
        create_media(media)
        return {
            "status": True,
            "media": {
                "id": media.id,
                "user_id": media.user_id,
                "original_filename": media.original_filename,
                "stored_filename": media.stored_filename,
                "media_type": media.media_type,
                "file_size": media.file_size,
                "resource_path": media.resource_path,
                "status": media.status,
                "custom_metadata": {},
                "error_message": media.error_message,
                "created_at": media.created_at,
            },
            "file_path": file_location,
        }

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


def _collect_user_workspace_ids(user_id: id_type) -> list[id_type]:
    return [workspace.id for workspace in get_workspaces_by_user_id(user_id)]


def _collect_workspace_journals(workspace_ids: list[id_type]) -> list[id_type]:
    return [
        journal.id
        for workspace_id in workspace_ids
        for journal in get_journals_by_workspace_id(workspace_id)
    ]


async def trim_unreferenced_media_for_user(user_id: id_type, db=None) -> dict:
    """Delete media records/files that are no longer referenced by any of the user's entries."""
    workspace_ids = _collect_user_workspace_ids(user_id)
    journal_ids = _collect_workspace_journals(workspace_ids)

    referenced_media_filenames: set[str] = set()
    entries = [
        entry
        for journal_id in journal_ids
        for entry in get_entries_by_journal_id(journal_id)
    ]
    entries.extend(get_entries_for_user(user_id, deleted=True))
    for entry in entries:
        media_refs = json.loads(entry.media_refs or "[]")
        for media_ref in media_refs:
            if isinstance(media_ref, str) and media_ref:
                ref_without_query = media_ref.split("?", 1)[0].rstrip("/")
                referenced_name = ref_without_query.rsplit("/", 1)[-1]
                if referenced_name:
                    referenced_media_filenames.add(referenced_name)

    deleted_count = 0
    scanned_count = 0

    for media_doc in get_media_by_user_id(user_id):
        scanned_count += 1
        stored_filename = media_doc.stored_filename
        if (
            isinstance(stored_filename, str)
            and stored_filename in referenced_media_filenames
        ):
            continue

        if isinstance(stored_filename, str) and stored_filename:
            delete_media_file(str(user_id), stored_filename)
        if delete_media_by_id(media_doc.id):
            deleted_count += 1

    return {
        "status": "success",
        "deleted_count": deleted_count,
        "scanned_count": scanned_count,
    }


async def trim_unused_resources_for_user(user_id: str, db) -> dict:
    media_result = await trim_unreferenced_media_for_user(int(user_id), db)

    return {
        "status": "success",
        "deleted_count": media_result["deleted_count"],
        "scanned_count": media_result["scanned_count"],
        "deleted_media_count": media_result["deleted_count"],
        "scanned_media_count": media_result["scanned_count"],
        "deleted_entry_type_count": 0,
        "scanned_entry_type_count": 0,
    }
