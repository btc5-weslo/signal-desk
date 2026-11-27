"""global backtests/signals, tagline, exits, pipeline cursors, alert channels

Revision ID: d9e3c2f6a4b1
Revises: c8d2b1e5f3a0
Create Date: 2026-11-25 23:30:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision: str = "d9e3c2f6a4b1"
down_revision: str | None = "c8d2b1e5f3a0"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("tenants", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tagline", sa.Text(), nullable=True))

    with op.batch_alter_table("signals", schema=None) as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.String(length=64), nullable=True)
        batch_op.add_column(sa.Column("exit_time", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("exit_price", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("exit_reason", sa.String(length=16), nullable=True))
        batch_op.create_unique_constraint(
            "ux_signals_dedupe",
            ["strategy_id", "strategy_version", "symbol", "timeframe", "bar_close_time"],
        )

    with op.batch_alter_table("backtest_runs", schema=None) as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.String(length=64), nullable=True)

    op.create_table(
        "pipeline_cursors",
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=4), nullable=False),
        sa.Column("last_close_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "timeframe"),
    )
    op.create_table(
        "alert_channels",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("channel_type", sa.String(length=20), nullable=False),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_channels_tenant_id", "alert_channels", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_alert_channels_tenant_id", table_name="alert_channels")
    op.drop_table("alert_channels")
    op.drop_table("pipeline_cursors")
    with op.batch_alter_table("backtest_runs", schema=None) as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.String(length=64), nullable=False)
    with op.batch_alter_table("signals", schema=None) as batch_op:
        batch_op.drop_constraint("ux_signals_dedupe", type_="unique")
        batch_op.drop_column("exit_reason")
        batch_op.drop_column("exit_price")
        batch_op.drop_column("exit_time")
        batch_op.alter_column("tenant_id", existing_type=sa.String(length=64), nullable=False)
    with op.batch_alter_table("tenants", schema=None) as batch_op:
        batch_op.drop_column("tagline")
