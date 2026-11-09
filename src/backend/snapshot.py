"""Write a consistent snapshot of the CodexJ database to backup/codexj.db.

Usage (from src/, like backend.serve):
    python -m backend.snapshot

Safe to run while the server is running. Only the latest snapshot is kept;
restic (or similar) provides history. Scheduled on Linux by
packaging/codexj-backup.timer - see RESTIC-README.md.
"""

import sys

from backend.utils.db_backup import snapshot_database


def main() -> int:
    try:
        path = snapshot_database()
    except Exception as exc:
        sys.stderr.write(f"DB snapshot failed: {exc}\n")
        return 1
    if path is None:
        sys.stderr.write("DB snapshot skipped: database file does not exist\n")
        return 1
    print(f"DB snapshot written to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
