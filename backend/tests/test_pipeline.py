"""Live pipeline: detect, emit, track, visibility. No hardcoded store prices/counts."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from signal_shared import ExitReason, Signal, SignalStatus

from app.core.config import Settings
from app.pipeline.detect import detect_new_closed_bars
from app.pipeline.emit import deterministic_signal_id, prepare_live_signal
from app.pipeline.hooks import apply_stale_and_gaps, slice_closed
from app.pipeline.runner import run_pipeline
from app.pipeline.tracker import track_open_signals
from app.pipeline.visibility import is_live_signal_visible
from app.services.repository import MockRepository
from tests.test_contract import _report, _signal


def _e2e_data_dir() -> Path | None:
    """Store root for the optional e2e test (SIGNAL_DATA_DIR or repo data/store)."""
    env = (os.environ.get("SIGNAL_DATA_DIR") or "").strip()
    if env:
        return Path(env)
    sibling = Path(__file__).resolve().parents[2] / "data" / "store"
    if (sibling / "crypto" / "BTC-USDT" / "1h.parquet").is_file():
        return sibling
    return None


_E2E_DATA_DIR = _e2e_data_dir()
REAL_BTC = (
    _E2E_DATA_DIR / "crypto" / "BTC-USDT" / "1h.parquet"
    if _E2E_DATA_DIR is not None else Path()
)


def _bars(tmp_path, *, symbol="BTC-USDT", timeframe="1h", n=4, start=None, stale_at=None):
    start = start or datetime(2026, 1, 1, tzinfo=UTC)
    step = timedelta(hours=1)
    rows = []
    for i in range(n):
        t = start + i * step
        stale = stale_at is not None and i == stale_at
        rows.append({
            "open_time": t,
            "close_time": t + step,
            "open": 100.0 + i,
            "high": 101.0 + i,
            "low": 99.0 + i,
            "close": 100.5 + i,
            "volume": 0.0 if stale else 10.0 + i,
            "source": "test",
            "is_stale": stale,
        })
        if stale:
            rows[-1].update(high=100.0 + i, low=100.0 + i, close=100.0 + i)
    path = tmp_path / "crypto" / symbol / f"{timeframe}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path, rows


def test_detect_is_idempotent_and_emits_only_after_cursor(tmp_path):
    _bars(tmp_path, n=4)
    cursors = {}
    first = detect_new_closed_bars(
        ["BTC-USDT"], ["1h"], data_dir=str(tmp_path), cursors=cursors,
    )
    assert first == []
    assert ("BTC-USDT", "1h") in cursors
    # Walk the cursor back one bar without hardcoding store file lengths.
    last = cursors[("BTC-USDT", "1h")]
    cursors[("BTC-USDT", "1h")] = last - timedelta(hours=1)
    newer = detect_new_closed_bars(
        ["BTC-USDT"], ["1h"], data_dir=str(tmp_path), cursors=cursors,
    )
    assert len(newer) == 1
    assert newer[0].close_time == last
    again = detect_new_closed_bars(
        ["BTC-USDT"], ["1h"], data_dir=str(tmp_path), cursors=cursors,
    )
    assert again == []


def test_slice_closed_drops_lookahead_bars():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    df = pd.DataFrame({
        "open_time": [t0, t0 + timedelta(hours=1), t0 + timedelta(hours=2)],
        "close_time": [t0 + timedelta(hours=1), t0 + timedelta(hours=2), t0 + timedelta(hours=3)],
        "open": [1, 2, 3], "high": [1, 2, 3], "low": [1, 2, 3], "close": [1, 2, 3],
        "volume": [1, 1, 1],
    })
    as_of = t0 + timedelta(hours=2)
    out = slice_closed(df, as_of)
    assert list(pd.to_datetime(out["close_time"], utc=True)) == [
        pd.Timestamp(t0 + timedelta(hours=1)),
        pd.Timestamp(t0 + timedelta(hours=2)),
    ]


def test_apply_stale_drops_is_stale_column_without_inventing_a_mask():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    df = pd.DataFrame({
        "open_time": [t0, t0 + timedelta(hours=1)],
        "close_time": [t0 + timedelta(hours=1), t0 + timedelta(hours=2)],
        "open": [1.0, 2.0], "high": [1.0, 2.0], "low": [1.0, 2.0], "close": [1.0, 2.0],
        "volume": [0.0, 5.0],
        "is_stale": [True, False],
    })
    out = apply_stale_and_gaps(df, "1h")
    assert len(out) == 1
    assert not bool(out.iloc[0]["is_stale"])


def test_deterministic_ids_and_dedupe():
    t = datetime(2026, 1, 1, tzinfo=UTC)
    a = deterministic_signal_id("s", "1", "BTC-USDT", "1h", t)
    b = deterministic_signal_id("s", "1", "BTC-USDT", "1h", t)
    assert a == b and len(a) == 32
    repo = MockRepository()
    sig = prepare_live_signal(_signal(
        id="ignored", strategy_id="s", strategy_version="1",
        symbol="BTC-USDT", timeframe="1h", bar_close_time=t, generated_at=t,
        is_mock=True,
    ))
    assert sig.is_mock is False
    assert repo.add_signal(sig, tenant_id=None) is True
    clone = sig.model_copy(update={"id": "other-id", "rationale": "dup"})
    assert repo.add_signal(clone, tenant_id=None) is False


def test_visibility_requires_approved_market():
    repo = MockRepository()
    settings = Settings(use_mock_data=False, serve_unapproved=False, env="dev")
    sig = _signal(id="live", is_mock=False, strategy_id="s", strategy_version="1",
                  symbol="BTC-USDT", timeframe="1h")
    repo.add_signal(sig, tenant_id=None)
    assert is_live_signal_visible(sig, repo=repo, tenant_id="demo", settings=settings) is False
    repo.add_backtest(
        _report(run_id="r1", data_hash="h", strategy_id="s", version="1",
                symbol="BTC-USDT", timeframe="1h"),
        tenant_id=None,
    )
    repo.add_approval("r1", "h")
    assert is_live_signal_visible(sig, repo=repo, tenant_id="demo", settings=settings) is True
    override = Settings(use_mock_data=False, serve_unapproved=True, env="dev")
    repo.remove_approval("r1")
    assert is_live_signal_visible(sig, repo=repo, tenant_id="demo", settings=override) is True
    prod = Settings(use_mock_data=False, serve_unapproved=True, env="prod", jwt_secret="s" * 32)
    # allow_unapproved() is false in prod even if the flag is set
    assert is_live_signal_visible(sig, repo=repo, tenant_id="demo", settings=prod) is False


def _bar(open_time, close_time, open, high, low, close, volume=1.0, source="t"):
    return {
        "open_time": open_time, "close_time": close_time,
        "open": open, "high": high, "low": low, "close": close,
        "volume": volume, "source": source,
    }


def _tracker_bars():
    """Synthetic path: signal closes at 11:00; fill at 11:00 open; SL on next bar."""
    t0 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    h = timedelta(hours=1)
    rows = [
        # signal bar
        _bar(t0, t0 + h, 100.0, 101.0, 99.0, 100.0),
        # fill bar (open at bar_close_time)
        _bar(t0 + h, t0 + 2 * h, 100.0, 101.0, 99.5, 100.2),
        # SL hits (long stop 98) — also a TP-high that should lose to SL if both trade
        _bar(t0 + 2 * h, t0 + 3 * h, 100.0, 104.0, 97.0, 99.0),
    ]
    return pd.DataFrame(rows), t0 + h


def test_tracker_same_bar_stop_wins_and_persists_exit(tmp_path, monkeypatch):
    df, bar_close = _tracker_bars()
    path = tmp_path / "crypto" / "BTC-USDT" / "1h.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    repo = MockRepository()
    sig = _signal(
        id="trk-sl", strategy_id="s", strategy_version="1", symbol="BTC-USDT",
        timeframe="1h", side="long", entry=100.0, stop_loss=98.0, take_profit=[103.0],
        horizon_bars=5, bar_close_time=bar_close, generated_at=bar_close,
        is_mock=False, status=SignalStatus.active,
    )
    repo.add_signal(sig, tenant_id=None)
    settings = Settings(use_mock_data=False, serve_unapproved=True, env="dev")
    changed = track_open_signals(repo=repo, data_dir=str(tmp_path), settings=settings)
    assert changed and changed[0].status == SignalStatus.hit_sl
    assert changed[0].exit_reason == ExitReason.sl
    assert changed[0].exit_price is not None and changed[0].exit_time is not None
    stored = repo._signals["trk-sl"]
    assert stored.status == SignalStatus.hit_sl


def test_tracker_timeout_and_gap_exit_at_open(tmp_path):
    t0 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    bar_close = t0 + timedelta(hours=1)
    h = timedelta(hours=1)
    # Gap down through the stop at the open of the fill bar.
    df = pd.DataFrame([
        _bar(t0, bar_close, 100.0, 101.0, 99.0, 100.0),
        _bar(bar_close, bar_close + h, 90.0, 91.0, 89.0, 90.5),
    ])
    path = tmp_path / "crypto" / "BTC-USDT" / "1h.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    repo = MockRepository()
    sig = _signal(
        id="trk-gap", strategy_id="s", strategy_version="1", symbol="BTC-USDT",
        timeframe="1h", side="long", entry=100.0, stop_loss=98.0, take_profit=[103.0],
        horizon_bars=5, bar_close_time=bar_close, generated_at=bar_close,
        is_mock=False,
    )
    repo.add_signal(sig, tenant_id=None)
    settings = Settings(use_mock_data=False, serve_unapproved=True, env="dev")
    changed = track_open_signals(repo=repo, data_dir=str(tmp_path), settings=settings)
    assert changed and changed[0].status == SignalStatus.hit_sl
    assert changed[0].exit_price == 90.0  # gap at open exits at the open

    # Timeout: no level hit within horizon.
    repo2 = MockRepository()
    df2 = pd.DataFrame([
        _bar(t0, bar_close, 100.0, 101.0, 99.0, 100.0),
        _bar(bar_close, bar_close + h, 100.0, 101.0, 99.0, 100.5),
        _bar(bar_close + h, bar_close + 2 * h, 100.5, 101.0, 99.5, 100.0),
    ])
    df2.to_parquet(path, index=False)
    sig2 = sig.model_copy(update={"id": "trk-to", "horizon_bars": 1, "status": SignalStatus.active})
    repo2.add_signal(sig2, tenant_id=None)
    timed = track_open_signals(repo=repo2, data_dir=str(tmp_path), settings=settings)
    assert timed and timed[0].status == SignalStatus.expired
    assert timed[0].exit_reason == ExitReason.timeout


@pytest.mark.skipif(not REAL_BTC.is_file(), reason="provisional BTC-USDT store not present")
def test_e2e_pipeline_against_real_btc_store_if_present():
    """Run the pipeline against the live store without asserting prices or counts."""
    repo = MockRepository()
    settings = Settings(
        use_mock_data=False, serve_unapproved=True, env="dev",
        data_dir=str(_E2E_DATA_DIR),
        pipeline_symbols=["BTC-USDT"], pipeline_timeframes=["1h"],
    )
    # First pass initializes the cursor and must not replay history.
    first = run_pipeline(repo=repo, settings=settings, data_dir=settings.data_dir,
                         symbols=["BTC-USDT"], timeframes=["1h"])
    assert first["new_bars"] == 0
    # Nudge the cursor back one closed bar so a second pass exercises emit.
    cur = repo.get_cursor("BTC-USDT", "1h")
    if cur is not None:
        repo.set_cursor("BTC-USDT", "1h", cur - timedelta(hours=1))
    second = run_pipeline(repo=repo, settings=settings, data_dir=settings.data_dir,
                          symbols=["BTC-USDT"], timeframes=["1h"])
    assert second["new_bars"] >= 1
    live = [s for s in repo._signals.values() if not s.is_mock]
    for s in live:
        Signal.model_validate(s.model_dump())
        assert s.is_mock is False
        assert s.generated_at >= s.bar_close_time
