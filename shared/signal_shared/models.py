"""Canonical cross-team contracts (v1). Source of truth for JSON schemas and TS types.

Quant produces Signal, Backend serves it, Frontend renders it, Data backtests it.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .symbols import normalize_symbol


class AssetClass(str, Enum):
    crypto = "crypto"
    equity = "equity"
    fx = "fx"


class Side(str, Enum):
    long = "long"
    short = "short"
    flat = "flat"


class SignalStatus(str, Enum):
    active = "active"
    hit_tp = "hit_tp"
    hit_sl = "hit_sl"
    expired = "expired"
    cancelled = "cancelled"


class ExitReason(str, Enum):
    tp = "tp"
    sl = "sl"
    timeout = "timeout"


class BacktestFlag(str, Enum):
    low_oos_trades = "low_oos_trades"
    sharpe_gt_3 = "sharpe_gt_3"
    win_rate_gt_75 = "win_rate_gt_75"
    metric_recompute_mismatch = "metric_recompute_mismatch"
    insufficient_oos_history = "insufficient_oos_history"
    data_quality_warning = "data_quality_warning"
    # A metric is null because it is mathematically undefined (e.g. profit
    # factor with no losing trades, Sharpe/Sortino with zero variance).
    metric_undefined = "metric_undefined"


Timeframe = str  # one of 15m, 1h, 4h, 1d (validated below)
TIMEFRAMES = {"15m", "1h", "4h", "1d"}

T = TypeVar("T")


class Signal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    strategy_id: str
    strategy_version: str
    symbol: str
    asset_class: AssetClass
    timeframe: Timeframe
    side: Side
    generated_at: datetime = Field(description="UTC ISO timestamp")
    bar_close_time: datetime = Field(description="Signal uses data up to this bar close only")
    entry: float | None = None
    stop_loss: float | None = None
    take_profit: list[float] = Field(default_factory=list)
    horizon_bars: int = Field(ge=1)
    confidence: float = Field(ge=0.0, le=1.0, description="Calibrated probability, not hype")
    features_snapshot: dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(max_length=500)
    status: SignalStatus = SignalStatus.active
    is_mock: bool = Field(default=False, description="True for placeholder data; never shown as real")
    confidence_calibrated: bool = Field(
        default=False, description="True only when confidence was calibrated on a named run"
    )
    calibration_run_id: str | None = Field(
        default=None, description="Backtest/calibration run that calibrated confidence"
    )
    exit_time: datetime | None = Field(default=None, title="SignalExitTime")
    exit_price: float | None = Field(default=None, title="SignalExitPrice")
    exit_reason: ExitReason | None = Field(default=None, title="SignalExitReason")

    @model_validator(mode="after")
    def _check(self) -> "Signal":
        self.symbol = normalize_symbol(self.symbol, self.asset_class)
        if self.confidence_calibrated and not self.calibration_run_id:
            raise ValueError("confidence_calibrated=True requires calibration_run_id")
        if self.timeframe not in TIMEFRAMES:
            raise ValueError(f"timeframe must be one of {sorted(TIMEFRAMES)}")
        if self.generated_at < self.bar_close_time:
            raise ValueError("generated_at must be >= bar_close_time (no lookahead)")
        if self.side != Side.flat:
            if self.entry is None or self.stop_loss is None or not self.take_profit:
                raise ValueError("long/short signals need entry, stop_loss and take_profit")
            if self.side == Side.long and not (self.stop_loss < self.entry < min(self.take_profit)):
                raise ValueError("long: stop_loss < entry < take_profit")
            if self.side == Side.short and not (self.stop_loss > self.entry > max(self.take_profit)):
                raise ValueError("short: stop_loss > entry > take_profit")
        return self


class Candle(BaseModel):
    """OHLCV bar. `time` is the bar open time (UTC). Never synthesize these."""

    model_config = ConfigDict(extra="forbid")

    time: datetime = Field(description="Bar open time, UTC ISO")
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str | None = Field(default=None, description="Vendor/store source of this bar, if recorded")


class OOSWindow(BaseModel):
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    trades: int | None = None
    # null = undefined for this window (see BacktestFlag.metric_undefined)
    metrics: dict[str, float | None] = Field(default_factory=dict)


class Trade(BaseModel):
    """One backtest trade. net_return and r_multiple are after fees and slippage."""

    model_config = ConfigDict(extra="forbid")

    symbol: str
    side: Side
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    exit_reason: ExitReason
    r_multiple: float
    bars_held: int = Field(ge=0)
    net_return: float

    @model_validator(mode="after")
    def _check(self) -> "Trade":
        if self.side == Side.flat:
            raise ValueError("trade side must be long or short")
        if self.exit_time < self.entry_time:
            raise ValueError("exit_time must be >= entry_time")
        return self


class BacktestReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    version: str
    period: dict[str, datetime]  # {"start": ..., "end": ...}
    oos_windows: list[OOSWindow]
    trades: list[Trade] = Field(description="Full trade list; net_return is after fees and slippage")
    trade_count: int = Field(ge=0, description="len(trades); stored so callers do not have to count")
    win_rate: float
    profit_factor: float | None = Field(description="null when undefined (no losing trades); see metric_undefined flag")
    sharpe: float | None = Field(description="null when undefined (zero variance); see metric_undefined flag")
    sortino: float | None = Field(description="null when undefined (no/zero-variance downside); see metric_undefined flag")
    max_drawdown: float
    avg_R: float
    exposure: float
    fees_bps: float
    slippage_bps: float
    run_id: str
    data_hash: str
    symbol: str | None = Field(
        default=None,
        title="BacktestSymbol",
        description="Per-market report symbol; null on the strategy summary",
    )
    timeframe: Timeframe | None = Field(
        default=None,
        title="BacktestTimeframe",
        description="Per-market report timeframe; null on the strategy summary",
    )
    flags: list[BacktestFlag] = Field(
        description="QA leakage warnings populated by Data. Always present on API responses."
    )

    @model_validator(mode="after")
    def _check(self) -> "BacktestReport":
        if self.trade_count != len(self.trades):
            raise ValueError("trade_count must equal len(trades)")
        if (self.symbol is None) != (self.timeframe is None):
            raise ValueError(
                "symbol and timeframe must both be set (per-market) or both be null (strategy summary)"
            )
        if self.symbol is not None:
            self.symbol = normalize_symbol(self.symbol)
            if self.timeframe not in TIMEFRAMES:
                raise ValueError(f"timeframe must be one of {sorted(TIMEFRAMES)}")
        return self


class Strategy(BaseModel):
    id: str
    version: str
    name: str
    description: str | None = None
    hypothesis: str | None = None
    hypothesis_id: str | None = None
    asset_classes: list[AssetClass]
    timeframes: list[Timeframe]
    latest_run_id: str | None = None

    @model_validator(mode="after")
    def _move_bare_hypothesis_id(self):
        """A bare id like 'H1' belongs in hypothesis_id, not hypothesis."""
        import re

        hyp = (self.hypothesis or "").strip() or None
        hid = (self.hypothesis_id or "").strip() or None
        self.hypothesis_id = hid
        if hyp and re.fullmatch(r"H\d+", hyp, re.IGNORECASE):
            if self.hypothesis_id is None:
                self.hypothesis_id = hyp
            self.hypothesis = None
        else:
            self.hypothesis = hyp
        desc = (self.description or "").strip() or None
        self.description = desc
        return self


class Page(BaseModel, Generic[T]):
    """List envelope for paginated collection endpoints."""

    model_config = ConfigDict(extra="forbid")

    items: list[T]
    next_cursor: str | None = None


class SignalPage(Page[Signal]):
    items: list[Signal] = Field(title="SignalItems")


class StrategyPage(Page[Strategy]):
    items: list[Strategy] = Field(title="StrategyItems")


class TenantConfig(BaseModel):
    """Public white-label config resolved from the request Host header."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    name: str
    logo_url: str | None = None
    colors: dict[str, str] = Field(default_factory=dict)
    extra_disclaimers: list[str] = Field(default_factory=list)
    tagline: str | None = None
    licensed_data_sources: list[str] = Field(
        default_factory=list,
        description="Platform licensed data sources. Read-only output; tenants cannot set this.",
        json_schema_extra={"readOnly": True},
    )



class BacktestIndexItem(BaseModel):
    """One per-market backtest in the index. Metrics live on GET /v1/backtests/{run_id}."""

    model_config = ConfigDict(extra="forbid")

    symbol: str
    timeframe: Timeframe
    run_id: str
    flags: list[BacktestFlag]
    approved: bool

    @model_validator(mode="after")
    def _check(self) -> "BacktestIndexItem":
        self.symbol = normalize_symbol(self.symbol)
        if self.timeframe not in TIMEFRAMES:
            raise ValueError(f"timeframe must be one of {sorted(TIMEFRAMES)}")
        return self


class BacktestIndexPage(Page[BacktestIndexItem]):
    items: list[BacktestIndexItem] = Field(title="BacktestIndexItems")


class StreamToken(BaseModel):
    """Short-lived, single-use token from POST /v1/stream/token for WS first-message auth."""

    model_config = ConfigDict(extra="forbid")

    token: str
    expires_at: datetime = Field(description="UTC expiry (60s after issue)")
