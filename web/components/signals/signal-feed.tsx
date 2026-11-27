"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LayoutGrid, List, Loader2, Radio, WifiOff } from "lucide-react";
import { api } from "@/lib/api/client";
import { config } from "@/lib/config";
import { useNow } from "@/hooks/use-now";
import { useStream } from "@/components/shell/stream-provider";
import { EmptyState } from "@/components/common/empty-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { Signal } from "@/lib/types/signal";
import { SignalCard } from "./signal-card";
import { SignalTable } from "./signal-table";
import { applyFilters, DEFAULT_FILTERS, SignalFilters, type Filters } from "./signal-filters";

type Load = { status: "loading" } | { status: "error"; error: Error } | { status: "ok" };

/**
 * Signal feed: cursor-paged REST (/v1/signals {items,next_cursor}) merged with live WS signals.
 * `paged` enables infinite scroll + "Load more"; otherwise shows the first page with a link.
 */
export function SignalFeed({
  pageSize = 24,
  paged = true,
  defaultView = "cards",
  initialFilters,
}: {
  pageSize?: number;
  paged?: boolean;
  defaultView?: "cards" | "table";
  initialFilters?: Partial<Filters>;
}) {
  const [filters, setFilters] = useState<Filters>({ ...DEFAULT_FILTERS, ...initialFilters });
  const [view, setView] = useState(defaultView);
  const [items, setItems] = useState<Signal[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [loadingMore, setLoadingMore] = useState(false);
  const now = useNow();
  const { live } = useStream();
  const gen = useRef(0);

  // First page whenever filters change (filters are sent server-side and re-applied client-side).
  useEffect(() => {
    const g = ++gen.current;
    setLoad({ status: "loading" });
    api.signals({ ...filters, limit: pageSize }).then(
      (p) => {
        if (g !== gen.current) return;
        setItems(p.items);
        setCursor(p.next_cursor ?? null);
        setLoad({ status: "ok" });
      },
      (e: unknown) => g === gen.current && setLoad({ status: "error", error: e instanceof Error ? e : new Error(String(e)) }),
    );
  }, [filters, pageSize]);

  const loadMore = useCallback(async () => {
    if (!cursor || loadingMore) return;
    const g = gen.current;
    setLoadingMore(true);
    try {
      const p = await api.signals({ ...filters, limit: pageSize, cursor });
      if (g !== gen.current) return;
      setItems((prev) => [...prev, ...p.items.filter((x) => !prev.some((y) => y.id === x.id))]);
      setCursor(p.next_cursor ?? null);
    } finally {
      setLoadingMore(false);
    }
  }, [cursor, loadingMore, filters, pageSize]);

  // Infinite scroll sentinel.
  const sentinel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!paged || !sentinel.current) return;
    const io = new IntersectionObserver((e) => e[0]?.isIntersecting && loadMore(), { rootMargin: "400px" });
    io.observe(sentinel.current);
    return () => io.disconnect();
  }, [paged, loadMore]);

  const rows = useMemo(() => {
    const merged = [...live, ...items.filter((b) => !live.some((l) => l.id === b.id))];
    merged.sort((a, b) => b.generated_at.localeCompare(a.generated_at));
    const f = applyFilters(merged, filters);
    return paged ? f : f.slice(0, pageSize);
  }, [items, live, filters, paged, pageSize]);

  const liveIds = new Set(live.slice(0, 3).map((l) => l.id));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SignalFilters value={filters} onChange={setFilters} />
        <div className="inline-flex rounded-lg border border-line bg-surface p-0.5">
          {(["cards", "table"] as const).map((v) => (
            <button key={v} onClick={() => setView(v)} aria-label={`${v} view`}
              className={cn("rounded-md p-1.5", view === v ? "bg-surface-2 text-text" : "text-text-muted hover:text-text")}>
              {v === "cards" ? <LayoutGrid className="size-4" /> : <List className="size-4" />}
            </button>
          ))}
        </div>
      </div>

      {load.status === "loading" && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-[168px] rounded-xl bg-surface" />)}
        </div>
      )}
      {load.status === "error" && (
        <EmptyState icon={WifiOff} title="Can't reach the signal API">
          {load.error.message}. Check NEXT_PUBLIC_API_URL ({config.apiUrl}) or run with NEXT_PUBLIC_USE_MOCK=1 for UI work.
        </EmptyState>
      )}
      {load.status === "ok" && rows.length === 0 && (
        <EmptyState icon={Radio} title="No signals match">New signals appear here in real time as strategies emit them.</EmptyState>
      )}
      {load.status === "ok" && rows.length > 0 && (view === "cards" ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {rows.map((s) => <SignalCard key={s.id} s={s} now={now} isNew={liveIds.has(s.id)} />)}
        </div>
      ) : (
        <SignalTable rows={rows} now={now} />
      ))}

      {load.status === "ok" && rows.some((r) => !r.confidence_calibrated) && (
        <p className="text-[11px] text-text-muted">Values shown as 0–1 are uncalibrated model scores, not probabilities. Percentages appear only for calibrated confidence.</p>
      )}

      {load.status === "ok" && paged && (
        <div ref={sentinel} className="flex justify-center py-2">
          {cursor ? (
            <Button variant="secondary" size="sm" onClick={loadMore} disabled={loadingMore}>
              {loadingMore ? <><Loader2 className="size-4 animate-spin" /> Loading</> : "Load more"}
            </Button>
          ) : rows.length > 0 ? (
            <span className="text-[11px] text-text-muted">End of feed</span>
          ) : null}
        </div>
      )}
      {load.status === "ok" && !paged && (
        <div className="flex justify-center">
          <Link href="/signals" className="text-xs text-brand hover:underline">View all signals →</Link>
        </div>
      )}
    </div>
  );
}
