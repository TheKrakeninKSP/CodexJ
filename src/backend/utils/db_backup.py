"""SQLite snapshots for external backup tools (e.g. restic).

A consistent copy of the live database is written to BACKUP_PATH/codexj.db using
`VACUUM INTO`, which is safe to run while the app is serving requests. Only the
latest snapshot is kept - versioning is the job of the external backup tool.
See RESTIC-README.md at the repo root.
"""

import os
import sqlite3
from pathlib import Path

from backend.constants import BACKUP_PATH, DB_PATH

SNAPSHOT_FILENAME = "codexj.db"


def snapshot_database(
    db_path: str = DB_PATH, backup_dir: str = BACKUP_PATH
) -> Path | None:
    """Write a consistent snapshot of the DB to backup_dir, replacing any previous one.

    Returns the snapshot path, or None if the source DB does not exist yet.
    """
    if not os.path.exists(db_path):
        return None

    os.makedirs(backup_dir, exist_ok=True)
    final_path = Path(backup_dir, SNAPSHOT_FILENAME)
    tmp_path = Path(backup_dir, SNAPSHOT_FILENAME + ".tmp")
    # VACUUM INTO refuses to overwrite an existing file (e.g. left by a crash).
    tmp_path.unlink(missing_ok=True)

    # Read-only URI so a missing/moved DB is never silently created empty.
    conn = sqlite3.connect(f"{Path(db_path).as_uri()}?mode=ro", uri=True)
    try:
        conn.execute("VACUUM INTO ?", (str(tmp_path),))
    finally:
        conn.close()

    # Atomic swap: a backup tool reading the folder never sees a half-written file.
    os.replace(tmp_path, final_path)
    return final_path
