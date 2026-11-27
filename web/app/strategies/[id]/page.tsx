import { StrategyDetail } from "@/components/strategies/strategy-detail";

export default async function StrategyPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ run?: string }>;
}) {
  const { id } = await params;
  const { run } = await searchParams;
  /* ?run=<run_id> deep-links a specific backtest run (e.g. the confidence calibration run). */
  return <StrategyDetail id={decodeURIComponent(id)} runId={run} />;
}
