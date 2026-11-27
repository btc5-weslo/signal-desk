"use client";

import { useRouter } from "next/navigation";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AssetBadge, MockBadge, SideBadge, StatusBadge, TfBadge, ValidationBadge } from "@/components/common/badges";
import { ConfidenceMeter } from "@/components/common/confidence";
import { displaySymbol, fmtPrice, relTime, riskReward } from "@/lib/format";
import type { Signal } from "@/lib/types/signal";

export function SignalTable({ rows, now }: { rows: Signal[]; now: number }) {
  const router = useRouter();
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-surface">
      <Table>
        <TableHeader>
          <TableRow className="border-line hover:bg-transparent">
            {["Symbol", "Side", "TF", "Entry", "Stop", "Target", "R:R", "Score", "Status", "Age"].map((h) => (
              <TableHead key={h} className="h-9 text-[11px] uppercase tracking-wider text-text-muted">{h}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((s) => {
            const rr = riskReward(s);
            return (
              <TableRow
                key={s.id}
                onClick={() => router.push(`/signals/${encodeURIComponent(s.id)}`)}
                className="cursor-pointer border-line hover:bg-surface-2/60"
              >
                <TableCell>
                  <div className="flex items-center gap-2">
                    <span className="num font-semibold">{displaySymbol(s.symbol, s.asset_class)}</span>
                    <AssetBadge asset={s.asset_class} />
                    {s.is_mock && <MockBadge />}
                    {s.validation_status === "insufficient_oos" && <ValidationBadge status="insufficient_oos" />}
                  </div>
                </TableCell>
                <TableCell><SideBadge side={s.side} /></TableCell>
                <TableCell><TfBadge tf={s.timeframe} /></TableCell>
                <TableCell className="num">{fmtPrice(s.entry)}</TableCell>
                <TableCell className="num text-short">{fmtPrice(s.stop_loss)}</TableCell>
                <TableCell className="num text-long">{fmtPrice(s.take_profit[0])}</TableCell>
                <TableCell className="num text-text-muted">{rr === null ? "—" : rr.toFixed(2)}</TableCell>
                <TableCell><ConfidenceMeter value={s.confidence} calibrated={s.confidence_calibrated} /></TableCell>
                <TableCell><StatusBadge status={s.status} /></TableCell>
                <TableCell className="text-xs text-text-muted" suppressHydrationWarning>{relTime(s.generated_at, now)}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
