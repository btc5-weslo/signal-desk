"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { CandlestickChart, WifiOff } from "lucide-react";
import { api } from "@/lib/api/client";
import { config } from "@/lib/config";
import { useAsync } from "@/hooks/use-async";
import { MockBadge, SideBadge, TfBadge } from "@/components/common/badges";
import { EmptyState } from "@/components/common/empty-state";
import { Segmented } from "@/components/common/segmented";
import { DisclaimerCallout } from "@/components/common/disclaimer";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { displaySymbol, fmtPrice, fmtUtc } from "@/lib/format";
import { TIMEFRAMES, type Timeframe } from "@/lib/types/signal";

const PriceChart = dynamic(() => import("@/components/signals/price-chart").then((m) => m.PriceChart), {
  ssr: false,
  loading: () => <Skeleton className="h-[380px] w-full rounded-lg bg-surface-2 md:h-[440px]" />,
});

/** Candles-only market chart (no signal overlay). Real /v1/candles data; mock candles only under the mock flag. */
export function MarketView({ symbol, timeframe }: { symbol: string; timeframe: Timeframe }) {
  const router = useRouter();
  const candles = useAsync(() => api.candles(symbol, timeframe, 500), [symbol, timeframe]);
  const signals = useAsync(() => api.signals({ symbol, limit: 20 }).then((p) => p.items), [symbol]);
  const last = candles.status === "ok" ? candles.data[candles.data.length - 1] : undefined;

  return (
    <div className="mx-auto max-w-[1400px] space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-text-muted">Market</div>
          <div className="flex items-center gap-3">
            <h1 className="num text-2xl font-semibold tracking-tight">{displaySymbol(symbol)}</h1>
            {last && <span className="num text-lg text-text-muted">{fmtPrice(last.close)}</span>}
          </div>
          {last && <div className="num mt-0.5 text-[11px] text-text-muted">Last bar {fmtUtc(last.time)}</div>}
        </div>
        <Segmented
          label="TF"
          value={timeframe}
          onChange={(v) => router.replace(`/markets/${encodeURIComponent(symbol)}?tf=${v}`)}
          options={TIMEFRAMES.map((t) => ({ value: t, label: t }))}
        />
      </div>

      <Card className="gap-3 bg-surface py-3">
        <CardHeader className="flex flex-row items-center justify-between px-4">
          <CardTitle className="text-sm">Chart · {timeframe}</CardTitle>
          {config.useMock && <MockBadge />}
        </CardHeader>
        <CardContent className="px-3">
          {candles.status === "loading" && <Skeleton className="h-[380px] w-full rounded-lg bg-surface-2 md:h-[440px]" />}
          {candles.status === "error" && (
            <EmptyState icon={WifiOff} title="Couldn't load candles" className="h-[380px] md:h-[440px]">{candles.error.message}</EmptyState>
          )}
          {candles.status === "ok" && candles.data.length === 0 && (
            <EmptyState icon={CandlestickChart} title="No candle data available" className="h-[380px] md:h-[440px]">
              No stored bars for {displaySymbol(symbol)} {timeframe} yet.
            </EmptyState>
          )}
          {candles.status === "ok" && candles.data.length > 0 && <PriceChart candles={candles.data} timeframe={timeframe} symbol={symbol} />}
        </CardContent>
      </Card>

      <Card className="bg-surface">
        <CardHeader><CardTitle className="text-sm">Signals for {displaySymbol(symbol)}</CardTitle></CardHeader>
        <CardContent>
          {signals.status === "ok" && signals.data.length > 0 ? (
            <ul className="divide-y divide-line">
              {signals.data.map((s) => (
                <li key={s.id}>
                  <Link href={`/signals/${encodeURIComponent(s.id)}`} className="flex items-center gap-2 py-2 text-xs hover:text-text">
                    <SideBadge side={s.side} />
                    <TfBadge tf={s.timeframe} />
                    {s.is_mock && <MockBadge />}
                    <span className="num ml-auto text-text-muted">{fmtUtc(s.generated_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-text-muted">{signals.status === "loading" ? "Loading…" : "No signals for this market yet."}</p>
          )}
        </CardContent>
      </Card>

      <DisclaimerCallout k="signal" />
    </div>
  );
}
