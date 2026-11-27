/**
 * White-label tenant theming.
 *
 * Source of truth: GET /v1/tenant/config (resolved by request host on the backend), fetched
 * server-side in app/layout.tsx via lib/tenant-server.ts. When that fails (or under mock),
 * the neutral `defaultTenant` below is used. This file is the ONLY place the placeholder
 * brand name / logo / tagline live — swap them here (one line each) or serve them from the API.
 *
 * Tokens are applied as CSS variables on <html>; app/globals.css derives shadcn vars from them.
 */
import type { TenantConfig } from "@/lib/types/signal";
import { cleanTenantText } from "@/lib/tenant-guard";


export interface TenantColors {
  bg: string;
  surface: string;
  surface2: string;
  border: string;
  text: string;
  muted: string;
  accent: string;
  accentText: string;
  long: string;
  short: string;
  warning: string;
}

export interface TenantTheme {
  id: string;
  name: string;
  /** Square logo; when omitted a monogram is rendered. */
  logoUrl?: string;
  /** Top-bar / meta tagline. Keep free of performance claims. Omit to hide. */
  tagline?: string;
  colors: TenantColors;
  radius?: string;
  /**
   * Extra disclaimer lines from the tenant — APPENDED after the QA defaults in lib/disclaimers.ts.
   * There is intentionally no way for a tenant to remove or replace the defaults.
   */
  extraDisclaimers: string[];
  // NOTE: licensed data sources are deliberately NOT part of the theme. They are platform-only and
  // read solely from GET /v1/tenant/config (lib/data-policy-server.ts), so no default/preview/override can set them.
}

// ---- Neutral default (placeholder brand: change here) --------------------------------------
export const defaultTenant: TenantTheme = {
  id: "default",
  name: "Signal Desk",
  logoUrl: "/logo.svg",
  tagline: "Multi-market trading signals",
  colors: {
    bg: "#0a0c10",
    surface: "#11141a",
    surface2: "#171b23",
    border: "#232835",
    text: "#e6e9ef",
    muted: "#8b93a7",
    accent: "#6d8bff",
    accentText: "#0a0c10",
    long: "#22c55e",
    short: "#f04452",
    warning: "#f5a524",
  },
  radius: "0.625rem",
  extraDisclaimers: [],
};
// ---------------------------------------------------------------------------------------------

/** Example palette for the Settings preview only (not a real tenant). */
export const PREVIEW_THEMES: TenantTheme[] = [
  defaultTenant,
  {
    ...defaultTenant,
    id: "example-violet",
    name: "Example tenant",
    logoUrl: undefined,
    tagline: undefined,
    colors: { ...defaultTenant.colors, bg: "#0b0a12", surface: "#13111d", surface2: "#1a1726", border: "#2a2540", accent: "#b07cff", long: "#2dd4bf", short: "#fb7185" },
    radius: "0.875rem",
  },
];

const HEX = /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i;
/** Accept backend color keys in camelCase or snake_case; hex only (charts append alpha to hex). */
const COLOR_KEYS: Record<keyof TenantColors, string[]> = {
  bg: ["bg", "background"],
  surface: ["surface"],
  surface2: ["surface2", "surface_2"],
  border: ["border", "line"],
  text: ["text", "foreground"],
  muted: ["muted", "text_muted"],
  accent: ["accent", "brand", "primary"],
  accentText: ["accentText", "accent_text", "primary_foreground"],
  long: ["long"],
  short: ["short"],
  warning: ["warning"],
};

function safeLogo(url?: string | null): string | undefined {
  if (!url) return undefined;
  return /^https:\/\//i.test(url) || url.startsWith("/") ? url : undefined;
}

/** Map generated TenantConfig (GET /v1/tenant/config) to a theme. Uses `tagline` when present, else the neutral default. */
export function tenantFromConfig(cfg: TenantConfig): TenantTheme {
  const colors = { ...defaultTenant.colors };
  for (const [k, aliases] of Object.entries(COLOR_KEYS) as [keyof TenantColors, string[]][]) {
    const v = aliases.map((a) => cfg.colors?.[a]).find((x) => typeof x === "string" && HEX.test(x));
    if (v) colors[k] = v;
  }
  return {
    id: cfg.tenant_id,
    // Tenant text passes the banned-claims guard (lib/tenant-guard.ts); rejected text falls back to the default.
    name: cleanTenantText(cfg.name, defaultTenant.name),
    logoUrl: safeLogo(cfg.logo_url),
    tagline: cleanTenantText(cfg.tagline, defaultTenant.tagline as string),
    colors,
    radius: defaultTenant.radius,
    // Rejected lines are dropped (the QA default disclaimers always render regardless).
    extraDisclaimers: (cfg.extra_disclaimers ?? []).map((l) => cleanTenantText(typeof l === "string" ? l : "")).filter((l): l is string => !!l),
  };
}

export function tenantCssVars(t: TenantTheme): Record<string, string> {
  const c = t.colors;
  return {
    "--bg": c.bg,
    "--surface": c.surface,
    "--surface-2": c.surface2,
    "--line": c.border,
    "--text": c.text,
    "--text-muted": c.muted,
    "--brand": c.accent,
    "--brand-text": c.accentText,
    "--long": c.long,
    "--short": c.short,
    "--warning": c.warning,
    ...(t.radius ? { "--radius": t.radius } : {}),
  };
}
