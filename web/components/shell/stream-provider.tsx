"use client";

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { isVisibleSignal } from "@/lib/signal-visibility";
import { useSignalStream, type StreamStatus } from "@/hooks/use-signal-stream";
import type { Signal } from "@/lib/types/signal";

interface StreamCtx {
  status: StreamStatus;
  attempt: number;
  /** Signals received over the stream this session, newest first. */
  live: Signal[];
}

const Ctx = createContext<StreamCtx>({ status: "connecting", attempt: 0, live: [] });

export function StreamProvider({ children }: { children: ReactNode }) {
  const [live, setLive] = useState<Signal[]>([]);
  const onSignal = useCallback((s: Signal) => {
    if (!isVisibleSignal(s)) return; // real mode: never surface placeholder rows from the stream
    setLive((prev) => [s, ...prev.filter((p) => p.id !== s.id)].slice(0, 200));
  }, []);
  const { status, attempt } = useSignalStream({ onSignal });
  return <Ctx.Provider value={{ status, attempt, live }}>{children}</Ctx.Provider>;
}

export const useStream = () => useContext(Ctx);
