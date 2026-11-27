import type { Signal } from "@/lib/types/signal";

/** Market price formatting (no currency symbol — instruments are quoted in their own units). */
export function fmtPrice(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  const digits = abs >= 1000 ? 2 : abs >= 100 ? 2 : abs >= 10 ? 3 : abs >= 1 ? 4 : 5;
  return v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function fmtPct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

export function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}

export function relTime(iso: string, now = Date.now()): string {
  const s = Math.round((now - new Date(iso).getTime()) / 1000);
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

export function fmtUtc(iso: string): string {
  const d = new Date(iso);
  return `${d.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

/** Reward:risk to the first target, computed from levels. */
export function riskReward(s: Pick<Signal, "entry" | "stop_loss" | "take_profit">, tpIndex = 0): number | null {
  const { entry, stop_loss } = s;
  const tp = s.take_profit[tpIndex];
  if (entry == null || stop_loss == null || tp == null) return null;
  const risk = Math.abs(entry - stop_loss);
  if (risk === 0) return null;
  return Math.abs(tp - entry) / risk;
}

export function pctFrom(entry: number | null, level: number | null | undefined): string {
  if (entry == null || level == null || entry === 0) return "";
  const p = ((level - entry) / entry) * 100;
  return `${p >= 0 ? "+" : ""}${p.toFixed(2)}%`;
}

export const STATUS_LABEL: Record<Signal["status"], string> = {
  active: "Active",
  hit_tp: "Target hit",
  hit_sl: "Stopped",
  expired: "Expired",
  cancelled: "Cancelled",
};

export const ASSET_LABEL = { crypto: "Crypto", equity: "Equity", fx: "FX" } as const;

/**
 * Display formatter for canonical symbol IDs (API/URLs always use the canonical ID):
 *   BTC-USDT -> BTC/USDT, EURUSD -> EUR/USD, equities (AAPL, SPY) unchanged.
 */
const FX_CCY = new Set(["USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF", "CNH", "SEK", "NOK", "MXN", "SGD", "HKD"]);
export function displaySymbol(id: string, assetClass?: string): string {
  if (id.includes("-")) return id.replace("-", "/");
  if ((assetClass === "fx" || assetClass === undefined) && /^[A-Z]{6}$/.test(id) && FX_CCY.has(id.slice(0, 3)) && FX_CCY.has(id.slice(3)))
    return `${id.slice(0, 3)}/${id.slice(3)}`;
  return id;
}
