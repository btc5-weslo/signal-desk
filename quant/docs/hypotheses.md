# Baseline strategy hypotheses (registered before testing)

**Status:** Pre-registered for v0. No hypothesis in this file has been tested on market data. Parameter values below are search-space anchors, not tuned results. Do not report accuracy or returns until Data and QA have published an approved out-of-sample backtest (`qa_approved: true`, with `run_id` and `data_hash`).

**Display.** lines were added after registration for UI use only. They do not change the tested claim in the **Hypothesis.** sentence.

Each baseline strategy in `signal_quant.strategies` is tied to exactly one hypothesis id. New variants get a new id *before* they are run. The number of variants actually tried must be logged with the backtest (QA overfitting checklist).

Shared execution assumptions (all four):

- Universe and timeframes are the v1 locked set (see the signal-engine spec).
- `Strategy.generate(bars_by_timeframe, as_of)` sees only bars with `close_time <= as_of`. Higher timeframes contain only fully closed bars. Strategies do not resample a lower timeframe to fabricate a partial higher-timeframe bar.
- `Signal.entry` is a reference price (the closed bar's close). The backtester fills at the **next bar open** (or an explicit fill model). Stops and targets are absolute prices.
- Exits are triple-barrier: stop, first take-profit, or timeout at `horizon_bars`. If stop and a target are both touched in the same bar, the outcome is a stop. Exported fields `outcome`, `r_multiple`, and `bars_held` are what confidence calibration trains on.
- Equity and FX 15m / 1h / 4h signals are **parameter-free rule confirmations** only and must be flagged `insufficient_oos_history`. Models are not fit on those series: 4h is resampled from yfinance 1h (~2 years of history), and 15m / 1h are shorter still. Crypto may use ML on all four timeframes; equity and FX ML on 1d only.
- Fees and slippage will be strictly greater than zero and stated per asset class in every report. Falsification is always evaluated *after* costs.
- A reported metric requires at least 100 out-of-sample trades; otherwise it is shown as insufficient sample (QA checklist).

Default horizon (bars, by signal timeframe): 15m → 16, 1h → 16, 4h → 10, 1d → 10. These are registered defaults, not optimized values.

---

## H1 — Trend (EMA relationship + ADX gate)

**Strategy id:** `trend_ema_adx` (version `0.1.0`)

**Hypothesis.** In a directional regime identified by ADX above a threshold, the relationship between a shorter and a longer EMA (confirmed by +DI/−DI) identifies the trade direction, and an ATR-multiple stop with R-multiple targets has positive expectancy after costs on the v1 universe, especially on 1h / 4h / 1d and in crypto / index ETFs.

**Display.** Trends tend to persist after a shorter-versus-longer EMA relationship is confirmed by ADX and plus/minus DI.

**Rationale.** Trend-following is the baseline for markets that spend time in persistent drift. ADX is used only as a *gate*, not as a magnitude forecast. DI alignment is a confirmation so the EMA relationship is not taken against the directional movement of the bar range. This is a rule-based baseline; a later gradient-boosting meta-model may accept or reject these events (meta-labeling) once enough labeled trades exist.

**Default parameters (v0 emit path).** `ema_fast=12`, `ema_slow=48`, `adx_period=14`, `adx_min=20`, `atr_period=14`, `sl_atr=2.0`, `tp_r=(1.5, 3.0)`, `cooldown_bars=4`, horizons as above.

**Fixed search space (pre-registered; do not expand after seeing results).**

- `ema_fast` ∈ {8, 12, 21}
- `ema_slow` ∈ {24, 48, 96} with `ema_fast < ema_slow`
- `adx_min` ∈ {15, 20, 25}
- `sl_atr` ∈ {1.5, 2.0, 2.5}
- first-target R ∈ {1.0, 1.5, 2.0}; second-target R ∈ {2.0, 3.0, 4.0} and strictly larger than the first

**Regime expected to work.** Trend regime (ADX at or above the gate), moderate realized vol.

**Regime expected to fail.** Range / low-ADX chop; immediate post-break regime flips; very high realized vol with wide two-sided wicks that tag both barriers.

**Falsification.** On pre-registered purged and embargoed walk-forward out-of-sample windows, after the stated fees and slippage: expectancy ≤ 0, or profit factor ≤ 1, or the result is not stable in a one-step neighbourhood of the chosen parameters, or a claimed metric is published with fewer than 100 OOS trades. Falsified hypotheses are kept in the log; they are not silently replaced by a newly searched variant under the same id.

---

## H2 — Mean reversion (RSI extremes + Bollinger, range regime)

**Strategy id:** `mean_reversion_rsi_bb` (version `0.1.0`)

**Hypothesis.** When ADX says the market is ranging and realized vol is not elevated, an RSI extreme that also tags or exits the matching Bollinger band mean-reverts enough, within the horizon, for an ATR-based stop and closer R-multiple targets to have positive expectancy after costs.

**Display.** When the market is ranging and realized vol is not elevated, price tends to mean-revert after an RSI extreme that also tags the matching Bollinger band.

**Rationale.** Mean reversion is the complement of H1 and should be *gated off* in trend and high-vol regimes (the usual failure mode is fading a break). RSI and Bollinger %b are combined so a single oscillator spike inside the bands is not enough. Targets are closer than H1 because the thesis is a return toward the middle of the range, not a new trend.

**Default parameters.** `rsi_window=14`, `rsi_low=30`, `rsi_high=70`, `bb_window=20`, `bb_std=2`, `sl_atr=1.5`, `tp_r=(1.0, 2.0)`, `cooldown_bars=4`, `block_high_vol=True`, range-regime gate on.

**Fixed search space.**

- `rsi_low` ∈ {20, 25, 30}; `rsi_high` ∈ {70, 75, 80}
- `bb_window` ∈ {16, 20, 24}; `bb_std` ∈ {1.5, 2.0, 2.5}
- `sl_atr` ∈ {1.0, 1.5, 2.0}
- first-target R ∈ {0.75, 1.0, 1.5}; second-target R ∈ {1.5, 2.0, 2.5} and strictly larger than the first

**Regime expected to work.** Range, not high-vol.

**Regime expected to fail.** Strong trend (ADX above the H1 gate); high realized vol; news-driven gaps that skip the stop (fill model and gap handling will be recorded, not assumed away).

**Falsification.** Same cost-aware OOS rules as H1, plus: if a material share of OOS losses cluster in periods the regime detector itself labeled `trend` or `high_vol`, the *gate* is considered broken and the hypothesis is falsified in its current form (do not “fix” it by tightening after the fact without a new id).

---

## H3 — Breakout (Donchian channel + volume confirmation)

**Strategy id:** `breakout_donchian` (version `0.1.0`)

**Hypothesis.** A close beyond the prior N-bar Donchian high or low, accompanied by a volume ratio above a threshold, marks the start of a short expansion move that can be traded with an ATR stop and R-multiple targets, after costs, on crypto at all v1 timeframes and on liquid equities / FX at 1d (and as a rule confirmation only on equity / FX 15m / 1h / 4h).

**Display.** A close beyond the prior Donchian channel, accompanied by volume above a threshold, tends to mark the start of a short expansion move.

**Rationale.** Donchian levels are computed on *prior* bars (`exclude_current=True`) so the break is measured against an already closed channel, not the bar that is making the new extreme. Volume ratio is a participation filter, not a prediction of continuation size. This is the natural counterpart to H2: H2 fades the range; H3 trades the range ending.

**Default parameters.** `donchian_window=20`, `volume_min=1.2`, `sl_atr=2.0`, `tp_r=(1.5, 3.0)`, `cooldown_bars=8`.

**Fixed search space.**

- `donchian_window` ∈ {10, 20, 40, 55}
- `volume_min` ∈ {1.0, 1.2, 1.5, 2.0}
- `sl_atr` ∈ {1.5, 2.0, 2.5}
- first-target R ∈ {1.0, 1.5, 2.0}; second-target R ∈ {2.0, 3.0, 4.0} and strictly larger than the first

**Regime expected to work.** Range-to-trend transitions; the first clean break after a compressed Donchian width.

**Regime expected to fail.** Repeated false breaks in two-sided chop; already-extended trends (late-channel rides); low-volume breaks.

**Falsification.** Same OOS, cost, sample-size, and neighbourhood-stability rules as H1. Also falsified if, on OOS windows, the volume filter does not change the trade set (i.e. it never binds) *and* we still attribute skill to it — in that case register a no-volume variant under a new id rather than claiming the filter helped.

---

## H4 — Multi-timeframe confirmation (closed HTF trend + LTF pullback)

**Strategy id:** `mtf_confirmation` (version `0.1.0`)

**Hypothesis.** Direction taken only from a *fully closed* higher timeframe (preferred pairs: 15m trigger with 1h HTF, 1h with 4h, 4h with 1d) in an ADX-confirmed HTF trend, with entry timed on the lower timeframe when price has pulled back to and resumed on the HTF side of the LTF fast EMA, has positive expectancy after costs relative to taking the HTF signal alone.

**Display.** A fully closed higher-timeframe ADX-confirmed trend sets direction, and a lower-timeframe pullback to the fast EMA is used to time entry.

**Rationale.** The higher timeframe is the hypothesis about direction; the lower timeframe is only a timing device. This strategy **must not** resample lower-timeframe bars to invent a partial HTF candle — if the HTF series is missing or the latest HTF bar is not fully closed, it emits nothing. Equity / FX 15m, 1h, and 4h triggers remain rule-only and flagged `insufficient_oos_history` (ML on equity / FX is 1d only).

**Default parameters.** HTF: `ema_fast=12`, `ema_slow=48`, `adx_min=20`. LTF trigger: close back on the HTF side of the LTF fast EMA and within 1 ATR of that EMA (pullback, not a chase). `sl_atr=2.0`, `tp_r=(1.5, 3.0)`, `cooldown_bars=4`. Horizons follow the *trigger* (lower) timeframe.

**Fixed search space.**

- HTF `ema_fast` / `ema_slow` / `adx_min` as in H1
- pullback band ∈ {0.5, 1.0, 1.5} ATR
- `sl_atr` and R-multiples as in H1
- preferred HTF pairing is fixed as above; a different pairing is a new hypothesis id

**Regime expected to work.** Established HTF trend, LTF pullbacks that do not break the HTF structure.

**Regime expected to fail.** HTF range (no ADX gate); LTF shocks that cut through the fast EMA and the stop in one bar; using an unfinished HTF bar (this is a process failure, not a market regime — the adapter and backtester are required to prevent it).

**Falsification.** Same OOS / cost / sample-size / stability rules as H1, plus a direct comparison (same walk-forward windows, same costs) against H1 run on the HTF alone. H4 is falsified if it does not improve after-cost expectancy or drawdown versus that HTF-only baseline on the pre-registered windows. That comparison is a relative test, not a claim that either number is known today.

---

## Changing a hypothesis

If a parameter outside the fixed search space is tried, or a rule is changed after seeing out-of-sample results, assign a new hypothesis id and a new `strategy_version`. Do not overwrite H1–H4. Data's backtest report carries `strategy_id` and `version` so QA can see which registered text was actually run.
