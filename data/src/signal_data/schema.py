"""Data-package models. Canonical Signal / Trade / BacktestReport live in signal_shared.

This module does not fork those contracts. It adds quality reports, fetch results,
and a slippage-audit trade record written next to the official Trade list.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from signal_shared import (
    TIMEFRAMES,
    AssetClass,
    BacktestReport,
    Candle,
    ExitReason,
    OOSWindow,
    Side,
    Signal,
    SignalStatus,
    Strategy,
    Trade,
)

from signal_data.paths import PARQUET_COLUMNS

__all__ = [
    "TIMEFRAMES",
    "PARQUET_COLUMNS",
    "AssetClass",
    "BacktestReport",
    "Candle",
    "ExitReason",
    "OOSWindow",
    "Side",
    "Signal",
    "SignalStatus",
    "Strategy",
    "Trade",
    "TradeAudit",
    "DataQualityReport",
    "FetchAttempt",
    "FetchResult",
    "GapRecord",
]


class GapRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime
    missing_bars_estimate: int
    kind: str  # "weekend_or_holiday" | "unexpected" | "source_limit"


class FetchAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    ok: bool
    bars: int = 0
    error: str | None = None
    notes: list[str] = Field(default_factory=list)


class DataQualityReport(BaseModel):
    """Per-series quality report. Flags live here, not in the locked Parquet columns."""

    model_config = ConfigDict(extra="forbid")

    symbol: str
    asset_class: str
    timeframe: str
    source: str | None
    start: datetime | None = None
    end: datetime | None = None
    n_bars: int = 0
    n_duplicates_removed: int = 0
    n_bad_ticks_dropped: int = 0
    n_outliers_flagged: int = 0
    n_zero_volume: int = 0
    n_stale_bars: int = 0
    n_stale_runs_gt_3: int = 0
    n_off_grid_dropped: int = 0
    off_grid_times: list[datetime] = Field(default_factory=list)
    n_gaps_unexpected: int = 0
    n_gaps_calendar: int = 0
    n_gaps_gt_3x: int = 0
    missing_pct_estimate: float = 0.0
    history_limitations: list[str] = Field(default_factory=list)
    bad_tick_times: list[datetime] = Field(default_factory=list)
    outlier_times: list[datetime] = Field(default_factory=list)
    stale_times: list[datetime] = Field(default_factory=list)
    gaps: list[GapRecord] = Field(default_factory=list)
    fetch_attempts: list[FetchAttempt] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    dropped_forming_bars: int = 0
    cleaned_at: datetime | None = None


class FetchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument_symbol: str
    asset_class: str
    timeframe: str
    source: str | None = None
    attempts: list[FetchAttempt] = Field(default_factory=list)
    history_limitations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    # bars are carried separately as a DataFrame (not in this model)


class TradeAudit(BaseModel):
    """Official Trade fields plus slippage-audit extras (not part of BacktestReport).

    `entry_price` is the actual fill (next bar open +/- slippage).
    `reference_entry` is the signal's reference close. These two let slippage
    be audited without changing the shared Trade contract (extra=forbid).
    """

    model_config = ConfigDict(extra="forbid")

    symbol: str
    side: Side
    signal_id: str | None = None
    bar_close_time: datetime | None = None
    reference_entry: float
    entry_time: datetime
    exit_time: datetime
    entry_price: float  # actual fill
    exit_price: float
    stop_loss: float
    take_profit: float | None = None
    exit_reason: ExitReason
    r_multiple: float
    bars_held: int = Field(ge=0)
    net_return: float
    gap_exit: bool = False
    fee_bps: float = 0.0
    slippage_bps: float = 0.0

    def to_trade(self) -> Trade:
        return Trade(
            symbol=self.symbol,
            side=self.side,
            entry_time=self.entry_time,
            exit_time=self.exit_time,
            entry_price=self.entry_price,
            exit_price=self.exit_price,
            exit_reason=self.exit_reason,
            r_multiple=self.r_multiple,
            bars_held=self.bars_held,
            net_return=self.net_return,
        )
