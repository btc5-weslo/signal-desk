"""Opaque cursors for signal list pagination, keyed on (generated_at, id) desc."""
from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime

_SEP = ""


def encode_signal_cursor(generated_at: datetime, signal_id: str) -> str:
    raw = f"{generated_at.isoformat()}{_SEP}{signal_id}".encode()
    return urlsafe_b64encode(raw).decode().rstrip("=")


def decode_signal_cursor(cursor: str) -> tuple[datetime, str]:
    if not cursor or not cursor.strip():
        raise ValueError("invalid cursor")
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = urlsafe_b64decode(padded.encode()).decode()
        stamp, signal_id = raw.split(_SEP, 1)
        generated_at = datetime.fromisoformat(stamp)
    except (ValueError, OSError) as e:
        raise ValueError("invalid cursor") from e
    if not signal_id:
        raise ValueError("invalid cursor")
    return generated_at, signal_id
