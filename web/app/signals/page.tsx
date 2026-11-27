import type { Metadata } from "next";
import { SignalFeed } from "@/components/signals/signal-feed";
import { PageHeader } from "@/components/common/page-header";

export const metadata: Metadata = { title: "Signals" };

export default function SignalsPage() {
  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader title="Signals" description="Every signal with its levels, calibrated confidence and lifecycle status." />
      <SignalFeed defaultView="table" pageSize={50} />
    </div>
  );
}
