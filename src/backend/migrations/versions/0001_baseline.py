"""Baseline – all tables without the entry theme column.

Revision ID: b1e3c8d2a9f1
Revises:
Create Date: 2026-10-17

No-op for existing databases that pre-date Alembic. Run
  alembic stamp b1e3c8d2a9f1
on any database that was created before this migration system was introduced,
then run `alembic upgrade head` to apply subsequent changes.
"""
from typing import Sequence, Union

revision: str = "b1e3c8d2a9f1"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
