import os
import sys

from .utils import utils

APP_VERSION = "1.2.0"

BASE_PATH = utils.get_project_root()
MEDIA_PATH = os.path.join(BASE_PATH, "media")
os.makedirs(MEDIA_PATH, exist_ok=True)
DUMPS_PATH = os.path.join(BASE_PATH, "dumps")
os.makedirs(DUMPS_PATH, exist_ok=True)
DEPS_PATH = os.path.join(BASE_PATH, "deps")
os.makedirs(DEPS_PATH, exist_ok=True)
RESOURCES_PATH = os.path.join(BASE_PATH, "resources")
os.makedirs(RESOURCES_PATH, exist_ok=True)
STATIC_PATH = utils.get_resource_path(dev_path=RESOURCES_PATH, resource_name="static")

# SingleFile CLI binary
single_file_exe_name = "single-file.exe" if sys.platform == "win32" else "single-file"
SINGLE_FILE = utils.get_resource_path(
    dev_path=DEPS_PATH, resource_name=single_file_exe_name
)
fpcalc_exe_name = "fpcalc.exe" if sys.platform == "win32" else "fpcalc"
FPCALC = utils.get_resource_path(dev_path=DEPS_PATH, resource_name=fpcalc_exe_name)


ENTRY_TYPE_NAME_MAX_LENGTH = 256
ENTRY_NAME_MAX_LENGTH = 256
JOURNAL_NAME_MAX_LENGTH = 256
JOURNAL_DESCRIPTION_MAX_LENGTH = 512
WORKSPACE_NAME_MAX_LENGTH = 128

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 64
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
