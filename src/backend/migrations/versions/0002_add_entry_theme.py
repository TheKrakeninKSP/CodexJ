"""Add theme column to entry table.

Revision ID: e7f4a2c6d8b0
Revises: b1e3c8d2a9f1
Create Date: 2026-10-17

Adds a nullable TEXT column `theme` that stores an EntryTheme JSON object
(bg_color, font_color, audio media-id). The check for column existence makes
the migration safe on databases created after the ORM was updated but before
this migration ran (create_all already added the column for those installs).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7f4a2c6d8b0"
down_revision: Union[str, None] = "b1e3c8d2a9f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("PRAGMA table_info('entry')"))
    col_names = {row[1] for row in result}
    if "theme" not in col_names:
        op.add_column("entry", sa.Column("theme", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("entry") as batch_op:
        batch_op.drop_column("theme")
