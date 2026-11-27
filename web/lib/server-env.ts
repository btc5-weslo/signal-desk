import "server-only";

/**
 * Server-only settings. NEVER prefix these with NEXT_PUBLIC_ — they must not reach the browser bundle.
 * - SIGNAL_API_URL: backend base for server-side calls (defaults to NEXT_PUBLIC_API_URL)
 * - SIGNAL_API_KEY: dev/service API key sent as `X-API-Key` by the proxy and stream-auth routes
 */
export const serverEnv = {
  apiUrl: (process.env.SIGNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, ""),
  apiKey: process.env.SIGNAL_API_KEY || undefined,
};

export function backendHeaders(extra?: HeadersInit): Headers {
  const h = new Headers(extra);
  h.set("Accept", "application/json");
  if (serverEnv.apiKey && !h.has("Authorization")) h.set("X-API-Key", serverEnv.apiKey);
  return h;
}
