"""Migration 0006: global tags -> per-user tags, backfilled from entries + versions."""

import json
import sqlite3

import pytest
from alembic import command
from alembic.config import Config

import backend.constants
from backend.constants import MIGRATIONS_PATH

PRE_TAG_SCOPING = "5d8e2f6a1b07"
TAG_SCOPING = "7a3c9e1d5f20"

# Just the columns migration 0006 reads, in the pre-0006 shape.
_OLD_SCHEMA = """
CREATE TABLE user (id VARCHAR(36) PRIMARY KEY);
CREATE TABLE workspace (id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36));
CREATE TABLE journal (id VARCHAR(36) PRIMARY KEY, workspace_id VARCHAR(36));
CREATE TABLE entry (
    id VARCHAR(36) PRIMARY KEY, journal_id VARCHAR(36), tags TEXT, date_created DATETIME
);
CREATE TABLE entry_version (
    id VARCHAR(36) PRIMARY KEY, entry_id VARCHAR(36), tags TEXT, created_at DATETIME
);
CREATE TABLE tag (
    id VARCHAR(36) NOT NULL, name VARCHAR NOT NULL, created_at DATETIME NOT NULL,
    PRIMARY KEY (id), UNIQUE (name)
);
CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);
"""


@pytest.fixture
def old_db(tmp_path, monkeypatch):
    db = tmp_path / "pre_tag_scoping.db"
    con = sqlite3.connect(db)
    con.executescript(_OLD_SCHEMA)
    rows = {
        "user": [("alice",), ("bob",)],
        "workspace": [("wa", "alice"), ("wb", "bob")],
        "journal": [("ja", "wa"), ("jb", "wb")],
        "entry": [
            ("ea", "ja", json.dumps(["shared", "alice-only"]), "2026-03-01 00:00:00.000000"),
            ("eb", "jb", json.dumps(["shared"]), "2026-04-01 00:00:00.000000"),
            ("eb2", "jb", "not json", "2026-04-02 00:00:00.000000"),
        ],
        # "draft" was removed from alice's entry but survives in a saved version.
        "entry_version": [
            ("va", "ea", json.dumps(["draft", "shared"]), "2026-02-01 00:00:00.000000"),
        ],
        "tag": [
            ("t1", "shared", "2026-01-01 00:00:00.000000"),
            ("t2", "nobody-uses-this", "2026-01-01 00:00:00.000000"),
        ],
        "alembic_version": [(PRE_TAG_SCOPING,)],
    }
    for table, values in rows.items():
        marks = ",".join("?" * len(values[0]))
        con.executemany(f'INSERT INTO "{table}" VALUES ({marks})', values)
    con.commit()
    con.close()

    monkeypatch.setattr(backend.constants, "SQLITE_DB_URL", f"sqlite:///{db.as_posix()}")
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_PATH))
    return db, cfg


def _tags(db) -> dict[tuple[str, str], str]:
    con = sqlite3.connect(db)
    try:
        return {
            (user_id, name): created
            for user_id, name, created in con.execute(
                "SELECT user_id, name, created_at FROM tag"
            )
        }
    finally:
        con.close()


def test_backfills_one_tag_per_user_reference(old_db):
    db, cfg = old_db
    command.upgrade(cfg, TAG_SCOPING)

    tags = _tags(db)
    assert set(tags) == {
        ("alice", "shared"),
        ("alice", "alice-only"),
        ("alice", "draft"),  # only in a saved version
        ("bob", "shared"),
    }
    # Old global row's timestamp is kept for names it had...
    assert tags[("alice", "shared")] == "2026-01-01 00:00:00.000000"
    assert tags[("bob", "shared")] == "2026-01-01 00:00:00.000000"
    # ...otherwise the earliest referencing entry/version wins.
    assert tags[("alice", "alice-only")] == "2026-03-01 00:00:00.000000"
    assert tags[("alice", "draft")] == "2026-02-01 00:00:00.000000"


def test_same_name_allowed_across_users_but_not_within(old_db):
    db, cfg = old_db
    command.upgrade(cfg, TAG_SCOPING)

    con = sqlite3.connect(db)
    try:
        con.execute(
            "INSERT INTO tag VALUES ('x1', 'bob', 'alice-only', '2026-05-01 00:00:00.000000')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                "INSERT INTO tag VALUES ('x2', 'bob', 'alice-only', '2026-05-01 00:00:00.000000')"
            )
    finally:
        con.close()


def test_downgrade_merges_back_to_global(old_db):
    db, cfg = old_db
    command.upgrade(cfg, TAG_SCOPING)
    command.downgrade(cfg, PRE_TAG_SCOPING)

    con = sqlite3.connect(db)
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info('tag')")]
        names = sorted(r[0] for r in con.execute("SELECT name FROM tag"))
    finally:
        con.close()
    assert "user_id" not in cols
    assert names == ["alice-only", "draft", "shared"]
