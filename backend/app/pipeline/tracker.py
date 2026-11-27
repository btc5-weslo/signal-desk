"""Walk active live signals with the same triple-barrier rules as the backtester."""

from __future__ import annotations

import logging

from signal_shared import ExitReason, Signal, SignalStatus

from app.pipeline.emit import _publish
from app.pipeline.hooks import load_ohlcv, resolve_barriers

log = logging.getLogger(__name__)
from app.pipeline.visibility import is_live_signal_visible


def _exit_update(signal: Signal, updated: Signal, audit) -> Signal:
    payload: dict = {"status": updated.status}
    if audit is not None:
        payload["exit_time"] = getattr(audit, "exit_time", None)
        payload["exit_price"] = getattr(audit, "exit_price", None)
        reason = getattr(audit, "exit_reason", None)
        if isinstance(reason, ExitReason):
            payload["exit_reason"] = reason
        elif reason is not None:
            payload["exit_reason"] = ExitReason(reason)
    elif updated.status == SignalStatus.cancelled:
        payload["exit_reason"] = None
    return signal.model_copy(update=payload)


def track_open_signals(
    *,
    repo,
    data_dir: str,
    settings,
    broadcaster=None,
) -> list[Signal]:
    """Re-score active non-mock signals. Persist and broadcast status changes."""
    changed: list[Signal] = []
    cache: dict[tuple[str, str], object] = {}
    for sig in repo.list_active_signals():
        key = (sig.symbol, sig.timeframe)
        if key not in cache:
            cache[key] = load_ohlcv(sig.symbol, sig.timeframe, data_dir=data_dir)
        bars = cache[key]
        if bars is None or getattr(bars, "empty", True):
            continue
        try:
            updated, audit = resolve_barriers(sig, bars)
        except (ValueError, TypeError, KeyError) as exc:
            log.warning("barrier resolve failed for %s: %s", sig.id, exc)
            continue
        if updated.status == sig.status:
            continue
        final = _exit_update(sig, updated, audit)
        repo.update_signal(final)
        changed.append(final)
        if broadcaster is None:
            continue
        for tid in repo.list_tenant_ids():
            if is_live_signal_visible(final, repo=repo, tenant_id=tid, settings=settings):
                _publish(broadcaster, final, tid)
    return changed
