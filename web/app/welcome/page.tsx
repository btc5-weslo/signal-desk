import type { Metadata } from "next";
import { Onboarding } from "@/components/onboarding/onboarding";
import { getTenantForRequest } from "@/lib/tenant-server";

export const metadata: Metadata = { title: "Welcome" };

export default async function WelcomePage() {
  return <Onboarding tenant={await getTenantForRequest()} />;
}
