"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  LineStyle,
  type AutoscaleInfo,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { AlertTriangle, Clock } from "lucide-react";
import { useNow } from "@/hooks/use-now";
import { barFreshness, delayedNote, inferAssetClass } from "@/lib/data-freshness";
import { fmtUtc } from "@/lib/format";
import { useLicensedDataSources } from "@/components/shell/data-policy-provider";
import { candleProvenance, dataCaption, PROVISIONAL_NOTE } from "@/lib/data-provenance";
import type { AssetClass, Candle, Signal } from "@/lib/types/signal";

function cssVar(name: string, fallback: string) {
  if (typeof window === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

function toTs(iso: string) {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
}

interface Zone {
  right: number;
  top: number;
  height: number;
  left: number;
  kind: "risk" | "reward";
  color: string;
}

/**
 * Candlestick chart (TradingView lightweight-charts) with entry / stop / target price lines
 * and shaded risk (entry→stop) and reward (entry→final target) zones drawn from the signal bar onward.
 */
/** Sort, de-duplicate and drop malformed bars. Gaps (e.g. dropped zero-volume bars, weekends) are left as-is:
 * the time scale is bar-indexed, so missing bars are simply absent — nothing is interpolated. */
export function sanitizeCandles(candles: Candle[]): Candle[] {
  const byTs = new Map<number, Candle>();
  for (const c of candles) {
    const t = Date.parse(c.time);
    if (!Number.isFinite(t) || ![c.open, c.high, c.low, c.close].every(Number.isFinite)) continue;
    byTs.set(Math.floor(t / 1000), c);
  }
  return [...byTs.entries()].sort((a, b) => a[0] - b[0]).map(([, c]) => c);
}

export function PriceChart({
  candles: raw,
  signal,
  timeframe,
  symbol,
  assetClass,
  showLastBar = false,
}: {
  candles: Candle[];
  signal?: Signal | null;
  timeframe?: string;
  /** Canonical symbol, used to infer the asset class for market-hours rules when `assetClass` isn't given. */
  symbol?: string;
  assetClass?: AssetClass;
  /** Render the "Last bar <UTC>" line in the caption (signal detail; the market page shows it in its header). */
  showLastBar?: boolean;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const host = useRef<HTMLDivElement>(null);
  const [zones, setZones] = useState<Zone[]>([]);

  const candles = useMemo(() => sanitizeCandles(raw), [raw]);
  const licensed = useLicensedDataSources();
  const tf = signal?.timeframe ?? timeframe;

  useEffect(() => {
    if (!host.current) return;
    const colors = {
      bg: cssVar("--surface", "#11141a"),
      text: cssVar("--text-muted", "#8b93a7"),
      line: cssVar("--line", "#232835"),
      long: cssVar("--long", "#22c55e"),
      short: cssVar("--short", "#f04452"),
      brand: cssVar("--brand", "#6d8bff"),
    };
    const ref = signal?.entry ?? candles[candles.length - 1]?.close ?? 1;
    const digits = Math.abs(ref) >= 100 ? 2 : Math.abs(ref) >= 10 ? 3 : Math.abs(ref) >= 1 ? 4 : 5;
    const chart: IChartApi = createChart(host.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: colors.bg },
        textColor: colors.text,
        fontFamily: "var(--font-mono-face), ui-monospace, monospace",
        fontSize: 11,
        attributionLogo: true,
      },
      grid: { vertLines: { color: colors.line + "66" }, horzLines: { color: colors.line + "66" } },
      rightPriceScale: { borderColor: colors.line },
      timeScale: { borderColor: colors.line, timeVisible: tf !== "1d", rightOffset: 40 },
      crosshair: { mode: 0 },
    });
    const series: ISeriesApi<"Candlestick"> = chart.addSeries(CandlestickSeries, {
      upColor: colors.long,
      downColor: colors.short,
      borderVisible: false,
      wickUpColor: colors.long,
      wickDownColor: colors.short,
      priceFormat: { type: "price", precision: digits, minMove: 10 ** -digits },
      // Keep entry/stop/all targets in view.
      autoscaleInfoProvider: (base: () => AutoscaleInfo | null) => {
        const res = base();
        const lv = signal ? [signal.entry, signal.stop_loss, ...signal.take_profit].filter((x): x is number => x != null) : [];
        if (!res || lv.length === 0) return res;
        return {
          ...res,
          priceRange: {
            minValue: Math.min(res.priceRange?.minValue ?? Infinity, ...lv),
            maxValue: Math.max(res.priceRange?.maxValue ?? -Infinity, ...lv),
          },
        };
      },
    });
    series.setData(
      candles.map((c) => ({ time: toTs(c.time), open: c.open, high: c.high, low: c.low, close: c.close })),
    );

    const entry = signal?.entry ?? null;
    const stop_loss = signal?.stop_loss ?? null;
    const tps = signal?.take_profit ?? [];
    if (entry != null) series.createPriceLine({ price: entry, color: colors.brand, lineWidth: 2, lineStyle: LineStyle.Solid, title: "Entry", axisLabelVisible: true });
    if (stop_loss != null) series.createPriceLine({ price: stop_loss, color: colors.short, lineWidth: 1, lineStyle: LineStyle.Dashed, title: "Stop", axisLabelVisible: true });
    tps.forEach((tp, i) =>
      series.createPriceLine({ price: tp, color: colors.long, lineWidth: 1, lineStyle: LineStyle.Dashed, title: tps.length > 1 ? `TP${i + 1}` : "Target", axisLabelVisible: true }),
    );

    const sigTs = signal ? toTs(signal.bar_close_time) : null;
    const markerBar = sigTs === null ? undefined : [...candles].reverse().find((c) => toTs(c.time) <= sigTs);
    if (signal && markerBar && signal.side !== "flat") {
      createSeriesMarkers(series, [{
        time: toTs(markerBar.time),
        position: signal.side === "long" ? "belowBar" : "aboveBar",
        color: signal.side === "long" ? colors.long : colors.short,
        shape: signal.side === "long" ? "arrowUp" : "arrowDown",
        text: signal.side.toUpperCase(),
      }]);
    }
    chart.timeScale().fitContent();

    // Shaded zones: recompute each frame (cheap) so they follow pan/zoom/resize.
    let raf = 0;
    let prev = "";
    const tick = () => {
      const out: Zone[] = [];
      const lastTp = tps[tps.length - 1];
      const right = chart.priceScale("right").width();
      if (entry != null && stop_loss != null && markerBar) {
        const x = chart.timeScale().timeToCoordinate(toTs(markerBar.time)) ?? 0;
        const yE = series.priceToCoordinate(entry);
        const yS = series.priceToCoordinate(stop_loss);
        const yT = lastTp != null ? series.priceToCoordinate(lastTp) : null;
        if (yE != null && yS != null) out.push({ kind: "risk", color: colors.short, right, left: Math.max(0, x), top: Math.min(yE, yS), height: Math.abs(yE - yS) });
        if (yE != null && yT != null) out.push({ kind: "reward", color: colors.long, right, left: Math.max(0, x), top: Math.min(yE, yT), height: Math.abs(yE - yT) });
      }
      const key = JSON.stringify(out);
      if (key !== prev) {
        prev = key;
        setZones(out);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(raf);
      chart.remove();
    };
  }, [candles, signal, tf]);

  const prov = candleProvenance(candles, licensed);
  const now = useNow(60_000);
  const lastBar = candles[candles.length - 1];
  const cls: AssetClass = signal?.asset_class ?? assetClass ?? inferAssetClass(signal?.symbol ?? symbol ?? "");
  const fresh = lastBar && tf ? barFreshness(lastBar.time, tf, cls, now) : null;
  return (
    <div>
    <div ref={wrap} className="relative h-[380px] w-full overflow-hidden rounded-lg md:h-[440px]">
      <div ref={host} className="absolute inset-0" />
      <div className="pointer-events-none absolute inset-0 z-[3] overflow-hidden">
        {zones.map((z) => (
          <div
            key={z.kind}
            className="absolute"
            style={{
              left: z.left,
              right: z.right,
              top: z.top,
              height: z.height,
              background: z.color + (z.kind === "risk" ? "38" : "2e"),
              borderTop: `1px solid ${z.color}66`,
              borderBottom: `1px solid ${z.color}66`,
            }}
          />
        ))}
      </div>
    </div>
    <div className="mt-1.5 flex flex-wrap items-center justify-end gap-2 text-[10.5px] text-text-muted">
      {showLastBar && lastBar && <span className="num mr-auto">Last bar {fmtUtc(lastBar.time)}</span>}
      {fresh?.delayed && (
        <span className="inline-flex items-center gap-1 rounded-md border border-warning/40 bg-warning/15 px-1.5 py-0.5 font-medium text-warning">
          <Clock className="size-3" /> {delayedNote(fresh)}
        </span>
      )}
      {prov.provisional && (
        <span className="inline-flex items-center gap-1 rounded-md border border-warning/40 bg-warning/15 px-1.5 py-0.5 font-medium text-warning">
          <AlertTriangle className="size-3" /> {PROVISIONAL_NOTE}
        </span>
      )}
      <span>{dataCaption(prov)}</span>
    </div>
    </div>
  );
}
