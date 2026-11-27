import type { Metadata } from "next";
import { MarketView } from "@/components/markets/market-view";
import { TIMEFRAMES, type Timeframe } from "@/lib/types/signal";

export const metadata: Metadata = { title: "Market" };

export default async function MarketPage({
  params,
  searchParams,
}: {
  params: Promise<{ symbol: string }>;
  searchParams: Promise<{ tf?: string }>;
}) {
  const { symbol } = await params;
  const { tf } = await searchParams;
  const timeframe: Timeframe = TIMEFRAMES.includes(tf as Timeframe) ? (tf as Timeframe) : "1h";
  return <MarketView symbol={decodeURIComponent(symbol).toUpperCase()} timeframe={timeframe} />;
}
