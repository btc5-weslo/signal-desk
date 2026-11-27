/**
 * Defense-in-depth banned-claims check for tenant-supplied text (name, tagline, extra disclaimers).
 * Text that matches is REJECTED and the caller falls back to the default.
 *
 * Patterns 1:1 with qa/audits/no_price_scan.py (product cost copy), plus QA's banned claims
 * (qa/DISCLAIMERS.md) and any currency amount. Keep in sync with those files.
 */

/** Ported from qa/audits/no_price_scan.py PATTERNS (case-insensitive). */
const NO_PRICE_SCAN = [
  String.raw`\bpricing\b`,
  String.raw`\bper\s+month\b`,
  String.raw`/\s*mo(nth)?\b`,
  String.raw`\bper\s+year\b`,
  String.raw`/\s*yr\b`,
  String.raw`\bsubscribe\s+(now|for)\b`,
  String.raw`\bpaywall\b`,
  String.raw`\bfree\s+trial\b`,
  String.raw`\bupgrade\s+to\s+(pro|premium)\b`,
  String.raw`\b(plan|tier)s?\b.{0,40}[$€£]\s?\d`,
  String.raw`[$€£]\s?\d+(\.\d{2})?\s*(/|per)\s*(mo|month|yr|year|week)`,
  String.raw`\bcheckout\b`,
  String.raw`\bstripe\b`,
];

/** QA banned claims (qa/DISCLAIMERS.md) + claims we can't substantiate yet. */
const BANNED_CLAIMS = [
  String.raw`\bguarantee(d|s)?\b`,
  String.raw`\bvalidated\b`,
  String.raw`\brisk[\s-]?free\b`,
  String.raw`\bsure[\s-]?(win|thing|bet)\b`,
  String.raw`\bcan'?t\s+lose\b`,
  String.raw`\bcannot\s+lose\b`,
  String.raw`\b100\s?%`,
  String.raw`\b\d{2,3}\s?%\s*(accura|win|success|hit)`,
  // Mirrors backend _CLAIM_PATTERNS additions + QA Display-line rule.
  String.raw`\bprofitab(le|ility)\b`,
  String.raw`\bhigh\s+win[\s-]?rates?\b`,
  String.raw`\b(positive\s+)?expectancy\b`,
  // QA tagline/strategy-text list. Scope: tenant + strategy text only, never the metrics grid.
  String.raw`\bwin[\s-]?rates?\b`,
  String.raw`\baccura(te|cy)\b`,
  String.raw`\boutperform(s|ed|ing|ance)?\b`,
  String.raw`\bprofit[\s-]?factor\b`,
  String.raw`\bsharpe\b`,
  String.raw`\d+(\.\d+)?\s?%`,
];

/** Any price / currency amount: symbol+number, number+symbol, ISO code or "dollars" next to a number. */
const CURRENCY_AMOUNT = [
  String.raw`[$€£¥₹₿]\s?\d`,
  String.raw`\d\s?[$€£¥₹₿]`,
  String.raw`\b(usd|eur|gbp|jpy|aud|cad|chf|usdt|usdc|btc)\s?\d`,
  String.raw`\d[\d,.]*\s?(usd|eur|gbp|jpy|aud|cad|chf|usdt|usdc)\b`,
  String.raw`\d[\d,.]*\s?(dollars?|euros?|pounds?|bucks)\b`,
];

const RX = new RegExp([...NO_PRICE_SCAN, ...BANNED_CLAIMS, ...CURRENCY_AMOUNT].join("|"), "i");

export function isBannedTenantText(text: string): boolean {
  return RX.test(text);
}

/** Returns trimmed text if clean and non-empty, otherwise the fallback. */
export function cleanTenantText(text: string | null | undefined, fallback: string): string;
export function cleanTenantText(text: string | null | undefined, fallback?: undefined): string | undefined;
export function cleanTenantText(text: string | null | undefined, fallback?: string): string | undefined {
  const t = (text ?? "").trim();
  if (!t || isBannedTenantText(t)) return fallback;
  return t;
}
