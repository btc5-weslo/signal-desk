"""Regenerate /shared/*.schema.json from the Pydantic models.

    python shared/export_schema.py

BacktestReport is written as both backtest.schema.json (original name) and
backtest_result.schema.json (name Data/QA use). Data had not added a separate
model when this was written; one Pydantic class remains the source of truth.
"""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from signal_shared import (
    Signal, BacktestReport, Strategy, Candle, SignalPage, StrategyPage, TenantConfig,
    BacktestIndexPage, StreamToken,
)
out = pathlib.Path(__file__).parent
mapping = {
    "signal": Signal,
    "backtest": BacktestReport,
    "backtest_result": BacktestReport,
    "strategy": Strategy,
    "candle": Candle,
    "signal_page": SignalPage,
    "strategy_page": StrategyPage,
    "tenant_config": TenantConfig,
    "backtest_index_page": BacktestIndexPage,
    "stream_token": StreamToken,
}
for name, m in mapping.items():
    (out / f"{name}.schema.json").write_text(json.dumps(m.model_json_schema(), indent=2) + "\n")
print("schemas written:", ", ".join(mapping))
