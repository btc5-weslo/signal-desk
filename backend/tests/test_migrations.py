from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core.config import get_settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "tenants", "users", "api_keys", "strategies", "signals",
    "backtest_runs", "backtest_approvals", "tenant_domains",
    "pipeline_cursors", "alert_channels",
}


@pytest.fixture
def sqlite_url(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'migrate.db'}"
    monkeypatch.setenv("SIGNAL_DATABASE_URL", url)
    get_settings.cache_clear()
    yield url
    get_settings.cache_clear()


def _cols(engine, table):
    return {c["name"]: c for c in inspect(engine).get_columns(table)}


def test_alembic_upgrade_creates_tables(sqlite_url):
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(cfg, "head")
    engine = create_engine(sqlite_url)
    tables = set(inspect(engine).get_table_names())
    missing = EXPECTED - tables
    assert not missing, f"missing tables: {missing}"
    assert "alembic_version" in tables

    signals = _cols(engine, "signals")
    assert signals["tenant_id"]["nullable"] is True
    assert "confidence_calibrated" in signals and "calibration_run_id" in signals
    assert "exit_time" in signals and "exit_price" in signals and "exit_reason" in signals
    uq = {u["name"] for u in inspect(engine).get_unique_constraints("signals")}
    assert "ux_signals_dedupe" in uq
    strategies = _cols(engine, "strategies")
    assert strategies["tenant_id"]["nullable"] is True
    assert "hypothesis_id" in strategies and strategies["hypothesis_id"]["nullable"] is True
    assert strategies["description"]["nullable"] is True
    assert strategies["hypothesis"]["nullable"] is True
    runs = _cols(engine, "backtest_runs")
    assert runs["tenant_id"]["nullable"] is True
    assert "qa_approved" not in runs
    assert "symbol" in runs and "timeframe" in runs
    assert runs["symbol"]["nullable"] is True and runs["timeframe"]["nullable"] is True
    approvals = _cols(engine, "backtest_approvals")
    assert set(approvals) >= {"run_id", "data_hash", "reviewer", "approved_at", "notes", "tenant_id"}
    assert approvals["tenant_id"]["nullable"] is True
    domains = _cols(engine, "tenant_domains")
    assert set(domains) >= {"host", "tenant_id"}
    idx_names = {i["name"] for i in inspect(engine).get_indexes("backtest_runs")}
    assert "ix_backtest_runs_market" in idx_names

    tenants = _cols(engine, "tenants")
    assert "tagline" in tenants and tenants["tagline"]["nullable"] is True
    cursors = _cols(engine, "pipeline_cursors")
    assert set(cursors) >= {"symbol", "timeframe", "last_close_time", "updated_at"}
    channels = _cols(engine, "alert_channels")
    assert set(channels) >= {"id", "tenant_id", "channel_type", "config", "enabled"}
