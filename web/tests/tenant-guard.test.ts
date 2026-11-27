import { describe, expect, it } from "vitest";
import { cleanTenantText, isBannedTenantText } from "@/lib/tenant-guard";
import { defaultTenant, tenantFromConfig } from "@/lib/tenant";

describe("isBannedTenantText", () => {
  it.each([
    "Guaranteed profits every week",
    "Signals validated by AI",
    "Risk-free trading",
    "risk free returns",
    "A sure win strategy",
    "You can't lose",
    "100% accurate signals",
    "92% win rate",
    "Only $49/mo", // qa-allow-price: banned-text test fixture
    "Pro plan from €19", // qa-allow-price: banned-text test fixture
    "Join for 29 USD",
    "Costs 10 dollars",
    "£5 a week",
    "Start your free trial", // qa-allow-price: banned-text test fixture
    "Subscribe now", // qa-allow-price: banned-text test fixture
    "See pricing", // qa-allow-price: banned-text test fixture
    "Upgrade to Pro", // qa-allow-price: banned-text test fixture
    "Secure checkout", // qa-allow-price: banned-text test fixture
  ])("rejects %s", (t) => expect(isBannedTenantText(t)).toBe(true));

  it.each([
    "Acme Markets",
    "Multi-market trading signals",
    "Signals for crypto, equities and FX",
    "Acme Ltd is not a registered investment adviser.",
    "Trading involves risk. Signals may be wrong.",
    "BTC/USDT and EUR/USD coverage",
  ])("accepts %s", (t) => expect(isBannedTenantText(t)).toBe(false));
});

describe("cleanTenantText", () => {
  it("falls back on banned or empty text", () => {
    expect(cleanTenantText("Guaranteed gains", "Default")).toBe("Default");
    expect(cleanTenantText("   ", "Default")).toBe("Default");
    expect(cleanTenantText(null, "Default")).toBe("Default");
    expect(cleanTenantText("  Acme  ", "Default")).toBe("Acme");
  });
});

describe("tenantFromConfig applies the guard", () => {
  it("replaces banned name/tagline with defaults and drops banned disclaimer lines", () => {
    const t = tenantFromConfig({
      tenant_id: "x",
      name: "100% Winners",
      tagline: "Validated, risk-free signals",
      colors: { accent: "#ff0000", bg: "red; background:url(x)" },
      extra_disclaimers: ["Acme is not an adviser.", "Returns guaranteed!", "Only $9 per month"], // qa-allow-price: banned-text test fixture
    });
    expect(t.name).toBe(defaultTenant.name);
    expect(t.tagline).toBe(defaultTenant.tagline);
    expect(t.extraDisclaimers).toEqual(["Acme is not an adviser."]);
    expect(t.colors.accent).toBe("#ff0000");
    expect(t.colors.bg).toBe(defaultTenant.colors.bg);
  });

  it("keeps clean tenant text", () => {
    const t = tenantFromConfig({ tenant_id: "a", name: "Acme Markets", tagline: "Multi-asset signal feed", extra_disclaimers: [] });
    expect(t.name).toBe("Acme Markets");
    expect(t.tagline).toBe("Multi-asset signal feed");
  });
});
