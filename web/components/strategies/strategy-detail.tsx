"use client";

import { strategyHypothesis, strategySubtitle } from "@/lib/strategy-text";
import Link from "next/link";
import dynamic from "next/dynamic";
import { ArrowLeft, FlaskConical, SearchX, WifiOff } from "lucide-react";
import { api } from "@/lib/api/client";
import { useAsync } from "@/hooks/use-async";
import { equityFromTrades, isSummary, resolveValidation, reviewState, tradeLog } from "@/lib/backtest";
import { displaySymbol } from "@/lib/format";
import { AssetBadge, TfBadge, ValidationBadge, VALIDATION_COPY } from "@/components/common/badges";
import { EmptyState } from "@/components/common/empty-state";
import { DisclaimerCallout, PerformanceNote } from "@/components/common/disclaimer";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { BacktestReport, Strategy } from "@/lib/types/signal";
import { MetricsGrid } from "./metrics-grid";
import { ReviewBanner } from "./review-banner";
import { Transparency } from "./transparency";
import { TradesTable } from "./trades-table";
import { DataQualityChip, MarketReports, type MarketRow } from "./market-reports";

const EquityCurve = dynamic(() => import("./equity-curve").then((m) => m.EquityCurve), { ssr: false });

export function StrategyDetail({ id, runId }: { id: string; runId?: string }) {
  const state = useAsync(async () => {
    const all = await api.strategies();
    const s = all.find((x) => x.id === id) ?? null;
    const run = runId ?? s?.latest_run_id;
    const r = s && run ? await api.backtest(run) : null;
    // Per-market index; full report fetched only for approved + unflagged markets (metrics shown only for those).
    // null = index failed to load (shown as an error, not as "no backtests").
    const index = s ? await api.backtestIndex(s.id, s.version).catch(() => null) : [];
    const markets: MarketRow[] | null = index && await Promise.all(
      index
        .filter((m) => m.symbol != null && m.timeframe != null)
        .map(async (m) => ({
          ...m,
          symbol: m.symbol as string,
          timeframe: m.timeframe as string,
          report: m.approved && m.flags.length === 0 ? await api.backtest(m.run_id).catch(() => null) : null,
        })),
    );
    return { s, r, markets };
  }, [id, runId]);

  if (state.status === "loading") return <Skeleton className="mx-auto h-96 max-w-[1400px] rounded-xl bg-surface" />;
  if (state.status === "error") return <EmptyState icon={WifiOff} title="Can't load strategy">{state.error.message}</EmptyState>;
  if (!state.data.s)
    return <EmptyState icon={SearchX} title="Strategy not found"><Link href="/strategies" className="text-brand">Back to strategies</Link></EmptyState>;
  return <Detail s={state.data.s} r={state.data.r} markets={state.data.markets} runId={runId} />;
}

function Detail({ s, r, markets, runId }: { s: Strategy; r: BacktestReport | null; markets: MarketRow[] | null; runId?: string }) {
  const validation = resolveValidation(s, r);
  const review = r ? reviewState(r) : null;
  const approved = review?.kind === "approved";
  const trades = r ? tradeLog(r) : null;
  const equity = approved && trades ? equityFromTrades(trades) : null;
  const byMarket = Object.entries(s.validation_by_market ?? {});
  const subtitle = strategySubtitle(s);
  const hyp = strategyHypothesis(s);

  return (
    <div className="mx-auto max-w-[1400px] space-y-5">
      <Link href="/strategies" className="inline-flex items-center gap-1 text-xs text-text-muted hover:text-text">
        <ArrowLeft className="size-3.5" /> Strategies
      </Link>
      <div>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{s.name}</h1>
          <span className="num text-xs text-text-muted">{s.id} · v{s.version}</span>
          {hyp.tag && (
            <span className="num rounded-md border border-line bg-surface-2 px-1.5 py-0.5 text-[11px] text-text-muted" title="Hypothesis ID">{hyp.tag}</span>
          )}
          <ValidationBadge status={validation} />
        </div>
        {subtitle && <p className="mt-1.5 max-w-3xl text-sm text-text-muted">{subtitle}</p>}
        <div className="mt-3 flex flex-wrap gap-1.5">
          {s.asset_classes.map((a) => <AssetBadge key={a} asset={a} />)}
          {s.timeframes.map((t) => <TfBadge key={t} tf={t} />)}
        </div>
      </div>

      {validation === "insufficient_oos" && (
        <div className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">{VALIDATION_COPY.insufficient_oos.long}</div>
      )}

      {hyp.text && (
        <Card className="bg-surface">
          <CardHeader><CardTitle className="text-sm">Hypothesis</CardTitle></CardHeader>
          <CardContent><p className="text-sm leading-relaxed">{hyp.text}</p></CardContent>
        </Card>
      )}

      {byMarket.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-medium text-text-muted">Validation by market</h2>
          <div className="flex flex-wrap gap-2">
            {byMarket.map(([k, v]) => (
              <div key={k} className="flex items-center gap-2 rounded-lg border border-line bg-surface px-2.5 py-1.5">
                <span className="num text-xs">{k}</span>
                <ValidationBadge status={v} />
              </div>
            ))}
          </div>
        </div>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-medium text-text-muted">Per-market reports</h2>
        {markets ? (
          <MarketReports strategyId={s.id} version={s.version} rows={markets} activeRunId={runId ?? undefined} />
        ) : (
          <div className="rounded-xl border border-line bg-surface px-4 py-5 text-center text-xs text-text-muted">
            Couldn&apos;t load per-market reports. No metrics are shown.
          </div>
        )}
      </section>

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-medium text-text-muted">
            Out-of-sample performance
            {r && !isSummary(r) ? ` · ${displaySymbol(r.symbol ?? "")} ${r.timeframe ?? ""}` : r ? " · strategy summary" : ""}
          </h2>
          {runId && runId !== s.latest_run_id && (
            <Link href={`/strategies/${encodeURIComponent(s.id)}`} className="text-xs text-brand hover:underline">Back to summary</Link>
          )}
        </div>
        {!r ? (
          <EmptyState icon={FlaskConical} title="No validated backtest yet">
            Performance appears here only after a walk-forward, out-of-sample backtest with fees and slippage has been run and approved by QA.
          </EmptyState>
        ) : (
          <>
            {review && <ReviewBanner state={review} />}
            {(r.flags ?? []).includes("data_quality_warning") && <DataQualityChip />}
            {approved && (
              <div className="space-y-2">
                <MetricsGrid r={r} />
                <PerformanceNote />
              </div>
            )}
            <Transparency r={r} />

            <Card className="bg-surface">
              <CardHeader><CardTitle className="text-sm">Equity curve (cumulative, net of fees + slippage)</CardTitle></CardHeader>
              <CardContent>
                {equity ? (
                  <>
                    <EquityCurve points={equity} unit="R" />
                    <PerformanceNote className="mt-2" />
                  </>
                ) : (
                  <div className="grid h-[200px] place-items-center rounded-lg border border-dashed border-line text-xs text-text-muted">
                    {approved ? "No per-trade data in this run" : "Hidden while under QA review"}
                  </div>
                )}
              </CardContent>
            </Card>

            {r.oos_windows?.length > 0 && (
              <Card className="bg-surface">
                <CardHeader><CardTitle className="text-sm">Walk-forward windows</CardTitle></CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow className="border-line hover:bg-transparent">
                        {["#", "Train", "Test (OOS)", "Trades"].map((h) => <TableHead key={h} className="text-[11px] uppercase tracking-wider text-text-muted">{h}</TableHead>)}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {r.oos_windows.map((w, i) => (
                        <TableRow key={i} className="border-line">
                          <TableCell className="num text-xs">{i + 1}</TableCell>
                          <TableCell className="num text-xs text-text-muted">{w.train_start.slice(0, 10)} → {w.train_end.slice(0, 10)}</TableCell>
                          <TableCell className="num text-xs">{w.test_start.slice(0, 10)} → {w.test_end.slice(0, 10)}</TableCell>
                          <TableCell className="num text-xs">{w.trades ?? "—"}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            )}

            {trades && trades.length > 0 && (
              <div>
                <h2 className="mb-2 text-sm font-medium text-text-muted">Trades ({trades.length})</h2>
                {approved ? (
                  <>
                    <TradesTable trades={trades} />
                    <PerformanceNote className="mt-2" />
                  </>
                ) : (
                  <div className="rounded-xl border border-dashed border-line p-6 text-center text-xs text-text-muted">Per-trade outcomes hidden while under QA review.</div>
                )}
              </div>
            )}
          </>
        )}
      </section>

      <DisclaimerCallout k="performance" />
    </div>
  );
}
