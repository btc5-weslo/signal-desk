"""Alert fan-out: Discord, Telegram, SMTP, and a Web Push stub.

Channel config stores env-var *names* for secrets, never the secrets themselves.
Each channel is isolated: one failure does not block the others. Tenants may
add disclaimer text but cannot remove the QA base wording.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

import httpx
from signal_shared import Signal

from app.services.repository import AlertChannelRecord

log = logging.getLogger(__name__)

ALERT_DISCLAIMER = (
    "Not financial advice. This signal is generated automatically and may be wrong. "
    "You are solely responsible for your trading decisions."
)

HTTP_TIMEOUT = httpx.Timeout(5.0)
HTTP_RETRIES = 2


def load_base_disclaimer() -> str:
    path = Path(__file__).resolve().parents[3] / "qa" / "DISCLAIMERS.md"
    if path.is_file():
        text = path.read_text()
        marker = "**Signal detail + every alert (email/Telegram/Discord/push):**"
        if marker in text:
            rest = text.split(marker, 1)[1].strip()
            line = rest.splitlines()[0].strip() if rest else ""
            if line:
                return line
    return ALERT_DISCLAIMER


def compose_alert_text(signal: Signal, extra_disclaimers: list[str] | None = None) -> str:
    base = load_base_disclaimer()
    levels = []
    if signal.entry is not None:
        levels.append(f"entry={signal.entry}")
    if signal.stop_loss is not None:
        levels.append(f"stop={signal.stop_loss}")
    if signal.take_profit:
        levels.append("tp=" + ",".join(str(x) for x in signal.take_profit))
    lines = [
        f"{signal.side.value} {signal.symbol} {signal.timeframe}",
        f"strategy={signal.strategy_id} {signal.strategy_version}",
        " ".join(levels),
        f"confidence={signal.confidence}",
        signal.rationale,
        base,
    ]
    seen = {base.strip()}
    for extra in extra_disclaimers or []:
        text = (extra or "").strip()
        if text and text not in seen:
            lines.append(text)
            seen.add(text)
    return "\n".join(line for line in lines if line)


def _secret(name: str | None, env: dict[str, str] | None) -> str | None:
    if not name:
        return None
    source = env if env is not None else os.environ
    return source.get(name)


def _post_with_retries(client: httpx.Client, url: str, **kwargs) -> None:
    last: Exception | None = None
    for attempt in range(HTTP_RETRIES + 1):
        try:
            r = client.post(url, **kwargs)
            r.raise_for_status()
            return
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            last = exc
    if last is not None:
        raise last


def send_discord(text: str, channel: AlertChannelRecord, *, client: httpx.Client, env=None) -> None:
    url = _secret(channel.config.get("webhook_url_env"), env)
    if not url:
        raise ValueError("discord channel missing webhook_url_env")
    _post_with_retries(client, url, json={"content": text})


def send_telegram(text: str, channel: AlertChannelRecord, *, client: httpx.Client, env=None) -> None:
    token = _secret(channel.config.get("bot_token_env"), env)
    chat_id = channel.config.get("chat_id")
    if not token or not chat_id:
        raise ValueError("telegram channel missing bot_token_env or chat_id")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    _post_with_retries(client, url, json={"chat_id": chat_id, "text": text})


def send_email(text: str, channel: AlertChannelRecord, *, env=None, smtp_factory=smtplib.SMTP) -> None:
    cfg = channel.config
    host = cfg.get("smtp_host", "localhost")
    port = int(cfg.get("smtp_port", 587))
    user = _secret(cfg.get("username_env"), env)
    password = _secret(cfg.get("password_env"), env)
    mail_from = cfg.get("from_addr")
    mail_to = cfg.get("to_addr")
    if not mail_from or not mail_to:
        raise ValueError("email channel missing from_addr or to_addr")
    msg = EmailMessage()
    msg["Subject"] = f"Signal {channel.config.get('subject_prefix', '')}".strip() or "Signal"
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg.set_content(text)
    with smtp_factory(host, port, timeout=5) as smtp:
        smtp.starttls()
        if user and password:
            smtp.login(user, password)
        smtp.send_message(msg)


def send_webpush_stub(text: str, channel: AlertChannelRecord) -> None:
    # TODO: Web Push (VAPID) delivery. Intentionally a no-op stub.
    log.info("webpush stub skipped for channel %s (%s chars)", channel.id, len(text))


def send_alerts(
    signal: Signal,
    channels: list[AlertChannelRecord],
    extra_disclaimers: list[str] | None = None,
    *,
    client: httpx.Client | None = None,
    env: dict[str, str] | None = None,
    smtp_factory=smtplib.SMTP,
) -> list[str]:
    """Send to every channel. Failures are isolated and returned as channel ids."""
    if signal.is_mock:
        from app.core.config import get_settings
        if not get_settings().use_mock_data:
            return []
    text = compose_alert_text(signal, extra_disclaimers)
    failed: list[str] = []
    own_client = client is None
    client = client or httpx.Client(timeout=HTTP_TIMEOUT)
    try:
        for ch in channels:
            if not ch.enabled:
                continue
            try:
                kind = ch.channel_type
                if kind == "discord":
                    send_discord(text, ch, client=client, env=env)
                elif kind == "telegram":
                    send_telegram(text, ch, client=client, env=env)
                elif kind == "email":
                    send_email(text, ch, env=env, smtp_factory=smtp_factory)
                elif kind == "webpush":
                    send_webpush_stub(text, ch)
                else:
                    raise ValueError(f"unknown alert channel type {kind}")
            except Exception:
                log.exception("alert channel %s (%s) failed", ch.id, ch.channel_type)
                failed.append(ch.id)
    finally:
        if own_client:
            client.close()
    return failed
