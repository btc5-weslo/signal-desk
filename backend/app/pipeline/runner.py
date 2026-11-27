"""Plain callable that the arq cron job and tests both invoke."""

from __future__ import annotations

from datetime import datetime

from app.core.config import Settings, get_settings
from app.pipeline.detect import detect_new_closed_bars
from app.pipeline.emit import emit_signals_for_bar
from app.pipeline.tracker import track_open_signals


def _load_cursors(repo, symbols: list[str], timeframes: list[str]) -> dict[tuple[str, str], datetime]:
    cursors: dict[tuple[str, str], datetime] = {}
    for symbol in symbols:
        for tf in timeframes:
            cur = repo.get_cursor(symbol, tf)
            if cur is not None:
                cursors[(symbol, tf)] = cur
    return cursors


def _persist_cursors(repo, cursors: dict[tuple[str, str], datetime]) -> None:
    for (symbol, tf), ts in cursors.items():
        repo.set_cursor(symbol, tf, ts)


def run_pipeline(
    *,
    repo,
    data_dir: str | None = None,
    settings: Settings | None = None,
    broadcaster=None,
    alert_fn=None,
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
) -> dict:
    """Detect new closed bars, emit signals, then update open-signal status.

    Safe to call repeatedly: cursors and signal-id dedupe make it idempotent.
    """
    settings = settings or get_settings()
    data_dir = data_dir or settings.data_dir
    if not data_dir:
        raise RuntimeError(
            "set SIGNAL_DATA_DIR; no hard-coded data path is used"
        )
    symbols = symbols or list(settings.pipeline_symbols)
    timeframes = timeframes or list(settings.pipeline_timeframes)
    cursors = _load_cursors(repo, symbols, timeframes)
    bars = detect_new_closed_bars(symbols, timeframes, data_dir=data_dir, cursors=cursors)
    emitted = []
    for bar in bars:
        emitted.extend(emit_signals_for_bar(
            bar, repo=repo, data_dir=data_dir, timeframes=timeframes,
            settings=settings, broadcaster=broadcaster, alert_fn=alert_fn,
        ))
    _persist_cursors(repo, cursors)
    updated = track_open_signals(
        repo=repo, data_dir=data_dir, settings=settings, broadcaster=broadcaster,
    )
    return {"new_bars": len(bars), "emitted": len(emitted), "updated": len(updated)}
