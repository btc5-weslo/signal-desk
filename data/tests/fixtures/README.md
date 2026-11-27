# Test fixtures

`bnb_usdt_15m_stale_2020-06-20.parquet` is a real excerpt of BNB-USDT 15m bars
from the ingested series (source recorded on each row), 2020-06-20 10:00–21:00 UTC
inclusive of the last open. It contains stale bars (`volume==0` and `o==h==l==c`)
including a 20-bar contiguous run (12:15–17:00 UTC) and later runs of 5. Nothing
in the file is synthesized. Used by `test_stale_gaps.py` so tests stay valid if
the live store is later re-ingested without stale placeholders.
