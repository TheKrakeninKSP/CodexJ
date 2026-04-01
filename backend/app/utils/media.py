import os
import shutil
import sys
import uuid
from datetime import datetime, timezone

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


async def trim_unreferenced_media_for_user(user_id: str, db) -> dict:
    """Delete media records/files that are no longer referenced by any of the user's entries."""
    workspace_ids = []
    async for workspace in db["workspaces"].find({"user_id": user_id}, {"_id": 1}):
        workspace_ids.append(str(workspace["_id"]))

    journal_ids = []
    if workspace_ids:
        async for journal in db["journals"].find(
            {"workspace_id": {"$in": workspace_ids}}, {"_id": 1}
        ):
            journal_ids.append(str(journal["_id"]))

    referenced_media_filenames: set[str] = set()
    if journal_ids:
        async for entry in db["entries"].find(
            {"journal_id": {"$in": journal_ids}}, {"media_refs": 1, "body": 1}
        ):
            media_refs = entry.get("media_refs")
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
