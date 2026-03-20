import os

from app.utils.utils import get_project_root

BASE_PATH = get_project_root()
MEDIA_PATH = os.path.join(BASE_PATH, "media")
os.makedirs(MEDIA_PATH, exist_ok=True) 