import os
import sys
import uuid
from datetime import datetime, timezone

from app.constants import MEDIA_PATH
from app.models.media import DB_Media
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
        url = f"http://localhost:8000/media/{user_id}/{stored_filename}"

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
        result = await db["media"].insert_one(media.model_dump())
        return {"status": True, "url": url, "media_id": str(result.inserted_id)}

    except Exception as exc:
        print(f"Error occurred while uploading media: {exc}", file=sys.stderr)
        return {"status": False, "url": None, "media_id": None}


def delete_media_file(user_id: str, stored_filename: str) -> None:
    try:
        file_location = os.path.join(MEDIA_PATH, user_id, stored_filename)
        if os.path.exists(file_location):
            os.remove(file_location)
    except Exception as exc:
        print(f"Error occurred while deleting media file: {exc}", file=sys.stderr)
