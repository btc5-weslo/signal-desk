"""Validate, dedupe, store, and optionally broadcast/alert new live signals."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from signal_shared import Signal

from app.pipeline.hooks import run_for_bar
from app.pipeline.visibility import is_live_signal_visible


def deterministic_signal_id(
    strategy_id: str, version: str, symbol: str, timeframe: str, bar_close_time: datetime,
) -> str:
    ts = bar_close_time.astimezone(UTC).isoformat()
    raw = f"{strategy_id}|{version}|{symbol}|{timeframe}|{ts}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def prepare_live_signal(sig: Signal) -> Signal:
    sid = deterministic_signal_id(
        sig.strategy_id, sig.strategy_version, sig.symbol, sig.timeframe, sig.bar_close_time,
    )
    return sig.model_copy(update={"id": sid, "is_mock": False})


def emit_signals_for_bar(
    bar,
    *,
    repo,
    data_dir: str,
    timeframes: list[str],
    settings,
    broadcaster=None,
    alert_fn=None,
) -> list[Signal]:
    """Run strategies at a closed bar, store every valid signal, publish visible ones.

    Live signals are global (tenant_id None). Unapproved markets are stored
    but never served, broadcast, or alerted (unless the dev override is on).
    """
    raw = run_for_bar(
        bar.symbol, bar.timeframe, bar.close_time,
        data_dir=data_dir, timeframes=timeframes,
    )
    stored: list[Signal] = []
    for sig in raw:
        live = prepare_live_signal(sig)
        if not repo.add_signal(live, tenant_id=None):
            continue
        stored.append(live)
        _publish_if_visible(
            live, repo=repo, settings=settings,
            broadcaster=broadcaster, alert_fn=alert_fn,
        )
    return stored


def _publish_if_visible(sig: Signal, *, repo, settings, broadcaster, alert_fn) -> None:
    tenants = [
        tid for tid in repo.list_tenant_ids()
        if is_live_signal_visible(sig, repo=repo, tenant_id=tid, settings=settings)
    ]
    if not tenants:
        return
    if broadcaster is not None:
        for tid in tenants:
            _publish(broadcaster, sig, tid)
    if alert_fn is not None:
        for tid in tenants:
            channels = repo.list_alert_channels(tenant_id=tid)
            cfg = repo.get_tenant_config_by_id(tid)
            extras = list(cfg.extra_disclaimers) if cfg is not None else []
            alert_fn(sig, channels, extras)


def _publish(broadcaster, sig: Signal, tenant_id: str | None) -> None:
    import asyncio
    import inspect

    result = broadcaster.publish(sig, tenant_id=tenant_id)
    if inspect.isawaitable(result):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(result)
        else:
            loop.create_task(result)
