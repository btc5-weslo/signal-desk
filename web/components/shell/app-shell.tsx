"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { Menu, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { MockBanner } from "@/components/common/mock-banner";
import { DisclaimerFooter } from "@/components/common/disclaimer";
import { cn } from "@/lib/utils";
import type { TenantTheme } from "@/lib/tenant";
import { ConnectionPill } from "./connection-pill";
import { TenantLogo } from "./tenant-logo";
import { NAV, isActive } from "./nav";

const COLLAPSE_KEY = "signal_app.sidebar_collapsed";

function NavLinks({ collapsed, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav className="flex flex-col gap-0.5">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = isActive(pathname, href);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            title={collapsed ? label : undefined}
            className={cn(
              "group flex h-9 items-center gap-2.5 rounded-md px-2.5 text-sm transition-colors",
              active ? "bg-surface-2 text-text" : "text-text-muted hover:bg-surface-2/60 hover:text-text",
              collapsed && "justify-center px-0",
            )}
          >
            <Icon className={cn("size-4 shrink-0", active && "text-brand")} />
            {!collapsed && <span>{label}</span>}
          </Link>
        );
      })}
    </nav>
  );
}

export function AppShell({ tenant, children }: { tenant: TenantTheme; children: ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setCollapsed(window.localStorage.getItem(COLLAPSE_KEY) === "1");
  }, []);
  const toggle = () => {
    setCollapsed((c) => {
      window.localStorage.setItem(COLLAPSE_KEY, c ? "0" : "1");
      return !c;
    });
  };

  if (pathname.startsWith("/welcome")) return <>{children}</>;

  return (
    <div className="flex min-h-dvh">
      {/* Desktop sidebar: outer column stretches to full page height (bg + border reach the bottom);
          inner panel is h-screen sticky so nav stays in view while scrolling. */}
      <aside
        className={cn(
          "hidden shrink-0 self-stretch border-r border-line bg-surface transition-[width] duration-200 md:block",
          collapsed ? "w-[60px]" : "w-[224px]",
        )}
      >
        <div className="sticky top-0 flex h-screen flex-col">
          <div className={cn("flex h-14 items-center gap-2.5 border-b border-line px-3.5", collapsed && "justify-center px-0")}>
            <TenantLogo tenant={tenant} size={26} />
            {!collapsed && <span className="truncate text-sm font-semibold tracking-tight">{tenant.name}</span>}
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            <NavLinks collapsed={collapsed} />
          </div>
          <div className="border-t border-line p-2">
            <Button variant="ghost" size="sm" onClick={toggle} className="w-full justify-center text-text-muted" aria-label="Toggle sidebar">
              {collapsed ? <PanelLeftOpen className="size-4" /> : <><PanelLeftClose className="size-4" /> <span className="ml-1 text-xs">Collapse</span></>}
            </Button>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <MockBanner />
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-bg/85 px-4 backdrop-blur md:px-6">
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open menu">
                <Menu className="size-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-[260px] border-line bg-surface p-3">
              <SheetTitle className="mb-3 flex items-center gap-2 px-1 pt-1">
                <TenantLogo tenant={tenant} size={24} /> {tenant.name}
              </SheetTitle>
              <NavLinks onNavigate={() => setOpen(false)} />
            </SheetContent>
          </Sheet>
          <div className="flex items-center gap-2 md:hidden">
            <TenantLogo tenant={tenant} size={22} />
            <span className="text-sm font-semibold">{tenant.name}</span>
          </div>
          {tenant.tagline && <div className="hidden text-xs text-text-muted md:block">{tenant.tagline}</div>}
          <div className="ml-auto flex items-center gap-2">
            <ConnectionPill />
          </div>
        </header>
        <main className="surface-glow flex-1 px-4 pt-5 pb-24 md:px-6 md:pb-8">{children}</main>
        <div className="pb-16 md:pb-0">
          <DisclaimerFooter />
        </div>
      </div>

      {/* Mobile bottom nav */}
      <nav className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t border-line bg-surface/95 backdrop-blur md:hidden">
        {NAV.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn("flex flex-col items-center gap-1 py-2 text-[10px]", isActive(pathname, href) ? "text-brand" : "text-text-muted")}
          >
            <Icon className="size-4.5" />
            {label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
