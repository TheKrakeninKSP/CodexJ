import os
import sqlite3

from backend.utils.db_backup import (
    SNAPSHOT_FILENAME,
    snapshot_database,
)


def _make_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
    conn.execute("DELETE FROM t")
    conn.executemany("INSERT INTO t VALUES (?)", [(r,) for r in rows])
    conn.commit()
    conn.close()


def _read_rows(path):
    conn = sqlite3.connect(path)
    try:
        return [r[0] for r in conn.execute("SELECT v FROM t ORDER BY v")]
    finally:
        conn.close()


def test_snapshot_copies_db(tmp_path):
    db = tmp_path / "live.db"
    _make_db(db, ["a", "b"])

    out = snapshot_database(str(db), str(tmp_path / "backup"))

    assert out == tmp_path / "backup" / SNAPSHOT_FILENAME
    assert _read_rows(out) == ["a", "b"]


def test_snapshot_keeps_only_latest(tmp_path):
    db = tmp_path / "live.db"
    backup = tmp_path / "backup"
    _make_db(db, ["old"])
    snapshot_database(str(db), str(backup))
    _make_db(db, ["new"])
    # Stale tmp file from a crashed run must not block the next snapshot.
    (backup / (SNAPSHOT_FILENAME + ".tmp")).write_bytes(b"junk")

    out = snapshot_database(str(db), str(backup))

    assert _read_rows(out) == ["new"]
    assert sorted(os.listdir(backup)) == [SNAPSHOT_FILENAME]


def test_snapshot_skips_missing_db(tmp_path):
    db = tmp_path / "missing.db"
    assert snapshot_database(str(db), str(tmp_path / "backup")) is None
    assert not db.exists()
