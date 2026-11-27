import { config } from "@/lib/config";

/**
 * Real-mode guard: placeholder/mock rows that a real backend still returns (is_mock=true or
 * status "mock") must never be shown as real signals. Applied once at the API client and stream
 * boundary, plus on signal detail (which then renders a "not available" state).
 * In mock mode (NEXT_PUBLIC_USE_MOCK=1) everything passes so the MOCK badges stay visible.
 */
type MaybeMock = { is_mock?: boolean | null; status?: string | null };

export function isMockSignal(s: MaybeMock): boolean {
  return s.is_mock === true || String(s.status ?? "").toLowerCase() === "mock";
}

export function isVisibleSignal(s: MaybeMock, useMock: boolean = config.useMock): boolean {
  return useMock || !isMockSignal(s);
}

export function visibleSignals<T extends MaybeMock>(items: readonly T[], useMock: boolean = config.useMock): T[] {
  return useMock ? [...items] : items.filter((s) => !isMockSignal(s));
}
