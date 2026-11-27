import { NextRequest, NextResponse } from "next/server";
import { backendHeaders, serverEnv } from "@/lib/server-env";

/**
 * Same-origin proxy for API v1 REST calls: /api/v1/* -> ${SIGNAL_API_URL}/v1/*.
 * Forwards the caller's `Authorization: Bearer <JWT>` (data scoping comes from that or the API key),
 * and adds the server-only `X-API-Key` (SIGNAL_API_KEY) when no Bearer token is present.
 * The request Host is NOT forwarded and plays no part in data scoping.
 */
export const dynamic = "force-dynamic";

const ALLOWED = /^(signals(\/[^/]+)?|strategies|backtests(\/[^/]+)?|candles|health|stream\/token)$/;

async function forward(req: NextRequest, path: string[], method: "GET" | "POST") {
  const p = path.map(encodeURIComponent).join("/");
  if (!ALLOWED.test(path.join("/"))) return NextResponse.json({ detail: "Not found" }, { status: 404 });
  const auth = req.headers.get("authorization");
  const headers = backendHeaders(auth ? { Authorization: auth } : undefined);
  const body = method === "POST" ? await req.text() : undefined;
  if (body) headers.set("Content-Type", req.headers.get("content-type") ?? "application/json");
  try {
    const res = await fetch(`${serverEnv.apiUrl}/v1/${p}${req.nextUrl.search}`, { method, headers, body, cache: "no-store" });
    return new NextResponse(await res.arrayBuffer(), {
      status: res.status,
      headers: { "Content-Type": res.headers.get("content-type") ?? "application/json", "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json({ detail: "Upstream API unreachable" }, { status: 502 });
  }
}

export async function GET(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return forward(req, (await ctx.params).path, "GET");
}

export async function POST(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return forward(req, (await ctx.params).path, "POST");
}
