import { describe, expect, it } from "vitest";
import { strategyHypothesis, strategySubtitle } from "@/lib/strategy-text";

describe("strategySubtitle", () => {
  it("hides a description that repeats the name (case/whitespace-insensitive)", () => {
    expect(strategySubtitle({ name: "Trend EMA + ADX", description: "Trend EMA + ADX" })).toBeNull();
    expect(strategySubtitle({ name: "Trend EMA + ADX", description: "  trend   ema + adx " })).toBeNull();
  });
  it("hides empty / null / missing", () => {
    expect(strategySubtitle({ name: "X", description: "" })).toBeNull();
    expect(strategySubtitle({ name: "X", description: "   " })).toBeNull();
    expect(strategySubtitle({ name: "X", description: null })).toBeNull();
    expect(strategySubtitle({ name: "X" })).toBeNull();
  });
  it("shows a distinct description, trimmed", () => {
    expect(strategySubtitle({ name: "Trend EMA + ADX", description: " Follows trends when ADX confirms strength. " })).toBe(
      "Follows trends when ADX confirms strength.",
    );
  });
  it("hides text that fails the banned-claims guard", () => {
    expect(strategySubtitle({ name: "X", description: "Guaranteed profits every week" })).toBeNull(); // qa-allow-price: banned-text test fixture
    expect(strategySubtitle({ name: "X", description: "Risk-free breakout entries" })).toBeNull(); // qa-allow-price: banned-text test fixture
  });
});

describe("strategyHypothesis", () => {
  it("bare id hypothesis becomes a tag, no section", () => {
    expect(strategyHypothesis({ name: "X", hypothesis: "H1" })).toEqual({ tag: "H1", text: null });
    expect(strategyHypothesis({ name: "X", hypothesis: " h12 " })).toEqual({ tag: "H12", text: null });
  });
  it("full sentence goes under the heading", () => {
    expect(strategyHypothesis({ name: "X", hypothesis: "Breakouts above a 20-bar high tend to continue." })).toEqual({
      tag: null,
      text: "Breakouts above a 20-bar high tend to continue.",
    });
  });
  it("prefers hypothesis_id for the tag and keeps the sentence", () => {
    expect(strategyHypothesis({ name: "X", hypothesis_id: "H3", hypothesis: "Mean reversion after band touches." })).toEqual({
      tag: "H3",
      text: "Mean reversion after band touches.",
    });
    expect(strategyHypothesis({ name: "X", hypothesis_id: "H3", hypothesis: "H1" })).toEqual({ tag: "H3", text: null });
  });
  it("nulls hide everything", () => {
    expect(strategyHypothesis({ name: "X", hypothesis: null, hypothesis_id: null })).toEqual({ tag: null, text: null });
    expect(strategyHypothesis({ name: "X" })).toEqual({ tag: null, text: null });
  });
  it("hides banned text in hypothesis and hypothesis_id", () => {
    expect(strategyHypothesis({ name: "X", hypothesis: "This strategy can't lose." }).text).toBeNull(); // qa-allow-price: banned-text test fixture
    expect(strategyHypothesis({ name: "X", hypothesis_id: "100% accurate", hypothesis: "H2" })).toEqual({ tag: "H2", text: null }); // qa-allow-price: banned-text test fixture
  });
});
