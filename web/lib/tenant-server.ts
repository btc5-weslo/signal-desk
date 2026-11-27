import "server-only";
import { cache } from "react";
import { fetchTenantConfig } from "@/lib/data-policy-server";
import { licensedFromTenantConfig } from "@/lib/data-provenance";
import { defaultTenant, tenantFromConfig, type TenantTheme } from "@/lib/tenant";

/** Tenant branding from GET /v1/tenant/config; neutral default on failure or in mock mode. */
export const getTenantForRequest = cache(async (): Promise<TenantTheme> => {
  const cfg = await fetchTenantConfig();
  return cfg ? tenantFromConfig(cfg) : defaultTenant;
});

/**
 * Platform licensed candle sources: ONLY GET /v1/tenant/config `licensed_data_sources`.
 * No default, env, or tenant-theme fallback: on failure / mock the list is empty (nothing licensed).
 */
export const getLicensedDataSources = cache(async (): Promise<string[]> => licensedFromTenantConfig(await fetchTenantConfig()));
