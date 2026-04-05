import os
import sys

from app.utils.utils import get_project_root

APP_VERSION = "1.1.0"

BASE_PATH = get_project_root()
MEDIA_PATH = os.path.join(BASE_PATH, "media")
os.makedirs(MEDIA_PATH, exist_ok=True)
DUMPS_PATH = os.path.join(BASE_PATH, "dumps")
os.makedirs(DUMPS_PATH, exist_ok=True)

# SingleFile CLI binary
_exe_name = "single-file.exe" if sys.platform == "win32" else "single-file"
if getattr(sys, "frozen", False):
    # PyInstaller bundle: binary is placed in _MEIPASS (_internal/) directory
    SINGLEFILE_EXE = os.path.join(getattr(sys, "_MEIPASS", BASE_PATH), _exe_name)
else:
    # Development: binary lives in backend/vendor/
    _vendor_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "vendor")
    )
    SINGLEFILE_EXE = os.path.join(_vendor_dir, _exe_name)

ENTRY_TYPE_NAME_MAX_LENGTH = 256
ENTRY_NAME_MAX_LENGTH = 256
JOURNAL_NAME_MAX_LENGTH = 256
JOURNAL_DESCRIPTION_MAX_LENGTH = 512
WORKSPACE_NAME_MAX_LENGTH = 128

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 64
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
