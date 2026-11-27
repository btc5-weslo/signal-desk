"""approvals, tenant isolation, signal calibration columns

Revision ID: b7c1a0d4e2f1
Revises: 07ef422cceba
Create Date: 2026-11-25 23:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c1a0d4e2f1"
down_revision: str | Sequence[str] | None = "07ef422cceba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backtest_approvals",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("data_hash", sa.String(length=128), nullable=False),
        sa.Column("reviewer", sa.String(length=200), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("run_id", "data_hash"),
    )

    with op.batch_alter_table("signals", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "tenant_id", sa.String(length=64), nullable=False, server_default="_pending",
        ))
        batch_op.add_column(sa.Column(
            "confidence_calibrated", sa.Boolean(), nullable=False, server_default=sa.false(),
        ))
        batch_op.add_column(sa.Column("calibration_run_id", sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f("ix_signals_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_foreign_key("fk_signals_tenant_id", "tenants", ["tenant_id"], ["id"])
        batch_op.alter_column("tenant_id", server_default=None)
        batch_op.alter_column("confidence_calibrated", server_default=None)

    with op.batch_alter_table("strategies", schema=None) as batch_op:
        # Nullable: NULL = shared catalog row visible to every tenant.
        batch_op.add_column(sa.Column("tenant_id", sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f("ix_strategies_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_foreign_key("fk_strategies_tenant_id", "tenants", ["tenant_id"], ["id"])

    with op.batch_alter_table("backtest_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "tenant_id", sa.String(length=64), nullable=False, server_default="_pending",
        ))
        batch_op.create_index(batch_op.f("ix_backtest_runs_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_foreign_key("fk_backtest_runs_tenant_id", "tenants", ["tenant_id"], ["id"])
        batch_op.drop_column("qa_approved")
        batch_op.alter_column("tenant_id", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("backtest_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("qa_approved", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.drop_constraint("fk_backtest_runs_tenant_id", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_backtest_runs_tenant_id"))
        batch_op.drop_column("tenant_id")
        batch_op.alter_column("qa_approved", server_default=None)

    with op.batch_alter_table("strategies", schema=None) as batch_op:
        batch_op.drop_constraint("fk_strategies_tenant_id", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_strategies_tenant_id"))
        batch_op.drop_column("tenant_id")

    with op.batch_alter_table("signals", schema=None) as batch_op:
        batch_op.drop_constraint("fk_signals_tenant_id", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_signals_tenant_id"))
        batch_op.drop_column("calibration_run_id")
        batch_op.drop_column("confidence_calibrated")
        batch_op.drop_column("tenant_id")

    op.drop_table("backtest_approvals")
