"""With use_mock_data=false, no is_mock row reaches any response surface."""

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_broadcaster, get_repo
from app.core.config import get_settings
from app.main import app
from app.services.alerts import send_alerts
from app.services.mock_data import mock_signals
from app.services.repository import AlertChannelRecord, MockRepository
from tests.test_contract import _signal

H = {"X-API-Key": "dev-key"}


@pytest.fixture
def mock_off(monkeypatch):
    monkeypatch.setenv("SIGNAL_USE_MOCK_DATA", "false")
    get_settings.cache_clear()
    get_repo.cache_clear()
    get_broadcaster.cache_clear()
    repo = MockRepository(seed_mocks=False)
    leftover = mock_signals()[0]
    repo.add_signal(leftover, tenant_id="demo")
    app.dependency_overrides[get_repo] = lambda: repo
    try:
        yield repo, leftover, TestClient(app)
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        get_repo.cache_clear()
        get_broadcaster.cache_clear()


def test_startup_does_not_seed_mocks_when_off(mock_off):
    repo, leftover, _ = mock_off
    # Only the planted leftover exists; mock_trend was not seeded.
    assert leftover.id in repo._signals
    assert all(s.is_mock for s in repo._signals.values() if s.id == leftover.id)
    assert repo._strategies == []
    fresh = MockRepository(seed_mocks=False)
    assert fresh._signals == {} and fresh._strategies == []


def test_list_signals_omits_mocks_and_has_empty_summary(mock_off):
    _, leftover, client = mock_off
    body = client.get("/v1/signals", headers=H).json()
    assert body == {"items": [], "next_cursor": None}
    assert leftover.id not in [s["id"] for s in body["items"]]
    assert all(not s.get("is_mock") for s in body["items"])


def test_get_signal_mock_is_404(mock_off):
    _, leftover, client = mock_off
    assert client.get(f"/v1/signals/{leftover.id}", headers=H).status_code == 404


def test_ws_does_not_broadcast_mock_when_mock_off(mock_off):
    _, leftover, client = mock_off
    real = _signal(id="real-live", is_mock=False, rationale="real")
    b = get_broadcaster()
    with client.websocket_connect("/v1/stream/signals") as ws:
        ws.send_json({"type": "auth", "api_key": "dev-key"})
        n = asyncio.run(b.publish(leftover, tenant_id="demo"))
        assert n == 0
        asyncio.run(b.publish(real, tenant_id="demo"))
        got = ws.receive_json()
        assert got["id"] == "real-live" and got["is_mock"] is False


def test_alerts_skip_mock_when_mock_off(mock_off):
    _, leftover, _ = mock_off
    called = []

    def handler(request: httpx.Request) -> httpx.Response:
        called.append(str(request.url))
        return httpx.Response(204)

    ch = AlertChannelRecord(
        id="disc", tenant_id="demo", channel_type="discord",
        config={"webhook_url_env": "DISCORD_WEBHOOK"},
    )
    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)
    failed = send_alerts(
        leftover, [ch], client=client, env={"DISCORD_WEBHOOK": "https://discord.example/hook"},
    )
    assert failed == []
    assert called == []
