/** Runtime config from public env vars (inlined at build time by Next.js). Nothing secret here. */
export const config = {
  /** Backend base URL (used by the server-side proxy and to derive the WS URL). */
  apiUrl: (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, ""),
  /**
   * Browser REST calls go to the same-origin proxy (app/api/v1/[...path]) which adds server-only
   * credentials (SIGNAL_API_KEY) and forwards the user's Bearer JWT. No CORS, no secrets in the bundle.
   */
  restBase: "/api",
  /** Explicit WS URL; defaults to API URL with ws(s) scheme. */
  wsUrl: process.env.NEXT_PUBLIC_WS_URL?.replace(/\/$/, ""),
  useMock: process.env.NEXT_PUBLIC_USE_MOCK === "1",
};

export function streamUrl(): string {
  const base = config.wsUrl ?? config.apiUrl.replace(/^http/, "ws");
  return `${base}/v1/stream/signals`;
}
