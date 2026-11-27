import { fmtNum, fmtPct } from "@/lib/format";
import { tradeCount } from "@/lib/backtest";
import type { BacktestReport } from "@/lib/types/signal";

/** Headline metrics. Render ONLY for QA-approved, unflagged reports (enforced by callers via reviewState). */
export function MetricsGrid({ r, compact }: { r: BacktestReport; compact?: boolean }) {
  const items = [
    { k: "Win rate", v: fmtPct(r.win_rate) },
    { k: "Profit factor", v: fmtNum(r.profit_factor) },
    { k: "Sharpe", v: fmtNum(r.sharpe) },
    { k: "Sortino", v: fmtNum(r.sortino) },
    { k: "Max drawdown", v: fmtPct(-Math.abs(r.max_drawdown)) },
    { k: "Avg R", v: fmtNum(r.avg_R) },
    { k: "OOS trades", v: String(tradeCount(r)) },
    { k: "Exposure", v: fmtPct(r.exposure) },
  ];
  const shown = compact ? items.slice(0, 4) : items;
  return (
    <div className={compact ? "grid grid-cols-4 gap-2" : "grid grid-cols-2 gap-3 md:grid-cols-4"}>
      {shown.map((i) => (
        <div key={i.k} className={compact ? "" : "rounded-xl border border-line bg-surface p-4"}>
          <div className="text-[11px] text-text-muted">{i.k}</div>
          <div className={`num font-semibold ${compact ? "text-sm" : "mt-1 text-xl"}`}>{i.v}</div>
        </div>
      ))}
    </div>
  );
}
