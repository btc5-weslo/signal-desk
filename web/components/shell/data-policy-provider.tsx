"use client";

import { createContext, useContext, type ReactNode } from "react";

/** Platform licensed candle sources, supplied only by the root layout from GET /v1/tenant/config. */
const Ctx = createContext<readonly string[]>([]);

export function DataPolicyProvider({ licensed, children }: { licensed: readonly string[]; children: ReactNode }) {
  return <Ctx.Provider value={licensed}>{children}</Ctx.Provider>;
}

export const useLicensedDataSources = () => useContext(Ctx);
