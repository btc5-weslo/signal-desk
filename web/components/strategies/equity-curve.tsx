"use client";

import { useEffect, useRef } from "react";
import { AreaSeries, ColorType, createChart, type UTCTimestamp } from "lightweight-charts";

/** Cumulative equity (R or %) built from the real backtest trade list. */
export function EquityCurve({ points, unit }: { points: { time: string; value: number }[]; unit: "R" | "%" }) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!host.current) return;
    const css = getComputedStyle(document.documentElement);
    const v = (n: string, f: string) => css.getPropertyValue(n).trim() || f;
    const chart = createChart(host.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: v("--text-muted", "#8b93a7"), fontSize: 11 },
      grid: { vertLines: { visible: false }, horzLines: { color: v("--line", "#232835") + "66" } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
      localization: { priceFormatter: (p: number) => `${p.toFixed(2)}${unit}` },
    });
    const brand = v("--brand", "#6d8bff");
    const s = chart.addSeries(AreaSeries, { lineColor: brand, topColor: brand + "40", bottomColor: brand + "00", lineWidth: 2 });
    const byTs = new Map<number, number>();
    for (const p of points) byTs.set(Math.floor(new Date(p.time).getTime() / 1000), p.value);
    s.setData([...byTs.entries()].sort((a, b) => a[0] - b[0]).map(([t, value]) => ({ time: t as UTCTimestamp, value })));
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [points, unit]);
  return <div ref={host} className="h-[260px] w-full" />;
}
