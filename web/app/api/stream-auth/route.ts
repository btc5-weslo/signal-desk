import { NextResponse } from "next/server";
import { backendHeaders, serverEnv } from "@/lib/server-env";
import type { StreamToken } from "@/lib/types/signal";

/**
 * Dev/service fallback for WS first-message auth when the user has no JWT:
 * exchanges the server-only SIGNAL_API_KEY for a short-lived stream token via backend
 * POST /v1/stream/token -> {token, expires_at}. The browser then sends {type:"auth", token}
 * as the first WS frame (what backend _authenticate_ws accepts). The API key never leaves the server.
 *
 * If the backend doesn't have the route yet (404/405) or anything fails, respond 503 with
 * {available:false}; the client then shows "Sign in required" and does not open a socket.
 */
export const dynamic = "force-dynamic";

const unavailable = (reason: string, status = 503) =>
  NextResponse.json({ available: false, reason }, { status, headers: { "Cache-Control": "no-store" } });

export async function POST() {
  if (!serverEnv.apiKey) return unavailable("no_server_credentials", 401);
  let res: Response;
  try {
    res = await fetch(`${serverEnv.apiUrl}/v1/stream/token`, { method: "POST", headers: backendHeaders(), cache: "no-store" });
  } catch {
    return unavailable("upstream_unreachable", 502);
  }
  if (res.status === 404 || res.status === 405) return unavailable("stream_token_route_missing");
  if (!res.ok) return unavailable(`upstream_${res.status}`, res.status === 401 || res.status === 403 ? 401 : 502);
  try {
    const body = (await res.json()) as Partial<StreamToken>;
    if (typeof body.token !== "string" || !body.token) return unavailable("malformed_token_response", 502);
    // 60 s, single-use: the browser must use it immediately as the WS first message.
    return NextResponse.json(
      { available: true, token: body.token, expires_at: typeof body.expires_at === "string" ? body.expires_at : null },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch {
    return unavailable("malformed_token_response", 502);
  }
}
