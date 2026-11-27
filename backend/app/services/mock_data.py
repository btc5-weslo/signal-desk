"""MOCK DATA ONLY. Every object here has is_mock=True and contains no performance metrics.
Removed once Quant/Data publish real signals and QA-approved backtests."""
from datetime import UTC, datetime, timedelta

from signal_shared import AssetClass, Side, Signal, Strategy


def mock_strategies() -> list[Strategy]:
    return [Strategy(id="mock_trend", version="0.0.0", name="[MOCK] Trend placeholder",
                     description="Placeholder until Quant ships baseline strategies.",
                     hypothesis="n/a (mock)", asset_classes=[AssetClass.crypto], timeframes=["1h"])]


def mock_signals() -> list[Signal]:
    bar = datetime(2026, 1, 1, 12, tzinfo=UTC)
    return [
        Signal(id="mock-1", strategy_id="mock_trend", strategy_version="0.0.0", symbol="BTC-USDT",
               asset_class=AssetClass.crypto, timeframe="1h", side=Side.long,
               generated_at=bar + timedelta(seconds=5), bar_close_time=bar, entry=100.0,
               stop_loss=95.0, take_profit=[110.0], horizon_bars=24, confidence=0.5,
               rationale="MOCK signal for UI wiring. Not a real signal.", is_mock=True),
        Signal(id="mock-2", strategy_id="mock_trend", strategy_version="0.0.0", symbol="EURUSD",
               asset_class=AssetClass.fx, timeframe="4h", side=Side.flat,
               generated_at=bar + timedelta(seconds=5), bar_close_time=bar, horizon_bars=6,
               confidence=0.5, rationale="MOCK flat signal. Not a real signal.", is_mock=True),
    ]
