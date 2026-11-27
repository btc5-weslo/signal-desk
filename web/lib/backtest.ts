import type { BacktestFlag, BacktestReport, BacktestTrade, Strategy, ValidationStatus } from "@/lib/types/signal";

export function tradeLog(r: BacktestReport): BacktestTrade[] | null {
  return Array.isArray(r.trades) ? r.trades : null;
}

export function tradeCount(r: BacktestReport): number {
  return typeof r.trade_count === "number" ? r.trade_count : (r.trades?.length ?? 0);
}

export type ReviewState = { kind: "approved" } | { kind: "under_review"; flags: string[] };

/**
 * The API serves only QA-approved reports, so a returned report counts as approved —
 * but headline metrics are shown ONLY while `flags` (QA leakage thresholds) is empty.
 * No dependency on qa_approved / qa_status fields.
 */
export function reviewState(r: BacktestReport): ReviewState {
  const flags = r.flags ?? [];
  return flags.length > 0 ? { kind: "under_review", flags } : { kind: "approved" };
}

/** Generated BacktestFlag enum -> friendly labels. Unknown values (newer backend) are shown raw. */
export const FLAG_LABELS: Record<BacktestFlag, string> = {
  low_oos_trades: "Fewer than 100 out-of-sample trades",
  sharpe_gt_3: "Sharpe above 3 — possible leakage",
  win_rate_gt_75: "Win rate above 75% — possible leakage",
  insufficient_oos_history: "Insufficient out-of-sample history",
  data_quality_warning: "Data quality warning",
  metric_recompute_mismatch: "Metrics didn't match on independent recompute",
};

export const flagLabel = (f: string) => FLAG_LABELS[f as BacktestFlag] ?? f;

export const isSummary = (r: BacktestReport) => r.symbol == null && r.timeframe == null;

/** Validation state of a single report (summary or per-market), from data only. */
export function reportValidation(r: BacktestReport): ValidationStatus {
  if (r.validation_status === "insufficient_oos" || (r.flags ?? []).includes("insufficient_oos_history" as BacktestFlag)) return "insufficient_oos";
  return (r.flags ?? []).length === 0 ? (r.validation_status ?? "validated") : "pending";
}

export function resolveValidation(
  strategy: Strategy | null | undefined,
  report: BacktestReport | null | undefined,
): ValidationStatus {
  if (strategy?.validation_status === "insufficient_oos") return "insufficient_oos";
  if (report) return reportValidation(report);
  return "pending";
}

/** Cumulative R series from the real trade list (R is net of fees + slippage). */
export function equityFromTrades(trades: BacktestTrade[]): { time: string; value: number }[] | null {
  if (trades.length === 0) return null;
  let cum = 0;
  return [...trades]
    .sort((a, b) => a.exit_time.localeCompare(b.exit_time))
    .map((t) => {
      cum += t.r_multiple;
      return { time: t.exit_time, value: cum };
    });
}
