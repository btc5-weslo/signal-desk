"use client";

import { Info, ShieldAlert } from "lucide-react";
import { useTenant } from "@/components/shell/tenant-provider";
import { getDisclaimer, type DisclaimerKey } from "@/lib/disclaimers";
import { cn } from "@/lib/utils";

/** Renders an approved default disclaimer (never altered by tenants). */
export function Disclaimer({ k, className }: { k: DisclaimerKey; className?: string }) {
  return <p className={className}>{getDisclaimer(k)}</p>;
}

/** Tenant-supplied extra lines — appended after the defaults, never instead of them. */
export function TenantExtraDisclaimers({ className }: { className?: string }) {
  const tenant = useTenant();
  if (tenant.extraDisclaimers.length === 0) return null;
  return (
    <>
      {tenant.extraDisclaimers.map((line, i) => (
        <p key={i} className={className}>{line}</p>
      ))}
    </>
  );
}

export function DisclaimerFooter() {
  return (
    <footer className="space-y-1 border-t border-line px-4 py-3 text-[11px] leading-relaxed text-text-muted md:px-6">
      <Disclaimer k="footer" />
      <TenantExtraDisclaimers />
    </footer>
  );
}

export function DisclaimerCallout({ k = "signal", className }: { k?: DisclaimerKey; className?: string }) {
  const Icon = k === "cryptoFxRisk" ? ShieldAlert : Info;
  return (
    <div className={cn("flex gap-2 rounded-lg border border-line bg-surface-2/60 p-3 text-xs text-text-muted", className)}>
      <Icon className="mt-0.5 size-3.5 shrink-0" />
      <Disclaimer k={k} />
    </div>
  );
}

/** Small caption placed directly under/next to any performance figure. */
export function PerformanceNote({ className }: { className?: string }) {
  return <Disclaimer k="performance" className={cn("text-[10.5px] leading-snug text-text-muted", className)} />;
}
