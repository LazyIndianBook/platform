// @vitest-environment node
// An outage is not a log-out, and never a 200 (security review S5): the session's three answers, the thrown
// "cannot be reached" error, and the proxy's 503 for the visitor's own pages while Django's health check fails. Nor a
// hang (RESILIENCE.md): a Django that never answers costs a page the request's deadline, and a failed or hung health
// check never wedges the proxy's 5-second cache.
import { redirect } from "next/navigation";
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Unavailable } from "@/components/site/unavailable";

import { UNAVAILABLE_DIGEST } from "./api/errors";

vi.mock("next/headers", () => ({
  headers: async () => new Headers(),
  cookies: async () => ({ toString: () => "sessionid=s1", has: (name: string) => name === "sessionid" }),
}));
// Next's data cache, empty: every public answer is asked for
vi.mock("next/cache", () => ({ unstable_cache: (ask: () => Promise<unknown>) => ask }));

// "hang": Django takes the call and never answers, until the call's signal gives up
const answers: (Response | Error | "hang")[] = [];
const django = vi.fn(async (_url: string, init?: RequestInit) => {
  const next = answers.shift() ?? new Response("{}");
  if (next === "hang")
    return new Promise<Response>((_, reject) =>
      init?.signal?.addEventListener("abort", () => reject(init.signal?.reason)),
    );
  if (next instanceof Error) throw next;
  return next;
});
beforeEach(() => {
  answers.length = 0;
  django.mockClear();
  vi.resetModules();
  vi.stubGlobal("fetch", django);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

const user = { display: "Rahul", has_usable_password: false };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

describe("the session during an outage", () => {
  it("is signed in, signed out, or not known: only the last throws the cannot-be-reached error", async () => {
    answers.push(json({ data: { user } }));
    expect(await (await import("./auth/session")).requireUser("/account/")).toEqual(user);

    vi.resetModules();
    answers.push(json({ status: 401 }, 401));
    await (await import("./auth/session")).requireUser("/account/");
    expect(redirect).toHaveBeenCalledWith("/account/login/?next=%2Faccount%2F"); // signed out: to log in

    for (const outage of [new TypeError("fetch failed"), json({}, 503), json({}, 500), json({}, 429)]) {
      vi.resetModules();
      answers.push(outage);
      const session = await import("./auth/session");
      await expect(session.requireUser("/account/")).rejects.toMatchObject({ digest: UNAVAILABLE_DIGEST });
      expect(await session.getSessionUser()).toBeNull(); // the header and public pages render as for a visitor
    }
  });

  it("a whole page that cannot be shown is a thrown server error, not a 200 page", () => {
    expect(() => Unavailable({ what: "The shop" })).toThrow(expect.objectContaining({ digest: UNAVAILABLE_DIGEST }));
  });

  it("a page whose calls Django never answers renders the unavailable state at the request's deadline", async () => {
    vi.stubEnv("API_INTERNAL_TIMEOUT_MS", "40");
    answers.push("hang", "hang", "hang");
    const { default: HomePage } = await import("@/app/(public)/page");
    const site = await import("@/components/site/unavailable"); // the page's own copy (modules were reset)
    const started = Date.now();
    const page = (await HomePage()) as React.ReactElement<{ what: string }>;
    expect(Date.now() - started).toBeLessThan(2000);
    expect(page.type).toBe(site.Unavailable); // which throws: error.tsx's "can't be reached" in a 500
    expect(() => site.Unavailable(page.props)).toThrow(expect.objectContaining({ digest: UNAVAILABLE_DIGEST }));
  });
});

describe("the proxy during an outage", () => {
  it("answers 503 for the visitor's own pages while Django's health check fails, and lets public pages render", async () => {
    answers.push(new TypeError("connect ECONNREFUSED"));
    const { proxy } = await import("../proxy");
    const account = await proxy(new NextRequest("http://localhost:3005/account/"));
    expect(account.status).toBe(503);
    expect(account.headers.get("Retry-After")).toBe("30");
    expect(account.headers.get("Cache-Control")).toBe("no-store");
    expect(await account.text()).toContain("ExamLeaf cannot be reached just now");
    expect((await proxy(new NextRequest("http://localhost:3005/cart/"))).status).toBe(503);
    expect(django).toHaveBeenCalledTimes(1); // one health check for both, kept 5 s
    const shop = await proxy(new NextRequest("http://localhost:3005/shop/"));
    expect(shop.status).toBe(200);
    expect(shop.headers.get("x-middleware-next")).toBe("1");
  });

  it("never wedges: a failed check and a hung one (given up after 2 s) are each asked again 5 s later", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    const probe = new AbortController(); // the probe's AbortSignal.timeout(2000), fired by hand
    const timeout = vi.spyOn(AbortSignal, "timeout").mockReturnValue(probe.signal);
    const { proxy } = await import("../proxy");
    const account = () => proxy(new NextRequest("http://localhost:3005/account/"));

    answers.push(new TypeError("fetch failed"));
    expect((await account()).status).toBe(503); // the rejected check

    vi.setSystemTime(Date.now() + 5001);
    answers.push("hang");
    const hanging = account();
    await vi.waitFor(() => expect(django).toHaveBeenCalledTimes(2)); // asked again: `checking` was cleared
    expect(timeout).toHaveBeenLastCalledWith(2000);
    probe.abort(new DOMException("The operation timed out.", "TimeoutError"));
    expect((await hanging).status).toBe(503); // the hung check, given up

    vi.setSystemTime(Date.now() + 5001);
    answers.push(json({ status: "ok" }));
    expect((await account()).headers.get("x-middleware-next")).toBe("1"); // Django is back: the page renders
    expect(django).toHaveBeenCalledTimes(3);
  });

  it("lets the visitor's own pages render while Django answers", async () => {
    answers.push(json({ status: "ok" }));
    const { proxy } = await import("../proxy");
    const before = Date.now();
    const account = await proxy(
      // a visitor's own x-request-start is replaced by the moment the proxy took the request (the deadline's start)
      new NextRequest("http://localhost:3005/account/", { headers: { "x-request-start": "0" } }),
    );
    expect(account.headers.get("x-middleware-next")).toBe("1");
    expect(account.headers.get("Content-Security-Policy")).toContain("'strict-dynamic'");
    expect(Number(account.headers.get("x-middleware-request-x-request-start"))).toBeGreaterThanOrEqual(before);
    // asked as the site, as every server-side call is: with DEBUG=0 Django refuses its internal host (web:8000)
    const { FORWARDED_HEADERS } = await import("./site");
    expect(django).toHaveBeenCalledWith(
      expect.stringMatching(/\/health\/web\/$/),
      expect.objectContaining({ headers: expect.objectContaining(FORWARDED_HEADERS) }),
    );
  });
});
