import os
from pathlib import Path


def dir_usage(path: Path) -> tuple[int, int]:
    """(file_count, total_bytes) for every file under `path`; (0, 0) if missing."""
    files = 0
    total = 0
    for root, _dirs, names in os.walk(path):
        for name in names:
            try:
                total += os.stat(os.path.join(root, name)).st_size
                files += 1
            except OSError:
                # File vanished mid-walk (e.g. concurrent media cleanup).
                continue
    return files, total
