/* eslint-disable @next/next/no-img-element */
import type { TenantTheme } from "@/lib/tenant";

export function TenantLogo({ tenant, size = 28 }: { tenant: TenantTheme; size?: number }) {
  if (tenant.logoUrl)
    return <img src={tenant.logoUrl} alt={`${tenant.name} logo`} width={size} height={size} className="shrink-0 rounded-md" />;
  return (
    <span
      className="grid shrink-0 place-items-center rounded-md bg-brand font-semibold text-brand-text"
      style={{ width: size, height: size, fontSize: size * 0.45 }}
    >
      {tenant.name.slice(0, 1)}
    </span>
  );
}
