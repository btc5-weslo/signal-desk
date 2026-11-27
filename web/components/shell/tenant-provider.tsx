"use client";

import { createContext, useContext, type ReactNode } from "react";
import { defaultTenant, type TenantTheme } from "@/lib/tenant";

const Ctx = createContext<TenantTheme>(defaultTenant);

export function TenantProvider({ tenant, children }: { tenant: TenantTheme; children: ReactNode }) {
  return <Ctx.Provider value={tenant}>{children}</Ctx.Provider>;
}

export const useTenant = () => useContext(Ctx);
