"""Truncation test for lookahead bias.
A strategy passes if, for sampled bars t, the signal computed using only data up to t
equals the signal computed on the full history at t.

Expected strategy interface: fn(df: pandas.DataFrame) -> pandas.DataFrame/Series indexed like df
with at least a 'side' column (long|short|flat) and optionally entry/stop_loss/take_profit/confidence.
"""
import numpy as np, pandas as pd
COLS = ["side","entry","stop_loss","confidence"]
def truncation_test(strategy_fn, df: pd.DataFrame, n_samples: int = 50, warmup: int = 300, seed: int = 0, atol=1e-9):
    full = strategy_fn(df)
    full = full.to_frame("side") if isinstance(full, pd.Series) else full
    rng = np.random.default_rng(seed)
    idxs = sorted(rng.choice(np.arange(warmup, len(df)), size=min(n_samples, len(df)-warmup), replace=False))
    failures = []
    for t in idxs:
        part = strategy_fn(df.iloc[: t + 1])
        part = part.to_frame("side") if isinstance(part, pd.Series) else part
        a, b = full.iloc[t], part.iloc[-1]
        for c in [c for c in COLS if c in full.columns]:
            x, y = a[c], b[c]
            same = (pd.isna(x) and pd.isna(y)) or (np.isclose(x, y, atol=atol) if isinstance(x,(int,float,np.floating)) else x == y)
            if not same: failures.append((df.index[t], c, x, y))
    return failures
