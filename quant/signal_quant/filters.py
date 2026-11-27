"""Signal filters applied after a raw rule/ML decision.

v0 filters: regime gating, confidence threshold, cooldown (bars since last
emit), and stubs for liquidity/spread and news/event calendars (Data-owned
inputs; not wired until those series exist).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FilterConfig:
    allow_regimes: tuple[str, ...] = ("trend", "range")
    block_high_vol: bool = False
    min_confidence: float = 0.0
    cooldown_bars: int = 0
    max_spread_bps: float | None = None  # stub: needs a spread series
    block_event_window: bool = False  # stub: needs an event calendar


@dataclass
class FilterState:
    last_emit_index: int | None = None
    extra: dict = field(default_factory=dict)


def regime_ok(regime: str, high_vol: bool, cfg: FilterConfig) -> bool:
    if regime not in cfg.allow_regimes and regime != "unknown":
        return False
    if cfg.block_high_vol and high_vol:
        return False
    return True


def confidence_ok(confidence: float, cfg: FilterConfig) -> bool:
    return confidence >= cfg.min_confidence


def cooldown_ok(bar_index: int, state: FilterState, cfg: FilterConfig) -> bool:
    if cfg.cooldown_bars <= 0 or state.last_emit_index is None:
        return True
    return (bar_index - state.last_emit_index) >= cfg.cooldown_bars


def liquidity_ok(spread_bps: float | None, cfg: FilterConfig) -> bool:
    if cfg.max_spread_bps is None:
        return True
    if spread_bps is None:
        return True  # no data yet — do not silently invent a block
    return spread_bps <= cfg.max_spread_bps


def event_ok(as_of: datetime, event_blackout: bool | None, cfg: FilterConfig) -> bool:
    if not cfg.block_event_window:
        return True
    if event_blackout is None:
        return True
    return not event_blackout


def accept(
    *,
    regime: str,
    high_vol: bool,
    confidence: float,
    bar_index: int,
    state: FilterState,
    cfg: FilterConfig,
    spread_bps: float | None = None,
    event_blackout: bool | None = None,
    as_of: datetime | None = None,
) -> bool:
    _ = as_of
    return (
        regime_ok(regime, high_vol, cfg)
        and confidence_ok(confidence, cfg)
        and cooldown_ok(bar_index, state, cfg)
        and liquidity_ok(spread_bps, cfg)
        and event_ok(as_of or datetime.min, event_blackout, cfg)
    )
