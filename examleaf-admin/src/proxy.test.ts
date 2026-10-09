// @vitest-environment node
// The proxy: Django's paths pass through, every page is the person's own (private, no-store) with a nonce CSP that no
// frame may embed, and while Django's health check fails a page is a 503, never a sign-out; a failed or hung check
// never wedges its 5-second cache. The check names the console's host as every server-side call does: with DEBUG=0
// Django refuses its internal one (web:8000).
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
    // the moment the proxy took the request: the start of its one deadline for Django (lib/api/server.ts)
    expect(Number(page.headers.get("x-middleware-request-x-request-start"))).toBeGreaterThan(0);
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

  it("never wedges: a failed check and a hung one (given up after 2 s) are each asked again 5 s later", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    const probe = new AbortController(); // the check's AbortSignal.timeout(2000), fired by hand
    const timeout = vi.spyOn(AbortSignal, "timeout").mockReturnValue(probe.signal);
    try {
      django.mockRejectedValueOnce(new TypeError("fetch failed"));
      expect((await ask("/inbox/")).status).toBe(503); // the rejected check

      vi.setSystemTime(Date.now() + 5001);
      django.mockImplementationOnce(
        (_url, init) =>
          new Promise((_, reject) => init?.signal?.addEventListener("abort", () => reject(init.signal?.reason))),
      );
      const hanging = ask("/inbox/");
      await vi.waitFor(() => expect(django).toHaveBeenCalledTimes(2)); // asked again: `checking` was cleared
      expect(timeout).toHaveBeenLastCalledWith(2000);
      probe.abort(new DOMException("The operation timed out.", "TimeoutError"));
      expect((await hanging).status).toBe(503); // the hung check, given up

      vi.setSystemTime(Date.now() + 5001);
      django.mockResolvedValueOnce(new Response("{}"));
      expect((await ask("/inbox/")).headers.get("x-middleware-next")).toBe("1"); // Django is back
      expect(django).toHaveBeenCalledTimes(3);
    } finally {
      timeout.mockRestore();
      vi.useRealTimers();
    }
  });
});
