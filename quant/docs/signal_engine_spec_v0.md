# Signal Engine Design Spec v0

**Status:** Draft, aligned with locked v1 decisions. This document is a design. It states no accuracy, hit rate, expectancy, Sharpe, or return figures — none have been measured on market data.

**Author:** Quant Strategist
**Date:** 25 November 2026 (America/New_York)
**Package:** `/workspace/signal-app/quant` (`signal_quant`)
**Canonical contract:** `/workspace/signal-app/shared` (`signal_shared.models`)

---

## 1. Purpose and sources of truth

The signal engine turns multi-timeframe OHLCV (and, later, auxiliary series) into `Signal` objects that Backend can serve, the web app can render, and Data can backtest. Quant does not invent a second wire format.

Sources of truth this spec follows:

- Lead Architect v1 models and JSON schemas in `/workspace/signal-app/shared` (`Signal`, `BacktestReport`, `OOSWindow`, `Strategy` metadata, including `is_mock` and `qa_approved`).
- Data Engineer backtester contract: at each bar close the backtester calls `generate(bars_by_timeframe, as_of)`; every timeframe is truncated at `as_of`; higher timeframes include only fully closed bars.
- Data Engineer labeling contract: exits are triple-barrier (stop, first take-profit, or timeout at `horizon_bars`); if stop and a target are both touched in one bar, the outcome is a stop. Exported `outcome`, `R` multiple, and `bars_held` are the calibration training target.
- Lead Architect final ML policy: fit models on crypto for all v1 timeframes; on equities and FX, fit on **1d only**. Equity / FX 15m, 1h, and 4h are parameter-free rule confirmations flagged `insufficient_oos_history` (4h is resampled from yfinance 1h and has only about two years of history; 15m / 1h yfinance history is shorter still).
- QA checklist and truncation audit in `/workspace/signal-app/qa` (lookahead, fill model, costs, sample size, calibration, no product-pricing copy).
- Research data layout: Parquet + DuckDB at `/workspace/signal-app/data/store/{asset_class}/{symbol}/{timeframe}.parquet` (columns: `open_time`, `close_time` UTC, OHLCV, `source`; closed bars only). Canonical symbols: `BTC-USDT`, `ETH-USDT`, `AAPL`, `EURUSD` (no slash). Quant loads this via `signal_quant.data_loader`. (An earlier path `/workspace/signal-data` was planned; the live store is under `signal-app/data`.)

If this package and `signal_shared` ever disagree, **shared wins**. Quant keeps a local model fallback only so the package can be imported when shared is not installed; it must stay field-compatible.

### 1.1 Locked v1 universe and stack

| Item | Locked value |
| --- | --- |
| Language / libs | Python 3.11, Polars / pandas, LightGBM, Pydantic v2 |
| Research storage | Parquet + DuckDB |
| Crypto (vs USDT) | BTC, ETH, SOL, BNB, XRP |
| Equities | SPY, QQQ, AAPL, MSFT, NVDA, TSLA, AMZN, META |
| FX | EURUSD, GBPUSD, USDJPY, AUDUSD |
| Timeframes | 15m, 1h, 4h, 1d |

### 1.2 Assumptions (where a plan is still missing)

- The store layout is published; files may still be absent. Until Parquet series are present, runnable demos and unit tests use **synthetic** OHLCV only. A real-store smoke, if files appear, only checks that `generate()` executes — it computes no performance metrics (Data's backtester owns those).
- Bar timestamps are **close times**, timezone-aware UTC. Higher timeframes built by `as_frame` are UTC-aligned to the Unix epoch (4h closes at 00/04/08/12/16/20 UTC; 1d at 00:00 UTC). Equity session closes and FX daily conventions may differ; when Data provides pre-built multi-timeframe Parquet or a session calendar, `generate` will consume those series as given and will not rebuild them.
- `Signal.entry` is the strategy's **reference price** (the closed bar's close). The backtester and live fill model use the **next bar open** (QA checklist), never the signal bar's high or low as a fill. Stops and targets are absolute prices computed from the reference entry and are fixed in v0 (no trailing). `Signal.symbol` is always the canonical store form (`BTC-USDT`, `AAPL`, `EURUSD`).
- v0 baseline strategies are rule-based. A LightGBM meta-model and a fitted calibrator are specified below but are **not fit on market data in this revision**. Until a calibrator is fit on exported trades, emitted `confidence` is an uncalibrated prior of 0.5 with `features_snapshot.confidence_is_calibrated = false`.
- HMM / clustering regime models are deferred; v0 regime labels are rule-based (ADX + trailing realized vol).
- News / event calendars, bid-ask spreads, and borrow/locate for equity shorts are Data-owned inputs. Filter hooks exist; they do not invent those series.
- This app is specified as a signal service, not an execution venue. Automated routing is an open product question (see §11).

---

## 2. Runtime interface

### 2.1 `Strategy.generate`

```text
generate(bars_by_timeframe: Mapping[str, DataFrame], as_of: datetime) -> list[Signal]
```

Called by the Data backtester at each trigger-timeframe bar close, and by the live pipeline on the same contract. `bars_by_timeframe` keys are `15m` / `1h` / `4h` / `1d`. Each frame is already truncated to `close_time <= as_of`. Higher-timeframe frames contain only **fully closed** bars.

`generate` itself truncates every timeframe to `close_time <= as_of` before any rule runs (implemented once in the `Strategy` base class). QA's mandatory gate (`qa/audits/lookahead_generate.py`) passes the *full* history and a future-scrambled copy; signals must not change. Strategies must also not resample a lower timeframe to fake a partial higher-timeframe bar. If the HTF series is missing or has not closed, a multi-timeframe rule simply does not fire.

`features_snapshot` is deterministic: key-sorted, rounded floats, no run-time clocks, no random key order. The QA gate compares `symbol`, `timeframe`, `side`, `entry`, `stop_loss`, `take_profit`, `confidence`, and `features_snapshot` at 1e-9 tolerance.

OHLCV schema: `open`, `high`, `low`, `close`, `volume`, indexed (or `close_time` column) by UTC close time, sorted, no future bars.

### 2.2 One generic adapter: `as_frame`

There is **no** per-strategy vectorized `to_frame`. A single adapter in `signal_quant.adapters` is the frame view that QA and any series-wide helper should use:

```text
as_frame(strategy, df) -> DataFrame[side, entry, stop_loss, confidence]
```

It replays `strategy.generate(bars_by_timeframe, as_of)` bar by bar over `df` (the trigger / base timeframe). At each close it:

1. Resets nothing mid-replay, but calls `strategy.reset()` at the *start* of each independent replay so cooldowns cannot leak from a previous full-frame pass into a prefix (required for QA's truncation test).
2. Keeps only closed base bars up to that `as_of`.
3. Builds higher timeframes with `resample_closed`. That function lives **only** in the data package (`signal_data.resample_closed`, session-aware). Crypto 4h: UTC-aligned blocks, complete only if all four hourly bars exist. Equities: anchored to the 09:30 ET session open — 09:30–13:30 (4 hourly bars) and 13:30–16:00 (shorter afternoon bar, `partial_session=True`); the afternoon bar is complete when all of its expected hourly bars are present; no bar spans two days. FX: drop any bucket that crosses the weekend close (Friday 17:00 America/New_York) or is missing hours. Until Data publishes the function, Quant's wrapper uses a temporary UTC full-count fallback for crypto only (TODO: remove) and **raises** on equity/FX 4h so a partial bucket cannot slip through.
4. Writes `side='flat'` and NaN entry / stop / confidence when `generate` returns no actionable signal.

`qa_strategy_fn(strategy)` wraps this in the `strategy_fn(df) -> DataFrame` shape expected by `qa/audits/lookahead.py`. That is how the truncation audit exercises the **exact** path the backtester and live pipeline run. Feature functions inside `generate` may still be vectorized for speed; only the strategy-to-frame boundary is the generic replay.

### 2.3 `Signal` object (canonical)

Fields must match `signal_shared.models.Signal` (extra fields forbidden):

| Field | Notes |
| --- | --- |
| `id` | UUID string |
| `strategy_id`, `strategy_version` | Link to a registered hypothesis |
| `symbol`, `asset_class` | `asset_class` ∈ {crypto, equity, fx} |
| `timeframe` | `15m` / `1h` / `4h` / `1d` |
| `side` | `long` / `short` / `flat` |
| `generated_at` | UTC; must be ≥ `bar_close_time` (no lookahead) |
| `bar_close_time` | Signal may use data only up to this close |
| `entry`, `stop_loss`, `take_profit[]` | Required for long/short. Long: `stop_loss < entry < min(take_profit)`. Short: `stop_loss > entry > max(take_profit)` |
| `horizon_bars` | ≥ 1 |
| `confidence` | In [0, 1]. Intended as a *calibrated* probability; see §6 |
| `features_snapshot` | JSON-safe values actually used, plus policy flags |
| `rationale` | ≤ 500 characters, human readable |
| `status` | `active` / `hit_tp` / `hit_sl` / `expired` / `cancelled` |
| `is_mock` | True for placeholders and synthetic smoke; never present as live |

`features_snapshot` always includes `ml_fit_allowed`, `insufficient_oos_history`, `rule_only`, and `confidence_is_calibrated`.

### 2.4 Backtest report (Data owns)

Quant does not produce user-visible metrics. Data's report follows `signal_shared.models.BacktestReport`:

`strategy_id`, `version`, `period`, `oos_windows[]`, `trades`, `win_rate`, `profit_factor`, `sharpe`, `sortino`, `max_drawdown`, `avg_R`, `exposure`, `fees_bps`, `slippage_bps`, `run_id`, `data_hash`, plus Architect-added `qa_approved` (only QA-approved reports are user-visible).

`fees_bps` and `slippage_bps` must be > 0 (QA). Report `flags` uses the shared `BacktestFlag` enum: `low_oos_trades`, `sharpe_gt_3`, `win_rate_gt_75`, `insufficient_oos_history`, `data_quality_warning`, `metric_recompute_mismatch`. Data / QA populate report flags. Quant only attaches `insufficient_oos_history` as signal *metadata* where the ML policy says so; it does not invent report flags (including `data_quality_warning`). Shared now types `trades` as `list[Trade]` plus `trade_count`, `qa_approved`, and `flags`. Each `Trade` carries `r_multiple`, `bars_held`, `exit_reason`, and `net_return` (after fees and slippage) — the same fields calibration trains on, together with signal `outcome` mapping (`tp` / `sl` / `timeout`).

A metric with fewer than 100 OOS trades is reported as insufficient sample, not as a headline number.

---

## 3. Features and multi-timeframe engineering

Implemented in `signal_quant.features` as **pure, causal, vectorized** functions. No centered rolling windows, no `shift(-n)`, no full-sample scaling or normalization. A unit test mutates future bars and asserts that past feature values do not change.

| Family | v0 functions |
| --- | --- |
| Trend | SMA, EMA, EMA difference / side, MACD line-signal-histogram, +DI/−DI |
| Momentum | RSI (Wilder), 1-bar return |
| Volatility | True range, ATR (Wilder), realized vol (trailing std of log returns), Bollinger width / %b |
| Volume | Volume / trailing SMA ratio, OBV |
| Structure | Donchian high/low on *prior* bars, causal swing high/low (`right=0`) |

`compute_features(df)` returns a frame aligned to the input index. Multi-timeframe features are joined only from **closed** HTF bars already present in `bars_by_timeframe` (last closed HTF row, possibly lagged to the HTF close, never a partial candle).

Feature fitting for ML (scalers, selection) happens **inside each training fold only**, never on the full sample.

---

## 4. Market regime detection

v0 labels (rule-based, `signal_quant.regime`):

- **Trend vs range:** ADX ≥ threshold (default 20, also an H1/H4 parameter) → `trend`, else `range`. Warmup → `unknown`.
- **High-vol:** trailing realized vol above a multiple of its own trailing median.

These labels gate H1–H4 (see `docs/hypotheses.md`). They are not a forecast and are not assigned an accuracy number.

A later revision may add an HMM or a clustering model on (ADX, realized vol, Bollinger width, signed volume). That work starts only after a registered hypothesis and will be fit inside walk-forward folds, not on the full history.

---

## 5. Ensemble / ML model design

### 5.1 Baseline (this revision)

Four rule-based strategies, each with a pre-registered hypothesis, emit the Signal contract:

| Hypothesis | Strategy id | Idea |
| --- | --- | --- |
| H1 | `trend_ema_adx` | EMA relationship + ADX / DI gate |
| H2 | `mean_reversion_rsi_bb` | RSI extreme + Bollinger tag, range only |
| H3 | `breakout_donchian` | Prior Donchian break + volume ratio |
| H4 | `mtf_confirmation` | Closed HTF trend + LTF pullback (no partial HTF) |

Parameters and the fixed search space are in `docs/hypotheses.md`, written **before** any market-data test. Search, if and when it happens, stays inside that space and is logged.

### 5.2 Labels (triple barrier)

Defined in `signal_quant.labeling`, matching Data's backtester:

- Fill at next bar open after `bar_close_time`.
- Path starts on the fill bar and lasts `horizon_bars`.
- End at stop, **first** take-profit, or timeout (exit at the last close).
- Stop and target both touched in the same bar → `hit_sl`.
- Outputs: `outcome` ∈ {hit_tp, hit_sl, expired, cancelled}, `r_multiple`, `bars_held`.

Primary ML / calibration labels are these trade outcomes (and optionally `R > 0` after costs). This is the López de Prado triple-barrier + meta-labeling setup, applied to the baseline events rather than to every bar.

### 5.3 Gradient-boosting meta-model (planned, not fit in v0)

When enough labeled OOS trades exist **and** the asset-class / timeframe is ML-eligible:

- Event = a baseline (H1–H4) candidate. Meta-label = 1 if the triple-barrier outcome is acceptable (registered definition: `hit_tp`, or `R` after costs above a pre-registered threshold — chosen before seeing results).
- Model: LightGBM classifier (and optionally a regression on `R`) on the causal feature snapshot plus regime flags.
- Fit only where `ml_fit_allowed` is true: **crypto all TFs; equity and FX 1d only**. Equity / FX 15m, 1h, and 4h stay parameter-free rule confirmations with `insufficient_oos_history` (4h comes from resampled yfinance 1h, ~2 years of history).
- Scalers, feature selection, and boosting rounds are fit inside each purged training fold. No full-sample encoding.
- The meta-model may turn a rule event into `flat` (reject) or pass it through with a calibrated confidence. It does not invent a second, unregistered entry rule in v1.

---

## 6. Confidence scoring and calibration

`Signal.confidence` is specified as a calibrated probability in [0, 1], not a marketing score.

- **Target:** estimated from Data's exported trades (`outcome`, `r_multiple`, `bars_held`), e.g. P(`hit_tp`) or P(`R > 0` after costs). The exact target is registered before fitting.
- **Methods:** isotonic regression or Platt (logistic) scaling, implemented in `signal_quant.calibration`. Fit on walk-forward **training** folds only.
- **Diagnostics (OOS, embargoed):** reliability diagram (calibration curve) and Brier score. These diagnostics are part of the QA pack that accompanies a backtest report; they are not user-facing claims until QA-approved.
- **v0 emit path:** no calibrator has been fit on market trades. Strategies emit `confidence = 0.5` with `confidence_is_calibrated = false`. Do not present that prior as a win probability.

---

## 7. Entry, stop, and target levels

Implemented in `signal_quant.levels`:

- **ATR-based:** `stop = entry ∓ sl_atr * ATR`; take-profits at registered R-multiples of that risk (defaults per hypothesis).
- **Structure-based:** optional stop beyond the prior causal swing (used as a fallback or tightening rule when it still satisfies `stop < entry` (long) or `stop > entry` (short)).
- **R-multiples:** targets are expressed as multiples of initial risk, then stored as absolute prices on the Signal.

Fill model (QA / Data): next bar open, or another explicit model Data documents. Gap past the stop on the fill bar is a stop.

---

## 8. Signal filtering

Applied after the raw rule (and, later, after the meta-model), via `signal_quant.filters`:

| Filter | v0 behavior |
| --- | --- |
| Regime gate | H1 requires `trend`; H2 requires `range` and blocks high-vol; H3 allows range or trend; H4 requires an HTF trend |
| Confidence threshold | Configurable; default 0.0 until a calibrator exists (the uncalibrated prior should not be thresholded as if it were a probability) |
| Cooldown | Applied in `as_frame` / the backtester only. `generate` is a pure function of `(bars, as_of)` so QA's gate can call it three times at the same as_of |
| Liquidity / spread | Hook only (`max_spread_bps`); no-ops until Data publishes a spread series |
| News / event | Hook only (`block_event_window`); no-ops until an event calendar exists |
| ML eligibility | Snapshot flags; equity / FX 15m, 1h, and 4h never become fitted-model signals in v1 (1d only) |

Overlapping signals from different strategy ids on the same symbol are all emitted; portfolio netting is a product / risk-policy question (§11), not a silent drop inside `generate`.

---

## 9. Validation protocol

Nothing in this section is a result. It is the protocol Data and Quant will use, and QA will audit, before a number can appear in the product.

1. **Hypothesis first.** Text in `docs/hypotheses.md` (or a new id) is committed before a run.
2. **Purged / embargoed walk-forward CV.** `signal_quant.walkforward.expanding_walk_forward` builds expanding train windows and fixed-length test windows with an embargo of at least `horizon_bars` so a training label cannot overlap the test fold. Parameter decisions are made only on training folds.
3. **Chronological holdout.** A final embargoed holdout (`holdout_split`) is touched once for the candidate that survived walk-forward. It is not used for search.
4. **Lookahead checks.** Feature unit test (mutate future bars). `as_frame` truncation test: `as_frame(df.iloc[:t+1]).iloc[-1] == as_frame(df).iloc[t]`. QA's `truncation_test` is run on `qa_strategy_fn(strategy)`. Higher-TF completeness is checked by `resample_closed`.
5. **Survivorship and data quality.** v1 names are current large caps / majors; delistings in the sample period are a residual risk and must be noted in the report. Gaps, duplicates, zero-volume bars, and outliers are flagged. Corporate actions must be adjusted consistently. Every run stores `run_id` and `data_hash` and is reproducible from the stored Parquet.
6. **Costs.** `fees_bps > 0` and `slippage_bps > 0`, stated per asset class. Falsification is after costs.
7. **Metrics Data will compute (and QA may recompute from the trade list):** hit rate (win rate), expectancy / `avg_R`, profit factor, Sharpe, Sortino, max drawdown, exposure, trade count. No metric is hardcoded in Quant, Backend, or the web app. Backtests are labeled hypothetical and are never mixed with live tallies.
8. **Calibration diagnostics** as in §6, OOS only.
9. **Overfitting controls.** Log the number of variants tried (inside the pre-registered space). Neighbourhood stability. Deflated Sharpe / multiple-testing note when many variants are tried. Minimum 100 OOS trades or "insufficient sample".
10. **Synthetic smoke only in this package revision.** `python -m signal_quant.smoke` and the unit tests use labeled synthetic data. They exist to prove the plumbing, not the edge.

---

## 10. Package layout

```text
/workspace/signal-app/quant/
  pyproject.toml
  README.md
  docs/
    signal_engine_spec_v0.md    # this file
    hypotheses.md               # H1–H4 registered before testing
  signal_quant/
    __init__.py                 # public exports
    models.py                   # re-exports signal_shared (no forked contract)
    symbols.py                  # canonical symbols; defers to data/shared helpers
    data_loader.py              # Parquet store loader (BTC-USDT / AAPL / EURUSD)
    strategy.py                 # Strategy.generate (truncates, then signals_at)
    adapters.py                 # as_frame, qa_strategy_fn  (THE frame adapter)
    bars.py                     # truncate; thin wrapper around signal_data.resample_closed
    audit_lookahead.py          # runner for qa/audits/lookahead_generate.py
    features.py                 # causal vectorized features
    regime.py                   # ADX / realized-vol labels
    levels.py                   # ATR and structure stops / R targets
    labeling.py                 # triple-barrier outcomes
    walkforward.py              # purged / embargoed splits
    calibration.py              # isotonic / Platt, reliability, Brier
    filters.py                  # regime, confidence, cooldown, stubs
    ml_policy.py                # where ML may be fit; insufficient-OOS flag
    synthetic.py                # SYNTHETIC OHLCV only
    smoke.py                    # python -m signal_quant.smoke
    strategies/
      trend.py                  # H1
      mean_reversion.py         # H2
      breakout.py               # H3
      mtf_confirmation.py       # H4
  tests/
    test_features_no_lookahead.py
    test_as_frame.py
    test_signal_contract.py
    test_triple_barrier.py
    test_walkforward.py
    test_smoke_synthetic.py
```

---

## 11. Open questions

### For Benjamin (product / data budget / risk)

1. **Market-data vendors and budget**, especially paid history for equity and FX 15m / 1h / 4h. Those timeframes are locked in the product but cannot support honest ML or long OOS tests on short yfinance history (4h is resampled from 1h, ~2 years). Should we buy a vendor (which one, what archive depth, what budget), drop sub-daily equity / FX as first-class signal timeframes, or keep 15m / 1h / 4h as rule-only confirmations indefinitely?
2. **Product mode.** Is this advisory-only (humans see signals), or will signals be routed to automatic execution? If execution is in scope: which venues, account types, and is **shorting equities** in scope (borrow / locate)? This changes both the fill model and whether `side=short` is valid for every equity.
3. **Risk policy for emission and display.** Risk per signal (percent or cash), max concurrent exposure / “heat”, what to do when H1–H4 overlap on the same symbol, and the confidence threshold at which a signal is user-visible once a calibrator exists.

### For the Lead Architect

4. **`BacktestReport.trades`:** resolved in shared as `list[Trade]` plus `trade_count`. Confirm QA's checker is pointed at this model (and the `flags` / `qa_approved` fields).
5. **Ingestion path and bar convention.** Confirm the move from `/workspace/signal-data` to `/workspace/signal-app/data`, the Parquet schema, and whether daily equity / FX bars are UTC midnight or session close. Quant's `as_frame` resampler is UTC-epoch-aligned only as a fallback when a single lower-TF frame is provided.
6. **Signal ingestion into Backend.** The backend README lists a future worker for Quant output. Preferred transport (object store of Signal JSON, a queue, or an HTTP ingest) and whether Quant writes `status=active` only, leaving Data / a position monitor to advance `hit_tp` / `hit_sl` / `expired`.

### For the Data & Backtesting Engineer

7. Confirm fee and slippage schedules per asset class (must be > 0) and the exact fill model (next-open vs more detailed) so hypotheses can be falsified against the same numbers the report will use.
8. Confirm the trade-export schema (`outcome`, `r_multiple`, `bars_held`, costs, `data_hash`) that calibration will train on, and when the first Parquet extract for the locked universe will be available.

---

## 12. What this revision explicitly does not claim

No walk-forward, no holdout, and no live book has been run on market data. Synthetic smoke tests prove that features are causal, `as_frame` matches prefix replays, signals validate against the shared contract, triple-barrier collisions resolve to a stop, and the splitter leaves an embargo. They are not evidence of an edge.
