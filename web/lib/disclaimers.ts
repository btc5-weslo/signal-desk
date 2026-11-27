/**
 * Required user-facing disclaimers — exact QA-approved wording from
 * /workspace/signal-app/qa/DISCLAIMERS.md. Do not edit here without QA sign-off.
 *
 * Tenants may only APPEND lines (TenantTheme.extraDisclaimers, from GET /v1/tenant/config).
 * The defaults are `as const` and not part of the tenant type, so they can't be removed or replaced.
 * See qa/DISCLAIMERS.md for the banned-words list for product copy.
 */
export const DEFAULT_DISCLAIMERS = {
  /** Footer / onboarding (short) */
  footer:
    "Signals are for informational and educational purposes only and are not financial, investment, or trading advice. Trading involves substantial risk of loss. Past performance, including backtested results, does not guarantee future results.",
  /** Signal detail + every alert (email/Telegram/Discord/push) */
  signal:
    "Not financial advice. This signal is generated automatically and may be wrong. You are solely responsible for your trading decisions.",
  /** Next to any performance figure */
  performance:
    "Hypothetical backtested results, net of modeled fees and slippage. Backtests have inherent limitations and do not reflect actual trading. Past performance does not guarantee future results.",
  /** Crypto / forex / leverage risk (settings + onboarding) */
  cryptoFxRisk:
    "Cryptocurrency and leveraged forex trading are highly volatile and can result in losses exceeding your expectations. Only trade with money you can afford to lose.",
} as const;

export type DisclaimerKey = keyof typeof DEFAULT_DISCLAIMERS;

/** Default text for a slot; tenant extra lines are rendered after it (footer + onboarding). */
export function getDisclaimer(key: DisclaimerKey): string {
  return DEFAULT_DISCLAIMERS[key];
}
