import { tradeCount } from "@/lib/backtest";
import type { BacktestReport } from "@/lib/types/signal";

/** Run provenance — always visible so any figure can be reproduced from run_id + data_hash. */
export function Transparency({ r }: { r: BacktestReport }) {
  const rows: [string, string][] = [
    ["Run ID", r.run_id],
    ["Data hash", r.data_hash],
    ["Version", r.version],
    ["Period", `${r.period?.start?.slice(0, 10) ?? "?"} → ${r.period?.end?.slice(0, 10) ?? "?"}`],
    ["Fees", `${r.fees_bps} bps`],
    ["Slippage", `${r.slippage_bps} bps`],
    ["OOS windows", String(r.oos_windows?.length ?? 0)],
    ["Trades", String(tradeCount(r))],
  ];
  return (
    <div className="grid grid-cols-2 gap-x-6 gap-y-2 rounded-xl border border-line bg-surface p-4 text-xs md:grid-cols-4">
      {rows.map(([k, v]) => (
        <div key={k} className="min-w-0">
          <div className="text-text-muted">{k}</div>
          <div className="num truncate" title={v}>{v}</div>
        </div>
      ))}
    </div>
  );
}
