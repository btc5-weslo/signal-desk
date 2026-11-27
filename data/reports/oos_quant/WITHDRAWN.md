# WITHDRAWN — do not quote any number from this folder

Withdrawn 2026-11-26 (America/New_York) after QA review. All 75 reports in
`reports/oos_quant/` are invalid, including the 4h / 1d results that looked
promising. They are kept only for the audit trail. The replacement run goes to
`reports/oos_quant_v2/`.

## Root cause (engine bug)

`src/signal_data/backtester/engine.py` (`run_backtest`) set `in_trade = True`
after resolving the first trade, in the "still inside the just-resolved trade"
branch, and never set it back to `False`. Pending signals were only filled
`if pending is not None and not in_trade`, so after the first trade the next
accepted signal stayed pending for the rest of the window and was only scored
by the post-loop "trailing pending" cleanup. Result: about 2 trades per test
window by construction, with trades taken depending on window boundaries.
Every metric (trade counts, win rate, profit factor, Sharpe, drawdown) is
therefore meaningless.

## Other defects in the same run (also fixed for v2)

1. `scripts/run_quant_walkforward.py` monkeypatched `last_bar_context` inside
   the Quant strategy modules and called `signals_at` on a 2-bar slice, so it
   did not test the code path the product runs.
2. `horizon = 16` was hard-coded for bar slicing instead of each signal's own
   `horizon_bars`.
3. Window metrics used `1000000.0` for an infinite profit factor and produced
   a Sortino of ~178 million; non-finite values were coerced to 0.0.

## Fix

- Engine: a position is open from fill until the `exit_time` returned by
  `signal_data.barriers.resolve` (the signal's own `horizon_bars`); signals are
  skipped only while a position is open; nothing is resolved after the loop;
  a trade that cannot fully resolve on the supplied bars is dropped and counted.
- Runner v2: signals from `signal_quant.registry.generate_range` only (fails
  loudly if missing), spot-checked against `run_for_bar` / `generate()`.
- Undefined PF / Sharpe / Sortino are `null` with the `metric_undefined` flag.
- Tests: `tests/test_engine_positions.py`, `tests/test_metric_undefined.py`,
  `tests/test_walkforward_runner.py`.
