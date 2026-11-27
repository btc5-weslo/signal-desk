import { cn } from "@/lib/utils";

function tone(c: number) {
  return c >= 0.65 ? "var(--long)" : c >= 0.55 ? "var(--brand)" : "var(--text-muted)";
}

const clamp = (v: number) => Math.max(0, Math.min(1, v));

/**
 * QA rule: only a CALIBRATED confidence may be shown as a percentage.
 * Uncalibrated values are shown as a 0–1 "Model score" (e.g. 0.68), never with %.
 */
export function fmtConfidence(value: number, calibrated: boolean): string {
  const v = clamp(value);
  return calibrated ? `${Math.round(v * 100)}%` : v.toFixed(2);
}

export function confidenceLabel(calibrated: boolean) {
  return calibrated ? "Confidence" : "Model score";
}

/** Compact bar meter for feeds/tables. */
export function ConfidenceMeter({ value, calibrated = false, className }: { value: number; calibrated?: boolean; className?: string }) {
  const v = clamp(value);
  return (
    <div
      className={cn("flex items-center gap-2", className)}
      title={calibrated ? `Calibrated confidence ${fmtConfidence(v, true)}` : `Model score ${fmtConfidence(v, false)} (uncalibrated, not a probability)`}
    >
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-2">
        <div className="h-full rounded-full" style={{ width: `${v * 100}%`, background: tone(v) }} />
      </div>
      <span className="num text-xs text-text-muted">{fmtConfidence(v, calibrated)}</span>
    </div>
  );
}

/** Semicircle gauge for signal detail. */
export function ConfidenceGauge({ value, calibrated = false }: { value: number; calibrated?: boolean }) {
  const v = clamp(value);
  const len = Math.PI * 52;
  return (
    <div className="relative mx-auto w-[150px]">
      <svg viewBox="0 0 128 72" className="w-full">
        <path d="M12 66 A52 52 0 0 1 116 66" fill="none" stroke="var(--surface-2)" strokeWidth="10" strokeLinecap="round" />
        <path d="M12 66 A52 52 0 0 1 116 66" fill="none" stroke={tone(v)} strokeWidth="10" strokeLinecap="round" strokeDasharray={`${len * v} ${len}`} />
      </svg>
      <div className="absolute inset-x-0 bottom-0 text-center">
        <div className="num text-2xl font-semibold">{fmtConfidence(v, calibrated)}</div>
        <div className="text-[10px] uppercase tracking-wider text-text-muted">{confidenceLabel(calibrated)}</div>
      </div>
    </div>
  );
}
