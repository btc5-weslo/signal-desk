"use client";
import type { AssetClass, Timeframe } from "@/lib/types/signal";

/** Local-only user preferences until Backend exposes a preferences endpoint. */
export interface Prefs {
  markets: AssetClass[];
  timeframes: Timeframe[];
  channels: { push: boolean; email: boolean; telegram: boolean; discord: boolean };
  email: string;
  telegramChatId: string;
  discordWebhook: string;
  minConfidence: number;
  riskAcknowledgedAt: string | null;
}

export const DEFAULT_PREFS: Prefs = {
  markets: ["crypto", "equity", "fx"],
  timeframes: ["1h", "4h", "1d"],
  channels: { push: true, email: false, telegram: false, discord: false },
  email: "",
  telegramChatId: "",
  discordWebhook: "",
  minConfidence: 0.55,
  riskAcknowledgedAt: null,
};

const KEY = "signal_app.prefs";

export function loadPrefs(): Prefs {
  if (typeof window === "undefined") return DEFAULT_PREFS;
  try {
    return { ...DEFAULT_PREFS, ...JSON.parse(window.localStorage.getItem(KEY) ?? "{}") };
  } catch {
    return DEFAULT_PREFS;
  }
}

export function savePrefs(p: Prefs) {
  window.localStorage.setItem(KEY, JSON.stringify(p));
}
