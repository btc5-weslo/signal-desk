# QA & Risk Review Checklist (v1)

Nothing ships to users until every applicable box is checked and signed off by QA & Risk.

## 1. Lookahead / leakage
- [ ] Truncation test passes: signal at bar t computed on data[:t] == signal at t computed on full history (`qa/audits/lookahead.py`).
- [ ] Features use only bars with close_time <= bar_close_time; no centered rolling windows, no `shift(-n)`, no full-sample normalization/scaling fit.
- [ ] Higher-timeframe features use only *closed* HTF bars (no partially formed 4h/1d bar leaking into 15m/1h).
- [ ] ML: scalers/encoders/feature selection fit inside each training fold only; purged + embargoed CV; labels' horizon doesn't overlap test fold.
- [ ] Entry price = next bar open (or explicit fill model), never the signal bar's close/high/low.
- [ ] Stop and target both touched in one bar resolve to the worse outcome (stop first) unless intrabar data proves otherwise.

## 2. Survivorship / data quality
- [ ] Universe defined as-of each date; delisted/renamed symbols documented (v1 large caps/majors: risk noted in report).
- [ ] Gaps, duplicates, zero-volume bars, outliers flagged; corporate actions (splits/dividends) adjusted consistently.
- [ ] Every backtest records `data_hash` + `run_id` and is reproducible bit-for-bit from the stored Parquet.

## 3. Overfitting
- [ ] Hypothesis documented before testing (Quant).
- [ ] Number of strategy/param variants tried is logged; reported results are OOS walk-forward only.
- [ ] Parameter stability: neighbours of chosen params don't collapse performance.
- [ ] Deflated Sharpe / multiple-testing note when many variants tried.
- [ ] Minimum trade count per reported metric (>= 100 OOS trades, else shown as "insufficient sample").

## 4. Honest performance reporting
- [ ] Fees and slippage > 0 and stated per asset class.
- [ ] Every number in the UI traces to a backtest JSON (`run_id`) or live-tracked signals; no hardcoded/example metrics.
- [ ] Backtest vs. live results labelled separately; backtest clearly marked "hypothetical".
- [ ] Confidence scores are calibrated (reliability plot); not marketed as win probability unless calibrated as such.
- [ ] Drawdown and losing periods shown, not just win rate.
- [ ] Mock data visibly flagged as mock and impossible to deploy to prod (env guard).

## 5. Disclaimers / compliance basics
- [ ] "Not financial advice / for informational and educational purposes only" in footer, onboarding, signal detail, alerts (email/Telegram/Discord).
- [ ] "Past performance (including backtests) does not guarantee future results" next to every performance figure.
- [ ] Risk warning for leverage/crypto/forex.
- [ ] No language like "guaranteed", "risk-free", "sure win", "100%".
- [ ] Terms + privacy pages exist (white-label tenants can override).

## 6. No price in product
- [ ] `qa/audits/no_price_scan.py` passes on /web, /backend, /shared, /docs (user-facing).
- [ ] No pricing page, plan tiers with amounts, paywall amounts, or checkout amounts in UI or API.

## 7. Security
- [ ] No secrets in repo (scan), env vars only; `.env.example` with placeholders.
- [ ] JWT: short expiry, rotation, strong secret; tenant API keys hashed at rest; tenant isolation enforced in every query (test cross-tenant access returns 404/403).
- [ ] Rate limiting, input validation (Pydantic), CORS allowlist, security headers, WS auth.
- [ ] Dependency audit (pip-audit, npm audit) clean of high/critical.

## 8. Correctness / tests / performance
- [ ] Every signal validates against `shared/signal.schema.json`; long: stop < entry < TP; short: TP < entry < stop.
- [ ] Unit tests for indicators against reference values; integration test data -> signal -> API -> WS.
- [ ] Metric recompute: QA recomputes win_rate/PF/Sharpe/MDD from the trade list and matches report.
- [ ] Load test WS + REST; p95 latency target set by Lead.

## 9. UI polish
- [ ] Responsive (mobile/tablet/desktop), dark mode contrast AA, empty/loading/error states, timezone labels, no placeholder lorem/fake numbers.
