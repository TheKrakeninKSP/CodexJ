"""Soft-delete journals and workspaces so their entries go to the bin.

Revision ID: 8b4d0f2e6a31
Revises: 7a3c9e1d5f20
Create Date: 2026-11-26

Deleting a journal or workspace used to hard-delete its entries and media.
Now the entries are binned and the container is kept as a hidden placeholder
(`deleted_at` set), so binned entries still resolve to their owner through
entry -> journal -> workspace and can be restored along with the journal.
`entry.binned_with_container` marks entries binned as part of that, as opposed
to ones binned individually beforehand. No backfill: until now deleting a
container also deleted its entries, so nothing points at a missing journal.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "8b4d0f2e6a31"
down_revision: Union[str, None] = "7a3c9e1d5f20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(sa.text(f"PRAGMA table_info('{table}')"))}


def upgrade() -> None:
    conn = op.get_bind()
    for table in ("workspace", "journal"):
        if "deleted_at" not in _columns(conn, table):
            op.add_column(
                table, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
            )
    if "binned_with_container" not in _columns(conn, "entry"):
        op.add_column(
            "entry",
            sa.Column(
                "binned_with_container",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    # Binned journals/workspaces reappear as live (empty-looking) ones after a
    # downgrade; their entries stay binned and can be restored as before.
    with op.batch_alter_table("entry") as batch_op:
        batch_op.drop_column("binned_with_container")
    for table in ("journal", "workspace"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_column("deleted_at")
