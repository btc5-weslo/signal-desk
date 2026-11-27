"""Production schema (Postgres, TimescaleDB-ready: signals can become a hypertable on generated_at).

Tenant isolation:
- signals.tenant_id and backtest_runs.tenant_id are nullable. NULL means a
  global (shared) row visible to every tenant; a non-null value is private.
  Live pipeline signals are stored with tenant_id NULL.
- strategies.tenant_id is nullable. NULL means a shared catalog row visible
  to every tenant; a non-null value is a tenant-private strategy. v1 mock
  strategies are global (NULL).
- backtest_approvals.tenant_id is nullable. NULL is a global approval any
  tenant may use for confidence calibration; a non-null value is private.
Approval is not a flag on the report: a backtest is served only when a
matching backtest_approvals row exists for the report's run_id and data_hash.
Host -> tenant lookups use tenant_domains (hostname, no port, lowercase).
"""
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    branding: Mapped[dict] = mapped_column(JSON, default=dict)  # white-label theme tokens
    tagline: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TenantDomain(Base):
    """Host header -> tenant. Hostname is stored lowercase, without a port."""
    __tablename__ = "tenant_domains"
    host: Mapped[str] = mapped_column(String(253), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="user")  # user|admin
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True)  # sha256, raw key never stored
    label: Mapped[str] = mapped_column(String(100), default="")
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StrategyRow(Base):
    __tablename__ = "strategies"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    # NULL = shared catalog row, visible to every tenant.
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    hypothesis_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    asset_classes: Mapped[list] = mapped_column(JSON)
    timeframes: Mapped[list] = mapped_column(JSON)
    latest_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SignalRow(Base):
    __tablename__ = "signals"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # NULL = global live-pipeline signal, visible to every tenant (subject to
    # per-market QA approval).
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    strategy_id: Mapped[str] = mapped_column(String(64))
    strategy_version: Mapped[str] = mapped_column(String(32))
    symbol: Mapped[str] = mapped_column(String(32))
    asset_class: Mapped[str] = mapped_column(String(10))
    timeframe: Mapped[str] = mapped_column(String(4))
    side: Mapped[str] = mapped_column(String(5))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    bar_close_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    entry: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[list] = mapped_column(JSON, default=list)
    horizon_bars: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float)
    features_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    rationale: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="active")
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence_calibrated: Mapped[bool] = mapped_column(Boolean, default=False)
    calibration_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)
    __table_args__ = (
        Index("ix_signals_sym_tf_time", "symbol", "timeframe", "generated_at"),
        UniqueConstraint(
            "strategy_id", "strategy_version", "symbol", "timeframe", "bar_close_time",
            name="ux_signals_dedupe",
        ),
    )


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # NULL = global run, visible to every tenant once QA-approved.
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    strategy_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(32))
    report: Mapped[dict] = mapped_column(JSON)  # full BacktestReport JSON from /data
    data_hash: Mapped[str] = mapped_column(String(128))
    # Per-market identity; both null on the strategy-summary report.
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    timeframe: Mapped[str | None] = mapped_column(String(4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        Index(
            "ix_backtest_runs_market",
            "tenant_id", "strategy_id", "version", "symbol", "timeframe",
        ),
    )


class BacktestApproval(Base):
    """QA sign-off for a specific (run_id, data_hash). Served only on an exact match.

    tenant_id NULL means a global approval that any tenant may use for
    calibration; a non-null value is tenant-private.
    """
    __tablename__ = "backtest_approvals"
    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    data_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    reviewer: Mapped[str] = mapped_column(String(200))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    notes: Mapped[str] = mapped_column(Text, default="")
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)


class PipelineCursor(Base):
    """Last processed closed-bar time per symbol/timeframe (live pipeline)."""
    __tablename__ = "pipeline_cursors"
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(4), primary_key=True)
    last_close_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AlertChannel(Base):
    """Per-tenant alert destination. Secrets are referenced by env var name only."""
    __tablename__ = "alert_channels"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    channel_type: Mapped[str] = mapped_column(String(20))  # email, telegram, discord, webpush
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
