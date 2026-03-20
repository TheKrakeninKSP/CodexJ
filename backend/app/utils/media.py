import os
import sys

from app.constants import MEDIA_PATH
from fastapi import File, UploadFile


async def save_media_to_user_directory(
    user_id: str, media_type: str, file: UploadFile
) -> dict:
    # Save the file to the media directory
    try:
        user_directory = os.path.join(MEDIA_PATH, user_id)
        os.makedirs(user_directory, exist_ok=True)
        file_name = file.filename or "unnamed"
        file_location = os.path.join(user_directory, file_name)
        url = f"http://localhost:8000/media/{user_id}/{file_name}"
        contents = await file.read()
        with open(file_location, "wb") as f:
            f.write(contents)
        return {"status": True, "url": url}

    except Exception as exc:
        print(f"Error occurred while uploading media: {exc}", file=sys.stderr)
        return {"status": False, "url": None}
