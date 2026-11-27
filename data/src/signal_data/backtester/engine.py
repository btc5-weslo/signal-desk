"""Event-driven backtester with no lookahead.

Fill rule: a signal's ``entry`` is the reference close of the signal bar.
The real fill is the next bar's open plus slippage. Stops and targets are
absolute prices. If the fill bar (or a later bar) opens past the stop or
the first target, the exit is that open, not the level.

The engine accepts either:

- a ``BarStrategy`` (``generate(bars_by_timeframe, as_of) -> list[Signal]``), or
- a vectorized signal DataFrame (bar_close_time, symbol, side, entry, ...).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable
from uuid import uuid4

import pandas as pd
from signal_shared import BacktestReport, ExitReason, Side, Signal, SignalStatus

from signal_data.backtester.costs import CostModel
from signal_data.backtester.flags import compute_flags
from signal_data.backtester.metrics import UNDEFINABLE, summarize, undefined_metrics
from signal_data.backtester.strategy import BarStrategy
from signal_data.hashing import config_hash, data_hash, run_id
from signal_data.schema import TradeAudit
from signal_data.stale import drop_stale, has_large_gaps
from signal_data.symbols import asset_class_of, to_canonical
from signal_data.timeutil import to_utc, to_utc_datetime


REQUIRED_BAR_COLS = ("open_time", "close_time", "open", "high", "low", "close")


def _prepare_bars(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in REQUIRED_BAR_COLS:
        if col not in out.columns:
            raise ValueError(f"bars missing required column {col}")
    out["open_time"] = pd.to_datetime(out["open_time"], utc=True)
    out["close_time"] = pd.to_datetime(out["close_time"], utc=True)
    # Stale bars must never be filled on or used for ATR / volatility.
    out = drop_stale(out)
    out = out.sort_values("open_time").drop_duplicates(subset=["open_time"], keep="last")
    return out.reset_index(drop=True)


def slice_bars(
    bars_by_timeframe: dict[str, pd.DataFrame],
    as_of: datetime | pd.Timestamp,
) -> dict[str, pd.DataFrame]:
    """Keep only bars with close_time <= as_of (fully closed)."""
    cut = to_utc(as_of)
    out: dict[str, pd.DataFrame] = {}
    for tf, df in bars_by_timeframe.items():
        if df is None or df.empty:
            out[tf] = df.iloc[0:0] if df is not None else pd.DataFrame()
            continue
        work = df.copy()
        work["close_time"] = pd.to_datetime(work["close_time"], utc=True)
        out[tf] = work.loc[work["close_time"] <= cut].copy()
    return out


def _signals_from_frame(frame: pd.DataFrame, *, default_horizon: int = 20) -> list[Signal]:
    """Convert a vectorized signal DataFrame into Signal objects."""
    rows = []
    work = frame.copy()
    if "bar_close_time" not in work.columns:
        if "timestamp" in work.columns:
            work["bar_close_time"] = work["timestamp"]
        else:
            raise ValueError("signal frame needs bar_close_time or timestamp")
    work["bar_close_time"] = pd.to_datetime(work["bar_close_time"], utc=True)
    for _, r in work.iterrows():
        side = r["side"]
        if isinstance(side, Side):
            side_v = side
        else:
            side_v = Side(str(side))
        if side_v == Side.flat:
            continue
        symbol = to_canonical(str(r["symbol"]))
        tps = r["take_profit"] if "take_profit" in work.columns else []
        if isinstance(tps, float) or tps is None:
            tps = [] if (tps is None or (isinstance(tps, float) and pd.isna(tps))) else [tps]
        if isinstance(tps, str):
            tps = [float(x) for x in tps.split(",") if x]
        tps = list(tps)
        close_t = to_utc_datetime(r["bar_close_time"])
        gen = r["generated_at"] if "generated_at" in work.columns and pd.notna(r.get("generated_at")) else close_t
        sig = Signal(
            id=str(r["id"]) if "id" in work.columns and pd.notna(r.get("id")) else uuid4().hex,
            strategy_id=str(r.get("strategy_id") or "vectorized"),
            strategy_version=str(r.get("strategy_version") or "v1"),
            symbol=symbol,
            asset_class=r["asset_class"] if "asset_class" in work.columns and pd.notna(r.get("asset_class")) else asset_class_of(symbol),
            timeframe=str(r.get("timeframe") or "1d"),
            side=side_v,
            generated_at=to_utc_datetime(gen),
            bar_close_time=close_t,
            entry=None if pd.isna(r.get("entry")) else float(r["entry"]),
            stop_loss=None if pd.isna(r.get("stop_loss")) else float(r["stop_loss"]),
            take_profit=tps,
            horizon_bars=int(r["horizon_bars"]) if "horizon_bars" in work.columns and pd.notna(r.get("horizon_bars")) else default_horizon,
            confidence=float(r["confidence"]) if "confidence" in work.columns and pd.notna(r.get("confidence")) else 0.5,
            features_snapshot=r["features_snapshot"] if "features_snapshot" in work.columns and isinstance(r.get("features_snapshot"), dict) else {},
            rationale=str(r.get("rationale") or "vectorized signal"),
            status=SignalStatus.active,
            is_mock=bool(r.get("is_mock", False)),
        )
        rows.append(sig)
    return rows


@dataclass
class BacktestRun:
    report: BacktestReport
    audits: list[TradeAudit]
    equity: pd.Series
    extra_metrics: dict[str, float]
    config: dict[str, Any]
    data_paths: list[str] = field(default_factory=list)


def _next_fill_index(bars: pd.DataFrame, bar_close_time: datetime) -> int | None:
    """Index of the first bar whose open_time >= bar_close_time (the next bar)."""
    cut = to_utc(bar_close_time)
    opens = bars["open_time"]
    hits = bars.index[opens >= cut]
    if len(hits) == 0:
        return None
    return int(hits[0])


def _build_equity_and_flags(
    bars: pd.DataFrame,
    audits: list[TradeAudit],
    *,
    initial_equity: float,
) -> tuple[pd.Series, pd.Series]:
    """Mark-to-market equity at each bar close; 1/0 position flags.

    Between entry_time and exit_time the position is open. Same-bar gap exits
    still apply the trade's net_return on that bar.
    """
    idx = pd.DatetimeIndex(pd.to_datetime(bars["close_time"], utc=True))
    equity = pd.Series(initial_equity, index=idx, dtype=float)
    flags = pd.Series(0, index=idx, dtype=int)
    if not audits:
        return equity, flags

    cash = initial_equity
    # Process bars in order, applying realized PnL at exit close/open time.
    # For simplicity and reproducibility we apply net_return to equity at the
    # exit bar, and flag bars from fill open through exit as in-market.
    realized = pd.Series(0.0, index=idx)
    for t in audits:
        exit_ts = to_utc(t.exit_time)
        # map exit_time onto the bar index: first close_time >= exit, else last
        later = idx[idx >= exit_ts]
        loc = later[0] if len(later) else idx[-1]
        realized.loc[loc] += t.net_return * cash if False else t.net_return
        # flags
        entry_ts = to_utc(t.entry_time)
        mask = (idx >= entry_ts) & (idx <= to_utc(t.exit_time) if t.gap_exit is False else (idx >= entry_ts) & (idx >= entry_ts))
        # Simpler: flag bars whose close_time is in [entry_time, exit_time] or
        # whose open_time is the entry for a same-bar exit.
        in_pos = (idx >= entry_ts) & (idx <= to_utc(t.exit_time))
        if not in_pos.any():
            # gap exit at entry open: still mark the fill bar (close after entry)
            later_entry = idx[idx >= entry_ts]
            if len(later_entry):
                flags.loc[later_entry[0]] = 1 if t.side.value == "long" else -1
        else:
            flags.loc[in_pos] = 1 if t.side.value == "long" else -1

    # Compound net_return at each exit (returns are fractional on notional == equity when fully invested)
    eq = initial_equity
    values = []
    for ts in idx:
        r = float(realized.loc[ts])
        if r != 0:
            eq = eq * (1.0 + r)
        values.append(eq)
    equity = pd.Series(values, index=idx, dtype=float)
    return equity, flags


def run_backtest(
    bars: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    strategy: BarStrategy | None = None,
    signals: list[Signal] | pd.DataFrame | None = None,
    bars_by_timeframe: dict[str, pd.DataFrame] | None = None,
    cost: CostModel | None = None,
    initial_equity: float = 100_000.0,
    strategy_id: str | None = None,
    strategy_version: str = "v1",
    data_paths: list | None = None,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    extra_config: dict[str, Any] | None = None,
) -> BacktestRun:
    """Run an event-driven backtest on a single primary-timeframe series.

    Either pass a ``strategy`` (called at each bar close with sliced frames)
    or a list/DataFrame of ``signals``. Fills never occur on the signal bar.
    """
    cost = cost or CostModel()
    primary = _prepare_bars(bars)
    symbol = to_canonical(symbol)
    frames = {timeframe: primary}
    if bars_by_timeframe:
        for tf, df in bars_by_timeframe.items():
            frames[tf] = _prepare_bars(df) if len(df) else df

    preloaded: list[Signal] = []
    if signals is not None:
        if isinstance(signals, pd.DataFrame):
            preloaded = _signals_from_frame(signals)
        else:
            preloaded = list(signals)
        # ignore any signal that would require data after its bar_close_time
        preloaded = sorted(preloaded, key=lambda s: to_utc(s.bar_close_time))

    # Position state (fixed 2026-11-26; the old ``in_trade`` flag never cleared,
    # capping every run at ~2 trades).
    #
    # - A signal accepted at bar close k is *pending*; it fills at the next bar
    #   open. At that bar we score it with ``signal_data.barriers.resolve`` (the
    #   same call the live tracker makes, with the signal's own horizon_bars).
    # - The position is then open from the fill until ``outcome.exit_time``.
    #   Signals emitted at a close strictly before that exit are skipped (and
    #   counted). A signal at the exact exit close is eligible again.
    # - Nothing is resolved after the loop. If resolve() runs out of bars before
    #   the stop, target or full horizon, the trade is still open at the end of
    #   the supplied bars: it is DROPPED (counted in ``dropped_open_at_end``),
    #   never closed at the last bar, so every recorded trade is exactly what
    #   barriers.resolve gives on complete data. A signal on the last bar has no
    #   fill bar and is counted in ``unfilled_at_end``.
    from signal_data import barriers as _barriers

    pending: Signal | None = None
    audits: list[TradeAudit] = []
    preload_by_close: dict[pd.Timestamp, list[Signal]] = {}
    for s in preloaded:
        key = to_utc(s.bar_close_time)
        preload_by_close.setdefault(key, []).append(s)

    open_until: pd.Timestamp | None = None  # exit_time of the open position
    open_forever = False  # a trade still open when the bars ran out
    skipped_in_position = 0
    dropped_open_at_end = 0
    horizons_used: set[int] = set()

    for i in range(len(primary)):
        bar = primary.iloc[i]
        as_of = to_utc(bar["close_time"])

        # Fill + score a pending signal once its fill bar is part of the series.
        if pending is not None:
            fill_i = _next_fill_index(primary, pending.bar_close_time)
            if fill_i is not None and i >= fill_i:
                outcome = _barriers.resolve(pending, primary, cost=cost)
                sig, pending = pending, None
                horizon = int(sig.horizon_bars)
                horizons_used.add(horizon)
                if outcome.exit_time is None:
                    pass  # cancelled (no fill bar / horizon < 1)
                elif (
                    outcome.exit_reason == ExitReason.timeout
                    and int(outcome.bars_held) < horizon
                ):
                    # resolve() hit the end of the bars, not the horizon.
                    dropped_open_at_end += 1
                    open_forever = True
                else:
                    audits.append(
                        TradeAudit(
                            symbol=symbol,
                            side=sig.side,
                            signal_id=sig.id,
                            bar_close_time=to_utc_datetime(sig.bar_close_time),
                            reference_entry=float(sig.entry),
                            entry_time=outcome.entry_time,
                            exit_time=outcome.exit_time,
                            entry_price=outcome.fill_price,
                            exit_price=outcome.exit_price,
                            stop_loss=float(sig.stop_loss),
                            take_profit=float(sig.take_profit[0]) if sig.take_profit else None,
                            exit_reason=outcome.exit_reason,
                            r_multiple=outcome.r_multiple,
                            bars_held=outcome.bars_held,
                            net_return=outcome.net_return,
                            gap_exit=outcome.gap_exit,
                            fee_bps=cost.fee_bps,
                            slippage_bps=cost.slippage_bps,
                        )
                    )
                    open_until = to_utc(outcome.exit_time)

        position_open = open_forever or (open_until is not None and as_of < open_until)

        # --- generate or pick signals at this bar close
        new_sigs: list[Signal] = []
        if strategy is not None and not position_open and pending is None:
            sliced = slice_bars(frames, as_of)
            new_sigs = list(strategy.generate(sliced, to_utc_datetime(as_of)) or [])
        if not new_sigs and preload_by_close:
            new_sigs = list(preload_by_close.get(as_of, []))

        candidates = [
            s
            for s in new_sigs
            if to_canonical(s.symbol) == symbol
            and s.side != Side.flat
            and to_utc(s.bar_close_time) <= as_of  # no lookahead
        ]
        if not candidates:
            continue
        if position_open or pending is not None:
            skipped_in_position += len(candidates)
            continue
        # Accept the first long/short signal for this symbol at this close.
        pending = candidates[0]

    unfilled_at_end = 1 if pending is not None else 0

    equity, flags = _build_equity_and_flags(primary, audits, initial_equity=initial_equity)
    ac = asset_class_of(symbol)
    metrics = summarize(audits, equity, flags, timeframe=timeframe, asset_class=ac)
    trades = [a.to_trade() for a in audits]
    start = period_start or to_utc_datetime(primary["open_time"].iloc[0])
    end = period_end or to_utc_datetime(primary["close_time"].iloc[-1])
    sid = strategy_id or getattr(strategy, "strategy_id", None) or "unknown"
    sver = strategy_version or getattr(strategy, "strategy_version", None) or "v1"
    cfg = {
        "symbol": symbol,
        "timeframe": timeframe,
        "fee_bps": cost.fee_bps,
        "slippage_bps": cost.slippage_bps,
        "atr_slippage_mult": cost.atr_slippage_mult,
        "initial_equity": initial_equity,
        "strategy_id": sid,
        "strategy_version": sver,
        "horizon_bars_used": sorted(horizons_used),
        "signals_skipped_in_position": skipped_in_position,
        "dropped_open_at_end": dropped_open_at_end,
        "unfilled_at_end": unfilled_at_end,
        "open_at_end_policy": "drop",
        **(extra_config or {}),
    }
    paths = [p for p in (data_paths or [])]
    dhash = data_hash(paths) if paths else config_hash({"n_bars": len(primary), "ohlcv": _bars_fingerprint(primary)})
    rid = run_id(sid, cfg, dhash)
    flags_list = compute_flags(
        trades=trades,
        win_rate_reported=metrics["win_rate"],
        profit_factor_reported=metrics["profit_factor"],
        sharpe=metrics["sharpe"],
        oos_bar_count=None,
        has_oos_windows=False if not (extra_config or {}).get("oos") else True,
        data_quality_warning=bool((extra_config or {}).get("data_quality_warning")) or has_large_gaps(primary, timeframe),
        metric_undefined=bool(undefined_metrics({k: metrics[k] for k in UNDEFINABLE})),
    )
    report = BacktestReport(
        strategy_id=sid,
        version=sver,
        period={"start": start, "end": end},
        oos_windows=[],
        trades=trades,
        trade_count=len(trades),
        win_rate=metrics["win_rate"],
        profit_factor=metrics["profit_factor"],
        sharpe=metrics["sharpe"],
        sortino=metrics["sortino"],
        max_drawdown=metrics["max_drawdown"],
        avg_R=metrics["avg_R"],
        exposure=metrics["exposure"],
        fees_bps=cost.fee_bps,
        slippage_bps=cost.slippage_bps,
        run_id=rid,
        data_hash=dhash,
        symbol=symbol,
        timeframe=timeframe,
        flags=flags_list,
    )
    return BacktestRun(
        report=report,
        audits=audits,
        equity=equity,
        extra_metrics={k: metrics[k] for k in ("total_return", "cagr", "avg_win", "avg_loss")},
        config=cfg,
        data_paths=[str(p) for p in paths],
    )


def _bars_fingerprint(bars: pd.DataFrame) -> str:
    """Content fingerprint used when no parquet path was provided (tests / toys)."""
    import hashlib

    sub = bars[["open_time", "close_time", "open", "high", "low", "close", "volume"]].copy()
    payload = sub.to_csv(index=False).encode()
    return hashlib.sha256(payload).hexdigest()
