# Signal backend (FastAPI)

Serves live and (when enabled) mock trading signals. **Every mock object has `is_mock: true`.** With `SIGNAL_USE_MOCK_DATA=false`, no `is_mock` row is seeded at startup or returned from `/v1/signals`, `/v1/signals/{id}` (404), list summaries, WebSocket broadcasts, or alerts. No performance metrics are served until a matching `backtest_approvals` row exists for the report's `run_id` and `data_hash`. Candle data is read from the data layer; it is never synthesized. No product prices or invented performance numbers appear in this API.

## Setup

```
cd backend && uv sync --extra dev --python 3.11
```

Config via `SIGNAL_*` env vars (see `app/core/config.py`). `SIGNAL_USE_MOCK_DATA` defaults to `false`: no `is_mock` rows are seeded or served. Opt in locally with `SIGNAL_USE_MOCK_DATA=true`. In prod (`SIGNAL_ENV=prod`) startup raises `RuntimeError` if the JWT secret is the dev default, is shorter than 32 bytes, if mock data is on, if `SIGNAL_SERVE_UNAPPROVED` is on, or if `SIGNAL_REDIS_URL` is unset. The single data location is `SIGNAL_DATA_DIR` (settings field `data_dir`; there is no `SIGNAL_DATA_STORE_DIR`). It is the store root itself — the folder that contains `crypto/`, `equity/`, and `fx/` — so files are `$SIGNAL_DATA_DIR/{asset_class}/{symbol}/{timeframe}.parquet`. In `SIGNAL_ENV=dev` only, an unset value defaults to the repo `data/store` resolved as an absolute path. Staging and prod raise at startup if it is unset. Every `signal_data` / `signal_quant` call is given that path explicitly as `data_dir=` and/or `store_dir=`.

Auth: `Authorization: Bearer <JWT>` or `X-API-Key: dev-key` (dev only). Every authenticated data route is scoped to the principal's `tenant_id`. Branding lookup (`GET /v1/tenant/config`) uses `Host` / `X-Forwarded-Host` only and never decides data tenancy.

## API

```
uv run uvicorn app.main:app --reload     # http://localhost:8000/docs
```

If a dev server is already bound to `:8000`, use another port. Do not kill an existing process you do not own.

Endpoints:

- `GET /v1/health`
- `GET /v1/tenant/config` (public; branding host — see below). Optional `tagline`. `PATCH /v1/tenant/config` (auth) sets `tagline`; banned claims return 422, and a bad stored tagline is dropped on read.
- `GET /v1/signals` (filters: symbol, timeframe, status, limit, cursor — returns `{items, next_cursor}`)
- `GET /v1/signals/{id}`
- `GET /v1/strategies` (`{items, next_cursor}`; cursor is always null in v1). In real mode the catalog is synced from `signal_quant.registry.list_strategies()` at API startup and via `python -m app.cli sync-strategies`. Rows are global (`tenant_id` NULL), `is_mock=false`, unvalidated (`latest_run_id` unset), and carry no metrics. If the listing function is missing, sync logs a warning and skips rather than crashing.
- `GET /v1/backtests?strategy_id=&version=` — per-market index `{items:[{symbol,timeframe,run_id,flags,approved}], next_cursor}`. Metrics stay behind `GET /v1/backtests/{run_id}`.
- `GET /v1/backtests/{run_id}` (served only with a matching approvals row; `flags` is a `BacktestFlag` list and a full `trades` list; optional `symbol`/`timeframe` for per-market reports, both null on the strategy summary)
- `GET /v1/candles?symbol=&timeframe=&limit=` (optional `asset_class`; auth required, limit 1–5000, default 500; 404 if no Parquet; **bare array**, not a page envelope). Optional `source` is copied from the store column when present. Stale bars (`is_stale=true`) are dropped.
- `POST /v1/stream/token` (auth required) — see WebSocket auth below
- `WS /v1/stream/signals`

Symbols on the wire must be canonical (`BTC-USDT`, `AAPL` / `BRK.B`, `EURUSD`). See `signal_shared.normalize_symbol`. Aliases like `BTCUSDT` or `EURUSD=X` are rejected (Data's `to_canonical` / `to_source` still map those at ingest).

### List pagination

`GET /v1/signals`, `GET /v1/strategies`, and `GET /v1/backtests` return `{ "items": [...], "next_cursor": "<opaque>" | null }`. Signal cursors are opaque and keyed on `(generated_at, id)` descending; pass `?cursor=` for the next page. Strategy and backtest-index cursors are currently always `null`. `GET /v1/candles` stays a bare array.

### WebSocket auth and stream tokens

`POST /v1/stream/token` is authenticated by Bearer JWT or `X-API-Key` and returns a `StreamToken`:

```
{ "token": "<opaque>", "expires_at": "<UTC ISO>" }
```

The token is tenant-scoped, single-use, and expires 60 seconds after issue. When `SIGNAL_REDIS_URL` is set, tokens are stored in Redis (`SET` with `EX 60`, atomic `GETDEL`) so any API instance can consume them. The in-memory store is used only in dev when Redis is unset; prod requires Redis. The web proxy should mint the token server-side so the browser never sees the API key.

Connect to `/v1/stream/signals` and send a first message within 5 seconds. Every variant uses the same `type:"auth"` envelope (a bare `{"token":...}` is rejected):

```
{"type":"auth","token":"<JWT access token>"}
# or
{"type":"auth","api_key":"dev-key"}
# or, after POST /v1/stream/token:
{"type":"auth","token":"<stream token>"}
```

Query-string tokens are not accepted.

### Tenants and branding

`signals.tenant_id` and `backtest_runs.tenant_id` are nullable: `NULL` means a global row visible to every tenant (live pipeline signals are global; a QA-approved backtest with `tenant_id` NULL is visible to every tenant). A non-null value is tenant-private. `strategies.tenant_id` is likewise nullable (`NULL` = shared catalog). `backtest_approvals.tenant_id` is nullable: `NULL` is a global approval that any tenant may use to calibrate a signal.

`GET /v1/tenant/config` is unauthenticated. It resolves the branding host from `X-Forwarded-Host` only when the peer IP is in `SIGNAL_TRUSTED_PROXIES` (defaults: loopback / `localhost` for dev; add the Vercel proxy via config, not a hardcoded host), otherwise `Host`. Hostname only, port stripped, lowercase. Returns `{tenant_id, name, logo_url, colors, extra_disclaimers, tagline, licensed_data_sources}`. `licensed_data_sources` is a platform setting (`SIGNAL_LICENSED_DATA_SOURCES`, empty by default, read-only on this endpoint). Tenant rows or writes cannot set or override it; any tenant-supplied value is stripped. `binance_vision`, `yfinance`, and any `ccxt:*` source are never licensed (dropped from the setting with a warning) even if listed. Use `app.core.licensing.is_licensed_source` to check a source name. Unknown hosts return 404 so the web app can fall back to its neutral default. In dev, the mock repository maps `localhost` and `127.0.0.1` to the `demo` tenant; when using a real database, insert the corresponding `tenants` and `tenant_domains` rows.

### Visibility

Live (non-mock) signals are stored even without a QA-approved backtest, but they are not served, broadcast, or alerted unless there is an approved report for that exact `strategy_id + version + symbol + timeframe` (or `SIGNAL_SERVE_UNAPPROVED=true` in dev only).

### Candles

The adapter imports `get_candles` from `signal_data.candles` and always passes an explicit `data_dir=` / `store_dir=` (no `limit`/`end` — those are applied after the call). Official `get_candles` / `load_closed` drop stale bars by default. A store file may contain mixed sources; `source` is copied per bar. Extra columns such as the boolean `source_seam` changeover flag are ignored and are not returned. The shared stale/gap mask is `signal_data.masks.is_stale` / `gap_segments`. `asset_class` is taken from the canonical symbol or the optional query param. No other paths are searched.

CORS: `SIGNAL_CORS_ORIGINS` is an explicit list (JSON array or comma-separated). Methods are GET/POST/PATCH/DELETE/OPTIONS; headers are Authorization, Content-Type, X-API-Key. Credentials are enabled only when origins are explicit, never when the list is `*`.

## Live pipeline

`app.pipeline.runner.run_pipeline` is a plain callable (also the arq cron entrypoint, every minute). It detects newly closed bars via a `pipeline_cursors` watermark (first run initializes the cursor without replaying history), runs Quant strategies, stores global live signals (`tenant_id` NULL, `is_mock=false`, deterministic ids, deduped on strategy+version+symbol+timeframe+bar_close_time), tracks open signals with the same triple-barrier rules as Data, and fans out visible signals.

The live pipeline calls `signal_quant.registry.run_for_bar`, `signal_data.live.update` (cron poll of `get_candles` remains the cursor-based path when update returns no new bars), `signal_data.barriers.resolve`, and `signal_data.masks.is_stale` / `gap_segments`. Missing imports fail loudly. Do not invent a volume-based placeholder mask.

Alerts (`app.services.alerts`): Discord, Telegram, SMTP, and a Web Push stub. Channel config stores env-var *names* for secrets, never the secrets. QA disclaimer from `qa/DISCLAIMERS.md` is always included; tenants may add text but cannot remove the base wording. httpx timeouts, a couple of retries, and per-channel isolation.

## Migrations

Alembic reads `SIGNAL_DATABASE_URL` (via `app.core.config`; default `sqlite:///./dev.db`). For Postgres use e.g. `postgresql+psycopg://user:pass@host/db`.

```
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "message"   # after model changes
```

## Redis and multi-instance fan-out

When `SIGNAL_REDIS_URL` is set, the API Broadcaster publishes `{tenant_id, signal}` envelopes on the `signals` channel and each API instance subscribes, then fans out to its local WebSocket clients (a `tenant_id` of `null` is global and is delivered to every local subscriber). Publisher-side visibility (`emit._publish_if_visible`) is the production gate: unapproved markets are never published onto the channel. When the URL is unset (local dev and unit tests), fan-out stays in-process.

Stream tokens use the same Redis when configured (see WebSocket auth above).

## Worker

The arq worker requires Redis (`SIGNAL_REDIS_URL`, default `redis://localhost:6379/0` for the worker process only). Prod must set the URL.

```
uv run arq app.workers.worker.WorkerSettings
```

Jobs: `publish_signal` (validates a `signal_shared.Signal` and routes it through `emit._publish_if_visible` so unapproved markets never reach Redis or WebSocket clients), `fanout_alerts` (Discord / Telegram / SMTP / Web Push stub), and `scan_pipeline` (cron, every minute; same callable as `run_pipeline`).

## Tests

```
uv run pytest
uv run ruff check
# QA mock gate (run from backend/ with this project's venv):
PYTHONPATH=. .venv/bin/pytest ../qa/backend_gates
# CI-friendly shared TS check (skipped if npx is missing):
npx -p typescript@5 tsc --noEmit --strict ../shared/ts/index.ts
```

Tests must not hardcode bar counts or prices from the provisional crypto store.

## TypeScript types (shared contracts)

Canonical models live in `/shared/signal_shared`. JSON Schema and generated TS:

```
# from backend/; uses this project's venv when present to refresh schemas
python ../shared/export_schema.py          # writes /shared/*.schema.json
bash ../shared/generate_ts.sh              # also refreshes schemas, writes /shared/ts/index.ts
```

`generate_ts.sh` converts every `*.schema.json` in `/shared` (signal, signal_page, strategy, strategy_page, backtest, backtest_result, candle, tenant_config, backtest_index_page, stream_token) with `npx json-schema-to-typescript`. Commit the generated `/shared/ts/index.ts`.
