
import os
import sys

from fastapi import File, UploadFile

from app.constants import MEDIA_PATH


def save_media_to_user_directory(user_id: str, media_type: str, file: UploadFile) -> bool:
    # Save the file to the media directory
    try:
        user_directory = os.path.join(MEDIA_PATH, user_id)
        os.makedirs(user_directory, exist_ok=True)
        file_name = file.filename or "unnamed"
        file_location = os.path.join(user_directory, file_name)
        with open(file_location, "wb") as f:
            f.write(file.file.read())
        return True
    
    except Exception as exc:
        print(f"Error occurred while uploading media: {exc}", file=sys.stderr)
        return False