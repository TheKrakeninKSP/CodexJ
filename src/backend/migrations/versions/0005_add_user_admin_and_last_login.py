"""Add is_admin and last_login_at columns to the user table.

Revision ID: 5d8e2f6a1b07
Revises: 9c2b7a1f4e3d
Create Date: 2026-11-26

`is_admin` gates the admin dashboard (GET /admin/overview). It defaults to
false for every existing user - grant it with
`python -m backend.admin promote <username>`. `last_login_at` is stamped on
login/unlock/register; it stays NULL for users who haven't logged in since
this migration ran. Column-existence checks keep this safe on databases where
create_all already added the columns.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "5d8e2f6a1b07"
down_revision: Union[str, None] = "9c2b7a1f4e3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("PRAGMA table_info('user')"))
    col_names = {row[1] for row in result}
    if "is_admin" not in col_names:
        op.add_column(
            "user",
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="0"),
        )
    if "last_login_at" not in col_names:
        op.add_column(
            "user",
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_column("last_login_at")
        batch_op.drop_column("is_admin")
