"""nullable strategy description/hypothesis; add hypothesis_id

Revision ID: e0f4d3a7b5c2
Revises: d9e3c2f6a4b1
Create Date: 2026-11-26 00:20:00.000000

"""

import re

import sqlalchemy as sa
from alembic import op

revision: str = "e0f4d3a7b5c2"
down_revision: str | None = "d9e3c2f6a4b1"
branch_labels: str | None = None
depends_on: str | None = None

_BARE_ID = re.compile(r"^H\d+$", re.IGNORECASE)


def upgrade() -> None:
    with op.batch_alter_table("strategies", schema=None) as batch_op:
        batch_op.add_column(sa.Column("hypothesis_id", sa.String(length=64), nullable=True))
        batch_op.alter_column("description", existing_type=sa.Text(), nullable=True)
        batch_op.alter_column("hypothesis", existing_type=sa.Text(), nullable=True)

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, version, hypothesis, hypothesis_id FROM strategies")).fetchall()
    for row in rows:
        hyp = (row[2] or "").strip() or None
        hid = (row[3] or "").strip() or None
        if hyp and _BARE_ID.fullmatch(hyp):
            new_hid = hid or hyp
            conn.execute(
                sa.text(
                    "UPDATE strategies SET hypothesis_id = :hid, hypothesis = NULL "
                    "WHERE id = :id AND version = :version"
                ),
                {"hid": new_hid, "id": row[0], "version": row[1]},
            )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE strategies SET hypothesis = hypothesis_id "
            "WHERE (hypothesis IS NULL OR hypothesis = '') AND hypothesis_id IS NOT NULL"
        )
    )
    conn.execute(sa.text("UPDATE strategies SET description = '' WHERE description IS NULL"))
    conn.execute(sa.text("UPDATE strategies SET hypothesis = '' WHERE hypothesis IS NULL"))
    with op.batch_alter_table("strategies", schema=None) as batch_op:
        batch_op.alter_column("description", existing_type=sa.Text(), nullable=False)
        batch_op.alter_column("hypothesis", existing_type=sa.Text(), nullable=False)
        batch_op.drop_column("hypothesis_id")
