"use client";

import { Segmented } from "@/components/common/segmented";

export interface Filters {
  asset_class: string;
  timeframe: string;
  side: string;
  status: string;
}

export const DEFAULT_FILTERS: Filters = { asset_class: "all", timeframe: "all", side: "all", status: "all" };

export function SignalFilters({ value, onChange }: { value: Filters; onChange: (f: Filters) => void }) {
  const set = (k: keyof Filters) => (v: string) => onChange({ ...value, [k]: v });
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2.5">
      <Segmented label="Asset" value={value.asset_class} onChange={set("asset_class")} options={[
        { value: "all", label: "All" }, { value: "crypto", label: "Crypto" }, { value: "equity", label: "Equity" }, { value: "fx", label: "FX" },
      ]} />
      <Segmented label="TF" value={value.timeframe} onChange={set("timeframe")} options={[
        { value: "all", label: "All" }, { value: "15m", label: "15m" }, { value: "1h", label: "1h" }, { value: "4h", label: "4h" }, { value: "1d", label: "1d" },
      ]} />
      <Segmented label="Side" value={value.side} onChange={set("side")} options={[
        { value: "all", label: "All" }, { value: "long", label: "Long" }, { value: "short", label: "Short" }, { value: "flat", label: "Flat" },
      ]} />
      <Segmented label="Status" value={value.status} onChange={set("status")} options={[
        { value: "all", label: "All" }, { value: "active", label: "Active" }, { value: "hit_tp", label: "Target" }, { value: "hit_sl", label: "Stopped" }, { value: "expired", label: "Expired" }, { value: "cancelled", label: "Cancelled" },
      ]} />
    </div>
  );
}

export function applyFilters<T extends { asset_class: string; timeframe: string; side: string; status: string }>(rows: T[], f: Filters) {
  return rows.filter(
    (s) =>
      (f.asset_class === "all" || s.asset_class === f.asset_class) &&
      (f.timeframe === "all" || s.timeframe === f.timeframe) &&
      (f.side === "all" || s.side === f.side) &&
      (f.status === "all" || s.status === f.status),
  );
}
