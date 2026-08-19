"""resource location varies depending on whether the app is run from source or as a PyInstaller bundle
this module provides utility functions to find the correct resource paths in either case
"""

import sys
from pathlib import Path


def get_project_root():
    """Get the root directory of the project if run from source or the directory of the frozen executable if run as a PyInstaller bundle"""
    if is_dev_env():
        # Running from source, get project root (src/backend/utils/utils.py)
        return Path(__file__).resolve().parent.parent.parent.parent
    else:
        return Path(__file__).resolve().parent.parent


def get_resource_path(dev_path: str, resource_name: str) -> Path:
    """Get the path to the resources directory (for PyInstaller)"""
    if is_dev_env():
        return (
            Path(__file__).resolve().parent.parent.parent.parent
            / dev_path
            / resource_name
        )
    else:
        return Path(__file__).resolve().parent / resource_name


def is_dev_env() -> bool:
    """Check if the application is running in a development environment (not frozen)"""
    return not (getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))
