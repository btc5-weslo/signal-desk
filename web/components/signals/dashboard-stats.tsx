"use client";

import { Activity, ArrowDownRight, ArrowUpRight, ShieldAlert } from "lucide-react";
import { api } from "@/lib/api/client";
import { useAsync } from "@/hooks/use-async";
import { useStream } from "@/components/shell/stream-provider";
import type { Signal } from "@/lib/types/signal";

/** Counts of current signals only (first page, up to 500) — no performance figures here by design. */
export function DashboardStats() {
  const state = useAsync(() => api.signals({ status: "active", limit: 500 }).then((p) => p.items), []);
  const { live } = useStream();
  const rows: Signal[] = state.status === "ok" ? [...live.filter((l) => l.status === "active"), ...state.data] : [];
  const uniq = Array.from(new Map(rows.map((r) => [r.id, r])).values());
  const val = (n: number) => (state.status === "ok" ? n : "—");
  const tiles = [
    { label: "Active signals", value: val(uniq.length), icon: Activity, cls: "text-brand" },
    { label: "Long", value: val(uniq.filter((s) => s.side === "long").length), icon: ArrowUpRight, cls: "text-long" },
    { label: "Short", value: val(uniq.filter((s) => s.side === "short").length), icon: ArrowDownRight, cls: "text-short" },
    { label: "Unvalidated (insufficient OOS)", value: val(uniq.filter((s) => s.validation_status === "insufficient_oos").length), icon: ShieldAlert, cls: "text-warning" },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {tiles.map((t) => (
        <div key={t.label} className="rounded-xl border border-line bg-surface p-4">
          <div className="flex items-center justify-between text-xs text-text-muted">
            {t.label}
            <t.icon className={`size-4 ${t.cls}`} />
          </div>
          <div className="num mt-2 text-2xl font-semibold">{t.value}</div>
        </div>
      ))}
    </div>
  );
}
