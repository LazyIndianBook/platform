// @vitest-environment node
// An outage is not a log-out, and never a 200 (security review S5): the session's three answers, the thrown
// "cannot be reached" error, and the proxy's 503 for the visitor's own pages while Django's health check fails.
import { redirect } from "next/navigation";
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Unavailable } from "@/components/site/unavailable";

import { UNAVAILABLE_DIGEST } from "./api/errors";

vi.mock("next/headers", () => ({
  headers: async () => new Headers(),
  cookies: async () => ({ toString: () => "sessionid=s1", has: (name: string) => name === "sessionid" }),
}));

const answers: (Response | Error)[] = [];
const django = vi.fn(async () => {
  const next = answers.shift() ?? new Response("{}");
  if (next instanceof Error) throw next;
  return next;
});
beforeEach(() => {
  answers.length = 0;
  django.mockClear();
  vi.resetModules();
  vi.stubGlobal("fetch", django);
});
afterEach(() => vi.unstubAllGlobals());

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

  it("lets the visitor's own pages render while Django answers", async () => {
    answers.push(json({ status: "ok" }));
    const { proxy } = await import("../proxy");
    const account = await proxy(new NextRequest("http://localhost:3005/account/"));
    expect(account.headers.get("x-middleware-next")).toBe("1");
    expect(account.headers.get("Content-Security-Policy")).toContain("'strict-dynamic'");
  });
});
