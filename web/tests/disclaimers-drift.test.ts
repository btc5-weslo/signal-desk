import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { DEFAULT_DISCLAIMERS } from "@/lib/disclaimers";

/** QA source of truth: lib/disclaimers.ts must match ../qa/DISCLAIMERS.md exactly (whitespace-normalized). */
const FILE = path.resolve(__dirname, "../../qa/DISCLAIMERS.md");

/** Map each `**Heading:**` to the paragraph that follows it. */
function sections(md: string): Record<string, string> {
  const out: Record<string, string> = {};
  const re = /^\*\*(.+?):\*\*\s*$\n([\s\S]*?)(?=^\*\*|\s*$(?![\s\S]))/gm;
  for (const m of md.matchAll(re)) out[m[1].trim()] = m[2].replace(/\s+/g, " ").trim();
  return out;
}

const HEADINGS: Record<keyof typeof DEFAULT_DISCLAIMERS, string> = {
  footer: "Footer / onboarding (short)",
  signal: "Signal detail + every alert (email/Telegram/Discord/push)",
  performance: "Next to any performance figure",
  cryptoFxRisk: "Crypto / forex / leverage risk (settings + onboarding)",
};

describe("disclaimers match qa/DISCLAIMERS.md", () => {
  it("QA file exists", () => {
    expect(existsSync(FILE), `missing ${FILE}`).toBe(true);
  });
  const md = existsSync(FILE) ? readFileSync(FILE, "utf8") : "";
  const qa = sections(md);
  it.each(Object.entries(HEADINGS))("%s matches the QA wording", (key, heading) => {
    expect(qa[heading], `QA section "${heading}" not found`).toBeTruthy();
    expect(DEFAULT_DISCLAIMERS[key as keyof typeof DEFAULT_DISCLAIMERS].replace(/\s+/g, " ").trim()).toBe(qa[heading]);
  });
  it("no QA disclaimer section is unmapped", () => {
    const mapped = new Set(Object.values(HEADINGS));
    const unmapped = Object.keys(qa).filter((h) => !mapped.has(h) && !/^Banned words/i.test(h));
    expect(unmapped).toEqual([]);
  });
});
