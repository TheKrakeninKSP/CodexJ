"""Rewrite absolute localhost media URLs to relative ones.

Revision ID: 9c2b7a1f4e3d
Revises: 3a9f1c7e2d40
Create Date: 2026-10-19

build_media_url() used to hardcode `http://localhost:8128`, which gets baked
directly into entry.body/media_refs (and entry_version snapshots) at save
time. That's fine for the desktop app (client and server are always the same
machine) but breaks media loading entirely once the backend is reachable from
a different host, e.g. a headless server accessed over the network. This
rewrites already-stored content to use the new relative form (`/media/...`),
which resolves correctly against whatever origin the client actually used.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9c2b7a1f4e3d"
down_revision: Union[str, None] = "3a9f1c7e2d40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_PREFIX = "http://localhost:8128/media/"
_NEW_PREFIX = "/media/"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    table_names = set(inspector.get_table_names())

    if "entry" in table_names:
        conn.execute(
            sa.text(
                "UPDATE entry SET body = REPLACE(body, :old, :new), "
                "media_refs = REPLACE(media_refs, :old, :new) "
                "WHERE body LIKE :pattern OR media_refs LIKE :pattern"
            ),
            {"old": _OLD_PREFIX, "new": _NEW_PREFIX, "pattern": f"%{_OLD_PREFIX}%"},
        )

    if "entry_version" in table_names:
        conn.execute(
            sa.text(
                "UPDATE entry_version SET body = REPLACE(body, :old, :new), "
                "media_refs = REPLACE(media_refs, :old, :new) "
                "WHERE body LIKE :pattern OR media_refs LIKE :pattern"
            ),
            {"old": _OLD_PREFIX, "new": _NEW_PREFIX, "pattern": f"%{_OLD_PREFIX}%"},
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    table_names = set(inspector.get_table_names())

    # Best-effort: only restores refs that look like media src/data-src
    # attribute values (quote-anchored) to avoid touching unrelated text.
    if "entry" in table_names:
        conn.execute(
            sa.text(
                'UPDATE entry SET body = REPLACE(body, \'="{new}\', \'="{old}\'), '
                'media_refs = REPLACE(media_refs, \'"{new}\', \'"{old}\')'.format(
                    new=_NEW_PREFIX, old=_OLD_PREFIX
                )
            )
        )

    if "entry_version" in table_names:
        conn.execute(
            sa.text(
                'UPDATE entry_version SET body = REPLACE(body, \'="{new}\', \'="{old}\'), '
                'media_refs = REPLACE(media_refs, \'"{new}\', \'"{old}\')'.format(
                    new=_NEW_PREFIX, old=_OLD_PREFIX
                )
            )
        )
