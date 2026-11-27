import type { Metadata } from "next";
import { PageHeader } from "@/components/common/page-header";
import { StrategyList } from "@/components/strategies/strategy-list";

export const metadata: Metadata = { title: "Strategies" };

export default function StrategiesPage() {
  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader title="Strategies" description="Performance is shown only from QA-approved walk-forward, out-of-sample backtests — net of fees and slippage." />
      <StrategyList />
    </div>
  );
}
