"""Test fixtures. All market-like data in this suite is SYNTHETIC."""

from __future__ import annotations

import pytest

from signal_quant.synthetic import make_synthetic_ohlcv


@pytest.fixture
def synth_15m():
    return make_synthetic_ohlcv(360, timeframe="15m", seed=42, process="trend")


@pytest.fixture
def synth_range():
    return make_synthetic_ohlcv(360, timeframe="15m", seed=21, process="range")
