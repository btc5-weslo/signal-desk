"""Tests for the generic as_frame adapter (no per-strategy to_frame, no agreement test)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from signal_quant.adapters import AS_FRAME_COLUMNS, as_frame, qa_strategy_fn
from signal_quant.bars import resample_closed
from signal_quant.strategies import TrendEmaAdx
from signal_quant.synthetic import make_synthetic_ohlcv


@pytest.fixture
def strategy():
    return TrendEmaAdx(symbol="ETH-USDT", asset_class="crypto", is_mock=True)


def test_as_frame_shape_and_flat_defaults(strategy):
    df = make_synthetic_ohlcv(180, timeframe="15m", seed=5, process="trend")
    frame = as_frame(strategy, df, warmup=40)
    assert list(frame.columns) == AS_FRAME_COLUMNS
    assert frame.index.equals(df.index)
    flat = frame["side"] == "flat"
    assert flat.any()
    assert frame.loc[flat, ["entry", "stop_loss", "confidence"]].isna().all().all()
    active = frame["side"] != "flat"
    if active.any():
        assert frame.loc[active, "side"].isin(["long", "short"]).all()
        assert frame.loc[active, ["entry", "stop_loss", "confidence"]].notna().all().all()


def test_as_frame_truncation_matches_prefix_replay(strategy):
    """The last row of as_frame(df[:t+1]) equals as_frame(df).iloc[t] (no lookahead)."""
    df = make_synthetic_ohlcv(160, timeframe="15m", seed=8, process="trend")
    full = as_frame(strategy, df, warmup=50)
    rng = np.random.default_rng(0)
    # Sample a handful of bars after warmup; each prefix is an independent replay.
    idxs = sorted(rng.choice(np.arange(80, len(df)), size=6, replace=False).tolist())
    for t in idxs:
        part = as_frame(strategy, df.iloc[: t + 1], warmup=50)
        a = full.iloc[t]
        b = part.iloc[-1]
        assert a["side"] == b["side"], (t, a["side"], b["side"])
        for c in ("entry", "stop_loss", "confidence"):
            x, y = a[c], b[c]
            if pd.isna(x) and pd.isna(y):
                continue
            assert np.isclose(x, y, atol=1e-9, equal_nan=True), (t, c, x, y)


def test_as_frame_does_not_feed_partial_htf(strategy):
    """A 1h bar appears in the mapping only when its closing 15m bar has arrived."""
    df = make_synthetic_ohlcv(96, timeframe="15m", seed=1, process="trend")  # 24 hours
    # Take a 15m close that is *not* an hour close (e.g. :15, :30, :45).
    mid_hour = next(ts for ts in df.index if ts.minute in (15, 30, 45))
    htf = resample_closed(df.loc[:mid_hour], "1h", mid_hour, asset_class="crypto")
    if len(htf):
        assert (htf.index <= mid_hour).all()
        # No 1h close after mid_hour, and no bucket whose close is mid_hour unless
        # mid_hour is itself an hour close (it is not).
        assert mid_hour not in htf.index
        # The last included 1h close must have a 15m bar at that exact timestamp.
        assert htf.index[-1] in df.index


def test_qa_wrapper_shape(strategy):
    df = make_synthetic_ohlcv(80, timeframe="15m", seed=2, process="trend")
    fn = qa_strategy_fn(strategy, warmup=20)
    out = fn(df)
    assert list(out.columns) == AS_FRAME_COLUMNS
    assert len(out) == len(df)
