import sys
from pathlib import Path


def get_project_root():
    """Get the root directory of the project if run from source or the directory of the frozen executable if run as a PyInstaller bundle"""
    if getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent.parent
    else:
        # Running from source, get project root (src/backend/utils/utils.py)
        return Path(__file__).resolve().parent.parent.parent.parent


def get_resource_path(dev_path: str, resource_name: str) -> Path:
    """Get the path to the resources directory (for PyInstaller)"""
    if getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent / resource_name
    else:
        return (
            Path(__file__).resolve().parent.parent.parent.parent
            / dev_path
            / resource_name
        )
