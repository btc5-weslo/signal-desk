import Link from "next/link";
import { AssetBadge, MockBadge, SideBadge, StatusBadge, TfBadge, ValidationBadge } from "@/components/common/badges";
import { ConfidenceMeter } from "@/components/common/confidence";
import { displaySymbol, fmtPrice, relTime, riskReward } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Signal } from "@/lib/types/signal";

export function SignalCard({ s, isNew, now }: { s: Signal; isNew?: boolean; now: number }) {
  const rr = riskReward(s);
  const accent = s.side === "long" ? "before:bg-long" : s.side === "short" ? "before:bg-short" : "before:bg-line";
  return (
    <Link
      href={`/signals/${encodeURIComponent(s.id)}`}
      className={cn(
        "group relative flex flex-col gap-3 overflow-hidden rounded-xl border border-line bg-surface p-4 transition-colors hover:border-text-muted/40 hover:bg-surface-2/50",
        "before:absolute before:inset-y-0 before:left-0 before:w-[3px]", accent,
        isNew && "ring-1 ring-brand/50",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="num text-[15px] font-semibold tracking-tight">{displaySymbol(s.symbol, s.asset_class)}</span>
            <SideBadge side={s.side} />
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <AssetBadge asset={s.asset_class} />
            <TfBadge tf={s.timeframe} />
            {s.is_mock && <MockBadge />}
            {s.validation_status === "insufficient_oos" && <ValidationBadge status="insufficient_oos" />}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <StatusBadge status={s.status} />
          <span className="text-[11px] text-text-muted" suppressHydrationWarning>{relTime(s.generated_at, now)}</span>
        </div>
      </div>

      {s.side === "flat" ? (
        <p className="line-clamp-2 text-xs text-text-muted">{s.rationale}</p>
      ) : (
        <div className="grid grid-cols-3 gap-2 rounded-lg bg-bg/60 p-2.5">
          <Level label="Entry" value={fmtPrice(s.entry)} />
          <Level label="Stop" value={fmtPrice(s.stop_loss)} className="text-short" />
          <Level label={s.take_profit.length > 1 ? `TP ×${s.take_profit.length}` : "Target"} value={fmtPrice(s.take_profit[0])} className="text-long" />
        </div>
      )}

      <div className="flex items-center justify-between">
        <ConfidenceMeter value={s.confidence} calibrated={s.confidence_calibrated} />
        {rr !== null && <span className="num text-xs text-text-muted">R:R {rr.toFixed(2)}</span>}
      </div>
    </Link>
  );
}

function Level({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-text-muted">{label}</div>
      <div className={cn("num text-[13px] font-medium", className)}>{value}</div>
    </div>
  );
}
