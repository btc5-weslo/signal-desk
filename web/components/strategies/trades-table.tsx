import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SideBadge } from "@/components/common/badges";
import { displaySymbol, fmtNum, fmtPrice, fmtUtc } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { BacktestTrade } from "@/lib/types/signal";

const OUTCOME: Record<string, { label: string; cls: string }> = {
  tp: { label: "Target", cls: "text-long border-long/25 bg-long/10" },
  sl: { label: "Stop", cls: "text-short border-short/25 bg-short/10" },
  timeout: { label: "Timeout", cls: "text-text-muted border-line bg-surface-2" },
};

export function TradesTable({ trades, max = 200 }: { trades: BacktestTrade[]; max?: number }) {
  const rows = trades.slice(-max).reverse();
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-surface">
      <div className="max-h-[480px] overflow-auto">
        <Table>
          <TableHeader className="sticky top-0 bg-surface">
            <TableRow className="border-line hover:bg-transparent">
              {["Exit time", "Symbol", "Side", "Entry", "Exit", "Net return", "R multiple", "Bars held", "Outcome"].map((h) => (
                <TableHead key={h} className="h-9 text-[11px] uppercase tracking-wider text-text-muted">{h}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((t, i) => {
              const o = OUTCOME[t.exit_reason] ?? { label: String(t.exit_reason ?? "—"), cls: "text-text-muted border-line" };
              const r = t.r_multiple;
              return (
                <TableRow key={i} className="border-line">
                  <TableCell className="num text-xs text-text-muted">{fmtUtc(t.exit_time)}</TableCell>
                  <TableCell className="num text-xs">{displaySymbol(t.symbol)}</TableCell>
                  <TableCell>{t.side ? <SideBadge side={t.side} /> : "—"}</TableCell>
                  <TableCell className="num text-xs">{fmtPrice(t.entry_price)}</TableCell>
                  <TableCell className="num text-xs">{fmtPrice(t.exit_price)}</TableCell>
                  <TableCell className={cn("num text-xs", (t.net_return ?? 0) >= 0 ? "text-long" : "text-short")}>
                    {t.net_return === undefined ? "—" : `${(t.net_return * 100).toFixed(2)}%`}
                  </TableCell>
                  <TableCell className={cn("num text-xs", (r ?? 0) >= 0 ? "text-long" : "text-short")}>{r === undefined ? "—" : `${fmtNum(r)}R`}</TableCell>
                  <TableCell className="num text-xs">{t.bars_held ?? "—"}</TableCell>
                  <TableCell>
                    <span className={cn("rounded-md border px-1.5 py-0.5 text-[11px]", o.cls)}>{o.label}</span>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      {trades.length > max && (
        <div className="border-t border-line px-3 py-2 text-[11px] text-text-muted">Showing latest {max} of {trades.length} trades.</div>
      )}
    </div>
  );
}
