// @vitest-environment node
// The server's calls to Django give up at the request's deadline (apiSignal): a Django that takes the call and never
// answers is "can't be reached" (status 0, the page's unavailable error), never a hang and never a sign-out.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/headers", () => ({
  headers: async () => new Headers(),
  cookies: async () => ({ toString: () => "sessionid=s1", has: (name: string) => name === "sessionid" }),
}));

/** A Django that takes the call and never answers: only the call's signal ends it. */
const hung = vi.fn(
  (input: Request | string, init?: RequestInit) =>
    new Promise<Response>((_, reject) => {
      const signal = init?.signal ?? (input as Request).signal;
      signal?.addEventListener("abort", () => reject(signal.reason));
    }),
);

beforeEach(() => {
  hung.mockClear();
  vi.resetModules();
  vi.stubEnv("API_INTERNAL_TIMEOUT_MS", "40");
  vi.stubGlobal("fetch", hung);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("a Django that never answers", () => {
  it("costs each server call the request's deadline, then can't be reached: never a hang, never a sign-out", async () => {
    const { allauthGet, staffTransport } = await import("./server");
    const { getConfig } = await import("./config");
    const { getSession } = await import("./staff");
    const { UNAVAILABLE_DIGEST } = await import("./errors");
    const { requireStaff } = await import("@/lib/auth/session");
    const started = Date.now();
    await expect(getSession(await staffTransport())).rejects.toMatchObject({ status: 0, code: "unavailable" });
    await expect(requireStaff("/inbox/")).rejects.toMatchObject({ digest: UNAVAILABLE_DIGEST });
    expect(await getConfig()).toBeNull(); // the sign-in page says so
    expect(await allauthGet("/auth/session")).toEqual({ status: 0, data: null });
    expect(hung).toHaveBeenCalledTimes(4);
    expect(Date.now() - started).toBeLessThan(2000);
  });

  it("keeps the caller's own signal beside the deadline: a cancelled call is still an AbortError", async () => {
    vi.stubEnv("API_INTERNAL_TIMEOUT_MS", "60000");
    const { staffTransport } = await import("./server");
    const transport = await staffTransport();
    const controller = new AbortController();
    const call = transport.fetch!(new Request("http://web:8000/api/v1/staff/session/", { signal: controller.signal }));
    controller.abort();
    await expect(call).rejects.toMatchObject({ name: "AbortError" });
  });
});
