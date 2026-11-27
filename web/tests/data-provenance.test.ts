import { describe, expect, it } from "vitest";
import { candleProvenance, dataCaption, isLicensedSource, isNeverLicensed, licensedFromTenantConfig, PROVISIONAL_NOTE } from "@/lib/data-provenance";
import { defaultTenant, PREVIEW_THEMES, tenantFromConfig } from "@/lib/tenant";

const bar = (source?: string | null) => ({ source });

describe("never-licensed sources (hard-coded)", () => {
  it.each(["binance_vision", "yfinance", "ccxt:binanceus", "ccxt:kraken", "CCXT:Coinbase", " YFinance "])("%s is never licensed", (s) => {
    expect(isNeverLicensed(s)).toBe(true);
    expect(isLicensedSource(s, [s, s.trim().toLowerCase()])).toBe(false);
  });
  it("does not treat lookalikes as never-licensed", () => {
    expect(isNeverLicensed("polygon")).toBe(false);
    expect(isNeverLicensed("not-ccxt:x")).toBe(false);
  });
});

describe("licensed allowlist", () => {
  it("licenses only explicitly listed sources (case-insensitive)", () => {
    expect(isLicensedSource("polygon", ["Polygon"])).toBe(true);
    expect(isLicensedSource("polygon", [])).toBe(false);
    expect(isLicensedSource("other", ["polygon"])).toBe(false);
  });
  it("missing source is never licensed", () => {
    expect(isLicensedSource(undefined, ["polygon"])).toBe(false);
    expect(isLicensedSource("  ", ["polygon"])).toBe(false);
  });
});

describe("candleProvenance", () => {
  it("live :8000 case: ccxt:binanceus with an empty list is provisional", () => {
    const p = candleProvenance([bar("ccxt:binanceus"), bar("ccxt:binanceus")], []);
    expect(p).toEqual({ sources: ["ccxt:binanceus"], missing: false, provisional: true });
    expect(PROVISIONAL_NOTE).toBe("Provisional data, not for live trading");
  });
  it("missing sources or no candles are provisional", () => {
    expect(candleProvenance([bar(), bar(null)], ["polygon"]).provisional).toBe(true);
    expect(candleProvenance([], ["polygon"]).provisional).toBe(true);
    expect(candleProvenance([bar("polygon"), bar()], ["polygon"]).missing).toBe(true);
  });
  it("any unlicensed bar makes the chart provisional", () => {
    expect(candleProvenance([bar("polygon"), bar("yfinance")], ["polygon", "yfinance"]).provisional).toBe(true);
  });
  it("fully licensed and attributed is not provisional", () => {
    expect(candleProvenance([bar("polygon"), bar("POLYGON")], ["polygon"]).provisional).toBe(false);
  });
});

describe("licensed list comes only from GET /v1/tenant/config", () => {
  it("reads licensed_data_sources from the config body, strings only", () => {
    expect(licensedFromTenantConfig({ licensed_data_sources: ["polygon", "", 3, null] as unknown[] })).toEqual(["polygon"]);
    expect(licensedFromTenantConfig({})).toEqual([]);
    expect(licensedFromTenantConfig(null)).toEqual([]);
  });
  it("tenant themes (defaults, previews, mapped config) never carry a licensed list", () => {
    const mapped = tenantFromConfig({ tenant_id: "t", name: "T", licensed_data_sources: ["polygon"] });
    for (const t of [defaultTenant, ...PREVIEW_THEMES, mapped]) expect("licensedDataSources" in t).toBe(false);
  });
});

describe("dataCaption", () => {
  it("lists every source shown, unrelabeled, in first-seen order", () => {
    const p = candleProvenance([bar("binance_vision"), bar("binance_vision"), bar("ccxt:binanceus")], []);
    expect(dataCaption(p)).toBe("Data: binance_vision, ccxt:binanceus");
    expect(p.provisional).toBe(true);
  });
  it("keeps exact source spelling", () => {
    expect(dataCaption(candleProvenance([bar("CCXT:BinanceUS"), bar("polygon")], ["polygon"]))).toBe("Data: CCXT:BinanceUS, polygon");
  });
  it("flags missing attribution", () => {
    expect(dataCaption(candleProvenance([bar("polygon"), bar()], ["polygon"]))).toBe("Data: polygon (some bars unattributed)");
    expect(dataCaption(candleProvenance([bar(), bar(null)], []))).toBe("Data: source not reported");
  });
});
