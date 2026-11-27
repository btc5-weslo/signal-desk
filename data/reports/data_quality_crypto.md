# Data quality — crypto

Generated at 2026-11-26T05:21:07.798984+00:00 (UTC).

- Series requested: **20**
- Succeeded: **20**
- Failed: **0**

Prices are from real free APIs. Empty or failed series are recorded honestly; no bars were synthesized.

## Notes

- Universe: BTC, ETH, SOL, BNB, XRP vs USDT. Timeframes 15m, 1h, 4h, 1d.
- Store root is SIGNAL_DATA_DIR / data_dir= (directory that contains crypto/, equity/, fx/). Dev default /workspace/signal-app/data/store. No SIGNAL_DATA_STORE_DIR. Staging is optional SIGNAL_DATA_STAGING_DIR.
- Mixed sources allowed; binance_vision preferred on duplicate open_time; source never relabeled; source_seam marks a source change.
- Off-grid open_times (Feb 2018 Binance outage restarts) were DROPPED, not snapped, and count as missing. Alignment check FAILS a series if any remain.
- Dropped: BTC-USDT 15m 81 and 1h 43; ETH-USDT 15m 81 and 1h 43; BNB-USDT 15m 81 and 1h 43. First 15m 2018-02-09 09:58:14/15 UTC, last 2018-02-10 05:58; first 1h 2018-02-09 09:28:14/15, last 2018-02-11 03:28. SOL and XRP and all 4h/1d had none.
- Post-repair alignment scan of all 20 files: 0 off-boundary open_times remain.
- Incremental refresh_closed at 2026-11-26 05:19:22–05:19:52 UTC caught BTC/ETH 1h up from last close 04:00 to 05:00 and 15m from 04:45 to 05:15 (same last close as BNB/SOL/XRP). Cause of the lag: the binanceus restore fetched BTC then ETH before the 04:00 1h / 04:45 15m bars had closed; later symbols were fetched after 05:00. There was previously no incremental live updater. 4h last close 04:00 and 1d last close 00:00 are the latest fully closed bars at that as_of.
- Stale bars are kept in the raw store with is_stale=True. gap_segments treats stale as missing; a run of more than 3 stale/missing bars is a gap and sets data_quality_warning.

## Series

| Symbol | TF | Source | Bars | First open (UTC) | Last close (UTC) | Unexpected gaps | Gaps >3x | Stale bars | Stale runs >3 | Off-grid dropped | Bad ticks | Outliers | Status |
|---|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| BNB-USDT | 15m | binance_vision:316842,ccxt:binanceus:190 | 317032 | 2017-11-06T03:45:00+00:00 | 2026-11-26T05:15:00+00:00 | 130 | 16 | 186 | 16 | 0 | 0 | 3284 | ok |
| BNB-USDT | 1d | binance_vision:3307 | 3307 | 2017-11-06T00:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 0 | 0 | 0 | 0 | 0 | 0 | 18 | ok |
| BNB-USDT | 1h | binance_vision:79202,ccxt:binanceus:40 | 79242 | 2017-11-06T03:00:00+00:00 | 2026-11-26T05:00:00+00:00 | 9 | 7 | 6 | 7 | 0 | 0 | 816 | ok |
| BNB-USDT | 4h | binance_vision:19826,ccxt:binanceus:2 | 19828 | 2017-11-06T00:00:00+00:00 | 2026-11-26T04:00:00+00:00 | 6 | 1 | 0 | 1 | 0 | 0 | 166 | ok |
| BTC-USDT | 15m | binance_vision:324589,ccxt:binanceus:190 | 324779 | 2017-08-17T04:00:00+00:00 | 2026-11-26T05:15:00+00:00 | 47 | 15 | 65 | 15 | 0 | 0 | 2930 | ok |
| BTC-USDT | 1d | binance_vision:3388 | 3388 | 2017-08-17T00:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | ok |
| BTC-USDT | 1h | binance_vision:81138,ccxt:binanceus:40 | 81178 | 2017-08-17T04:00:00+00:00 | 2026-11-26T05:00:00+00:00 | 7 | 8 | 4 | 8 | 0 | 0 | 806 | ok |
| BTC-USDT | 4h | binance_vision:20310,ccxt:binanceus:2 | 20312 | 2017-08-17T04:00:00+00:00 | 2026-11-26T04:00:00+00:00 | 7 | 1 | 0 | 1 | 0 | 0 | 151 | ok |
| ETH-USDT | 15m | binance_vision:324589,ccxt:binanceus:190 | 324779 | 2017-08-17T04:00:00+00:00 | 2026-11-26T05:15:00+00:00 | 115 | 17 | 172 | 17 | 0 | 0 | 2284 | ok |
| ETH-USDT | 1d | binance_vision:3388 | 3388 | 2017-08-17T00:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | ok |
| ETH-USDT | 1h | binance_vision:81138,ccxt:binanceus:40 | 81178 | 2017-08-17T04:00:00+00:00 | 2026-11-26T05:00:00+00:00 | 9 | 8 | 6 | 8 | 0 | 0 | 589 | ok |
| ETH-USDT | 4h | binance_vision:20310,ccxt:binanceus:2 | 20312 | 2017-08-17T04:00:00+00:00 | 2026-11-26T04:00:00+00:00 | 7 | 1 | 0 | 1 | 0 | 0 | 106 | ok |
| SOL-USDT | 15m | binance_vision:220491,ccxt:binanceus:114 | 220605 | 2020-08-11T06:00:00+00:00 | 2026-11-26T05:15:00+00:00 | 1 | 5 | 32 | 5 | 0 | 0 | 1251 | ok |
| SOL-USDT | 1d | binance_vision:2298 | 2298 | 2020-08-11T00:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | ok |
| SOL-USDT | 1h | binance_vision:55127,ccxt:binanceus:24 | 55151 | 2020-08-11T06:00:00+00:00 | 2026-11-26T05:00:00+00:00 | 5 | 0 | 6 | 0 | 0 | 0 | 280 | ok |
| SOL-USDT | 4h | binance_vision:13787,ccxt:binanceus:1 | 13788 | 2020-08-11T04:00:00+00:00 | 2026-11-26T04:00:00+00:00 | 0 | 0 | 0 | 0 | 0 | 0 | 38 | ok |
| XRP-USDT | 15m | binance_vision:299868,ccxt:binanceus:120 | 299988 | 2018-05-04T08:00:00+00:00 | 2026-11-26T05:15:00+00:00 | 13 | 16 | 31 | 16 | 0 | 0 | 2370 | ok |
| XRP-USDT | 1d | binance_vision:3128 | 3128 | 2018-05-04T00:00:00+00:00 | 2026-11-26T00:00:00+00:00 | 0 | 0 | 0 | 0 | 0 | 0 | 22 | ok |
| XRP-USDT | 1h | binance_vision:74977,ccxt:binanceus:26 | 75003 | 2018-05-04T08:00:00+00:00 | 2026-11-26T05:00:00+00:00 | 10 | 7 | 4 | 7 | 0 | 0 | 638 | ok |
| XRP-USDT | 4h | binance_vision:18757,ccxt:binanceus:2 | 18759 | 2018-05-04T08:00:00+00:00 | 2026-11-26T04:00:00+00:00 | 6 | 0 | 0 | 0 | 0 | 0 | 140 | ok |

## Details

### BNB-USDT 15m

**Warnings / flags:**
- flagged 3284 statistical outlier bar(s); prices kept as published
- kept 186 stale bar(s) in the raw store with is_stale=True (volume==0 and open==high==low==close); get_candles/load_closed drop them by default
- detected 16 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 130 unexpected gap(s)
- detected 16 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

### BNB-USDT 1d

**Warnings / flags:**
- flagged 18 statistical outlier bar(s); prices kept as published

### BNB-USDT 1h

**Warnings / flags:**
- flagged 816 statistical outlier bar(s); prices kept as published
- kept 6 stale bar(s) in the raw store with is_stale=True (volume==0 and open==high==low==close); get_candles/load_closed drop them by default
- detected 7 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 9 unexpected gap(s)
- detected 7 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

### BNB-USDT 4h

**Warnings / flags:**
- flagged 166 statistical outlier bar(s); prices kept as published
- detected 1 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 6 unexpected gap(s)
- detected 1 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

### BTC-USDT 15m

**Warnings / flags:**
- flagged 2930 statistical outlier bar(s); prices kept as published
- kept 65 stale bar(s) in the raw store with is_stale=True (volume==0 and open==high==low==close); get_candles/load_closed drop them by default
- detected 15 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 47 unexpected gap(s)
- detected 15 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

### BTC-USDT 1d

**Warnings / flags:**
- flagged 5 statistical outlier bar(s); prices kept as published

### BTC-USDT 1h

**Warnings / flags:**
- flagged 806 statistical outlier bar(s); prices kept as published
- kept 4 stale bar(s) in the raw store with is_stale=True (volume==0 and open==high==low==close); get_candles/load_closed drop them by default
- detected 8 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 7 unexpected gap(s)
- detected 8 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

### BTC-USDT 4h

**Warnings / flags:**
- flagged 151 statistical outlier bar(s); prices kept as published
- detected 1 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 7 unexpected gap(s)
- detected 1 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

### ETH-USDT 15m

**Warnings / flags:**
- flagged 2284 statistical outlier bar(s); prices kept as published
- kept 172 stale bar(s) in the raw store with is_stale=True (volume==0 and open==high==low==close); get_candles/load_closed drop them by default
- detected 17 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 115 unexpected gap(s)
- detected 17 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

### ETH-USDT 1d

**Warnings / flags:**
- flagged 5 statistical outlier bar(s); prices kept as published

### ETH-USDT 1h

**Warnings / flags:**
- flagged 589 statistical outlier bar(s); prices kept as published
- kept 6 stale bar(s) in the raw store with is_stale=True (volume==0 and open==high==low==close); get_candles/load_closed drop them by default
- detected 8 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 9 unexpected gap(s)
- detected 8 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

### ETH-USDT 4h

**Warnings / flags:**
- flagged 106 statistical outlier bar(s); prices kept as published
- detected 1 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 7 unexpected gap(s)
- detected 1 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

### SOL-USDT 15m

**Warnings / flags:**
- flagged 1251 statistical outlier bar(s); prices kept as published
- kept 32 stale bar(s) in the raw store with is_stale=True (volume==0 and open==high==low==close); get_candles/load_closed drop them by default
- detected 5 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 1 unexpected gap(s)
- detected 5 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

### SOL-USDT 1d

**Warnings / flags:**
- flagged 5 statistical outlier bar(s); prices kept as published

### SOL-USDT 1h

**Warnings / flags:**
- flagged 280 statistical outlier bar(s); prices kept as published
- kept 6 stale bar(s) in the raw store with is_stale=True (volume==0 and open==high==low==close); get_candles/load_closed drop them by default
- detected 5 unexpected gap(s)

### SOL-USDT 4h

**Warnings / flags:**
- flagged 38 statistical outlier bar(s); prices kept as published

### XRP-USDT 15m

**Warnings / flags:**
- flagged 2370 statistical outlier bar(s); prices kept as published
- kept 31 stale bar(s) in the raw store with is_stale=True (volume==0 and open==high==low==close); get_candles/load_closed drop them by default
- detected 16 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 13 unexpected gap(s)
- detected 16 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

### XRP-USDT 1d

**Warnings / flags:**
- flagged 22 statistical outlier bar(s); prices kept as published

### XRP-USDT 1h

**Warnings / flags:**
- flagged 638 statistical outlier bar(s); prices kept as published
- kept 4 stale bar(s) in the raw store with is_stale=True (volume==0 and open==high==low==close); get_candles/load_closed drop them by default
- detected 7 stale/missing run(s) longer than 3 bars (sets data_quality_warning; gap_segments starts a new segment; dropping stale does not hide the hole)
- detected 10 unexpected gap(s)
- detected 7 gap(s) longer than 3x the bar interval (sets data_quality_warning; walk-forward must split around them)

### XRP-USDT 4h

**Warnings / flags:**
- flagged 140 statistical outlier bar(s); prices kept as published
- detected 6 unexpected gap(s)

