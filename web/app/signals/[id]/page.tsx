import { SignalDetail } from "@/components/signals/signal-detail";

export default async function SignalPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <SignalDetail id={decodeURIComponent(id)} />;
}
