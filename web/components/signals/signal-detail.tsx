"use client";

import { isVisibleSignal } from "@/lib/signal-visibility";
import Link from "next/link";
import dynamic from "next/dynamic";
import { ArrowLeft, CandlestickChart, SearchX, WifiOff } from "lucide-react";
import { api } from "@/lib/api/client";
import { config } from "@/lib/config";
import { useAsync } from "@/hooks/use-async";
import { AssetBadge, MockBadge, SideBadge, StatusBadge, TfBadge, ValidationBadge, VALIDATION_COPY } from "@/components/common/badges";
import { ConfidenceGauge } from "@/components/common/confidence";
import { DisclaimerCallout } from "@/components/common/disclaimer";
import { EmptyState } from "@/components/common/empty-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table";
import { displaySymbol, fmtPrice, fmtUtc, pctFrom, riskReward } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Signal } from "@/lib/types/signal";

const PriceChart = dynamic(() => import("./price-chart").then((m) => m.PriceChart), {
  ssr: false,
  loading: () => <Skeleton className="h-[380px] w-full rounded-lg bg-surface-2 md:h-[440px]" />,
});

export function SignalDetail({ id }: { id: string }) {
  const state = useAsync(() => api.signal(id), [id]);

  if (state.status === "loading")
    return (
      <div className="mx-auto max-w-[1400px] space-y-4">
        <Skeleton className="h-10 w-72 bg-surface" />
        <Skeleton className="h-[460px] w-full rounded-xl bg-surface" />
      </div>
    );
  if (state.status === "error")
    return <EmptyState icon={WifiOff} title="Can't load this signal">{state.error.message}</EmptyState>;
  if (!state.data)
    return (
      <EmptyState icon={SearchX} title="Signal not found">
        It may have been removed. <Link href="/signals" className="text-brand underline-offset-4 hover:underline">Back to signals</Link>
      </EmptyState>
    );
  if (!isVisibleSignal(state.data))
    return (
      <EmptyState icon={SearchX} title="Signal not available">
        This signal is placeholder data and isn&apos;t shown outside mock mode.{" "}
        <Link href="/signals" className="text-brand underline-offset-4 hover:underline">Back to signals</Link>
      </EmptyState>
    );
  return <Detail s={state.data} />;
}

function Detail({ s }: { s: Signal }) {
  const rr = riskReward(s);
  const features = Object.entries(s.features_snapshot ?? {});
  return (
    <div className="mx-auto max-w-[1400px]">
      <Link href="/signals" className="mb-4 inline-flex items-center gap-1 text-xs text-text-muted hover:text-text">
        <ArrowLeft className="size-3.5" /> Signals
      </Link>

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <h1 className="num text-2xl font-semibold tracking-tight">{displaySymbol(s.symbol, s.asset_class)}</h1>
        <SideBadge side={s.side} className="px-2 py-1 text-xs" />
        <AssetBadge asset={s.asset_class} />
        <TfBadge tf={s.timeframe} />
        <StatusBadge status={s.status} />
        {s.is_mock && <MockBadge />}
        {s.validation_status && <ValidationBadge status={s.validation_status} />}
      </div>

      {s.validation_status === "insufficient_oos" && (
        <div className="mb-4 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
          {VALIDATION_COPY.insufficient_oos.long} Treat this signal as experimental.
        </div>
      )}

      <DisclaimerCallout k="signal" className="mb-4" />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Card className="gap-3 bg-surface py-3">
          <CardHeader className="flex flex-row items-center justify-between px-4">
            <CardTitle className="flex items-center gap-2 text-sm">
              Chart · {s.timeframe}
              <Link href={`/markets/${encodeURIComponent(s.symbol)}?tf=${s.timeframe}`} className="text-[11px] font-normal text-brand hover:underline">Open market</Link>
            </CardTitle>
            <div className="flex items-center gap-3 text-[11px] text-text-muted">
              <Legend color="var(--brand)" label="Entry" />
              <Legend color="var(--short)" label="Stop / risk" />
              <Legend color="var(--long)" label="Target / reward" />
            </div>
          </CardHeader>
          <CardContent className="px-3">
            <ChartArea s={s} />
          </CardContent>
        </Card>

        <div className="flex flex-col gap-4">
          <Card className="bg-surface">
            <CardHeader><CardTitle className="text-sm">Levels</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {s.side === "flat" ? (
                <p className="text-xs text-text-muted">Flat signal — no position, no levels.</p>
              ) : (
                <>
                  <LevelRow label="Entry" value={fmtPrice(s.entry)} />
                  <LevelRow label="Stop loss" value={fmtPrice(s.stop_loss)} sub={pctFrom(s.entry, s.stop_loss)} cls="text-short" />
                  {s.take_profit.map((tp, i) => {
                    const r = riskReward(s, i);
                    return (
                      <LevelRow key={i} label={s.take_profit.length > 1 ? `Target ${i + 1}` : "Target"} value={fmtPrice(tp)}
                        sub={`${pctFrom(s.entry, tp)}${r !== null ? ` · ${r.toFixed(2)}R` : ""}`} cls="text-long" />
                    );
                  })}
                  <div className="mt-3 flex items-center justify-between rounded-lg bg-bg/60 px-3 py-2">
                    <span className="text-xs text-text-muted">Reward : Risk (to T1)</span>
                    <span className="num text-lg font-semibold">{rr === null ? "—" : `${rr.toFixed(2)} : 1`}</span>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          <Card className="bg-surface">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-sm">{s.confidence_calibrated ? "Confidence" : "Model score"}</CardTitle>
              <CalibrationBadge s={s} />
            </CardHeader>
            <CardContent>
              <ConfidenceGauge value={s.confidence} calibrated={s.confidence_calibrated} />
              <p className="mt-2 text-center text-[11px] text-text-muted">
                {s.confidence_calibrated ? (
                  <>
                    Calibrated probability
                    {s.calibration_run_id && (
                      <>
                        {" "}from backtest run{" "}
                        <Link className="num text-brand hover:underline" href={`/strategies/${encodeURIComponent(s.strategy_id)}?run=${encodeURIComponent(s.calibration_run_id)}`}>
                          {s.calibration_run_id.slice(0, 12)}
                        </Link>
                      </>
                    )}
                    ; signals can be wrong.
                  </>
                ) : (
                  "Raw 0–1 model score, not a probability — not yet calibrated against out-of-sample outcomes. Signals can be wrong."
                )}
              </p>
            </CardContent>
          </Card>

          <Card className="bg-surface">
            <CardContent className="space-y-1.5 text-xs">
              <Meta k="Strategy" v={<Link className="text-brand hover:underline" href={`/strategies/${encodeURIComponent(s.strategy_id)}`}>{s.strategy_id}</Link>} />
              <Meta k="Version" v={<span className="num">{s.strategy_version}</span>} />
              <Meta k="Bar close" v={<span className="num">{fmtUtc(s.bar_close_time)}</span>} />
              <Meta k="Generated" v={<span className="num">{fmtUtc(s.generated_at)}</span>} />
              <Meta k="Horizon" v={<span className="num">{s.horizon_bars} bars</span>} />
              <Meta k="Signal ID" v={<span className="num truncate">{s.id}</span>} />
            </CardContent>
          </Card>
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card className="bg-surface">
          <CardHeader><CardTitle className="text-sm">Rationale</CardTitle></CardHeader>
          <CardContent><p className="text-sm leading-relaxed text-text/90">{s.rationale}</p></CardContent>
        </Card>
        <Card className="bg-surface">
          <CardHeader><CardTitle className="text-sm">Features snapshot</CardTitle></CardHeader>
          <CardContent>
            {features.length === 0 ? (
              <p className="text-xs text-text-muted">No features recorded.</p>
            ) : (
              <Table>
                <TableBody>
                  {features.map(([k, v]) => (
                    <TableRow key={k} className="border-line hover:bg-transparent">
                      <TableCell className="py-1.5 text-xs text-text-muted">{k}</TableCell>
                      <TableCell className="num py-1.5 text-right text-xs">{fmtFeature(v)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      <DisclaimerCallout k="signal" className="mt-4" />
    </div>
  );
}

function ChartArea({ s }: { s: Signal }) {
  const state = useAsync(() => api.candles(s.symbol, s.timeframe, 240), [s.symbol, s.timeframe]);
  if (state.status === "loading") return <Skeleton className="h-[380px] w-full rounded-lg bg-surface-2 md:h-[440px]" />;
  if (state.status === "error")
    return (
      <EmptyState icon={WifiOff} title="Couldn't load candles" className="h-[380px] md:h-[440px]">
        {state.error.message}
      </EmptyState>
    );
  if (state.data.length === 0)
    return (
      <EmptyState icon={CandlestickChart} title="No candle data available" className="h-[380px] md:h-[440px]">
        No stored bars for {displaySymbol(s.symbol, s.asset_class)} {s.timeframe} yet (GET /v1/candles returned no data).
      </EmptyState>
    );
  return (
    <div className="relative">
      {config.useMock && <MockBadge className="absolute top-2 left-2 z-10" />}
      <PriceChart candles={state.data} signal={s} showLastBar />
    </div>
  );
}

function CalibrationBadge({ s }: { s: Signal }) {
  const body = s.confidence_calibrated ? "Calibrated" : "Uncalibrated";
  const cls = s.confidence_calibrated ? "border-long/25 bg-long/10 text-long" : "border-line bg-surface-2 text-text-muted";
  const tip = s.confidence_calibrated
    ? `Confidence calibrated on backtest run ${s.calibration_run_id ?? "(run id not provided)"}`
    : "Confidence is a raw model score until calibrated on out-of-sample results";
  const pill = <span className={cn("rounded-md border px-1.5 py-0.5 text-[11px]", cls)}>{body}</span>;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {s.confidence_calibrated && s.calibration_run_id ? (
          <Link href={`/strategies/${encodeURIComponent(s.strategy_id)}?run=${encodeURIComponent(s.calibration_run_id)}`}>{pill}</Link>
        ) : (
          <button type="button">{pill}</button>
        )}
      </TooltipTrigger>
      <TooltipContent>{tip}</TooltipContent>
    </Tooltip>
  );
}

function fmtFeature(v: unknown) {
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  if (typeof v === "boolean") return v ? "true" : "false";
  if (v === null || v === undefined) return "—";
  return typeof v === "string" ? v : JSON.stringify(v);
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="hidden items-center gap-1.5 sm:inline-flex">
      <span className="h-2 w-2 rounded-sm" style={{ background: color }} />
      {label}
    </span>
  );
}

function LevelRow({ label, value, sub, cls }: { label: string; value: string; sub?: string; cls?: string }) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="text-xs text-text-muted">{label}</span>
      <span className="text-right">
        <span className={cn("num text-sm font-medium", cls)}>{value}</span>
        {sub && <span className="num ml-2 text-[11px] text-text-muted">{sub}</span>}
      </span>
    </div>
  );
}

function Meta({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-text-muted">{k}</span>
      <span className="min-w-0 truncate text-right">{v}</span>
    </div>
  );
}
