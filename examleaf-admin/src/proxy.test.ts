// @vitest-environment node
// The proxy: Django's paths pass through, every page is the person's own (private, no-store) with a nonce CSP that no
// frame may embed, and while Django's health check fails a page is a 503, never a sign-out. The check names the
// console's host as every server-side call does: with DEBUG=0 Django refuses its internal one (web:8000).
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FORWARDED_HEADERS } from "@/lib/site";

const django = vi.fn<typeof fetch>();
beforeEach(() => {
  django.mockReset();
  vi.resetModules();
  vi.stubGlobal("fetch", django);
});
afterEach(() => vi.unstubAllGlobals());

const ask = async (path: string) => (await import("./proxy")).proxy(new NextRequest(`http://localhost:3020${path}`));

describe("proxy", () => {
  it("answers a page with its nonce CSP, no frames, and nothing kept", async () => {
    django.mockResolvedValue(new Response("{}"));
    const page = await ask("/inbox/");
    const csp = page.headers.get("Content-Security-Policy") ?? "";
    expect(csp).toMatch(/script-src 'self' 'nonce-[^']+' 'strict-dynamic'/);
    expect(csp).toContain("frame-ancestors 'none'");
    expect(page.headers.get("Cache-Control")).toBe("private, no-cache, no-store, max-age=0, must-revalidate");
    expect(django).toHaveBeenCalledWith(
      expect.stringMatching(/\/health\/web\/$/),
      expect.objectContaining({ headers: expect.objectContaining(FORWARDED_HEADERS) }),
    );
  });

  it("answers 503 while Django's health check fails, and passes Django's own paths", async () => {
    django.mockRejectedValue(new TypeError("connect ECONNREFUSED"));
    const down = await ask("/inbox/");
    expect(down.status).toBe(503);
    expect(down.headers.get("Retry-After")).toBe("30");
    const api = await ask("/api/v1/staff/session/");
    expect(api.headers.get("x-middleware-rewrite")).toMatch(/\/api\/v1\/staff\/session\/$/);
  });
});
