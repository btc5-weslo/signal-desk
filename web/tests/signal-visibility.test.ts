import { describe, expect, it } from "vitest";
import { isMockSignal, isVisibleSignal, visibleSignals } from "@/lib/signal-visibility";

const real = { id: "a", is_mock: false, status: "active" };
const flagged = { id: "b", is_mock: true, status: "active" };
const statusMock = { id: "c", is_mock: false, status: "mock" };
const statusMockUpper = { id: "d", status: "MOCK" };
const noFlag = { id: "e", status: "closed" };

describe("signal visibility", () => {
  it("detects mock rows by is_mock or status", () => {
    expect(isMockSignal(real)).toBe(false);
    expect(isMockSignal(flagged)).toBe(true);
    expect(isMockSignal(statusMock)).toBe(true);
    expect(isMockSignal(statusMockUpper)).toBe(true);
    expect(isMockSignal(noFlag)).toBe(false);
  });
  it("drops mock rows in real mode", () => {
    expect(visibleSignals([real, flagged, statusMock, noFlag], false).map((s) => s.id)).toEqual(["a", "e"]);
    expect(isVisibleSignal(flagged, false)).toBe(false);
    expect(isVisibleSignal(real, false)).toBe(true);
  });
  it("returns an empty list when only mock rows exist", () => {
    expect(visibleSignals([flagged, statusMock], false)).toEqual([]);
  });
  it("keeps everything in mock mode", () => {
    expect(visibleSignals([real, flagged, statusMock], true)).toHaveLength(3);
    expect(isVisibleSignal(flagged, true)).toBe(true);
  });
});
