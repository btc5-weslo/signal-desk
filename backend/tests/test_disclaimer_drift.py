"""Hard-coded backend disclaimer text must match qa/DISCLAIMERS.md exactly."""

from pathlib import Path

from app.services.alerts import ALERT_DISCLAIMER

_DISCLAIMERS = Path(__file__).resolve().parents[2] / "qa" / "DISCLAIMERS.md"
_MARKER = "**Signal detail + every alert (email/Telegram/Discord/push):**"


def test_hardcoded_alert_disclaimer_matches_qa_file():
    assert _DISCLAIMERS.is_file(), "qa/DISCLAIMERS.md is missing from the repo checkout"
    text = _DISCLAIMERS.read_text(encoding="utf-8")
    assert _MARKER in text, "qa/DISCLAIMERS.md is missing the alert-disclaimer marker"
    line = text.split(_MARKER, 1)[1].strip().splitlines()[0].strip()
    assert ALERT_DISCLAIMER == line
