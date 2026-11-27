"use client";

import { cn } from "@/lib/utils";
import { useStream } from "./stream-provider";

const MAP = {
  live: { label: "Live", dot: "bg-long", cls: "text-long border-long/25 bg-long/10" },
  connecting: { label: "Connecting", dot: "bg-warning animate-pulse", cls: "text-warning border-warning/25 bg-warning/10" },
  reconnecting: { label: "Reconnecting", dot: "bg-warning animate-pulse", cls: "text-warning border-warning/25 bg-warning/10" },
  offline: { label: "Offline", dot: "bg-short", cls: "text-short border-short/25 bg-short/10" },
  unauthorized: { label: "Sign in required", dot: "bg-short", cls: "text-short border-short/25 bg-short/10" },
  mock: { label: "Mock stream", dot: "bg-warning", cls: "text-warning border-warning/30 bg-warning/10" },
} as const;

export function ConnectionPill() {
  const { status, attempt } = useStream();
  const m = MAP[status];
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium", m.cls)}
      title={status === "reconnecting" ? `Signal stream reconnect attempt ${attempt}` : `Signal stream: ${m.label}`}
    >
      <span className={cn("size-1.5 rounded-full", m.dot)} />
      {m.label}
    </span>
  );
}
