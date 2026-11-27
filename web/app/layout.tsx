import type { Metadata } from "next";
import type { CSSProperties } from "react";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { AppShell } from "@/components/shell/app-shell";
import { StreamProvider } from "@/components/shell/stream-provider";
import { TenantProvider } from "@/components/shell/tenant-provider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { tenantCssVars } from "@/lib/tenant";
import { getLicensedDataSources, getTenantForRequest } from "@/lib/tenant-server";
import { DataPolicyProvider } from "@/components/shell/data-policy-provider";

const inter = Inter({ variable: "--font-sans-face", subsets: ["latin"] });
const mono = JetBrains_Mono({ variable: "--font-mono-face", subsets: ["latin"] });

export async function generateMetadata(): Promise<Metadata> {
  const tenant = await getTenantForRequest();
  return {
    title: { default: tenant.name, template: `%s · ${tenant.name}` },
    description: tenant.tagline,
    icons: tenant.logoUrl ? { icon: tenant.logoUrl } : undefined,
  };
}

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const [tenant, licensed] = await Promise.all([getTenantForRequest(), getLicensedDataSources()]);
  return (
    <html lang="en" className={`dark ${inter.variable} ${mono.variable}`} data-tenant={tenant.id} style={tenantCssVars(tenant) as CSSProperties}>
      <body>
        <TenantProvider tenant={tenant}>
          <DataPolicyProvider licensed={licensed}>
          <TooltipProvider>
            <StreamProvider>
              <AppShell tenant={tenant}>{children}</AppShell>
            </StreamProvider>
          </TooltipProvider>
          </DataPolicyProvider>
        </TenantProvider>
      </body>
    </html>
  );
}
