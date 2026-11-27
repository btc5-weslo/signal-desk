/**
 * MOCK DATA — UI development only. Loaded exclusively when NEXT_PUBLIC_USE_MOCK=1.
 * Every signal here has is_mock: true and the UI renders a MOCK badge/banner.
 * There are deliberately NO mock backtest reports or performance numbers:
 * strategy performance must come from real, QA-approved walk-forward runs.
 * Price levels below are illustrative placeholders, not recommendations.
 */
import type { SignalQuery } from "@/lib/api/client";
import type { Page } from "@/lib/types/signal";
import type { AssetClass, Candle, Side, Signal, Strategy, Timeframe } from "@/lib/types/signal";

const TF_MS: Record<Timeframe, number> = { "15m": 9e5, "1h": 36e5, "4h": 144e5, "1d": 864e5 };

function floorTo(t: number, tf: Timeframe) {
  return Math.floor(t / TF_MS[tf]) * TF_MS[tf];
}

type Seed = [string, AssetClass, Timeframe, Side, number, number, number[], number, Signal["status"], string, number];
// symbol, class, tf, side, entry, stop, tps, confidence, status, strategy, barsAgo
const SEEDS: Seed[] = [
  ["BTC-USDT", "crypto", "4h", "long", 97250, 95100, [100400, 103600], 0.68, "active", "trend_mtf", 1],
  ["ETH-USDT", "crypto", "1h", "short", 3420, 3488, [3320, 3240], 0.61, "active", "mean_reversion", 2],
  ["SOL-USDT", "crypto", "15m", "long", 241.6, 238.9, [245.2], 0.57, "active", "breakout", 3],
  ["SPY", "equity", "1d", "long", 598.4, 589.7, [611.0, 622.5], 0.64, "active", "trend_mtf", 1],
  ["NVDA", "equity", "1h", "short", 141.2, 143.9, [137.4], 0.55, "active", "mean_reversion", 4],
  ["EURUSD", "fx", "4h", "short", 1.0542, 1.0588, [1.0476, 1.0421], 0.6, "active", "trend_mtf", 2],
  ["USDJPY", "fx", "15m", "long", 154.32, 153.98, [154.85], 0.52, "active", "breakout", 1],
  ["XRP-USDT", "crypto", "1d", "flat", 0, 0, [], 0.5, "active", "regime_filter", 1],
  ["AAPL", "equity", "4h", "long", 229.1, 225.8, [234.0], 0.59, "hit_tp", "breakout", 9],
  ["GBPUSD", "fx", "1h", "long", 1.2671, 1.2633, [1.2735], 0.54, "hit_sl", "mean_reversion", 14],
  ["BNB-USDT", "crypto", "4h", "short", 655.0, 668.0, [632.0], 0.58, "expired", "mean_reversion", 20],
  ["MSFT", "equity", "1d", "long", 423.5, 414.0, [440.0], 0.62, "cancelled", "trend_mtf", 5],
];

function insufficientOos(ac: AssetClass, tf: Timeframe) {
  return (ac === "equity" || ac === "fx") && (tf === "15m" || tf === "1h");
}

function build(): Signal[] {
  const now = Date.now();
  return SEEDS.map(([symbol, asset_class, timeframe, side, entry, stop, tps, confidence, status, strategy, barsAgo], i) => {
    const bar = floorTo(now, timeframe) - barsAgo * TF_MS[timeframe];
    const flat = side === "flat";
    return {
      id: `mock-${i + 1}-${symbol.toLowerCase().replace("-", "")}-${timeframe}`,
      strategy_id: strategy,
      strategy_version: "0.1.0",
      symbol,
      asset_class,
      timeframe,
      side,
      generated_at: new Date(bar + 4000).toISOString(),
      bar_close_time: new Date(bar).toISOString(),
      entry: flat ? null : entry,
      stop_loss: flat ? null : stop,
      take_profit: tps,
      horizon_bars: timeframe === "1d" ? 10 : 24,
      confidence,
      features_snapshot: flat
        ? { regime: "high_vol_chop", adx_14: 14.2, atr_pct: 6.1 }
        : {
            regime: side === "long" ? "trend_up" : "trend_down",
            rsi_14: side === "long" ? 58.3 : 41.7,
            adx_14: 27.4,
            ema_20_50_cross: side === "long" ? 1 : -1,
            atr_14: Math.abs(entry - stop) / 1.5,
            htf_confirm: true,
          },
      rationale: flat
        ? "MOCK: regime filter detects high-volatility chop; no directional edge, standing aside."
        : `MOCK: ${side === "long" ? "Higher-timeframe uptrend" : "Overextended move"} with ${timeframe} confirmation; stop beyond recent swing, targets at measured move.`,
      status,
      is_mock: true,
      confidence_calibrated: false,
      validation_status: insufficientOos(asset_class, timeframe) ? "insufficient_oos" : "pending",
    } satisfies Signal;
  });
}

let cache: Signal[] | null = null;
function all(): Signal[] {
  if (!cache) cache = build();
  return cache;
}

export function mockSignals(q: SignalQuery = {}): Page<Signal> {
  const rows = filterRows(q);
  const start = Number(q.cursor ?? 0);
  const limit = q.limit ?? 100;
  const end = start + limit;
  return { items: rows.slice(start, end), next_cursor: end < rows.length ? String(end) : null };
}

function filterRows(q: SignalQuery): Signal[] {
  return all().filter(
    (s) =>
      (!q.asset_class || q.asset_class === "all" || s.asset_class === q.asset_class) &&
      (!q.timeframe || q.timeframe === "all" || s.timeframe === q.timeframe) &&
      (!q.side || q.side === "all" || s.side === q.side) &&
      (!q.status || q.status === "all" || s.status === q.status),
  );
}

export function mockSignal(id: string): Signal | null {
  return all().find((s) => s.id === id) ?? streamed.find((s) => s.id === id) ?? null;
}

export function mockStrategies(): Strategy[] {
  const base = { version: "0.1.0", latest_run_id: null };
  return [
    {
      ...base,
      id: "trend_mtf",
      name: "Multi-timeframe Trend",
      description: "Trend-following entries confirmed by the next higher timeframe.",
      hypothesis: "MOCK: trends persist when higher-timeframe structure agrees.",
      asset_classes: ["crypto", "equity", "fx"],
      timeframes: ["1h", "4h", "1d"],
      validation_status: "pending",
    },
    {
      ...base,
      id: "mean_reversion",
      name: "Mean Reversion",
      description: "Fades stretched moves back toward a volatility-adjusted mean.",
      hypothesis: "MOCK: short-horizon overextensions revert in range regimes.",
      asset_classes: ["crypto", "equity", "fx"],
      timeframes: ["15m", "1h", "4h"],
      validation_status: "insufficient_oos",
    },
    {
      ...base,
      id: "breakout",
      name: "Volatility Breakout",
      description: "Enters on range expansion after compression.",
      hypothesis: "MOCK: compression precedes directional expansion.",
      asset_classes: ["crypto", "equity", "fx"],
      timeframes: ["15m", "1h", "4h"],
      validation_status: "insufficient_oos",
    },
    {
      ...base,
      id: "regime_filter",
      name: "Regime Filter",
      description: "Stands aside (flat) when the market regime offers no edge.",
      hypothesis: "MOCK: avoiding chop improves risk-adjusted outcomes.",
      asset_classes: ["crypto"],
      timeframes: ["1d"],
      validation_status: "pending",
    },
  ];
}

/** Deterministic random-walk candles ending near the signal's entry. MOCK ONLY. */
export function mockCandles(symbol: string, timeframe: Timeframe, limit: number): Candle[] {
  const sig = all().find((s) => s.symbol === symbol && s.timeframe === timeframe) ?? all().find((s) => s.symbol === symbol);
  const anchor = sig?.entry ?? sig?.features_snapshot?.["last_close"] ?? 100;
  const end = floorTo(Date.now(), timeframe);
  let seed = [...symbol + timeframe].reduce((a, c) => a + c.charCodeAt(0), 7);
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const fx = sig?.asset_class === "fx";
  const vol = Number(anchor) * (timeframe === "1d" ? 0.012 : timeframe === "4h" ? 0.006 : 0.003) * (fx ? 0.35 : 1);
  const closes: number[] = [];
  let p = Number(anchor);
  for (let i = 0; i < limit; i++) {
    closes.push(p);
    p -= (rnd() - 0.5 + (sig?.side === "long" ? 0.08 : sig?.side === "short" ? -0.08 : 0)) * vol;
  }
  closes.reverse();
  return closes.map((close, i) => {
    const open = i ? closes[i - 1] : close;
    const hi = Math.max(open, close) + rnd() * vol * 0.6;
    const lo = Math.min(open, close) - rnd() * vol * 0.6;
    return { time: new Date(end - (limit - 1 - i) * TF_MS[timeframe]).toISOString(), open, high: hi, low: lo, close, volume: 0 };
  });
}

const streamed: Signal[] = [];
/** Simulated stream: re-emits a mock signal with a fresh id/time every few seconds. */
export function startMockStream(onSignal: (s: Signal) => void, everyMs = 9000): () => void {
  let n = 0;
  const id = setInterval(() => {
    const src = all().filter((s) => s.status === "active" && s.side !== "flat");
    const base = src[n++ % src.length];
    const now = new Date();
    const s: Signal = { ...base, id: `mock-stream-${now.getTime()}`, generated_at: now.toISOString(), bar_close_time: now.toISOString() };
    streamed.unshift(s);
    onSignal(s);
  }, everyMs);
  return () => clearInterval(id);
}
