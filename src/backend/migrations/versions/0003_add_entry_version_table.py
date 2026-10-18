"""Add entry_version table for version history tracking.

Revision ID: 3a9f1c7e2d40
Revises: e7f4a2c6d8b0
Create Date: 2026-10-18

Creates the entry_version table that stores HTML body snapshots whenever
an entry with track-versions enabled is saved. The guard against
pre-existing tables makes the migration safe on fresh installs where
init_db() already ran after the ORM was updated.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "3a9f1c7e2d40"
down_revision: Union[str, None] = "e7f4a2c6d8b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "entry_version" not in inspector.get_table_names():
        op.create_table(
            "entry_version",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("entry_id", sa.String(36), sa.ForeignKey("entry.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("body", sa.Text(), nullable=False, server_default=""),
            sa.Column("tags", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("media_refs", sa.Text(), nullable=False, server_default="[]"),
        )
        op.create_index("ix_entry_version_entry_id", "entry_version", ["entry_id"])


def downgrade() -> None:
    op.drop_index("ix_entry_version_entry_id", table_name="entry_version")
    op.drop_table("entry_version")
