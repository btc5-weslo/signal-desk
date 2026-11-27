# Schemas

The canonical backtest result / signal / candle contracts live in
`/workspace/signal-app/shared` and are owned by the shared package:

- `../shared/backtest_result.schema.json` (alias of `backtest.schema.json`)
- `../shared/signal.schema.json`
- `../shared/candle.schema.json`

This package imports the Pydantic models from `signal_shared` and does not
define a competing `BacktestReport`. Extra run artifacts (equity curve,
slippage-audit trade log, total return / CAGR) are written alongside the
report JSON under `reports/` and are documented in the data README.
