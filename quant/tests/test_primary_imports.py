"""Primary data-package imports must resolve to signal_data, not the fallback."""

from __future__ import annotations

import inspect

from signal_quant.bars import _ensure_signal_data_path
from signal_quant.labeling import _try_import_resolve
from signal_quant.masks import SOURCE, STALE_RUN_GAP_BARS, gap_segments, is_stale, stale_mask


def test_primary_imports_are_from_signal_data():
    _ensure_signal_data_path()

    import signal_data.masks as official_masks

    assert SOURCE == "signal_data.masks"
    # is_stale is the team name; official may export it or stale_mask.
    official_mask = getattr(official_masks, "is_stale", official_masks.stale_mask)
    assert is_stale is official_mask or stale_mask is official_masks.stale_mask
    assert is_stale.__module__.startswith("signal_data.")
    # Public names are the official functions (no behavior-changing wrapper).
    assert gap_segments is official_masks.gap_segments
    assert STALE_RUN_GAP_BARS == official_masks.STALE_RUN_GAP_BARS == 3

    import signal_quant._pending_data as pending

    assert is_stale is not pending.is_stale
    assert SOURCE != "signal_quant._pending_data"

    resolve = _try_import_resolve()
    assert resolve is not None
    assert resolve.__module__ == "signal_data.barriers"
    assert resolve.__name__ == "resolve"

    from signal_data.bars import load_closed

    assert load_closed.__module__ == "signal_data.bars"
    params = inspect.signature(load_closed).parameters
    assert "store_dir" in params or "data_dir" in params

    from signal_data.live import update

    assert update.__module__ == "signal_data.live"
    live_params = inspect.signature(update).parameters
    assert "store_dir" in live_params or "data_dir" in live_params
