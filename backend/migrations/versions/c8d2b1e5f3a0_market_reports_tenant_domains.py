"""per-market backtests, approval tenant, tenant_domains

Revision ID: c8d2b1e5f3a0
Revises: b7c1a0d4e2f1
Create Date: 2026-11-25 23:16:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision: str = "c8d2b1e5f3a0"
down_revision: str | None = "b7c1a0d4e2f1"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("backtest_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("symbol", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("timeframe", sa.String(length=4), nullable=True))
        batch_op.create_index(
            "ix_backtest_runs_market",
            ["tenant_id", "strategy_id", "version", "symbol", "timeframe"],
            unique=False,
        )

    with op.batch_alter_table("backtest_approvals", schema=None) as batch_op:
        # NULL = global approval, usable by any tenant for calibration.
        batch_op.add_column(sa.Column("tenant_id", sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f("ix_backtest_approvals_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_backtest_approvals_tenant_id", "tenants", ["tenant_id"], ["id"]
        )

    op.create_table(
        "tenant_domains",
        sa.Column("host", sa.String(length=253), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("host"),
    )
    op.create_index(op.f("ix_tenant_domains_tenant_id"), "tenant_domains", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tenant_domains_tenant_id"), table_name="tenant_domains")
    op.drop_table("tenant_domains")

    with op.batch_alter_table("backtest_approvals", schema=None) as batch_op:
        batch_op.drop_constraint("fk_backtest_approvals_tenant_id", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_backtest_approvals_tenant_id"))
        batch_op.drop_column("tenant_id")

    with op.batch_alter_table("backtest_runs", schema=None) as batch_op:
        batch_op.drop_index("ix_backtest_runs_market")
        batch_op.drop_column("timeframe")
        batch_op.drop_column("symbol")
