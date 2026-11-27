import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon,
  title,
  children,
  className,
}: {
  icon: LucideIcon;
  title: string;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-line px-6 py-12 text-center", className)}>
      <div className="grid size-10 place-items-center rounded-full border border-line bg-surface-2">
        <Icon className="size-4.5 text-text-muted" />
      </div>
      <div className="text-sm font-medium">{title}</div>
      {children && <div className="max-w-md text-xs leading-relaxed text-text-muted">{children}</div>}
    </div>
  );
}
