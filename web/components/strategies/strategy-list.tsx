"use client";

import { strategySubtitle } from "@/lib/strategy-text";
import Link from "next/link";
import { FlaskConical, LineChart, WifiOff } from "lucide-react";
import { api } from "@/lib/api/client";
import { config } from "@/lib/config";
import { useAsync } from "@/hooks/use-async";
import { reviewState, resolveValidation } from "@/lib/backtest";
import { AssetBadge, TfBadge, ValidationBadge } from "@/components/common/badges";
import { EmptyState } from "@/components/common/empty-state";
import { PerformanceNote } from "@/components/common/disclaimer";
import { Skeleton } from "@/components/ui/skeleton";
import type { BacktestReport, Strategy } from "@/lib/types/signal";
import { MetricsGrid } from "./metrics-grid";
import { ReviewPill } from "./review-banner";

export function StrategyList() {
  const state = useAsync(async () => {
    const strategies = await api.strategies();
    const reports = await Promise.all(
      strategies.map((s) => (s.latest_run_id ? api.backtest(s.latest_run_id).catch(() => null) : Promise.resolve(null))),
    );
    return strategies.map((s, i) => ({ s, r: reports[i] }));
  }, []);

  if (state.status === "loading")
    return <div className="grid gap-3 md:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-44 rounded-xl bg-surface" />)}</div>;
  if (state.status === "error") return <EmptyState icon={WifiOff} title="Can't load strategies">{state.error.message}</EmptyState>;
  if (state.data.length === 0) return <EmptyState icon={LineChart} title="No strategies published yet" />;

  return (
    <div className="grid gap-3 md:grid-cols-2">
      {state.data.map(({ s, r }) => <StrategyCard key={s.id} s={s} r={r} />)}
    </div>
  );
}

function StrategyCard({ s, r }: { s: Strategy; r: BacktestReport | null }) {
  const review = r ? reviewState(r) : null;
  const validation = resolveValidation(s, r);
  const subtitle = strategySubtitle(s);
  return (
    <Link href={`/strategies/${encodeURIComponent(s.id)}`}
      className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4 transition-colors hover:border-text-muted/40 hover:bg-surface-2/50">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-semibold">{s.name}</span>
            <span className="num text-[11px] text-text-muted">v{s.version}</span>
          </div>
          {subtitle && <p className="mt-1 line-clamp-2 text-xs text-text-muted">{subtitle}</p>}
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <ValidationBadge status={validation} />
          {review && <ReviewPill state={review} />}
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {s.asset_classes.map((a) => <AssetBadge key={a} asset={a} />)}
        {s.timeframes.map((t) => <TfBadge key={t} tf={t} />)}
      </div>
      <div className="mt-auto rounded-lg bg-bg/60 p-3">
        {r && review?.kind === "approved" ? (
          <div className="space-y-2">
            <MetricsGrid r={r} compact />
            <PerformanceNote />
          </div>
        ) : (
          <div className="flex items-center gap-2 text-xs text-text-muted">
            <FlaskConical className="size-3.5" />
            {r ? "Metrics hidden while under QA review" : "No validated backtest yet"}
            {config.useMock && !r && <span className="ml-auto text-[10px]">(backtests are never mocked)</span>}
          </div>
        )}
      </div>
    </Link>
  );
}
