
import httpx

from app.services.alerts import compose_alert_text, load_base_disclaimer, send_alerts
from app.services.repository import AlertChannelRecord
from tests.test_contract import _signal

BASE = "Not financial advice. This signal is generated automatically and may be wrong."


def test_alert_text_includes_base_disclaimer_and_tenant_extras():
    text = compose_alert_text(
        _signal(side="flat", rationale="breakout setup"),
        extra_disclaimers=["Tenant extra note.", BASE + " You are solely responsible for your trading decisions."],
    )
    base = load_base_disclaimer()
    assert base in text
    assert text.count(base) == 1  # tenant cannot strip or duplicate-remove the base
    assert "Tenant extra note." in text
    assert "breakout setup" in text
    assert "guaranteed" not in text.lower()


def test_send_alerts_mocks_http_and_isolates_failures():
    sig = _signal(id="a1", side="flat")
    good = AlertChannelRecord(
        id="disc-ok", tenant_id="demo", channel_type="discord",
        config={"webhook_url_env": "DISCORD_WEBHOOK"},
    )
    bad = AlertChannelRecord(
        id="tg-bad", tenant_id="demo", channel_type="telegram",
        config={"bot_token_env": "TG_TOKEN", "chat_id": "123"},
    )
    push = AlertChannelRecord(
        id="push", tenant_id="demo", channel_type="webpush", config={},
    )
    env = {"DISCORD_WEBHOOK": "https://discord.example/hook", "TG_TOKEN": "secret-token"}

    def handler(request: httpx.Request) -> httpx.Response:
        if "discord.example" in str(request.url):
            return httpx.Response(204)
        return httpx.Response(500, text="nope")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, timeout=5.0)
    failed = send_alerts(sig, [good, bad, push], ["extra"], client=client, env=env)
    assert failed == ["tg-bad"]
    # webpush is a stub and must not be treated as a failure
    assert "push" not in failed
    assert "disc-ok" not in failed
