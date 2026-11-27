import { FlaskConical } from "lucide-react";
import { config } from "@/lib/config";

export function MockBanner() {
  if (!config.useMock) return null;
  return (
    <div className="flex items-center justify-center gap-2 border-b border-warning/30 bg-warning/10 px-4 py-1.5 text-[11px] font-medium text-warning">
      <FlaskConical className="size-3.5" />
      MOCK DATA MODE — signals, candles and stream are simulated placeholders (NEXT_PUBLIC_USE_MOCK=1). No performance data is shown.
    </div>
  );
}
