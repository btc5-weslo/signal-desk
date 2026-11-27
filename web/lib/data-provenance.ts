/**
 * Candle data provenance. A chart is "provisional" (amber note: not for live trading) when ANY bar
 * has no `source`, or a source that isn't licensed.
 *
 * - NEVER licensed (hard-coded, cannot be overridden by any config): `binance_vision`, `yfinance`,
 *   and anything with the `ccxt:` prefix.
 * - Licensed only if listed in the platform `licensed_data_sources` from GET /v1/tenant/config
 *   (read-only, platform-set; see lib/data-policy-server.ts). Never from local tenant defaults, env,
 *   or any tenant/theme override. Empty today, so every chart is provisional.
 */
export const NEVER_LICENSED_SOURCES = ["binance_vision", "yfinance"] as const;
export const NEVER_LICENSED_PREFIXES = ["ccxt:"] as const;

export const PROVISIONAL_NOTE = "Provisional data, not for live trading";

const norm = (s: string) => s.trim().toLowerCase();

export function isNeverLicensed(source: string): boolean {
  const s = norm(source);
  return (NEVER_LICENSED_SOURCES as readonly string[]).includes(s) || NEVER_LICENSED_PREFIXES.some((p) => s.startsWith(p));
}

export function isLicensedSource(source: string | null | undefined, licensed: readonly string[]): boolean {
  if (!source || !source.trim()) return false;
  if (isNeverLicensed(source)) return false;
  return licensed.map(norm).includes(norm(source));
}

/** Extract the platform licensed list from a raw GET /v1/tenant/config body (strings only). */
export function licensedFromTenantConfig(cfg: { licensed_data_sources?: readonly unknown[] | null } | null | undefined): string[] {
  const list = cfg?.licensed_data_sources;
  if (!Array.isArray(list)) return [];
  return list.filter((x): x is string => typeof x === "string" && !!x.trim());
}

export interface Provenance {
  /** Distinct reported sources, in first-seen order. */
  sources: string[];
  /** True if any bar lacks a source. */
  missing: boolean;
  /** True when the provisional note must be shown. */
  provisional: boolean;
}

export function candleProvenance(candles: readonly { source?: string | null }[], licensed: readonly string[]): Provenance {
  const sources: string[] = [];
  let missing = candles.length === 0;
  for (const c of candles) {
    const s = c.source?.trim();
    if (!s) missing = true;
    else if (!sources.includes(s)) sources.push(s);
  }
  const provisional = missing || sources.some((s) => !isLicensedSource(s, licensed));
  return { sources, missing, provisional };
}

/** Caption text: lists EVERY distinct source as reported (first-seen order, never relabeled). */
export function dataCaption(p: Provenance): string {
  if (p.sources.length === 0) return "Data: source not reported";
  return `Data: ${p.sources.join(", ")}${p.missing ? " (some bars unattributed)" : ""}`;
}
