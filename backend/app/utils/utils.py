import os
import sys


def get_project_root():
    """Get the root directory of the project"""
    if getattr(sys, "frozen", False):
        # Running from PyInstaller bundle
        return os.path.dirname(sys.executable)
    else:
        # Running from source
        return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
