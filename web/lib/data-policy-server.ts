import "server-only";
import { cache } from "react";
import { headers } from "next/headers";
import { config } from "@/lib/config";
import { serverEnv } from "@/lib/server-env";
import type { TenantConfig } from "@/lib/types/signal";

/** Revalidate tenant config every 5 minutes per host. */
const REVALIDATE_SECONDS = 300;

/**
 * Raw GET /v1/tenant/config for this request (cached per request; null on failure or in mock mode).
 * The backend resolves the tenant by host; we forward the browser-facing host as X-Forwarded-Host
 * (backend trusts it only from allowlisted proxies, see README). The host is used ONLY for branding /
 * this public config, never for data scoping (JWT / API key). No credentials are sent.
 */
export const fetchTenantConfig = cache(async (): Promise<TenantConfig | null> => {
  if (config.useMock) return null;
  try {
    const h = await headers();
    const host = h.get("x-forwarded-host") ?? h.get("host") ?? "";
    const res = await fetch(`${serverEnv.apiUrl}/v1/tenant/config`, {
      headers: { Accept: "application/json", "X-Forwarded-Host": host },
      next: { revalidate: REVALIDATE_SECONDS, tags: [`tenant:${host}`] },
      signal: AbortSignal.timeout(2500),
    });
    if (!res.ok) return null;
    return (await res.json()) as TenantConfig;
  } catch {
    return null;
  }
});
