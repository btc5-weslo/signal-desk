/**
 * Candle freshness. A chart is "delayed" when the newest bar's CLOSE time (open time + one interval)
 * is more than 2 bar intervals behind `now` for its timeframe.
 *
 * Market hours (simple rules, so closed markets aren't flagged as delayed):
 * - crypto: 24/7, plain wall-clock lag.
 * - fx: closed Fri 22:00 UTC -> Sun 22:00 UTC (ignores the 1h DST shift and holidays).
 * - equity (US): open Mon-Fri 09:30-16:00 America/New_York. Exchange holidays and half days are NOT
 *   modelled, so the session right after a holiday can briefly show as delayed.
 * For fx/equity only open-market minutes count toward the lag; a daily equity bar's interval is one
 * 390-minute session. Any lag over 10 calendar days is delayed regardless of market hours.
 */
import type { AssetClass } from "@/lib/types/signal";

export const TF_MINUTES: Record<string, number> = { "15m": 15, "1h": 60, "4h": 240, "1d": 1440 };
const MIN = 60_000;
const HARD_CAP_MS = 10 * 24 * 60 * MIN;
const STEP_MIN = 5;
const EQUITY_SESSION_MIN = 390;

const FX_CCY = new Set(["USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF", "CNH", "SEK", "NOK", "MXN", "SGD", "HKD"]);
/** Canonical IDs: crypto has a dash (BTC-USDT), FX is a 6-letter pair (EURUSD), otherwise equity. */
export function inferAssetClass(symbol: string): AssetClass {
  if (symbol.includes("-")) return "crypto";
  if (/^[A-Z]{6}$/.test(symbol) && FX_CCY.has(symbol.slice(0, 3)) && FX_CCY.has(symbol.slice(3))) return "fx";
  return "equity";
}

const nyFmt = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });

export function isMarketOpen(t: number, cls: AssetClass): boolean {
  if (cls === "crypto") return true;
  const d = new Date(t);
  if (cls === "fx") {
    const day = d.getUTCDay();
    const h = d.getUTCHours();
    if (day === 6) return false;
    if (day === 5 && h >= 22) return false;
    if (day === 0 && h < 22) return false;
    return true;
  }
  const parts = Object.fromEntries(nyFmt.formatToParts(d).map((p) => [p.type, p.value]));
  if (parts.weekday === "Sat" || parts.weekday === "Sun") return false;
  const mins = Number(parts.hour) * 60 + Number(parts.minute);
  return mins >= 9 * 60 + 30 && mins < 16 * 60;
}

/** Open-market minutes in [from, to), stepping 5 minutes; stops counting once `cap` is exceeded. */
export function openMinutesBetween(from: number, to: number, cls: AssetClass, cap = Infinity): number {
  if (to <= from) return 0;
  if (cls === "crypto") return (to - from) / MIN;
  let open = 0;
  for (let t = from; t < to && open <= cap; t += STEP_MIN * MIN) if (isMarketOpen(t, cls)) open += Math.min(STEP_MIN, (to - t) / MIN);
  return open;
}

export interface Freshness {
  delayed: boolean;
  /** Close time of the newest bar (ms). */
  lastCloseMs: number;
  /** Wall-clock age of the newest bar's close (ms, >= 0). */
  ageMs: number;
}

export function barFreshness(lastBarOpenIso: string, timeframe: string, assetClass: AssetClass, now: number): Freshness | null {
  const tfMin = TF_MINUTES[timeframe];
  const open = Date.parse(lastBarOpenIso);
  if (!tfMin || Number.isNaN(open)) return null;
  const lastCloseMs = open + tfMin * MIN;
  const ageMs = Math.max(0, now - lastCloseMs);
  const intervalMin = assetClass === "equity" && tfMin >= 1440 ? EQUITY_SESSION_MIN : tfMin;
  const threshold = 2 * intervalMin;
  const delayed = ageMs > HARD_CAP_MS || openMinutesBetween(lastCloseMs, now, assetClass, threshold) > threshold;
  return { delayed, lastCloseMs, ageMs };
}

/** Relative age: "45m ago", "5h ago", "3d ago", "11 months ago", "2 years ago". */
export function fmtAge(ms: number): string {
  const m = Math.floor(ms / MIN);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 60) return `${d}d ago`;
  const mo = Math.floor(d / 30.44);
  if (mo < 24) return `${mo} months ago`;
  return `${Math.floor(d / 365.25)} years ago`;
}

export const delayedNote = (f: Freshness) => `Data delayed: last bar ${fmtAge(f.ageMs)}`;
