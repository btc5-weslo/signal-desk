import { DashboardStats } from "@/components/signals/dashboard-stats";
import { SignalFeed } from "@/components/signals/signal-feed";
import { PageHeader } from "@/components/common/page-header";

export default function DashboardPage() {
  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader title="Dashboard" description="Live signals across crypto, US equities and FX majors." />
      <DashboardStats />
      <div className="mt-6">
        <h2 className="mb-3 text-sm font-medium text-text-muted">Live signal feed</h2>
        <SignalFeed pageSize={12} paged={false} />
      </div>
    </div>
  );
}
