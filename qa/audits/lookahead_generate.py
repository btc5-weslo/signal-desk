"""Pass/fail lookahead gate for the standard interface:
    strategy.generate(bars_by_timeframe: dict[str, DataFrame], as_of) -> list[Signal]
Two checks per sampled as_of:
 1. Future perturbation: scramble every bar with close_time > as_of (all timeframes); signals must not change.
 2. Truncation: drop all future bars; signals must equal the full-history call.
Bars frames need a 'close_time' column (UTC). Compared: symbol, timeframe, side, entry, stop_loss, take_profit, confidence, features_snapshot (float tol 1e-9).
"""
import numpy as np, pandas as pd
KEYS = ("symbol","timeframe","bar_close_time","horizon_bars","side","entry","stop_loss","take_profit","confidence","features_snapshot")
RTOL, ATOL = 1e-9, 1e-9
def _norm(v):
    if isinstance(v, dict): return {k: _norm(x) for k, x in sorted(v.items())}
    if isinstance(v, (list, tuple)): return [_norm(x) for x in v]
    if hasattr(v, "value"): return v.value
    if isinstance(v, (np.floating, np.integer)): return v.item()
    return v
def _close(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        if a != a and b != b: return True
        return bool(np.isclose(a, b, rtol=RTOL, atol=ATOL))
    return a == b
def _sigs(sigs):
    out = []
    for s in sigs or []:
        d = s if isinstance(s, dict) else (s.model_dump() if hasattr(s, "model_dump") else vars(s))
        out.append({k: _norm(d.get(k)) for k in KEYS})
    return sorted(out, key=lambda d: (str(d["symbol"]), str(d["timeframe"]), str(d["side"])))
def _same(a, b):
    return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
def _perturb(bars, as_of, rng):
    res = {}
    for tf, df in bars.items():
        df = df.copy(); m = df["close_time"] > as_of
        for c in ("open","high","low","close","volume"):
            if c in df: df.loc[m, c] = df.loc[m, c].to_numpy() * rng.uniform(0.5, 1.5, m.sum())
        res[tf] = df
    return res
def _ts(v):
    return None if v is None else pd.Timestamp(v).tz_localize("UTC") if pd.Timestamp(v).tzinfo is None else pd.Timestamp(v).tz_convert("UTC")
def _scramble_times(bars, as_of, rng):
    """Shuffle the timestamps (index + close_time/open_time) of future bars only."""
    res = {}
    for tf, df in bars.items():
        df = df.copy(); m = (df["close_time"] > as_of).to_numpy()
        if m.sum() > 1:
            perm = rng.permutation(np.flatnonzero(m))
            for c in ("close_time", "open_time"):
                if c in df: df.iloc[np.flatnonzero(m), df.columns.get_loc(c)] = df[c].to_numpy()[perm]
        res[tf] = df
    return res
def _contract_checks(raw, as_of, validator):
    errs = []
    for s in raw or []:
        d = s if isinstance(s, dict) else (s.model_dump() if hasattr(s, "model_dump") else vars(s))
        if validator is not None:
            try: validator(d)
            except Exception as e: errs.append(f"contract: {e}".splitlines()[0][:160])
        g, b = _ts(d.get("generated_at")), _ts(d.get("bar_close_time"))
        if b is not None and b > _ts(as_of): errs.append("bar_close_time > as_of")
        if g is not None and b is not None and g < b: errs.append("generated_at < bar_close_time")
    return errs
def _default_validator():
    try:
        from signal_shared import Signal
        return Signal.model_validate
    except Exception:
        return None
def lookahead_gate(generate, bars, as_of_list, seed=0, validator="auto"):
    """Returns list of (as_of, reason). Checks: contract validity, timestamps, future OHLCV
    perturbation, future timestamp scramble, truncation."""
    if validator == "auto": validator = _default_validator()
    rng = np.random.default_rng(seed); fails = []
    for as_of in as_of_list:
        raw = generate(bars, as_of)
        for e in _contract_checks(raw, as_of, validator): fails.append((as_of, e))
        base = _sigs(raw)
        if not _same(_sigs(generate(_scramble_times(bars, as_of, rng), as_of)), base): fails.append((as_of, "future_timestamp_scramble"))
        if not _same(_sigs(generate(_perturb(bars, as_of, rng), as_of)), base): fails.append((as_of, "future_perturbation"))
        trunc = {tf: df[df["close_time"] <= as_of] for tf, df in bars.items()}
        if not _same(_sigs(generate(trunc, as_of)), base): fails.append((as_of, "truncation"))
    return fails
