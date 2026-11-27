# signal-quant

Quant signal engine (v0) for the Signal app.

- Design spec: `docs/signal_engine_spec_v0.md`
- Pre-registered hypotheses (documented before any test): `docs/hypotheses.md`
- Runnable package: `signal_quant`

This package emits signals that match the canonical contract in `/workspace/signal-app/shared`. It does not report accuracy or returns; nothing has been measured on live or historical market data.

```bash
cd /workspace/signal-app/quant
uv sync --extra dev --extra ml --python 3.11
uv run pytest
uv run python -m signal_quant.smoke   # synthetic data only
```

The backtester (Data) and QA truncation audit should call `as_frame(strategy, df)` from `signal_quant.adapters`, which replays `Strategy.generate(bars_by_timeframe, as_of)` bar by bar. Strategies must not resample lower timeframes to fabricate a partial higher-timeframe bar.

## Public generate APIs

Per closed bar (Data backtester and live):

```python
Strategy.generate(bars_by_timeframe, as_of) -> list[Signal]
run_for_bar(symbol, asset_class, timeframe, as_of, loader=None, *, data_dir=None) -> list[Signal]
```

`generate` truncates every timeframe at `as_of` (higher timeframes: fully closed bars only) and is a pure function of its arguments.

Vectorized range (indicators computed once on the frame truncated at `end`; still no lookahead):

```python
Strategy.signals_series(bars_by_timeframe, start, end, *, timeframe=None) -> list[Signal]
generate_range(strategy_id, symbol, asset_class, timeframe, start, end, *, data_dir=None, loader=None, version=None) -> list[Signal]
```

`signals_series` / `generate_range` return the same `Signal` objects `generate()` would emit at each closed trigger bar in `[start, end]` (`side`, `entry`, `stop_loss`, `take_profit`, `horizon_bars`, `confidence`; new UUIDs differ). Pass `data_dir` or set `SIGNAL_DATA_DIR`; there is no implicit default store path.

