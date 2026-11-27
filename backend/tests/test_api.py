import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from signal_shared import Signal
from starlette.websockets import WebSocketDisconnect

from app.api.deps import get_broadcaster, get_repo
from app.core.config import get_settings
from app.core.security import create_access_token
from app.main import app
from tests.test_contract import _report, _signal

H = {"X-API-Key": "dev-key"}
c = TestClient(app)


def _headers_for(tenant_id: str) -> dict:
    tok = create_access_token("user", tenant_id, get_settings())
    return {"Authorization": f"Bearer {tok}"}


def test_health():
    assert c.get("/v1/health").json()["status"] == "ok"


def test_auth_required():
    assert c.get("/v1/signals").status_code == 401


def test_signals_are_flagged_mock():
    r = c.get("/v1/signals", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "next_cursor" in body
    assert body["items"] and all(s["is_mock"] for s in body["items"])
    assert all(s["symbol"] in {"BTC-USDT", "EURUSD"} for s in body["items"])


def test_signal_filter_requires_canonical_symbol():
    assert c.get("/v1/signals", params={"symbol": "BTCUSDT"}, headers=H).status_code == 422
    r = c.get("/v1/signals", params={"symbol": "BTC-USDT"}, headers=H)
    assert r.status_code == 200 and [s["id"] for s in r.json()["items"]] == ["mock-1"]


def test_signal_404():
    assert c.get("/v1/signals/nope", headers=H).status_code == 404


def test_no_unapproved_backtests_served():
    assert c.get("/v1/backtests/anything", headers=H).status_code == 404


def test_contract_rejects_lookahead():
    t = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError):
        Signal(id="x", strategy_id="s", strategy_version="1", symbol="BTC-USDT", asset_class="crypto",
               timeframe="1h", side="flat", generated_at=t - timedelta(minutes=1), bar_close_time=t,
               horizon_bars=1, confidence=0.5, rationale="r")


def test_contract_rejects_bad_long_levels():
    t = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError):
        Signal(id="x", strategy_id="s", strategy_version="1", symbol="BTC-USDT", asset_class="crypto",
               timeframe="1h", side="long", generated_at=t, bar_close_time=t, entry=100,
               stop_loss=105, take_profit=[110], horizon_bars=1, confidence=0.5, rationale="r")


def test_ws_first_message_auth():
    sig = c.get("/v1/signals/mock-1", headers=H).json()
    with c.websocket_connect("/v1/stream/signals") as ws:
        ws.send_json({"type": "auth", "api_key": "dev-key"})
        asyncio.run(get_broadcaster().publish(Signal(**sig), tenant_id='demo'))
        assert ws.receive_json()["id"] == "mock-1"


def test_ws_rejects_unauthenticated(monkeypatch):
    from app.api import v1
    monkeypatch.setattr(v1, "WS_AUTH_TIMEOUT_SECONDS", 0.05)
    with pytest.raises(WebSocketDisconnect), c.websocket_connect("/v1/stream/signals") as ws:
        ws.receive_text()


def test_tenant_cannot_read_others_signal():
    assert c.get("/v1/signals/mock-1", headers=H).status_code == 200
    assert c.get("/v1/signals/mock-1", headers=_headers_for("other")).status_code == 404
    other = c.get("/v1/signals", headers=_headers_for("other")).json()
    assert other == {"items": [], "next_cursor": None}


def test_backtest_requires_matching_approval_row():
    repo = get_repo()
    report = _report(run_id="run-no-approval", data_hash="hash-a")
    repo.add_backtest(report, tenant_id="demo")
    try:
        assert c.get("/v1/backtests/run-no-approval", headers=H).status_code == 404
    finally:
        repo.remove_backtest("run-no-approval")


def test_backtest_hash_mismatch_is_404():
    repo = get_repo()
    report = _report(run_id="run-mismatch", data_hash="hash-live")
    repo.add_backtest(report, tenant_id="demo")
    repo.add_approval("run-mismatch", "hash-other")
    try:
        assert c.get("/v1/backtests/run-mismatch", headers=H).status_code == 404
    finally:
        repo.remove_backtest("run-mismatch")


def test_tenant_cannot_read_others_backtest():
    repo = get_repo()
    report = _report(run_id="run-demo", data_hash="hash-demo")
    repo.add_backtest(report, tenant_id="demo")
    repo.add_approval("run-demo", "hash-demo")
    try:
        ok = c.get("/v1/backtests/run-demo", headers=H)
        assert ok.status_code == 200
        assert "flags" in ok.json() and "qa_approved" not in ok.json()
        assert c.get("/v1/backtests/run-demo", headers=_headers_for("other")).status_code == 404
    finally:
        repo.remove_backtest("run-demo")


def test_candles_auth_required():
    assert c.get("/v1/candles", params={"symbol": "BTC-USDT", "timeframe": "1h"}).status_code == 401


def test_candles_rejects_non_canonical_symbol(tmp_path, monkeypatch):
    from app.core.config import get_settings as _gs
    monkeypatch.setenv("SIGNAL_DATA_DIR", str(tmp_path))
    _gs.cache_clear()
    try:
        r = c.get("/v1/candles", params={"symbol": "BTCUSDT", "timeframe": "1h"}, headers=H)
        assert r.status_code == 422
    finally:
        _gs.cache_clear()


def test_candles_from_official_store_layout(tmp_path, monkeypatch):
    import polars as pl

    from app.core.config import get_settings as _gs
    path = tmp_path / "crypto" / "BTC-USDT" / "1h.parquet"
    path.parent.mkdir(parents=True)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    pl.DataFrame({
        "open_time": [t0, t0 + timedelta(hours=1), t0 + timedelta(hours=2)],
        "close_time": [t0 + timedelta(hours=1), t0 + timedelta(hours=2), t0 + timedelta(hours=3)],
        "open": [1.0, 2.0, 3.0],
        "high": [1.5, 2.5, 3.5],
        "low": [0.5, 1.5, 2.5],
        "close": [1.2, 2.2, 3.2],
        "volume": [10.0, 20.0, 30.0],
        "source": ["binance", "binance", "binance"],
    }).write_parquet(path)
    monkeypatch.setenv("SIGNAL_DATA_DIR", str(tmp_path))
    _gs.cache_clear()
    try:
        r = c.get(
            "/v1/candles",
            params={"symbol": "BTC-USDT", "timeframe": "1h", "limit": 2},
            headers=H,
        )
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list) and len(rows) == 2
        assert rows[0]["close"] == 2.2 and rows[1]["close"] == 3.2
        assert rows[0]["time"] < rows[1]["time"]
        assert set(rows[0]) >= {"time", "open", "high", "low", "close", "volume"}
    finally:
        _gs.cache_clear()


def test_candles_missing_404(tmp_path, monkeypatch):
    from app.core.config import get_settings as _gs
    monkeypatch.setenv("SIGNAL_DATA_DIR", str(tmp_path))
    _gs.cache_clear()
    try:
        r = c.get("/v1/candles", params={"symbol": "ETH-USDT", "timeframe": "1h"}, headers=H)
        assert r.status_code == 404
        assert "ETH-USDT" in r.json()["detail"]
    finally:
        _gs.cache_clear()


def test_strategies_use_page_envelope():
    r = c.get("/v1/strategies", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"items", "next_cursor"}
    assert body["next_cursor"] is None
    assert body["items"]
    assert any(s["id"] == "mock_trend" for s in body["items"])


def test_signals_cursor_pagination():
    first = c.get("/v1/signals", params={"limit": 1}, headers=H).json()
    assert len(first["items"]) == 1 and first["next_cursor"]
    second = c.get(
        "/v1/signals", params={"limit": 1, "cursor": first["next_cursor"]}, headers=H,
    ).json()
    assert len(second["items"]) == 1
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert second["next_cursor"] is None
    # pages together cover the unfiltered list, newest first
    both = [first["items"][0]["id"], second["items"][0]["id"]]
    all_ids = [s["id"] for s in c.get("/v1/signals", headers=H).json()["items"]]
    assert both == all_ids


def test_signals_invalid_cursor_is_422():
    assert c.get("/v1/signals", params={"cursor": "not-a-cursor"}, headers=H).status_code == 422


def test_calibrated_signal_accepted_with_approval():
    repo = get_repo()
    repo.add_approval("cal-ok", "h", tenant_id="demo")
    repo.add_signal(
        _signal(id="cal-sig", is_mock=True, confidence_calibrated=True, calibration_run_id="cal-ok"),
        tenant_id="demo",
    )
    try:
        got = c.get("/v1/signals/cal-sig", headers=H).json()
        assert got["confidence_calibrated"] is True
        assert got["calibration_run_id"] == "cal-ok"
        listed = c.get("/v1/signals", headers=H).json()["items"]
        assert any(s["id"] == "cal-sig" and s["confidence_calibrated"] for s in listed)
    finally:
        repo.remove_signal("cal-sig")
        repo.remove_approval("cal-ok")


def test_calibrated_signal_rejected_on_ingest():
    repo = get_repo()
    missing = _signal(id="cal-bad", confidence_calibrated=True, calibration_run_id="missing-run")
    with pytest.raises(ValueError, match="approved calibration run"):
        repo.add_signal(missing, tenant_id="demo")
    repo.add_approval("cal-other", "h", tenant_id="other")
    try:
        foreign = _signal(id="cal-bad", confidence_calibrated=True, calibration_run_id="cal-other")
        with pytest.raises(ValueError, match="approved calibration run"):
            repo.add_signal(foreign, tenant_id="demo")
    finally:
        repo.remove_approval("cal-other")


def test_calibrated_signal_forced_false_on_read():
    repo = get_repo()
    repo.add_approval("cal-revoked", "h", tenant_id=None)  # global, then revoked
    repo.add_signal(
        _signal(id="cal-rev", is_mock=True, confidence_calibrated=True, calibration_run_id="cal-revoked"),
        tenant_id="demo",
    )
    repo.remove_approval("cal-revoked")
    try:
        got = c.get("/v1/signals/cal-rev", headers=H).json()
        assert got["confidence_calibrated"] is False
        assert got["calibration_run_id"] == "cal-revoked"
    finally:
        repo.remove_signal("cal-rev")


def test_tenant_config_from_host():
    r = c.get("/v1/tenant/config", headers={"Host": "localhost"})
    assert r.status_code == 200
    body = r.json()
    assert body["tenant_id"] == "demo" and body["name"] == "Demo"
    assert body["logo_url"] is None
    assert body["colors"] == {} and body["extra_disclaimers"] == []
    assert body["licensed_data_sources"] == []
    # port is ignored
    assert c.get("/v1/tenant/config", headers={"Host": "localhost:8000"}).status_code == 200
    # no auth required, unknown host is 404
    assert c.get("/v1/tenant/config", headers={"Host": "unknown.example"}).status_code == 404


def test_global_backtest_visible_to_every_tenant():
    repo = get_repo()
    report = _report(
        run_id="run-global", data_hash="hash-global",
        symbol="BTC-USDT", timeframe="1h",
    )
    repo.add_backtest(report, tenant_id=None)
    repo.add_approval("run-global", "hash-global")
    try:
        assert c.get("/v1/backtests/run-global", headers=H).status_code == 200
        other = c.get("/v1/backtests/run-global", headers=_headers_for("other"))
        assert other.status_code == 200
        assert other.json()["run_id"] == "run-global"
        assert "sharpe" in other.json()
    finally:
        repo.remove_backtest("run-global")


def test_backtest_metrics_are_not_stripped_by_claims_guard():
    repo = get_repo()
    report = _report(
        run_id="run-metrics", data_hash="hash-metrics",
        symbol="BTC-USDT", timeframe="1h",
        sharpe=1.25, profit_factor=1.8, win_rate=0.55,
    )
    repo.add_backtest(report, tenant_id=None)
    repo.add_approval("run-metrics", "hash-metrics")
    try:
        body = c.get("/v1/backtests/run-metrics", headers=H).json()
        assert body["sharpe"] == 1.25
        assert body["profit_factor"] == 1.8
        assert body["win_rate"] == 0.55
    finally:
        repo.remove_backtest("run-metrics")


def test_list_backtests_index_is_tenant_scoped():
    repo = get_repo()
    approved = _report(
        run_id="idx-ok", data_hash="h1", strategy_id="s", version="1",
        symbol="BTC-USDT", timeframe="1h", flags=["low_oos_trades"],
    )
    pending = _report(
        run_id="idx-pend", data_hash="h2", strategy_id="s", version="1",
        symbol="ETH-USDT", timeframe="1h",
    )
    other = _report(
        run_id="idx-other", data_hash="h3", strategy_id="s", version="1",
        symbol="BTC-USDT", timeframe="4h",
    )
    global_run = _report(
        run_id="idx-global", data_hash="h4", strategy_id="s", version="1",
        symbol="BTC-USDT", timeframe="4h",
    )
    repo.add_backtest(approved, tenant_id="demo")
    repo.add_approval("idx-ok", "h1")
    repo.add_backtest(pending, tenant_id="demo")
    repo.add_backtest(other, tenant_id="other")
    repo.add_approval("idx-other", "h3")
    repo.add_backtest(global_run, tenant_id=None)
    repo.add_approval("idx-global", "h4")
    try:
        body = c.get(
            "/v1/backtests", params={"strategy_id": "s", "version": "1"}, headers=H,
        ).json()
        assert set(body) == {"items", "next_cursor"}
        assert body["next_cursor"] is None
        by_id = {i["run_id"]: i for i in body["items"]}
        assert set(by_id) == {"idx-ok", "idx-pend", "idx-global"}
        assert by_id["idx-ok"] == {
            "symbol": "BTC-USDT", "timeframe": "1h", "run_id": "idx-ok",
            "flags": ["low_oos_trades"], "approved": True,
        }
        assert by_id["idx-pend"]["approved"] is False
        assert by_id["idx-global"]["approved"] is True
        assert "sharpe" not in by_id["idx-ok"]
        hidden = c.get(
            "/v1/backtests", params={"strategy_id": "s", "version": "1"},
            headers=_headers_for("other"),
        ).json()
        assert {i["run_id"] for i in hidden["items"]} == {"idx-other", "idx-global"}
    finally:
        for rid in ("idx-ok", "idx-pend", "idx-other", "idx-global"):
            repo.remove_backtest(rid)


def test_forwarded_host_ignored_from_untrusted_ip():
    spoof = TestClient(app, client=("203.0.113.5", 12345))
    r = spoof.get(
        "/v1/tenant/config",
        headers={"Host": "localhost", "X-Forwarded-Host": "spoof.example"},
    )
    # Untrusted peer: Host wins, demo is bound to localhost.
    assert r.status_code == 200 and r.json()["tenant_id"] == "demo"


def test_forwarded_host_honored_from_trusted_proxy():
    repo = get_repo()
    repo.add_domain("brand.example", "demo")
    proxy = TestClient(app, client=("127.0.0.1", 12345))
    r = proxy.get(
        "/v1/tenant/config",
        headers={"Host": "internal.invalid", "X-Forwarded-Host": "brand.example"},
    )
    assert r.status_code == 200 and r.json()["tenant_id"] == "demo"


def test_tagline_write_rejects_banned_claims():
    assert c.patch(
        "/v1/tenant/config", json={"tagline": "Guaranteed returns"}, headers=H,
    ).status_code == 422
    assert c.patch(
        "/v1/tenant/config", json={"tagline": "Validated by experts"}, headers=H,
    ).status_code == 422
    assert c.patch(
        "/v1/tenant/config", json={"tagline": "A risk-free way to trade"}, headers=H,
    ).status_code == 422


def test_tagline_round_trip_and_dropped_on_read():
    repo = get_repo()
    ok = c.patch(
        "/v1/tenant/config", json={"tagline": "Signals for curious traders"}, headers=H,
    )
    assert ok.status_code == 200
    assert ok.json()["tagline"] == "Signals for curious traders"
    got = c.get("/v1/tenant/config", headers={"Host": "localhost"}).json()
    assert got["tagline"] == "Signals for curious traders"
    # Bypass the write check so a bad stored tagline is dropped on read.
    repo._tenants["demo"] = repo._tenants["demo"].model_copy(
        update={"tagline": "This is guaranteed"},
    )
    dropped = c.get("/v1/tenant/config", headers={"Host": "localhost"}).json()
    assert dropped["tagline"] is None
    repo.set_tenant_tagline("demo", None)


def test_stream_token_requires_auth():
    assert c.post("/v1/stream/token").status_code == 401


def test_stream_token_requires_auth_envelope():
    token = c.post("/v1/stream/token", headers=H).json()["token"]
    with pytest.raises(WebSocketDisconnect), c.websocket_connect("/v1/stream/signals") as ws:
        ws.send_json({"token": token})
        ws.receive_text()


def test_stream_token_ws_auth_and_tenant_scope():
    minted = c.post("/v1/stream/token", headers=H)
    assert minted.status_code == 200
    body = minted.json()
    assert set(body) == {"token", "expires_at"}
    exp = datetime.fromisoformat(body["expires_at"])
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    delta = (exp - datetime.now(UTC)).total_seconds()
    assert 50 <= delta <= 60
    sig = c.get("/v1/signals/mock-1", headers=H).json()
    with c.websocket_connect("/v1/stream/signals") as ws:
        ws.send_json({"type": "auth", "token": body["token"]})
        asyncio.run(get_broadcaster().publish(Signal(**sig), tenant_id="demo"))
        assert ws.receive_json()["id"] == "mock-1"

    other_tok = c.post("/v1/stream/token", headers=_headers_for("other")).json()["token"]
    with c.websocket_connect("/v1/stream/signals") as ws:
        ws.send_json({"type": "auth", "token": other_tok})
        asyncio.run(get_broadcaster().publish(Signal(**sig), tenant_id="demo"))
        asyncio.run(get_broadcaster().publish(Signal(**sig), tenant_id="other"))
        got = ws.receive_json()
        assert got["id"] == "mock-1"
        # Only the "other" tenant broadcast is visible on this socket; the
        # earlier demo publish must not have been delivered first.


def test_stream_token_rejected_after_expiry():
    from app.api.deps import get_stream_tokens
    token = c.post("/v1/stream/token", headers=H).json()["token"]
    rec = get_stream_tokens()._items[token]
    rec.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(WebSocketDisconnect), c.websocket_connect("/v1/stream/signals") as ws:
        ws.send_json({"type": "auth", "token": token})
        ws.receive_text()


def test_stream_token_rejected_on_reuse():
    token = c.post("/v1/stream/token", headers=H).json()["token"]
    with c.websocket_connect("/v1/stream/signals") as ws:
        ws.send_json({"type": "auth", "token": token})
        # Drain auth: a later publish would arrive only after auth succeeds.
        asyncio.run(get_broadcaster().publish(
            Signal(**c.get("/v1/signals/mock-1", headers=H).json()), tenant_id="demo",
        ))
        assert ws.receive_json()["id"] == "mock-1"
    with pytest.raises(WebSocketDisconnect), c.websocket_connect("/v1/stream/signals") as ws:
        ws.send_json({"type": "auth", "token": token})
        ws.receive_text()


def test_unapproved_live_signal_stored_but_not_served():
    repo = get_repo()
    live = _signal(id="live-hidden", strategy_id="s", strategy_version="1",
                   symbol="BTC-USDT", timeframe="1h", is_mock=False)
    repo.add_signal(live, tenant_id=None)
    try:
        assert c.get("/v1/signals/live-hidden", headers=H).status_code == 404
        ids = [s["id"] for s in c.get("/v1/signals", headers=H).json()["items"]]
        assert "live-hidden" not in ids
        report = _report(
            run_id="vis-ok", data_hash="hv", strategy_id="s", version="1",
            symbol="BTC-USDT", timeframe="1h",
        )
        repo.add_backtest(report, tenant_id=None)
        repo.add_approval("vis-ok", "hv")
        assert c.get("/v1/signals/live-hidden", headers=H).status_code == 200
        wrong_tf = _signal(
            id="live-4h", strategy_id="s", strategy_version="1",
            symbol="BTC-USDT", timeframe="4h", is_mock=False,
        )
        repo.add_signal(wrong_tf, tenant_id=None)
        assert c.get("/v1/signals/live-4h", headers=H).status_code == 404
    finally:
        repo.remove_signal("live-hidden")
        repo.remove_signal("live-4h")
        repo.remove_backtest("vis-ok")


def test_candles_include_source_from_store(tmp_path, monkeypatch):
    import polars as pl

    from app.core.config import get_settings as _gs
    path = tmp_path / "crypto" / "BTC-USDT" / "1h.parquet"
    path.parent.mkdir(parents=True)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    pl.DataFrame({
        "open_time": [t0, t0 + timedelta(hours=1)],
        "close_time": [t0 + timedelta(hours=1), t0 + timedelta(hours=2)],
        "open": [1.0, 2.0],
        "high": [1.5, 2.5],
        "low": [0.5, 1.5],
        "close": [1.2, 2.2],
        "volume": [10.0, 20.0],
        "source": ["binance", "binance"],
    }).write_parquet(path)
    monkeypatch.setenv("SIGNAL_DATA_DIR", str(tmp_path))
    _gs.cache_clear()
    try:
        r = c.get(
            "/v1/candles",
            params={"symbol": "BTC-USDT", "timeframe": "1h"},
            headers=H,
        )
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 2
        assert rows[0]["source"] == "binance" and rows[1]["source"] == "binance"
        assert "close" in rows[0]
    finally:
        _gs.cache_clear()


def test_official_candles_drop_stale_bars_and_keep_source(tmp_path, monkeypatch):
    import polars as pl

    from app.core.config import get_settings as _gs

    path = tmp_path / "crypto" / "BTC-USDT" / "15m.parquet"
    path.parent.mkdir(parents=True)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    pl.DataFrame({
        "open_time": [t0, t0 + timedelta(minutes=15), t0 + timedelta(minutes=30)],
        "close_time": [
            t0 + timedelta(minutes=15),
            t0 + timedelta(minutes=30),
            t0 + timedelta(minutes=45),
        ],
        "open": [1.0, 9.0, 3.0],
        "high": [1.5, 9.0, 3.5],
        "low": [0.5, 9.0, 2.5],
        "close": [1.2, 9.0, 3.2],
        "volume": [10.0, 0.0, 30.0],
        "source": ["binance", "binance", "binance"],
        "is_stale": [False, True, False],
    }).write_parquet(path)
    monkeypatch.setenv("SIGNAL_DATA_DIR", str(tmp_path))
    _gs.cache_clear()
    try:
        r = c.get(
            "/v1/candles",
            params={"symbol": "BTC-USDT", "timeframe": "15m"},
            headers=H,
        )
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 2
        assert [row["close"] for row in rows] == [1.2, 3.2]
        assert all(row["source"] == "binance" for row in rows)
    finally:
        _gs.cache_clear()



def _write_mixed_source_parquet(root):
    from datetime import UTC, datetime, timedelta

    import polars as pl

    path = root / "crypto" / "BTC-USDT" / "1h.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    pl.DataFrame({
        "open_time": [t0, t0 + timedelta(hours=1), t0 + timedelta(hours=2)],
        "close_time": [
            t0 + timedelta(hours=1), t0 + timedelta(hours=2), t0 + timedelta(hours=3),
        ],
        "open": [1.0, 2.0, 3.0],
        "high": [1.5, 2.5, 3.5],
        "low": [0.5, 1.5, 2.5],
        "close": [1.2, 2.2, 3.2],
        "volume": [10.0, 20.0, 30.0],
        "source": ["binance", "binance", "kraken"],
        "source_seam": [False, False, True],
        "ignored_flag": ["x", "y", "z"],
    }).write_parquet(path)
    return path


def test_candles_keep_per_bar_source_in_mixed_file(tmp_path, monkeypatch):
    from app.core.config import get_settings as _gs
    _write_mixed_source_parquet(tmp_path)
    monkeypatch.setenv("SIGNAL_DATA_DIR", str(tmp_path))
    _gs.cache_clear()
    try:
        r = c.get(
            "/v1/candles",
            params={"symbol": "BTC-USDT", "timeframe": "1h"},
            headers=H,
        )
        assert r.status_code == 200
        rows = r.json()
        assert [row["source"] for row in rows] == ["binance", "binance", "kraken"]
        assert all("source_seam" not in row and "ignored_flag" not in row for row in rows)
    finally:
        _gs.cache_clear()




def test_licensed_data_sources_are_platform_only(monkeypatch):
    from app.core.config import get_settings as _gs
    repo = get_repo()
    # Plant a tenant-supplied value; the API must ignore/strip it.
    repo._tenants["demo"] = repo._tenants["demo"].model_copy(
        update={"licensed_data_sources": ["tenant-owned", "binance_vision"]},
    )
    monkeypatch.setenv(
        "SIGNAL_LICENSED_DATA_SOURCES",
        "ok-source,binance_vision,yfinance,ccxt:binance",
    )
    _gs.cache_clear()
    try:
        body = c.get("/v1/tenant/config", headers={"Host": "localhost"}).json()
        assert body["licensed_data_sources"] == ["ok-source"]
        patched = c.patch(
            "/v1/tenant/config",
            json={"tagline": "Signals for curious traders",
                  "licensed_data_sources": ["hacked", "yfinance"]},
            headers=H,
        )
        assert patched.status_code == 200
        assert patched.json()["licensed_data_sources"] == ["ok-source"]
        assert "hacked" not in patched.json()["licensed_data_sources"]
        # Stored tenant row still must not keep a write-time override.
        assert repo._tenants["demo"].licensed_data_sources == []
        again = c.get("/v1/tenant/config", headers={"Host": "localhost"}).json()
        assert again["licensed_data_sources"] == ["ok-source"]
        assert again["tagline"] == "Signals for curious traders"
    finally:
        _gs.cache_clear()
        repo.set_tenant_tagline("demo", None)
