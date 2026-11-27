import { config } from "@/lib/config";
import { visibleSignals } from "@/lib/signal-visibility";
import { normalizeSignal, type ApiSignal, type BacktestIndexItem, type BacktestIndexPage, type Page, type SignalPage, type StrategyPage, type BacktestReport, type Candle, type Health, type Signal, type Strategy, type Timeframe } from "@/lib/types/signal";

/** Typed client for API v1. In mock mode (NEXT_PUBLIC_USE_MOCK=1) every call is served from lib/mock. */

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

const TOKEN_KEY = "signal_app.jwt";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${config.restBase}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText} on ${path}`);
  return (await res.json()) as T;
}

export interface SignalQuery {
  asset_class?: string;
  timeframe?: string;
  side?: string;
  status?: string;
  symbol?: string;
  limit?: number;
  cursor?: string;
}


function qs(params: object): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "" && v !== "all");
  return entries.length ? `?${new URLSearchParams(entries.map(([k, v]) => [k, String(v)]))}` : "";
}

async function mock() {
  return import("@/lib/mock");
}

export const api = {
  async health(): Promise<Health> {
    if (config.useMock) return { status: "mock" };
    return request<Health>("/v1/health");
  },
  /** One page of signals (?cursor= paging). */
  async signals(q: SignalQuery = {}): Promise<Page<Signal>> {
    if (config.useMock) return (await mock()).mockSignals(q);
    const page = await request<SignalPage>(`/v1/signals${qs(q)}`);
    return { items: visibleSignals(page.items.map(normalizeSignal)), next_cursor: page.next_cursor ?? null };
  },
  async signal(id: string): Promise<Signal | null> {
    if (config.useMock) return (await mock()).mockSignal(id);
    try {
      return normalizeSignal(await request<ApiSignal>(`/v1/signals/${encodeURIComponent(id)}`));
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }
  },
  /** All strategies (follows next_cursor until exhausted). */
  async strategies(): Promise<Strategy[]> {
    if (config.useMock) return (await mock()).mockStrategies();
    const out: Strategy[] = [];
    let cursor: string | null | undefined = undefined;
    for (let guard = 0; guard < 50; guard++) {
      const page: StrategyPage = await request<StrategyPage>(`/v1/strategies${qs({ cursor })}`);
      out.push(...(page.items as Strategy[]));
      cursor = page.next_cursor;
      if (!cursor) break;
    }
    return out;
  },
  /**
   * Backtests are NEVER mocked: performance comes from real runs only.
   * /v1/backtests returns QA-approved runs only (404 otherwise => null).
   */
  async backtest(runId: string): Promise<BacktestReport | null> {
    if (config.useMock) return null;
    try {
      return await request<BacktestReport>(`/v1/backtests/${encodeURIComponent(runId)}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }
  },
  /**
   * Per-market backtest index: GET /v1/backtests?strategy_id=&version= -> {items, next_cursor?}.
   * Never mocked. Full reports still come from backtest(run_id).
   */
  async backtestIndex(strategy_id: string, version: string): Promise<BacktestIndexItem[]> {
    if (config.useMock) return [];
    const out: BacktestIndexItem[] = [];
    let cursor: string | null | undefined = undefined;
    try {
      for (let guard = 0; guard < 50; guard++) {
        const page: BacktestIndexPage = await request<BacktestIndexPage>(`/v1/backtests${qs({ strategy_id, version, cursor })}`);
        out.push(...page.items);
        cursor = page.next_cursor;
        if (!cursor) break;
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return [];
      throw e;
    }
    return out;
  },
  /**
   * GET /v1/candles?symbol&timeframe&limit — bare array, served from Parquet.
   * 404 => no data => []. Mock candles ONLY when NEXT_PUBLIC_USE_MOCK=1.
   */
  async candles(symbol: string, timeframe: Timeframe, limit = 300): Promise<Candle[]> {
    if (config.useMock) return (await mock()).mockCandles(symbol, timeframe, limit);
    try {
      return await request<Candle[]>(`/v1/candles${qs({ symbol, timeframe, limit })}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return [];
      throw e;
    }
  },

};
