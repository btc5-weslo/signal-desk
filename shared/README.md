# Shared contracts

Pydantic models in `signal_shared/` are the source of truth for the signal, candle, strategy, and backtest contracts.

```
# from this directory; uses ../backend/.venv when present
python export_schema.py     # writes *.schema.json
bash generate_ts.sh         # refreshes schemas and writes ts/index.ts
```

`backtest.schema.json` and `backtest_result.schema.json` are both exported from `BacktestReport` so the historical name and the Data/QA name stay in sync. Data had not added a separate model when Backend took ownership of `/shared`.
