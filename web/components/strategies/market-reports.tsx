"use client";

import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ValidationBadge } from "@/components/common/badges";
import { PerformanceNote } from "@/components/common/disclaimer";
import { flagLabel, reviewState, tradeCount } from "@/lib/backtest";
import { displaySymbol, fmtNum, fmtPct } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { BacktestReport, ValidationStatus } from "@/lib/types/signal";

export interface MarketRow {
  symbol: string;
  timeframe: string;
  run_id: string;
  flags: string[];
  approved: boolean;
  /** Full report — fetched only when approved && flags empty. */
  report: BacktestReport | null;
}

export function DataQualityChip() {
  return (
    <span className="inline-flex items-center gap-1 rounded-md border border-warning/40 bg-warning/15 px-1.5 py-0.5 text-[11px] font-medium text-warning" title="Data quality warning raised for this market's data">
      <AlertTriangle className="size-3" /> Data quality
    </span>
  );
}

/** Per-market validation from the index row (data only). */
function rowValidation(m: MarketRow): ValidationStatus {
  if (m.flags.includes("insufficient_oos_history")) return "insufficient_oos";
  if (!m.approved || m.flags.length > 0) return "pending";
  return m.report?.validation_status ?? "validated";
}

/** Per symbol+timeframe reports, each with its own validation state. Metrics only for unflagged reports. */
export function MarketReports({
  strategyId,
  rows,
  activeRunId,
  version,
}: {
  strategyId: string;
  rows: MarketRow[];
  activeRunId?: string;
  /** Shown in the empty-state row. */
  version?: string;
}) {
  const anyShown = rows.some((r) => r.report && r.approved && r.flags.length === 0);
  return (
    <div className="space-y-2">
      <div className="overflow-hidden rounded-xl border border-line bg-surface">
        <Table>
          <TableHeader>
            <TableRow className="border-line hover:bg-transparent">
              {["Market", "Validation", "Trades", "Win rate", "Profit factor", "Sharpe", "Max DD", "Run"].map((h) => (
                <TableHead key={h} className="h-9 text-[11px] uppercase tracking-wider text-text-muted">{h}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 && (
              <TableRow className="border-line hover:bg-transparent">
                <TableCell colSpan={8} className="py-5 text-center text-xs text-text-muted">
                  <span className="font-medium text-text">Not yet validated.</span> No per-market backtest
                  {version ? ` for v${version}` : ""} has been run and approved by QA, so no metrics are shown.
                </TableCell>
              </TableRow>
            )}
            {rows.map((m) => {
              const r = m.report;
              const ok = !!r && m.approved && m.flags.length === 0 && reviewState(r).kind === "approved";
              const flags = m.flags;
              return (
                <TableRow key={m.run_id} className={cn("border-line", activeRunId === m.run_id && "bg-surface-2/60")}>
                  <TableCell className="num text-xs font-medium">{displaySymbol(m.symbol)} · {m.timeframe}</TableCell>
                  <TableCell>
                    {m.approved || flags.length > 0 ? (
                      <div className="flex flex-wrap items-center gap-1.5">
                        <ValidationBadge status={rowValidation(m)} />
                        {!m.approved && <span className="text-[11px] text-text-muted">Awaiting QA approval</span>}
                        {flags.includes("data_quality_warning") && <DataQualityChip />}
                        {flags.length > 0 && (
                          <span className="inline-flex items-center gap-1 text-[11px] text-warning" title={flags.map(flagLabel).join("; ")}>
                            <AlertTriangle className="size-3" /> {flags.length === 1 ? flagLabel(flags[0]) : `${flags.length} flags`}
                          </span>
                        )}
                      </div>
                    ) : (
                      <span className="text-[11px] text-text-muted">Awaiting QA approval</span>
                    )}
                  </TableCell>
                  <TableCell className="num text-xs">{r ? tradeCount(r) : "—"}</TableCell>
                  <TableCell className="num text-xs">{ok && r ? fmtPct(r.win_rate) : "—"}</TableCell>
                  <TableCell className="num text-xs">{ok && r ? fmtNum(r.profit_factor) : "—"}</TableCell>
                  <TableCell className="num text-xs">{ok && r ? fmtNum(r.sharpe) : "—"}</TableCell>
                  <TableCell className="num text-xs">{ok && r ? fmtPct(-Math.abs(r.max_drawdown)) : "—"}</TableCell>
                  <TableCell className="text-xs">
                    {m.approved ? (
                      <Link className="num text-brand hover:underline" href={`/strategies/${encodeURIComponent(strategyId)}?run=${encodeURIComponent(m.run_id)}`}>
                        {m.run_id.slice(0, 10)}
                      </Link>
                    ) : (
                      <span className="num text-text-muted">{m.run_id.slice(0, 10)}</span>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      {rows.length > 0 && <p className="text-[11px] text-text-muted">“—” = metrics hidden: the market has QA flags or isn’t QA-approved yet.</p>}
      {anyShown && <PerformanceNote />}
    </div>
  );
}
