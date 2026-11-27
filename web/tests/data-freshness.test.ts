import { describe, expect, it } from "vitest";
import { barFreshness, delayedNote, fmtAge, inferAssetClass, isMarketOpen } from "@/lib/data-freshness";

const T = (iso: string) => Date.parse(iso);

describe("inferAssetClass", () => {
  it("classifies canonical ids", () => {
    expect(inferAssetClass("BTC-USDT")).toBe("crypto");
    expect(inferAssetClass("EURUSD")).toBe("fx");
    expect(inferAssetClass("AAPL")).toBe("equity");
  });
});

describe("crypto (24/7)", () => {
  const now = T("2026-11-26T04:00:00Z");
  it("fresh within 2 intervals of close", () => {
    expect(barFreshness("2026-11-26T02:00:00Z", "1h", "crypto", now)?.delayed).toBe(false);
    // closes 02:00 -> exactly 2h behind -> not MORE than 2 intervals
    expect(barFreshness("2026-11-26T01:00:00Z", "1h", "crypto", now)?.delayed).toBe(false);
  });
  it("delayed beyond 2 intervals, per timeframe", () => {
    expect(barFreshness("2026-11-26T00:59:00Z", "1h", "crypto", now)?.delayed).toBe(true);
    expect(barFreshness("2026-11-26T03:15:00Z", "15m", "crypto", now)?.delayed).toBe(false);
    expect(barFreshness("2026-11-26T03:14:00Z", "15m", "crypto", now)?.delayed).toBe(true);
    expect(barFreshness("2026-11-25T19:59:00Z", "4h", "crypto", now)?.delayed).toBe(false);
    expect(barFreshness("2026-11-25T15:59:00Z", "4h", "crypto", now)?.delayed).toBe(true);
    expect(barFreshness("2026-11-24T00:00:00Z", "1d", "crypto", now)?.delayed).toBe(false);
    expect(barFreshness("2026-11-23T00:00:00Z", "1d", "crypto", now)?.delayed).toBe(true);
  });
  it("live :8000 case: bars ending 2024-12-31 are delayed", () => {
    const f = barFreshness("2024-12-31T23:00:00Z", "1h", "crypto", now)!;
    expect(f.delayed).toBe(true);
    expect(delayedNote(f)).toBe("Data delayed: last bar 22 months ago");
  });
  it("in-progress / future bars are not delayed", () => {
    expect(barFreshness("2026-11-26T03:30:00Z", "1h", "crypto", now)).toMatchObject({ delayed: false, ageMs: 0 });
  });
  it("unknown timeframe or bad time -> null", () => {
    expect(barFreshness("2026-11-26T03:00:00Z", "2h", "crypto", now)).toBeNull();
    expect(barFreshness("nope", "1h", "crypto", now)).toBeNull();
  });
});

describe("fx hours (closed Fri 22:00 -> Sun 22:00 UTC)", () => {
  it("open/closed boundaries", () => {
    expect(isMarketOpen(T("2026-11-27T21:59:00Z"), "fx")).toBe(true); // Fri
    expect(isMarketOpen(T("2026-11-27T22:00:00Z"), "fx")).toBe(false);
    expect(isMarketOpen(T("2026-11-28T12:00:00Z"), "fx")).toBe(false); // Sat
    expect(isMarketOpen(T("2026-11-29T22:00:00Z"), "fx")).toBe(true); // Sun
  });
  it("weekend is not delayed; same lag midweek is", () => {
    expect(barFreshness("2026-11-27T21:00:00Z", "1h", "fx", T("2026-11-29T21:00:00Z"))?.delayed).toBe(false);
    expect(barFreshness("2026-11-25T21:00:00Z", "1h", "fx", T("2026-11-27T20:00:00Z"))?.delayed).toBe(true);
    // Sun 23:30: 1.5 open hours since reopen -> fresh; Mon 01:00 -> 3 open hours -> delayed
    expect(barFreshness("2026-11-27T21:00:00Z", "1h", "fx", T("2026-11-29T23:30:00Z"))?.delayed).toBe(false);
    expect(barFreshness("2026-11-27T21:00:00Z", "1h", "fx", T("2026-11-30T01:00:00Z"))?.delayed).toBe(true);
  });
});

describe("US equity hours (Mon-Fri 09:30-16:00 New York)", () => {
  it("session boundaries (EST = UTC-5)", () => {
    expect(isMarketOpen(T("2026-11-25T14:29:00Z"), "equity")).toBe(false);
    expect(isMarketOpen(T("2026-11-25T14:30:00Z"), "equity")).toBe(true);
    expect(isMarketOpen(T("2026-11-25T21:00:00Z"), "equity")).toBe(false);
    expect(isMarketOpen(T("2026-11-28T16:00:00Z"), "equity")).toBe(false); // Sat
  });
  it("overnight and weekend are not delayed", () => {
    // Fri 15:00-16:00 ET bar; Mon 09:45 ET -> 15 open minutes
    expect(barFreshness("2026-11-27T20:00:00Z", "1h", "equity", T("2026-11-30T14:45:00Z"))?.delayed).toBe(false);
    // Mon 12:00 ET -> 150 open minutes > 120 -> delayed
    expect(barFreshness("2026-11-27T20:00:00Z", "1h", "equity", T("2026-11-30T17:00:00Z"))?.delayed).toBe(true);
  });
  it("daily bars use 390-minute sessions", () => {
    // Fri 2026-11-27 daily bar (closes Fri 19:00 ET); Tue 12:00 ET = 540 open min (< 780) -> fresh;
    // Wed 16:00 ET = 1170 open min -> delayed
    expect(barFreshness("2026-11-27T00:00:00Z", "1d", "equity", T("2026-12-01T17:00:00Z"))?.delayed).toBe(false);
    expect(barFreshness("2026-11-27T00:00:00Z", "1d", "equity", T("2026-12-02T21:00:00Z"))?.delayed).toBe(true);
  });
  it("over 10 days is delayed regardless", () => {
    expect(barFreshness("2026-11-01T14:30:00Z", "1d", "equity", T("2026-11-25T15:00:00Z"))?.delayed).toBe(true);
  });
});

describe("fmtAge", () => {
  it("formats", () => {
    expect(fmtAge(45 * 60_000)).toBe("45m ago");
    expect(fmtAge(5 * 3600_000)).toBe("5h ago");
    expect(fmtAge(3 * 86400_000)).toBe("3d ago");
    expect(fmtAge(800 * 86400_000)).toBe("2 years ago");
  });
});
