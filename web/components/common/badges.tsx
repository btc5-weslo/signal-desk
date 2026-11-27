import { ArrowDownRight, ArrowUpRight, FlaskConical, Minus, ShieldAlert, ShieldCheck, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import { STATUS_LABEL, ASSET_LABEL } from "@/lib/format";
import type { AssetClass, Side, SignalStatus, ValidationStatus } from "@/lib/types/signal";

const pill = "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium leading-none whitespace-nowrap";

export function SideBadge({ side, className }: { side: Side; className?: string }) {
  const map = {
    long: { cls: "border-long/30 bg-long/12 text-long", Icon: ArrowUpRight, label: "LONG" },
    short: { cls: "border-short/30 bg-short/12 text-short", Icon: ArrowDownRight, label: "SHORT" },
    flat: { cls: "border-line bg-surface-2 text-text-muted", Icon: Minus, label: "FLAT" },
  }[side];
  return (
    <span className={cn(pill, "font-semibold tracking-wide", map.cls, className)}>
      <map.Icon className="size-3" />
      {map.label}
    </span>
  );
}

export function StatusBadge({ status }: { status: SignalStatus }) {
  const cls = {
    active: "border-brand/30 bg-brand/10 text-brand",
    hit_tp: "border-long/25 bg-long/10 text-long",
    hit_sl: "border-short/25 bg-short/10 text-short",
    expired: "border-line bg-surface-2 text-text-muted",
    cancelled: "border-line bg-surface-2 text-text-muted line-through decoration-1",
  }[status];
  return (
    <span className={cn(pill, cls)}>
      {status === "active" && <span className="size-1.5 animate-pulse rounded-full bg-brand" />}
      {STATUS_LABEL[status]}
    </span>
  );
}

export function AssetBadge({ asset }: { asset: AssetClass }) {
  return <span className={cn(pill, "border-line bg-surface-2 text-text-muted")}>{ASSET_LABEL[asset]}</span>;
}

export function TfBadge({ tf }: { tf: string }) {
  return <span className={cn(pill, "num border-line bg-transparent text-text-muted")}>{tf}</span>;
}

export function MockBadge({ className }: { className?: string }) {
  return (
    <span className={cn(pill, "border-warning/40 bg-warning/15 font-bold tracking-wider text-warning", className)}>
      <FlaskConical className="size-3" />
      MOCK
    </span>
  );
}

export const VALIDATION_COPY: Record<ValidationStatus, { label: string; long: string }> = {
  validated: { label: "OOS validated", long: "Validated by QA-approved walk-forward out-of-sample backtest." },
  insufficient_oos: {
    label: "Unvalidated",
    long: "Unvalidated: insufficient out-of-sample history for this market/timeframe.",
  },
  pending: { label: "Validation pending", long: "No QA-approved out-of-sample backtest yet." },
};

export function ValidationBadge({ status, verbose }: { status?: ValidationStatus; verbose?: boolean }) {
  if (!status) return null;
  const v = VALIDATION_COPY[status];
  const cfg = {
    validated: { cls: "border-long/25 bg-long/10 text-long", Icon: ShieldCheck },
    insufficient_oos: { cls: "border-warning/35 bg-warning/10 text-warning", Icon: ShieldAlert },
    pending: { cls: "border-line bg-surface-2 text-text-muted", Icon: Clock },
  }[status];
  return (
    <span className={cn(pill, cfg.cls)} title={v.long}>
      <cfg.Icon className="size-3" />
      {verbose ? v.long : v.label}
    </span>
  );
}
