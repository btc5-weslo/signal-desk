"use client";

import { cn } from "@/lib/utils";

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
  label?: string;
}) {
  return (
    <div className="flex min-w-0 max-w-full items-center gap-2">
      {label && <span className="text-[11px] uppercase tracking-wider text-text-muted">{label}</span>}
      <div role="radiogroup" aria-label={label} className="inline-flex max-w-full overflow-x-auto rounded-lg border border-line bg-surface p-0.5 [scrollbar-width:none]">
        {options.map((o) => (
          <button
            key={o.value}
            role="radio"
            aria-checked={value === o.value}
            onClick={() => onChange(o.value)}
            className={cn(
              "shrink-0 rounded-md px-2.5 py-1 text-xs transition-colors",
              value === o.value ? "bg-surface-2 text-text shadow-sm ring-1 ring-line" : "text-text-muted hover:text-text",
            )}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}
