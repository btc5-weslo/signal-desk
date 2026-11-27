"""Live signal tracker: persist emitted signals and score them on later real bars.

Statuses resolve to hit_tp / hit_sl / expired using the same triple-barrier
rules as the backtester (gap at open exits at the open; stop wins if both
levels trade in one bar). Cancelled is reserved for signals that never fill
(no next bar) or are explicitly cancelled.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
from signal_shared import ExitReason, Signal, SignalStatus

from signal_data.backtester.costs import CostModel
from signal_data.backtester.engine import _next_fill_index, _prepare_bars
from signal_data.backtester.triple_barrier import evaluate_barriers
from signal_data.paths import TRACKER_DIR
from signal_data.schema import TradeAudit
from signal_data.storage import atomic_write_parquet, read_parquet
from signal_data.symbols import to_canonical
from signal_data.timeutil import now_utc, to_utc, to_utc_datetime

SIGNALS_PATH = TRACKER_DIR / "signals.parquet"
RESOLUTIONS_PATH = TRACKER_DIR / "resolutions.parquet"


def _ensure_dir() -> None:
    TRACKER_DIR.mkdir(parents=True, exist_ok=True)


def _signals_frame(signals: list[Signal]) -> pd.DataFrame:
    rows = []
    for s in signals:
        d = s.model_dump(mode="json")
        d["take_profit"] = json.dumps(d.get("take_profit") or [])
        d["features_snapshot"] = json.dumps(d.get("features_snapshot") or {})
        rows.append(d)
    return pd.DataFrame(rows)


def log_signals(signals: list[Signal], *, path: Path | None = None) -> Path:
    """Append signals to the tracker log (idempotent on id)."""
    _ensure_dir()
    path = path or SIGNALS_PATH
    incoming = _signals_frame(signals)
    if path.exists():
        existing = pd.read_parquet(path)
        combined = pd.concat([existing, incoming], ignore_index=True)
        combined = combined.drop_duplicates(subset=["id"], keep="last")
    else:
        combined = incoming
    # Use pandas to_parquet via a temp file for this non-OHLCV log.
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    combined.to_parquet(tmp, index=False)
    tmp.replace(path)
    return path


def load_signals(path: Path | None = None) -> list[Signal]:
    path = path or SIGNALS_PATH
    if not path.exists():
        return []
    df = pd.read_parquet(path)
    out: list[Signal] = []
    for _, r in df.iterrows():
        payload = r.to_dict()
        payload["take_profit"] = json.loads(payload["take_profit"]) if isinstance(payload.get("take_profit"), str) else payload.get("take_profit") or []
        payload["features_snapshot"] = json.loads(payload["features_snapshot"]) if isinstance(payload.get("features_snapshot"), str) else payload.get("features_snapshot") or {}
        out.append(Signal.model_validate(payload))
    return out


def resolve_signal(
    signal: Signal,
    bars: pd.DataFrame,
    *,
    cost: CostModel | None = None,
) -> tuple[Signal, TradeAudit | None]:
    """Score one signal against later real bars. Returns the updated signal and an audit if filled."""
    cost = cost or CostModel(fee_bps=0.0, slippage_bps=0.0)
    work = _prepare_bars(bars)
    fill_i = _next_fill_index(work, signal.bar_close_time)
    if fill_i is None:
        updated = signal.model_copy(update={"status": SignalStatus.cancelled})
        return updated, None
    # If the fill bar has not yet closed, leave it active.
    if to_utc(work.iloc[fill_i]["close_time"]) > now_utc():
        return signal, None
    result = evaluate_barriers(
        work,
        fill_index=fill_i,
        side=signal.side.value,
        stop_loss=float(signal.stop_loss),
        take_profit=list(signal.take_profit),
        horizon_bars=int(signal.horizon_bars),
        cost=cost,
    )
    if result is None:
        return signal, None

    status = {
        ExitReason.tp: SignalStatus.hit_tp,
        ExitReason.sl: SignalStatus.hit_sl,
        ExitReason.timeout: SignalStatus.expired,
    }[result.exit_reason]
    updated = signal.model_copy(update={"status": status})
    fill_time = to_utc_datetime(work.iloc[fill_i]["open_time"])
    audit = TradeAudit(
        symbol=to_canonical(signal.symbol),
        side=signal.side,
        signal_id=signal.id,
        bar_close_time=to_utc_datetime(signal.bar_close_time),
        reference_entry=float(signal.entry),
        entry_time=fill_time,
        exit_time=result.exit_time,
        entry_price=result.fill_price,
        exit_price=result.exit_price,
        stop_loss=float(signal.stop_loss),
        take_profit=float(signal.take_profit[0]) if signal.take_profit else None,
        exit_reason=result.exit_reason,
        r_multiple=result.r_multiple,
        bars_held=result.bars_held,
        net_return=result.net_return,
        gap_exit=result.gap_exit,
        fee_bps=cost.fee_bps,
        slippage_bps=cost.slippage_bps,
    )
    return updated, audit


def resolve_open_signals(
    bars_by_symbol: dict[str, pd.DataFrame],
    *,
    cost: CostModel | None = None,
    path: Path | None = None,
) -> list[tuple[Signal, TradeAudit | None]]:
    """Re-score every still-active tracked signal against later real bars."""
    signals = load_signals(path)
    resolved: list[tuple[Signal, TradeAudit | None]] = []
    updated: list[Signal] = []
    audits: list[TradeAudit] = []
    for s in signals:
        if s.status != SignalStatus.active:
            updated.append(s)
            continue
        key = to_canonical(s.symbol)
        if key not in bars_by_symbol:
            updated.append(s)
            continue
        u, audit = resolve_signal(s, bars_by_symbol[key], cost=cost)
        updated.append(u)
        resolved.append((u, audit))
        if audit is not None:
            audits.append(audit)
    log_signals(updated, path=path)
    if audits:
        _write_resolutions(audits)
    return resolved


def _write_resolutions(audits: list[TradeAudit]) -> Path:
    _ensure_dir()
    rows = [a.model_dump(mode="json") for a in audits]
    incoming = pd.DataFrame(rows)
    if RESOLUTIONS_PATH.exists():
        existing = pd.read_parquet(RESOLUTIONS_PATH)
        combined = pd.concat([existing, incoming], ignore_index=True)
        if "signal_id" in combined.columns:
            combined = combined.drop_duplicates(subset=["signal_id"], keep="last")
    else:
        combined = incoming
    tmp = RESOLUTIONS_PATH.with_name(f".{RESOLUTIONS_PATH.name}.tmp")
    combined.to_parquet(tmp, index=False)
    tmp.replace(RESOLUTIONS_PATH)
    return RESOLUTIONS_PATH
