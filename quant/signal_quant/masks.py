"""Re-export official ``signal_data.masks`` helpers; do not wrap them.

``is_stale``, ``gap_segments``, and ``STALE_RUN_GAP_BARS`` are the official
functions (Data's reports were built on them). A missing ``signal_data.masks``
import fails loudly.
"""

from __future__ import annotations

from signal_quant.bars import _ensure_signal_data_path

_ensure_signal_data_path()

from signal_data.masks import STALE_RUN_GAP_BARS, gap_segments, is_stale

SOURCE = "signal_data.masks"
stale_mask = is_stale

__all__ = [
    "SOURCE",
    "STALE_RUN_GAP_BARS",
    "gap_segments",
    "is_stale",
    "stale_mask",
]
