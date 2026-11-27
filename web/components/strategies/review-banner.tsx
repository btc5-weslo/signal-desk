import { AlertTriangle } from "lucide-react";
import { flagLabel, type ReviewState } from "@/lib/backtest";

export function ReviewBanner({ state }: { state: ReviewState }) {
  if (state.kind === "approved") return null;
  return (
    <div className="rounded-lg border border-warning/35 bg-warning/10 p-3 text-xs text-warning">
      <div className="flex items-center gap-2 font-medium">
        <AlertTriangle className="size-3.5" /> Under review — headline metrics hidden pending leakage review
      </div>
      {state.flags.length > 0 && (
        <ul className="mt-2 ml-5 list-disc space-y-0.5 text-warning/90">
          {state.flags.map((f) => <li key={f}>{flagLabel(f)} <span className="num text-warning/60">({f})</span></li>)}
        </ul>
      )}
    </div>
  );
}

export function ReviewPill({ state }: { state: ReviewState }) {
  if (state.kind === "approved") return null;
  return (
    <span className="inline-flex items-center gap-1 rounded-md border border-warning/35 bg-warning/10 px-1.5 py-0.5 text-[11px] font-medium text-warning">
      <AlertTriangle className="size-3" /> Under review
    </span>
  );
}
