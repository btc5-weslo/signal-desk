# Data quality — crypto_vision_staging

Generated at 2026-11-26T05:03:48.996492+00:00 (UTC).

- Series requested: **20**
- Succeeded: **20**
- Failed: **0**

Prices are from real free APIs. Empty or failed series are recorded honestly; no bars were synthesized.

## Notes

- Backfill written only to staging/. store/ was not touched.
- Source is binance_vision. CHECKSUM SHA-256 verified. 2025+ archives use microsecond timestamps (parsed, not dropped).

## Series

| Symbol | TF | Source | Bars | First open (UTC) | Last close (UTC) | Unexpected gaps | Gaps >3x | Stale bars | Stale runs >3 | Bad ticks | Outliers | Status |
|---|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| BTC-USDT | 15m | binance_vision | 324670 | 2017-08-17T04:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 42 | 30 | 60 | 30 | 0 | 2929 | ok |
| BTC-USDT | 1h | binance_vision | 81181 | 2017-08-17T04:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 18 | 11 | 4 | 11 | 0 | 806 | ok |
| BTC-USDT | 4h | binance_vision | 20310 | 2017-08-17T04:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 8 | 1 | 0 | 1 | 0 | 151 | ok |
| BTC-USDT | 1d | binance_vision | 3388 | 2017-08-17T00:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 0 | 0 | 0 | 0 | 0 | 5 | ok |
| ETH-USDT | 15m | binance_vision | 324670 | 2017-08-17T04:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 102 | 32 | 154 | 32 | 0 | 2283 | ok |
| ETH-USDT | 1h | binance_vision | 81181 | 2017-08-17T04:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 20 | 11 | 6 | 11 | 0 | 585 | ok |
| ETH-USDT | 4h | binance_vision | 20310 | 2017-08-17T04:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 8 | 1 | 0 | 1 | 0 | 106 | ok |
| ETH-USDT | 1d | binance_vision | 3388 | 2017-08-17T00:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 0 | 0 | 0 | 0 | 0 | 5 | ok |
| SOL-USDT | 15m | binance_vision | 220491 | 2020-08-11T06:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 0 | 10 | 13 | 10 | 0 | 1248 | ok |
| SOL-USDT | 1h | binance_vision | 55127 | 2020-08-11T06:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 8 | 2 | 3 | 2 | 0 | 280 | ok |
| SOL-USDT | 4h | binance_vision | 13787 | 2020-08-11T04:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 0 | 0 | 0 | 0 | 0 | 38 | ok |
| SOL-USDT | 1d | binance_vision | 2298 | 2020-08-11T00:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 0 | 0 | 0 | 0 | 0 | 5 | ok |
| BNB-USDT | 15m | binance_vision | 316923 | 2017-11-06T03:45:00+00:00 | 2026-11-26T00:00:00+00:00 | 115 | 30 | 161 | 30 | 0 | 3285 | ok |
| BNB-USDT | 1h | binance_vision | 79245 | 2017-11-06T03:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 19 | 10 | 5 | 10 | 0 | 817 | ok |
| BNB-USDT | 4h | binance_vision | 19826 | 2017-11-06T00:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 7 | 1 | 0 | 1 | 0 | 166 | ok |
| BNB-USDT | 1d | binance_vision | 3307 | 2017-11-06T00:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 0 | 0 | 0 | 0 | 0 | 18 | ok |
| XRP-USDT | 15m | binance_vision | 299868 | 2018-05-04T08:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 0 | 26 | 17 | 26 | 0 | 2370 | ok |
| XRP-USDT | 1h | binance_vision | 74977 | 2018-05-04T08:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 17 | 9 | 4 | 9 | 0 | 638 | ok |
| XRP-USDT | 4h | binance_vision | 18757 | 2018-05-04T08:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 7 | 0 | 0 | 0 | 0 | 140 | ok |
| XRP-USDT | 1d | binance_vision | 3128 | 2018-05-04T00:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 0 | 0 | 0 | 0 | 0 | 22 | ok |

## Details

### BTC-USDT 15m

**Warnings / flags:**
- flagged 2929 statistical outlier bar(s); prices kept as published
- kept 60 stale bar(s) in the raw store with is_stale=True (volume==0 and open==high==low==close); get_candles/load_closed drop them by default
- detected 30 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 42 unexpected gap(s)
- detected 30 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

**Source history limitations (not fabricated coverage):**
- History is whatever data.binance.vision published for this pair (first monthly archive through the latest daily file). No binanceus rows were merged.

**Fetch attempts:**
- `binance_vision` ok, bars=324670 (monthly_zips=111; daily_zips=25; checksums=sha256 verified)

### BTC-USDT 1h

**Warnings / flags:**
- flagged 806 statistical outlier bar(s); prices kept as published
- kept 4 stale bar(s) in the raw store with is_stale=True (volume==0 and open==high==low==close); get_candles/load_closed drop them by default
- detected 11 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 18 unexpected gap(s)
- detected 11 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

**Source history limitations (not fabricated coverage):**
- History is whatever data.binance.vision published for this pair (first monthly archive through the latest daily file). No binanceus rows were merged.

**Fetch attempts:**
- `binance_vision` ok, bars=81181 (monthly_zips=111; daily_zips=25; checksums=sha256 verified)

### BTC-USDT 4h

**Warnings / flags:**
- flagged 151 statistical outlier bar(s); prices kept as published
- detected 1 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 8 unexpected gap(s)
- detected 1 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

**Source history limitations (not fabricated coverage):**
- History is whatever data.binance.vision published for this pair (first monthly archive through the latest daily file). No binanceus rows were merged.

**Fetch attempts:**
- `binance_vision` ok, bars=20310 (monthly_zips=111; daily_zips=25; checksums=sha256 verified)

### BTC-USDT 1d

**Warnings / flags:**
- flagged 5 statistical outlier bar(s); prices kept as published

**Source history limitations (not fabricated coverage):**
- History is whatever data.binance.vision published for this pair (first monthly archive through the latest daily file). No binanceus rows were merged.

**Fetch attempts:**
- `binance_vision` ok, bars=3388 (monthly_zips=111; daily_zips=25; checksums=sha256 verified)

### ETH-USDT 15m

**Warnings / flags:**
- flagged 2283 statistical outlier bar(s); prices kept as published
- kept 154 stale bar(s) in the raw store with is_stale=True (volume==0 and open==high==low==close); get_candles/load_closed drop them by default
- detected 32 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 102 unexpected gap(s)
- detected 32 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

**Source history limitations (not fabricated coverage):**
- History is whatever data.binance.vision published for this pair (first monthly archive through the latest daily file). No binanceus rows were merged.

**Fetch attempts:**
- `binance_vision` ok, bars=324670 (monthly_zips=111; daily_zips=25; checksums=sha256 verified)

### ETH-USDT 1h

**Warnings / flags:**
- flagged 585 statistical outlier bar(s); prices kept as published
- kept 6 stale bar(s) in the raw store with is_stale=True (volume==0 and open==high==low==close); get_candles/load_closed drop them by default
- detected 11 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 20 unexpected gap(s)
- detected 11 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

**Source history limitations (not fabricated coverage):**
- History is whatever data.binance.vision published for this pair (first monthly archive through the latest daily file). No binanceus rows were merged.

**Fetch attempts:**
- `binance_vision` ok, bars=81181 (monthly_zips=111; daily_zips=25; checksums=sha256 verified)

### ETH-USDT 4h

**Warnings / flags:**
- flagged 106 statistical outlier bar(s); prices kept as published
- detected 1 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 8 unexpected gap(s)
- detected 1 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

**Source history limitations (not fabricated coverage):**
- History is whatever data.binance.vision published for this pair (first monthly archive through the latest daily file). No binanceus rows were merged.

**Fetch attempts:**
- `binance_vision` ok, bars=20310 (monthly_zips=111; daily_zips=25; checksums=sha256 verified)

### ETH-USDT 1d

**Warnings / flags:**
- flagged 5 statistical outlier bar(s); prices kept as published

**Source history limitations (not fabricated coverage):**
- History is whatever data.binance.vision published for this pair (first monthly archive through the latest daily file). No binanceus rows were merged.

**Fetch attempts:**
- `binance_vision` ok, bars=3388 (monthly_zips=111; daily_zips=25; checksums=sha256 verified)

### SOL-USDT 15m

**Warnings / flags:**
- flagged 1248 statistical outlier bar(s); prices kept as published
- kept 13 stale bar(s) in the raw store with is_stale=True (volume==0 and open==high==low==close); get_candles/load_closed drop them by default
- detected 10 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 10 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

**Source history limitations (not fabricated coverage):**
- History is whatever data.binance.vision published for this pair (first monthly archive through the latest daily file). No binanceus rows were merged.

**Fetch attempts:**
- `binance_vision` ok, bars=220491 (monthly_zips=75; daily_zips=25; checksums=sha256 verified)

### SOL-USDT 1h

**Warnings / flags:**
- flagged 280 statistical outlier bar(s); prices kept as published
- kept 3 stale bar(s) in the raw store with is_stale=True (volume==0 and open==high==low==close); get_candles/load_closed drop them by default
- detected 2 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 8 unexpected gap(s)
- detected 2 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

**Source history limitations (not fabricated coverage):**
- History is whatever data.binance.vision published for this pair (first monthly archive through the latest daily file). No binanceus rows were merged.

**Fetch attempts:**
- `binance_vision` ok, bars=55127 (monthly_zips=75; daily_zips=25; checksums=sha256 verified)

### SOL-USDT 4h

**Warnings / flags:**
- flagged 38 statistical outlier bar(s); prices kept as published

**Source history limitations (not fabricated coverage):**
- History is whatever data.binance.vision published for this pair (first monthly archive through the latest daily file). No binanceus rows were merged.

**Fetch attempts:**
- `binance_vision` ok, bars=13787 (monthly_zips=75; daily_zips=25; checksums=sha256 verified)

### SOL-USDT 1d

**Warnings / flags:**
- flagged 5 statistical outlier bar(s); prices kept as published

**Source history limitations (not fabricated coverage):**
- History is whatever data.binance.vision published for this pair (first monthly archive through the latest daily file). No binanceus rows were merged.

**Fetch attempts:**
- `binance_vision` ok, bars=2298 (monthly_zips=75; daily_zips=25; checksums=sha256 verified)

### BNB-USDT 15m

**Warnings / flags:**
- flagged 3285 statistical outlier bar(s); prices kept as published
- kept 161 stale bar(s) in the raw store with is_stale=True (volume==0 and open==high==low==close); get_candles/load_closed drop them by default
- detected 30 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 115 unexpected gap(s)
- detected 30 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

**Source history limitations (not fabricated coverage):**
- History is whatever data.binance.vision published for this pair (first monthly archive through the latest daily file). No binanceus rows were merged.

**Fetch attempts:**
- `binance_vision` ok, bars=316923 (monthly_zips=108; daily_zips=25; checksums=sha256 verified)

### BNB-USDT 1h

**Warnings / flags:**
- flagged 817 statistical outlier bar(s); prices kept as published
- kept 5 stale bar(s) in the raw store with is_stale=True (volume==0 and open==high==low==close); get_candles/load_closed drop them by default
- detected 10 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 19 unexpected gap(s)
- detected 10 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

**Source history limitations (not fabricated coverage):**
- History is whatever data.binance.vision published for this pair (first monthly archive through the latest daily file). No binanceus rows were merged.

**Fetch attempts:**
- `binance_vision` ok, bars=79245 (monthly_zips=108; daily_zips=25; checksums=sha256 verified)

### BNB-USDT 4h

**Warnings / flags:**
- flagged 166 statistical outlier bar(s); prices kept as published
- detected 1 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 7 unexpected gap(s)
- detected 1 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

**Source history limitations (not fabricated coverage):**
- History is whatever data.binance.vision published for this pair (first monthly archive through the latest daily file). No binanceus rows were merged.

**Fetch attempts:**
- `binance_vision` ok, bars=19826 (monthly_zips=108; daily_zips=25; checksums=sha256 verified)

### BNB-USDT 1d

**Warnings / flags:**
- flagged 18 statistical outlier bar(s); prices kept as published

**Source history limitations (not fabricated coverage):**
- History is whatever data.binance.vision published for this pair (first monthly archive through the latest daily file). No binanceus rows were merged.

**Fetch attempts:**
- `binance_vision` ok, bars=3307 (monthly_zips=108; daily_zips=25; checksums=sha256 verified)

### XRP-USDT 15m

**Warnings / flags:**
- flagged 2370 statistical outlier bar(s); prices kept as published
- kept 17 stale bar(s) in the raw store with is_stale=True (volume==0 and open==high==low==close); get_candles/load_closed drop them by default
- detected 26 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 26 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

**Source history limitations (not fabricated coverage):**
- History is whatever data.binance.vision published for this pair (first monthly archive through the latest daily file). No binanceus rows were merged.

**Fetch attempts:**
- `binance_vision` ok, bars=299868 (monthly_zips=102; daily_zips=25; checksums=sha256 verified)

### XRP-USDT 1h

**Warnings / flags:**
- flagged 638 statistical outlier bar(s); prices kept as published
- kept 4 stale bar(s) in the raw store with is_stale=True (volume==0 and open==high==low==close); get_candles/load_closed drop them by default
- detected 9 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 17 unexpected gap(s)
- detected 9 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

**Source history limitations (not fabricated coverage):**
- History is whatever data.binance.vision published for this pair (first monthly archive through the latest daily file). No binanceus rows were merged.

**Fetch attempts:**
- `binance_vision` ok, bars=74977 (monthly_zips=102; daily_zips=25; checksums=sha256 verified)

### XRP-USDT 4h

**Warnings / flags:**
- flagged 140 statistical outlier bar(s); prices kept as published
- detected 7 unexpected gap(s)

**Source history limitations (not fabricated coverage):**
- History is whatever data.binance.vision published for this pair (first monthly archive through the latest daily file). No binanceus rows were merged.

**Fetch attempts:**
- `binance_vision` ok, bars=18757 (monthly_zips=102; daily_zips=25; checksums=sha256 verified)

### XRP-USDT 1d

**Warnings / flags:**
- flagged 22 statistical outlier bar(s); prices kept as published

**Source history limitations (not fabricated coverage):**
- History is whatever data.binance.vision published for this pair (first monthly archive through the latest daily file). No binanceus rows were merged.

**Fetch attempts:**
- `binance_vision` ok, bars=3128 (monthly_zips=102; daily_zips=25; checksums=sha256 verified)

