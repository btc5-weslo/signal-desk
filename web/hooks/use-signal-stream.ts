"use client";

import { useEffect, useRef, useState } from "react";
import { getToken } from "@/lib/api/client";
import { config, streamUrl } from "@/lib/config";
import { normalizeSignal, type ApiSignal, type Signal } from "@/lib/types/signal";

/** Time after sending the auth frame before an un-rejected socket counts as live. */
const AUTH_GRACE_MS = 1500;

export type StreamStatus = "connecting" | "live" | "reconnecting" | "offline" | "unauthorized" | "mock";

export interface UseSignalStreamOptions {
  onSignal?: (s: Signal) => void;
  /** Initial backoff in ms (doubles each attempt, capped at maxBackoffMs, with jitter). */
  baseBackoffMs?: number;
  maxBackoffMs?: number;
  enabled?: boolean;
}

/**
 * First-message auth (locked; matches backend _authenticate_ws): connect to the plain URL, then send {type:"auth", token}
 * immediately on open — the server closes with 4401 if it doesn't arrive within 5s.
 */
export function authFrame(token: string | null): string | null {
  return token ? JSON.stringify({ type: "auth", token }) : null;
}

/** User JWT if signed in; otherwise a short-lived stream token minted server-side from SIGNAL_API_KEY (dev). */
async function resolveStreamToken(): Promise<string | null> {
  const jwt = getToken();
  if (jwt) return jwt;
  try {
    const res = await fetch("/api/stream-auth", { method: "POST", cache: "no-store" });
    if (!res.ok) return null; // incl. 503 when backend lacks POST /v1/stream/token
    const body = (await res.json()) as { available?: boolean; token?: string };
    return body.available && body.token ? body.token : null;
  } catch {
    return null;
  }
}

/**
 * Connects to WS /v1/stream/signals. Reconnects with exponential backoff + jitter.
 * Auth: first-message only — `{type:"auth", token}` sent on open (see authFrame()).
 * Close code 4401 => "unauthorized" (no retry until remount / token change).
 * Under NEXT_PUBLIC_USE_MOCK=1 a simulated stream is used instead.
 */
export function useSignalStream({
  onSignal,
  baseBackoffMs = 1000,
  maxBackoffMs = 30000,
  enabled = true,
}: UseSignalStreamOptions = {}) {
  const [status, setStatus] = useState<StreamStatus>(config.useMock ? "mock" : "connecting");
  const [lastMessageAt, setLastMessageAt] = useState<number | null>(null);
  const [attempt, setAttempt] = useState(0);
  const cb = useRef(onSignal);
  useEffect(() => {
    cb.current = onSignal;
  }, [onSignal]);

  useEffect(() => {
    if (!enabled) return;
    let disposed = false;

    if (config.useMock) {
      let stop: (() => void) | undefined;
      import("@/lib/mock").then((m) => {
        if (disposed) return;
        stop = m.startMockStream((s) => {
          setLastMessageAt(Date.now());
          cb.current?.(s);
        });
      });
      return () => {
        disposed = true;
        stop?.();
      };
    }

    let ws: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let tries = 0;
    let liveTimer: ReturnType<typeof setTimeout> | undefined;
    const markLive = () => {
      if (liveTimer) clearTimeout(liveTimer);
      liveTimer = undefined;
      if (disposed) return;
      tries = 0;
      setAttempt(0);
      setStatus("live");
    };

    const connect = async () => {
      if (disposed) return;
      setStatus(tries === 0 ? "connecting" : "reconnecting");
      const frame = authFrame(await resolveStreamToken());
      if (disposed) return;
      if (!frame) {
        // No JWT and no server-minted stream token: don't open an unauthenticated socket.
        setStatus("unauthorized");
        return;
      }
      try {
        ws = new WebSocket(streamUrl());
      } catch {
        schedule();
        return;
      }
      ws.onopen = () => {
        ws?.send(frame);
        // Backend sends no auth ack; it closes with 4401 on bad auth. Only report "live" after a
        // message arrives or the socket survives a short grace period after the auth frame.
        liveTimer = setTimeout(markLive, AUTH_GRACE_MS);
      };
      ws.onmessage = (ev) => {
        markLive();
        try {
          const data = JSON.parse(typeof ev.data === "string" ? ev.data : "");
          const items: unknown[] = Array.isArray(data) ? data : data?.type === "signal" && data.data ? [data.data] : [data];
          for (const it of items) {
            if (it && typeof it === "object" && "id" in it && "symbol" in it && "side" in it) cb.current?.(normalizeSignal(it as ApiSignal));
          }
          setLastMessageAt(Date.now());
        } catch {
          /* ignore malformed frames (e.g. heartbeats) */
        }
      };
      ws.onclose = (ev) => {
        if (liveTimer) clearTimeout(liveTimer);
        if (disposed) return;
        if (ev.code === 4401) {
          setStatus("unauthorized");
          return;
        }
        schedule();
      };
      ws.onerror = () => ws?.close();
    };

    const schedule = () => {
      tries += 1;
      setAttempt(tries);
      setStatus(tries > 6 ? "offline" : "reconnecting");
      const delay = Math.min(maxBackoffMs, baseBackoffMs * 2 ** (tries - 1)) * (0.75 + Math.random() * 0.5);
      timer = setTimeout(() => void connect(), delay);
    };

    void connect();
    return () => {
      disposed = true;
      if (timer) clearTimeout(timer);
      if (liveTimer) clearTimeout(liveTimer);
      if (ws) {
        ws.onclose = null;
        ws.close();
      }
    };
  }, [enabled, baseBackoffMs, maxBackoffMs]);

  return { status, lastMessageAt, attempt };
}
