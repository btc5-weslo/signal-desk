# Walk-forward OOS reports

Fees: **10 bps** on entry and on exit. Slippage: **5 bps** of price. Quant v0.1.0 published defaults; no parameter search on train or OOS.
Windows: 365 calendar days train / 180 days test / 180-day step, split on gaps and source seams so no window spans one.

## mtf_confirmation 1d

`mtf_confirmation.supported` is 15m, 1h, and 4h only (1d has no higher timeframe in the locked universe). Those 5 symbol×1d slots were skipped, not backtested. That is why this strategy has 15 `backtest_report.json` files (and 30 JSON files counting `config.json`) versus 20 reports / 40 JSON files for the other three strategies.

## data_hash

Each report's `data_hash` is SHA-256 of the Parquet file(s) used. Non-MTF reports hash the trigger series only; MTF reports also hash the higher-timeframe file (15m→1h, 1h→4h, 4h→1d). All finished reports match the current store (after the Feb 2018 off-grid drop and the 2026-11-26 05:19 UTC refresh).

| data_hash | used by |
|---|---|
| `07092374717684b41001f9f9ec9bd38f0630e2294006b0db192a9a22cff67dc3` | 3 runs: breakout_donchian BNB-USDT 4h, mean_reversion_rsi_bb BNB-USDT 4h, trend_ema_adx BNB-USDT 4h |
| `099c53fc2a06b52235bc5ad63cd6584c670d0648650cad1a59847fb58f4e93b1` | 3 runs: breakout_donchian ETH-USDT 1d, mean_reversion_rsi_bb ETH-USDT 1d, trend_ema_adx ETH-USDT 1d |
| `0ed94a0d1c303c8f412033caa6d714a5fc7b5c61f84f8e7f888a8ec4030ae561` | 3 runs: breakout_donchian XRP-USDT 1d, mean_reversion_rsi_bb XRP-USDT 1d, trend_ema_adx XRP-USDT 1d |
| `1102c8a9654bbc6d4d155b5cf32614f20462acaec8ee6e4ff9eb6b36ee7adf00` | 3 runs: breakout_donchian SOL-USDT 1h, mean_reversion_rsi_bb SOL-USDT 1h, trend_ema_adx SOL-USDT 1h |
| `1b65fdb9bd900e523a566ede5cccf2ee814a1d7d834176dfbc6104df2f5845de` | 1 runs: mtf_confirmation BTC-USDT 1h |
| `311336e8f9b30f060db72df112ac593a088b6d09d4aaebe6be476c2abe61ca94` | 1 runs: mtf_confirmation XRP-USDT 4h |
| `31727a0c9506a88a5d395a8bde6f7da74c8ff361cdb6d8110f365ab9d058ec03` | 1 runs: mtf_confirmation ETH-USDT 4h |
| `339f89b040b87ced39f3982c2577210e242b310dc31906787a34b9e7fee3e12c` | 3 runs: breakout_donchian XRP-USDT 1h, mean_reversion_rsi_bb XRP-USDT 1h, trend_ema_adx XRP-USDT 1h |
| `386b66a1df7769aa44c2e27ba875e8f75902a8fe1113b4e4072ffc97550ff061` | 3 runs: breakout_donchian BNB-USDT 15m, mean_reversion_rsi_bb BNB-USDT 15m, trend_ema_adx BNB-USDT 15m |
| `472a55aeb1d720a0823dcfa81260ac874513a368eb7af7940af8c0aa71351f44` | 3 runs: breakout_donchian BTC-USDT 4h, mean_reversion_rsi_bb BTC-USDT 4h, trend_ema_adx BTC-USDT 4h |
| `5c45d538d0630885d1a9e2150b4f2ae2779bc039515b6f634521f87be4b18600` | 1 runs: mtf_confirmation SOL-USDT 4h |
| `7181eab975fee94adac0ae0c6bdfec7a9bef13ab5123c2678f93a31b74fe56b6` | 3 runs: breakout_donchian BTC-USDT 1d, mean_reversion_rsi_bb BTC-USDT 1d, trend_ema_adx BTC-USDT 1d |
| `78d7065c0ac612868fcdbebd626dd48488d92d634d0945a2544cb6c0c2850e45` | 1 runs: mtf_confirmation ETH-USDT 1h |
| `7f87eb28d850d7b00d69339931da5548ec8930241ff30112ca444979c737d467` | 3 runs: breakout_donchian SOL-USDT 15m, mean_reversion_rsi_bb SOL-USDT 15m, trend_ema_adx SOL-USDT 15m |
| `855716dd08af7e64930ae046a58df0dad17b16a7be31628b69eb20f83c011396` | 3 runs: breakout_donchian SOL-USDT 4h, mean_reversion_rsi_bb SOL-USDT 4h, trend_ema_adx SOL-USDT 4h |
| `86c68846ed7b754adc6751ddee13909217c92760c770ed822f4aecd14e795ca4` | 1 runs: mtf_confirmation BTC-USDT 15m |
| `8915530289a37cf65b2b97d6e94c0362282260baabe0b22a534c6e2ac46fb4ed` | 3 runs: breakout_donchian XRP-USDT 15m, mean_reversion_rsi_bb XRP-USDT 15m, trend_ema_adx XRP-USDT 15m |
| `8c467a255219aa06a53efc24b64f58881855a81b89f193a017bb8f7940e4a14c` | 3 runs: breakout_donchian BNB-USDT 1d, mean_reversion_rsi_bb BNB-USDT 1d, trend_ema_adx BNB-USDT 1d |
| `9cf1b007b0304853a7e508a492d2bfdbb8283c9796814983c0843d0a7be1c80f` | 3 runs: breakout_donchian XRP-USDT 4h, mean_reversion_rsi_bb XRP-USDT 4h, trend_ema_adx XRP-USDT 4h |
| `a12fd04a5b4134e8f0fe355f9a74e6f70b51d0d2ed8b50cd7e5070e9738e8b4c` | 1 runs: mtf_confirmation BNB-USDT 1h |
| `a2a1e87c45937409a6f42380e7c12f37cd4f35bf699e7bf5eeb52923ca5e9612` | 1 runs: mtf_confirmation SOL-USDT 1h |
| `a6a466f380e3b731c4e9b03de308cc9c3ff921b1f3034e3202b489823f0a0a70` | 3 runs: breakout_donchian SOL-USDT 1d, mean_reversion_rsi_bb SOL-USDT 1d, trend_ema_adx SOL-USDT 1d |
| `a929bfad70690a2445e0393e49ae0bb8280c936c8db0c0c111d2c364c2da3881` | 1 runs: mtf_confirmation XRP-USDT 15m |
| `b3f614b7654977abf1a0fc9c59f0ba0b6333d15b61b7ebcb96fa065e9a1f82a2` | 3 runs: breakout_donchian BTC-USDT 1h, mean_reversion_rsi_bb BTC-USDT 1h, trend_ema_adx BTC-USDT 1h |
| `ba01f416b91b68106808492f461818b57ce904336bfc00a67ef650ec77e89fbe` | 3 runs: breakout_donchian ETH-USDT 1h, mean_reversion_rsi_bb ETH-USDT 1h, trend_ema_adx ETH-USDT 1h |
| `bc2ceff7ce3d2682c596188122055b901c108000d558693a746e4ba5e321be86` | 3 runs: breakout_donchian BTC-USDT 15m, mean_reversion_rsi_bb BTC-USDT 15m, trend_ema_adx BTC-USDT 15m |
| `c4bed00f513f6c3bdbea1e200beb81cef91141949714529e68e3b560673a68d4` | 1 runs: mtf_confirmation ETH-USDT 15m |
| `d1e9a80823d89091659a08089513f11bb9396b876a8544eecf4ef39743459fc1` | 3 runs: breakout_donchian BNB-USDT 1h, mean_reversion_rsi_bb BNB-USDT 1h, trend_ema_adx BNB-USDT 1h |
| `d31d9d60ffcb02ebc7e0c3d1311d8886e1adc3f3889971410d7a062db62b6e50` | 1 runs: mtf_confirmation BTC-USDT 4h |
| `d51c5d7254ae6c38adcce2afefb431704f07bc3332c54ba50e3c60dd9a233cfa` | 1 runs: mtf_confirmation SOL-USDT 15m |
| `dbe1734a9cf407dd5e99e100c711cd8cd4e78c82ead2e30e9027dac8c6da0d3e` | 1 runs: mtf_confirmation BNB-USDT 4h |
| `e256a8cd071beed54e7dd3039c344f8f605a1573d9e135e8b656747eb6e23ba8` | 1 runs: mtf_confirmation BNB-USDT 15m |
| `eb3068a50e1e2f0b867400a1452b1b969a759261c7c41860c012afe766b04821` | 3 runs: breakout_donchian ETH-USDT 15m, mean_reversion_rsi_bb ETH-USDT 15m, trend_ema_adx ETH-USDT 15m |
| `efe1b18803a6b2bc59c6916767fcd945abf51e129f93c2ce31b3306f769fbc2d` | 3 runs: breakout_donchian ETH-USDT 4h, mean_reversion_rsi_bb ETH-USDT 4h, trend_ema_adx ETH-USDT 4h |
| `f82c5e206fb9b55b4161bec709626260f94ae6ea73404c3b91decf32179e76e7` | 1 runs: mtf_confirmation XRP-USDT 1h |

## Results

| strategy | symbol | TF | trades | win_rate | PF | sharpe | max_dd | flags | run_id | audit | schema |
|---|---|---|---:|---:|---:|---:|---:|---|---|---|---|
| breakout_donchian | BTC-USDT | 15m | 11 | 0.363636 | 0.505973 | -0.647189 | -0.0426856 | low_oos_trades,data_quality_warning | `1bf2dbc28bce10a7` | OK | OK |
| breakout_donchian | BTC-USDT | 1h | 10 | 0.3 | 0.481352 | -0.644435 | -0.0571508 | low_oos_trades,data_quality_warning | `cb00d9b0da14d48b` | OK | OK |
| breakout_donchian | BTC-USDT | 4h | 26 | 0.692308 | 2.15869 | 0.628705 | -0.141047 | low_oos_trades,data_quality_warning | `34942437c896ad30` | OK | OK |
| breakout_donchian | BTC-USDT | 1d | 32 | 0.375 | 0.651504 | -0.36714 | -0.486647 | low_oos_trades | `f1280891266dc402` | OK | OK |
| breakout_donchian | ETH-USDT | 15m | 10 | 0.1 | 0.163392 | -1.34355 | -0.0555389 | low_oos_trades,data_quality_warning | `e3c18561a51deb88` | OK | OK |
| breakout_donchian | ETH-USDT | 1h | 10 | 0.4 | 1.11377 | 0.0947628 | -0.0505366 | low_oos_trades,data_quality_warning | `f1a84b8b747d747c` | OK | OK |
| breakout_donchian | ETH-USDT | 4h | 26 | 0.615385 | 2.0833 | 0.588423 | -0.0982827 | low_oos_trades,data_quality_warning | `84fb89568788c74a` | OK | OK |
| breakout_donchian | ETH-USDT | 1d | 33 | 0.484848 | 1.2819 | 0.218603 | -0.334065 | low_oos_trades | `a96879f213f9aa3f` | OK | OK |
| breakout_donchian | SOL-USDT | 15m | 10 | 0 | 0 | -1.70636 | -0.0908689 | low_oos_trades,data_quality_warning | `80786339cd88b624` | OK | OK |
| breakout_donchian | SOL-USDT | 1h | 10 | 0.6 | 2.76202 | 0.838489 | -0.0331036 | low_oos_trades,data_quality_warning | `63efa93cd140d5de` | OK | OK |
| breakout_donchian | SOL-USDT | 4h | 21 | 0.619048 | 1.9002 | 0.560105 | -0.0893377 | low_oos_trades,data_quality_warning | `461538d532ef542c` | OK | OK |
| breakout_donchian | SOL-USDT | 1d | 21 | 0.52381 | 1.16495 | 0.145315 | -0.634042 | low_oos_trades | `6ceabc6ed65a529d` | OK | OK |
| breakout_donchian | BNB-USDT | 15m | 10 | 0.5 | 0.782918 | -0.222664 | -0.013673 | low_oos_trades,data_quality_warning | `f704c4e3c5bc5643` | OK | OK |
| breakout_donchian | BNB-USDT | 1h | 10 | 0.2 | 0.355811 | -0.853481 | -0.0974637 | low_oos_trades,data_quality_warning | `2b1ab32496657af9` | OK | OK |
| breakout_donchian | BNB-USDT | 4h | 27 | 0.592593 | 2.69627 | 0.671883 | -0.13916 | low_oos_trades,data_quality_warning | `ca55505a9bdf7a5e` | OK | OK |
| breakout_donchian | BNB-USDT | 1d | 33 | 0.545455 | 2.45842 | 0.6845 | -0.2876 | low_oos_trades | `00fd596f81c8d8a3` | OK | OK |
| breakout_donchian | XRP-USDT | 15m | 10 | 0.3 | 0.214467 | -1.2376 | -0.058605 | low_oos_trades,data_quality_warning | `b52dda333e774a84` | OK | OK |
| breakout_donchian | XRP-USDT | 1h | 16 | 0.5625 | 1.86614 | 0.514874 | -0.0654767 | low_oos_trades,data_quality_warning | `60518c7dcffa7c76` | OK | OK |
| breakout_donchian | XRP-USDT | 4h | 25 | 0.4 | 0.792953 | -0.206174 | -0.422659 | low_oos_trades,data_quality_warning | `092eeb8bcfced4c9` | OK | OK |
| breakout_donchian | XRP-USDT | 1d | 31 | 0.419355 | 1.20124 | 0.156356 | -0.416347 | low_oos_trades | `3535730203a48fa9` | OK | OK |
| mean_reversion_rsi_bb | BTC-USDT | 15m | 22 | 0.363636 | 0.269762 | -1.4479 | -0.0643818 | low_oos_trades,data_quality_warning | `1b747cf2362e3b3b` | OK | OK |
| mean_reversion_rsi_bb | BTC-USDT | 1h | 11 | 0.181818 | 0.0827062 | -1.66382 | -0.0864293 | low_oos_trades,data_quality_warning | `5751d7d862b0f911` | OK | OK |
| mean_reversion_rsi_bb | BTC-USDT | 4h | 31 | 0.290323 | 0.419597 | -0.791563 | -0.277802 | low_oos_trades,data_quality_warning | `e4a6db626ebf28d6` | OK | OK |
| mean_reversion_rsi_bb | BTC-USDT | 1d | 9 | 0 | 0 | -0.976806 | -0.335497 | low_oos_trades | `5d8910885e9a4479` | OK | OK |
| mean_reversion_rsi_bb | ETH-USDT | 15m | 13 | 0.692308 | 0.949903 | -0.0512319 | -0.0259859 | low_oos_trades,data_quality_warning | `5c461d1289b80ae8` | OK | OK |
| mean_reversion_rsi_bb | ETH-USDT | 1h | 10 | 0.7 | 1.40184 | 0.323911 | -0.0182427 | low_oos_trades,data_quality_warning | `5386fbc8c0a7d737` | OK | OK |
| mean_reversion_rsi_bb | ETH-USDT | 4h | 23 | 0.391304 | 0.494991 | -0.581671 | -0.279837 | low_oos_trades,data_quality_warning | `6d081ae3320ddd36` | OK | OK |
| mean_reversion_rsi_bb | ETH-USDT | 1d | 12 | 0.166667 | 0.248546 | -0.629465 | -0.392047 | low_oos_trades | `a39dac2ac559fbc7` | OK | OK |
| mean_reversion_rsi_bb | SOL-USDT | 15m | 11 | 0.454545 | 0.452707 | -0.743228 | -0.0357947 | low_oos_trades,data_quality_warning | `f28ee857ce0f3b4a` | OK | OK |
| mean_reversion_rsi_bb | SOL-USDT | 1h | 10 | 0.4 | 0.378984 | -0.847266 | -0.086185 | low_oos_trades,data_quality_warning | `55abe62a25469eaa` | OK | OK |
| mean_reversion_rsi_bb | SOL-USDT | 4h | 20 | 0.35 | 0.404886 | -0.776697 | -0.300067 | low_oos_trades,data_quality_warning | `39e03448db458832` | OK | OK |
| mean_reversion_rsi_bb | SOL-USDT | 1d | 6 | 0.5 | 0.668453 | -0.211144 | -0.162965 | low_oos_trades | `826ebf7acd2f8c75` | OK | OK |
| mean_reversion_rsi_bb | BNB-USDT | 15m | 13 | 0.538462 | 0.462413 | -0.734328 | -0.0325688 | low_oos_trades,data_quality_warning | `f9d214969364cf04` | OK | OK |
| mean_reversion_rsi_bb | BNB-USDT | 1h | 10 | 0.5 | 0.992757 | -0.00714166 | -0.0542651 | low_oos_trades,data_quality_warning | `08855c37af1c7f0f` | OK | OK |
| mean_reversion_rsi_bb | BNB-USDT | 4h | 26 | 0.692308 | 1.41659 | 0.294768 | -0.0900892 | low_oos_trades,data_quality_warning | `2505baf6a703a57d` | OK | OK |
| mean_reversion_rsi_bb | BNB-USDT | 1d | 14 | 0.214286 | 0.230567 | -0.803981 | -0.475253 | low_oos_trades | `dce0e54c9c1335bd` | OK | OK |
| mean_reversion_rsi_bb | XRP-USDT | 15m | 11 | 0.636364 | 0.415901 | -0.700991 | -0.0228874 | low_oos_trades,data_quality_warning | `e78e5bfbae28f4a4` | OK | OK |
| mean_reversion_rsi_bb | XRP-USDT | 1h | 19 | 0.368421 | 0.317559 | -1.04344 | -0.130366 | low_oos_trades,data_quality_warning | `11fe75d7feda30a5` | OK | OK |
| mean_reversion_rsi_bb | XRP-USDT | 4h | 29 | 0.344828 | 0.357446 | -0.986527 | -0.402725 | low_oos_trades,data_quality_warning | `41e698419c4d3f23` | OK | OK |
| mean_reversion_rsi_bb | XRP-USDT | 1d | 8 | 0.75 | 1.98451 | 0.309411 | -0.18008 | low_oos_trades | `579bbbf40439dac5` | OK | OK |
| mtf_confirmation | BTC-USDT | 15m | 10 | 0.3 | 0.260034 | -1.03775 | -0.048166 | low_oos_trades,data_quality_warning | `3fccdcf3a4c92f1c` | OK | OK |
| mtf_confirmation | BTC-USDT | 1h | 10 | 0.3 | 0.183984 | -1.16942 | -0.069541 | low_oos_trades,data_quality_warning | `1bb86f3110eb083c` | OK | OK |
| mtf_confirmation | BTC-USDT | 4h | 26 | 0.423077 | 0.868544 | -0.111342 | -0.124582 | low_oos_trades,data_quality_warning | `a9e5ad330e862e8f` | OK | OK |
| mtf_confirmation | BTC-USDT | 1d | — | — | — | — | — | skipped_unsupported | — | — | — |
| mtf_confirmation | ETH-USDT | 15m | 11 | 0.272727 | 0.137276 | -1.25313 | -0.0650278 | low_oos_trades,data_quality_warning | `108b17ec0f95c16f` | OK | OK |
| mtf_confirmation | ETH-USDT | 1h | 10 | 0.2 | 0.269876 | -1.07238 | -0.115395 | low_oos_trades,data_quality_warning | `f07546bdb7e8526e` | OK | OK |
| mtf_confirmation | ETH-USDT | 4h | 27 | 0.555556 | 1.17163 | 0.142023 | -0.172896 | low_oos_trades,data_quality_warning | `ad10b14973d11658` | OK | OK |
| mtf_confirmation | ETH-USDT | 1d | — | — | — | — | — | skipped_unsupported | — | — | — |
| mtf_confirmation | SOL-USDT | 15m | 10 | 0.4 | 0.995867 | -0.00347341 | -0.0486891 | low_oos_trades,data_quality_warning | `8d54a9070820767f` | OK | OK |
| mtf_confirmation | SOL-USDT | 1h | 10 | 0.4 | 0.35943 | -0.875881 | -0.117948 | low_oos_trades,data_quality_warning | `467d658397a56075` | OK | OK |
| mtf_confirmation | SOL-USDT | 4h | 20 | 0.4 | 0.639829 | -0.33894 | -0.278192 | low_oos_trades,data_quality_warning | `242cfec0298828ec` | OK | OK |
| mtf_confirmation | SOL-USDT | 1d | — | — | — | — | — | skipped_unsupported | — | — | — |
| mtf_confirmation | BNB-USDT | 15m | 10 | 0.2 | 0.1857 | -1.21669 | -0.050542 | low_oos_trades,data_quality_warning | `37143bd54682bd1b` | OK | OK |
| mtf_confirmation | BNB-USDT | 1h | 10 | 0.4 | 0.229233 | -1.11635 | -0.0994339 | low_oos_trades,data_quality_warning | `1535dfd01e5873ef` | OK | OK |
| mtf_confirmation | BNB-USDT | 4h | 26 | 0.423077 | 0.899328 | -0.092529 | -0.149744 | low_oos_trades,data_quality_warning | `3b7eea08cfe82205` | OK | OK |
| mtf_confirmation | BNB-USDT | 1d | — | — | — | — | — | skipped_unsupported | — | — | — |
| mtf_confirmation | XRP-USDT | 15m | 10 | 0.2 | 0.162891 | -1.22027 | -0.0553605 | low_oos_trades,data_quality_warning | `03ee3e1375f1218c` | OK | OK |
| mtf_confirmation | XRP-USDT | 1h | 16 | 0.5625 | 1.97649 | 0.543916 | -0.0743664 | low_oos_trades,data_quality_warning | `274d92463ba6e4c2` | OK | OK |
| mtf_confirmation | XRP-USDT | 4h | 24 | 0.5 | 0.947615 | -0.0413122 | -0.216549 | low_oos_trades,data_quality_warning | `46dbf9c18d7b301a` | OK | OK |
| mtf_confirmation | XRP-USDT | 1d | — | — | — | — | — | skipped_unsupported | — | — | — |
| trend_ema_adx | BTC-USDT | 15m | 10 | 0.2 | 0.0511911 | -1.50285 | -0.0615869 | low_oos_trades,data_quality_warning | `541574d8b872a9d4` | OK | OK |
| trend_ema_adx | BTC-USDT | 1h | 10 | 0.4 | 0.722002 | -0.311337 | -0.0708774 | low_oos_trades,data_quality_warning | `ece2da233e212f5b` | OK | OK |
| trend_ema_adx | BTC-USDT | 4h | 27 | 0.555556 | 1.63482 | 0.422433 | -0.095221 | low_oos_trades,data_quality_warning | `025724776e211dc5` | OK | OK |
| trend_ema_adx | BTC-USDT | 1d | 32 | 0.40625 | 0.868987 | -0.112285 | -0.406511 | low_oos_trades | `94d56e504fb456bd` | OK | OK |
| trend_ema_adx | ETH-USDT | 15m | 10 | 0.2 | 0.197207 | -1.24431 | -0.0704794 | low_oos_trades,data_quality_warning | `325ae8a97384b324` | OK | OK |
| trend_ema_adx | ETH-USDT | 1h | 10 | 0.6 | 1.46932 | 0.37292 | -0.0479671 | low_oos_trades,data_quality_warning | `81f6a69d2cea7ba5` | OK | OK |
| trend_ema_adx | ETH-USDT | 4h | 26 | 0.5 | 1.28493 | 0.211026 | -0.199956 | low_oos_trades,data_quality_warning | `740766b89ce4be67` | OK | OK |
| trend_ema_adx | ETH-USDT | 1d | 33 | 0.727273 | 2.7969 | 0.837623 | -0.234031 | low_oos_trades | `2164105420b012e2` | OK | OK |
| trend_ema_adx | SOL-USDT | 15m | 10 | 0.2 | 0.125314 | -1.47119 | -0.0965548 | low_oos_trades,data_quality_warning | `0acc4c49e708ccef` | OK | OK |
| trend_ema_adx | SOL-USDT | 1h | 10 | 0.5 | 0.75479 | -0.246046 | -0.105396 | low_oos_trades,data_quality_warning | `e1275a1b14931469` | OK | OK |
| trend_ema_adx | SOL-USDT | 4h | 20 | 0.5 | 1.62658 | 0.408427 | -0.0698968 | low_oos_trades,data_quality_warning | `a9ac32fed7f98d1e` | OK | OK |
| trend_ema_adx | SOL-USDT | 1d | 20 | 0.35 | 0.7407 | -0.269018 | -0.707398 | low_oos_trades | `a43f1646f5f92e66` | OK | OK |
| trend_ema_adx | BNB-USDT | 15m | 10 | 0.3 | 0.295252 | -1.02202 | -0.0425401 | low_oos_trades,data_quality_warning | `a04ab373cf402ee3` | OK | OK |
| trend_ema_adx | BNB-USDT | 1h | 10 | 0.3 | 0.259122 | -1.01232 | -0.0906724 | low_oos_trades,data_quality_warning | `6ed8327575d08027` | OK | OK |
| trend_ema_adx | BNB-USDT | 4h | 27 | 0.555556 | 2.16463 | 0.528213 | -0.0911527 | low_oos_trades,data_quality_warning | `903e822afeeb9732` | OK | OK |
| trend_ema_adx | BNB-USDT | 1d | 32 | 0.53125 | 1.799 | 0.459169 | -0.297586 | low_oos_trades | `952d68469558290c` | OK | OK |
| trend_ema_adx | XRP-USDT | 15m | 10 | 0.3 | 0.297108 | -0.942163 | -0.0427775 | low_oos_trades,data_quality_warning | `8a53d3cc87adacf5` | OK | OK |
| trend_ema_adx | XRP-USDT | 1h | 16 | 0.4375 | 1.04087 | 0.0345629 | -0.0600024 | low_oos_trades,data_quality_warning | `857df46a956f762f` | OK | OK |
| trend_ema_adx | XRP-USDT | 4h | 24 | 0.666667 | 1.47995 | 0.312666 | -0.203254 | low_oos_trades,data_quality_warning | `d92a8d9d1584a5b6` | OK | OK |
| trend_ema_adx | XRP-USDT | 1d | 30 | 0.366667 | 1.11993 | 0.0988884 | -0.413375 | low_oos_trades | `043f9dbd40325f8e` | OK | OK |

