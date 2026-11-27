"""QA gate: with mock mode off, no is_mock row may reach any real-mode response.

Run with the backend venv:  cd backend && PYTHONPATH=. .venv/bin/pytest ../qa/backend_gates/test_no_mock_in_real_mode.py
Covers REST list + detail + pagination and the live/broadcast visibility check,
including the worst case where the mock market is approved and the dev
serve_unapproved override is on.
"""
import pytest

# Hard import on purpose: a missing backend venv/PYTHONPATH must fail, never skip.

from fastapi.testclient import TestClient  # noqa: E402

from app.api.deps import get_repo  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.pipeline.visibility import is_live_signal_visible  # noqa: E402
from app.services.mock_data import mock_signals  # noqa: E402
from app.services.repository import MockRepository  # noqa: E402

H = {"X-API-Key": "dev-key"}
MOCK_IDS = [s.id for s in mock_signals()]


def _real(serve_unapproved: bool) -> Settings:
    return Settings(use_mock_data=False, serve_unapproved=serve_unapproved, env="dev")


@pytest.fixture(params=[False, True], ids=["approved-only", "dev-override"])
def client(request):
    repo = MockRepository()
    for sig in mock_signals():  # inject mock rows explicitly; don't rely on dev seeding
        repo.add_signal(sig, tenant_id="demo")
    settings = _real(request.param)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_repo] = lambda: repo
    try:
        yield TestClient(app), repo, settings
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_repo, None)


def _all_items(c, **params):
    items, cursor = [], None
    while True:
        p = dict(params, limit=1, **({"cursor": cursor} if cursor else {}))
        r = c.get("/v1/signals", params=p, headers=H)
        assert r.status_code == 200, r.text
        body = r.json()
        items += body["items"]
        cursor = body["next_cursor"]
        if not cursor:
            return items


def test_health_reports_mock_off(client):
    c, _, _ = client
    assert c.get("/v1/health").json()["mock_data"] is False


@pytest.mark.parametrize("params", [{}, {"symbol": "BTC-USDT"}, {"symbol": "EURUSD"},
                                    {"status": "active"}, {"timeframe": "1h"}])
def test_list_never_returns_mock(client, params):
    c, _, _ = client
    items = _all_items(c, **params)
    assert not any(s["is_mock"] for s in items)
    assert not {s["id"] for s in items} & set(MOCK_IDS)


@pytest.mark.parametrize("sid", MOCK_IDS)
def test_detail_404s_for_mock(client, sid):
    c, _, _ = client
    assert c.get(f"/v1/signals/{sid}", headers=H).status_code == 404


@pytest.mark.parametrize("sig", mock_signals(), ids=MOCK_IDS)
def test_live_visibility_rejects_mock_even_if_market_approved(sig):
    repo = MockRepository()
    from tests.test_contract import _report  # backend test helper

    repo.add_backtest(_report(run_id="r-mock", data_hash="h", strategy_id=sig.strategy_id,
                              version=sig.strategy_version, symbol=sig.symbol,
                              timeframe=sig.timeframe), tenant_id=None)
    repo.add_approval("r-mock", "h")
    for override in (False, True):
        assert is_live_signal_visible(sig, repo=repo, tenant_id="demo",
                                      settings=_real(override)) is False
