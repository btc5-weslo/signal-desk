import { describe, expect, it } from "vitest";
import { classifyStreamAuth } from "@/hooks/use-signal-stream";

describe("classifyStreamAuth", () => {
  it("returns the token on success", () => {
    expect(classifyStreamAuth(200, { available: true, token: "t" })).toEqual({ token: "t" });
  });
  it("treats 401/403 as a real sign-in problem", () => {
    expect(classifyStreamAuth(401, { available: false })).toEqual({ error: "auth" });
    expect(classifyStreamAuth(403, null)).toEqual({ error: "auth" });
  });
  it("treats a cold or unreachable backend as transient (retry, not 'Sign in required')", () => {
    for (const s of [500, 502, 503, 504]) expect(classifyStreamAuth(s, { available: false })).toEqual({ error: "transient" });
    expect(classifyStreamAuth(200, { available: false })).toEqual({ error: "transient" });
    expect(classifyStreamAuth(200, null)).toEqual({ error: "transient" });
  });
});
