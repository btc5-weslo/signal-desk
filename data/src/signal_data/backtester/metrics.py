"""Performance metrics from an equity curve and a trade list.

All figures are computed from the actual trades / equity path — never hardcoded.
Sharpe and Sortino use sample standard deviation (ddof=1) and a 0 risk-free rate.
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd

from signal_data.schema import Trade, TradeAudit

# Periods per year for Sharpe/Sortino/CAGR on a regular bar equity curve.
ANNUALIZATION = {"15m": 365 * 24 * 4, "1h": 365 * 24, "4h": 365 * 6, "1d": 365}
EQUITY_DAILY = 252  # used when asset_class == equity and timeframe == 1d


def annualization_factor(timeframe: str, asset_class: str | None = None) -> float:
    if asset_class == "equity" and timeframe == "1d":
        return float(EQUITY_DAILY)
    return float(ANNUALIZATION.get(timeframe, 365))


def _as_trades(trades: Iterable[Trade | TradeAudit | dict]) -> list:
    return list(trades)


def win_rate(trades: Iterable) -> float:
    rows = _as_trades(trades)
    if not rows:
        return 0.0
    wins = sum(1 for t in rows if _net(t) > 0)
    return wins / len(rows)


# Metrics that can be mathematically undefined. They are reported as None
# (JSON null) with the ``metric_undefined`` flag, never a stand-in number.
UNDEFINABLE = ("profit_factor", "sharpe", "sortino")


def undefined_metrics(metrics: dict) -> list[str]:
    """Names of metrics in ``metrics`` that are None or non-finite."""
    out = []
    for k, v in (metrics or {}).items():
        if v is None or (isinstance(v, float) and not math.isfinite(v)):
            out.append(str(k))
    return out


def profit_factor(trades: Iterable) -> float | None:
    """Gross gains / gross losses. None when there are no losing trades (undefined)."""
    rows = _as_trades(trades)
    gains = sum(_net(t) for t in rows if _net(t) > 0)
    losses = sum(-_net(t) for t in rows if _net(t) < 0)
    if losses == 0:
        return None
    return gains / losses


def avg_R(trades: Iterable) -> float:
    rows = [t for t in _as_trades(trades) if math.isfinite(_r(t))]
    if not rows:
        return 0.0
    return float(np.mean([_r(t) for t in rows]))


def avg_win_loss(trades: Iterable) -> tuple[float, float]:
    rows = _as_trades(trades)
    wins = [_net(t) for t in rows if _net(t) > 0]
    losses = [_net(t) for t in rows if _net(t) < 0]
    avg_w = float(np.mean(wins)) if wins else 0.0
    avg_l = float(np.mean(losses)) if losses else 0.0
    return avg_w, avg_l


def max_drawdown(equity: pd.Series) -> float:
    """Maximum peak-to-trough decline as a negative fraction (e.g. -0.25)."""
    if equity is None or len(equity) == 0:
        return 0.0
    eq = equity.astype(float)
    peak = eq.cummax()
    dd = eq / peak - 1.0
    return float(dd.min()) if len(dd) else 0.0


def total_return(equity: pd.Series) -> float:
    if equity is None or len(equity) < 1:
        return 0.0
    start = float(equity.iloc[0])
    end = float(equity.iloc[-1])
    if start == 0:
        return 0.0
    return end / start - 1.0


# Pinned convention: year length is 365.25 calendar days.
CALENDAR_DAYS_PER_YEAR = 365.25


def cagr(equity: pd.Series, *, years: float | None = None, periods_per_year: float | None = None) -> float:
    """Compound annual growth rate of an equity curve.

    When ``years`` is omitted and the series has a DatetimeIndex, the year
    count is ``calendar_days / 365.25``, where ``calendar_days`` is the
    exact span between the first and last timestamps (including leap days).
    This is the only annualization convention used for CAGR in this package.
    ``periods_per_year`` is used only when there is no DatetimeIndex.
    """
    if equity is None or len(equity) < 2:
        return 0.0
    start = float(equity.iloc[0])
    end = float(equity.iloc[-1])
    if start <= 0:
        return 0.0
    if years is None:
        if isinstance(equity.index, pd.DatetimeIndex) and len(equity.index) >= 2:
            delta_days = (equity.index[-1] - equity.index[0]).total_seconds() / 86400.0
            years = delta_days / CALENDAR_DAYS_PER_YEAR
        elif periods_per_year:
            years = (len(equity) - 1) / periods_per_year
        else:
            years = (len(equity) - 1) / CALENDAR_DAYS_PER_YEAR
    if years <= 0:
        return 0.0
    return float((end / start) ** (1.0 / years) - 1.0)


def _period_returns(equity: pd.Series) -> pd.Series:
    return equity.astype(float).pct_change().dropna()


def sharpe(equity: pd.Series, periods_per_year: float) -> float | None:
    """None when undefined (fewer than 2 returns or zero variance)."""
    rets = _period_returns(equity)
    if len(rets) < 2:
        return None
    std = float(rets.std(ddof=1))
    if not math.isfinite(std) or std == 0:
        return None
    return float(rets.mean() / std * math.sqrt(periods_per_year))


def sortino(equity: pd.Series, periods_per_year: float) -> float | None:
    """None when undefined (fewer than 2 returns, or fewer than 2 / zero-variance downside returns)."""
    rets = _period_returns(equity)
    if len(rets) < 2:
        return None
    downside = rets[rets < 0]
    if len(downside) < 2:
        return None
    dstd = float(downside.std(ddof=1))
    if not math.isfinite(dstd) or dstd == 0:
        return None
    return float(rets.mean() / dstd * math.sqrt(periods_per_year))


def exposure(position_flags: pd.Series) -> float:
    """Fraction of bars with a non-flat position."""
    if position_flags is None or len(position_flags) == 0:
        return 0.0
    return float(np.mean(np.asarray(position_flags, dtype=float) != 0))


def _net(t) -> float:
    if isinstance(t, dict):
        return float(t["net_return"])
    return float(t.net_return)


def _r(t) -> float:
    if isinstance(t, dict):
        return float(t["r_multiple"])
    return float(t.r_multiple)


def summarize(
    trades: Iterable,
    equity: pd.Series,
    position_flags: pd.Series,
    *,
    timeframe: str,
    asset_class: str | None = None,
) -> dict[str, float | None]:
    ppy = annualization_factor(timeframe, asset_class)
    avg_w, avg_l = avg_win_loss(trades)
    return {
        "trade_count": float(len(_as_trades(trades))),
        "win_rate": win_rate(trades),
        "profit_factor": profit_factor(trades),
        "sharpe": sharpe(equity, ppy),
        "sortino": sortino(equity, ppy),
        "max_drawdown": max_drawdown(equity),
        "avg_R": avg_R(trades),
        "exposure": exposure(position_flags),
        "total_return": total_return(equity),
        "cagr": cagr(equity, periods_per_year=ppy),
        "avg_win": avg_w,
        "avg_loss": avg_l,
    }
