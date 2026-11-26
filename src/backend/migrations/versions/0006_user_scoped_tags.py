"""Make tags per-user instead of one global list.

Revision ID: 7a3c9e1d5f20
Revises: 5d8e2f6a1b07
Create Date: 2026-11-26

The tag table used to be global with UNIQUE(name), so every user's editor
suggested every other user's tag names. Entries store tag names directly
(entry.tags JSON), so tag rows only feed suggestions; this rebuilds the table
with a user_id column and UNIQUE(user_id, name), then backfills one row per
(user, name) for every tag that user references in an entry (binned included)
or a saved entry version. created_at comes from the old global row when there
was one, else from the earliest referencing entry/version. Old global rows no
entry or version references are dropped - there is no owner to give them to.

SQLite can't drop the old unnamed UNIQUE(name) in place, so the table is
copied out, dropped and recreated.
"""
import json
from datetime import datetime, timezone
from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "7a3c9e1d5f20"
down_revision: Union[str, None] = "5d8e2f6a1b07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Matches how SQLAlchemy's DateTime stores values in SQLite.
_DT_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

# Every tags JSON column a user owns, with its timestamp, via
# entry -> journal -> workspace -> user.
_USER_TAG_SOURCES = """
    SELECT w.user_id, e.tags, e.date_created
    FROM entry e
    JOIN journal j ON e.journal_id = j.id
    JOIN workspace w ON j.workspace_id = w.id
    UNION ALL
    SELECT w.user_id, v.tags, v.created_at
    FROM entry_version v
    JOIN entry e ON v.entry_id = e.id
    JOIN journal j ON e.journal_id = j.id
    JOIN workspace w ON j.workspace_id = w.id
"""


def _parse_tags(raw) -> list[str]:
    try:
        tags = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        return []
    return [t for t in tags if isinstance(t, str) and t] if isinstance(tags, list) else []


def _create_user_scoped_table() -> None:
    op.create_table(
        "tag",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_tag_user_name"),
    )
    op.create_index("ix_tag_user_id", "tag", ["user_id"])


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if "tag" not in tables:
        _create_user_scoped_table()
        return
    if "user_id" in {c["name"] for c in inspector.get_columns("tag")}:
        return  # created by create_all after the ORM change

    old_created: dict[str, str] = {
        name: created
        for name, created in conn.execute(sa.text("SELECT name, created_at FROM tag"))
    }

    # (user_id, name) -> earliest referencing timestamp
    referenced: dict[tuple[str, str], str | None] = {}
    if {"entry", "journal", "workspace", "entry_version"} <= tables:
        for user_id, raw_tags, when in conn.execute(sa.text(_USER_TAG_SOURCES)):
            for name in _parse_tags(raw_tags):
                key = (user_id, name)
                prev = referenced.get(key)
                if key not in referenced or (
                    when is not None and (prev is None or when < prev)
                ):
                    referenced[key] = when

    op.drop_table("tag")
    _create_user_scoped_table()

    now = datetime.now(timezone.utc).strftime(_DT_FORMAT)
    rows = [
        {
            "id": str(uuid4()),
            "user_id": user_id,
            "name": name,
            "created_at": old_created.get(name) or first_seen or now,
        }
        for (user_id, name), first_seen in sorted(referenced.items())
    ]
    if rows:
        conn.execute(
            sa.text(
                "INSERT INTO tag (id, user_id, name, created_at) "
                "VALUES (:id, :user_id, :name, :created_at)"
            ),
            rows,
        )


def downgrade() -> None:
    conn = op.get_bind()
    merged: dict[str, tuple[str, str]] = {}
    for tag_id, name, created in conn.execute(
        sa.text("SELECT id, name, created_at FROM tag")
    ):
        if name not in merged or created < merged[name][1]:
            merged[name] = (tag_id, created)

    op.drop_index("ix_tag_user_id", table_name="tag")
    op.drop_table("tag")
    op.create_table(
        "tag",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    if merged:
        conn.execute(
            sa.text("INSERT INTO tag (id, name, created_at) VALUES (:id, :name, :created_at)"),
            [{"id": i, "name": n, "created_at": c} for n, (i, c) in merged.items()],
        )
