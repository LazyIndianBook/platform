// @vitest-environment node
// The server-side API client speaks for the visitor (security review S4): every call carries their address, their
// browser and the shared secret, and a public answer is kept by URL alone, so visitors share it. A Django that does not
// answer costs a call the request's deadline, never a hang.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const incoming = new Headers();
vi.mock("next/headers", () => ({
  headers: async () => incoming,
  cookies: async () => ({ toString: () => "sessionid=s1; csrftoken=c1", has: () => true }),
}));
// Next's data cache, by the key it is given
const kept = new Map<string, unknown>();
vi.mock("next/cache", () => ({
  unstable_cache: (ask: () => Promise<unknown>, key: string[]) => async () => {
    const id = JSON.stringify(key);
    if (!kept.has(id)) kept.set(id, await ask());
    return kept.get(id);
  },
}));

const django = vi.fn(async (url: string, init?: RequestInit) => {
  void init;
  const missing = url.includes("NOPE");
  return new Response(missing ? '{"detail":"Not found."}' : '{"ok":true}', {
    status: missing ? 404 : 200,
    headers: { "Content-Type": "application/json" },
  });
});

async function load() {
  vi.stubEnv("INTERNAL_API_TOKEN", "t0ken");
  vi.resetModules();
  return import("./server");
}

/** A Django that takes the call and never answers: only the call's signal ends it. */
const hung = vi.fn(
  (input: Request | string, init?: RequestInit) =>
    new Promise<Response>((_, reject) => {
      const signal = init?.signal ?? (input as Request).signal;
      signal?.addEventListener("abort", () => reject(signal.reason));
    }),
);

function visit(address: string, browser: string) {
  incoming.set("X-Forwarded-For", address);
  incoming.set("User-Agent", browser);
}

beforeEach(() => {
  kept.clear();
  django.mockClear();
  vi.stubGlobal("fetch", django);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("the server's API calls", () => {
  it("ask for a public answer as the visitor, and keep it by URL for everyone", async () => {
    const { publicFetch } = await load();
    visit("203.0.113.5", "Phone A");
    const first = await publicFetch("papers").fetch(new Request("http://web:8000/api/v1/qr/PHY-E01/"));
    expect(await first.json()).toEqual({ ok: true });
    const sent = new Headers(django.mock.calls[0][1]?.headers);
    expect(sent.get("X-Forwarded-For")).toBe("203.0.113.5");
    expect(sent.get("User-Agent")).toBe("Phone A");
    expect(sent.get("X-Internal-Token")).toBe("t0ken");

    visit("198.51.100.7", "Phone B");
    await publicFetch("papers").fetch(new Request("http://web:8000/api/v1/qr/PHY-E01/"));
    expect(django).toHaveBeenCalledTimes(1); // another visitor, the same kept answer

    const missing = await publicFetch("papers").fetch(new Request("http://web:8000/api/v1/qr/NOPE/"));
    expect(missing.status).toBe(404);
    await publicFetch("papers").fetch(new Request("http://web:8000/api/v1/qr/NOPE/"));
    expect(django).toHaveBeenCalledTimes(3); // a 404 is never kept
  });

  it("send the visitor's cookies, address, browser and the secret on personal calls", async () => {
    const { personalFetch, anonymousFetch } = await load();
    visit("203.0.113.5", "Phone A");
    expect((await personalFetch()).headers).toEqual({
      "X-Internal-Token": "t0ken",
      "X-Forwarded-For": "203.0.113.5",
      "User-Agent": "Phone A",
      Cookie: "sessionid=s1; csrftoken=c1",
    });
    expect((await anonymousFetch()).headers).not.toHaveProperty("Cookie");
  });

  it("give up at the request's deadline when Django takes the call and never answers: status 0, never a hang", async () => {
    vi.stubEnv("API_INTERNAL_TIMEOUT_MS", "40");
    vi.stubGlobal("fetch", hung);
    const { serverApi, publicFetch, personalFetch, anonymousFetch } = await load();
    const { unwrap } = await import("./errors");
    const { allauthGet } = await import("./account");
    const { getSessionUser, requireUser } = await import("@/lib/auth/session");
    const started = Date.now();
    const unavailable = { status: 0, code: "unavailable" };
    await expect(unwrap(serverApi.GET("/api/v1/books/", publicFetch("books")))).rejects.toMatchObject(unavailable);
    await expect(unwrap(serverApi.GET("/api/v1/cart/", await personalFetch()))).rejects.toMatchObject(unavailable);
    await expect(unwrap(serverApi.GET("/api/v1/me/", await anonymousFetch()))).rejects.toMatchObject(unavailable);
    await expect(allauthGet("/account/email")).rejects.toMatchObject(unavailable);
    expect(await getSessionUser()).toBeNull(); // the header renders as for a visitor
    await expect(requireUser("/account/")).rejects.toMatchObject({ digest: "examleaf-unavailable" }); // not a log-out
    expect(hung).toHaveBeenCalledTimes(6);
    expect(Date.now() - started).toBeLessThan(2000);
    expect(kept.size).toBe(0); // nothing kept from a call that failed
  });

  it("keep the caller's own signal beside the deadline: a cancelled call is still an AbortError", async () => {
    vi.stubGlobal("fetch", hung);
    const { serverApi, personalFetch } = await load();
    const { unwrap } = await import("./errors");
    const controller = new AbortController();
    const call = unwrap(serverApi.GET("/api/v1/cart/", { ...(await personalFetch()), signal: controller.signal }));
    controller.abort();
    await expect(call).rejects.toMatchObject({ name: "AbortError" });
  });
});
