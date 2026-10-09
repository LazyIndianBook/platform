// @vitest-environment node
// The health check: 200 while the process serves, 503 from SIGTERM on (the handler is called by hand: no signal is sent
// to the test's own process). Never a call to Django.
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => vi.restoreAllMocks());

describe("/api/health/", () => {
  it("answers ok, then 503 once SIGTERM came", async () => {
    vi.resetModules();
    const once = vi.spyOn(process, "once").mockImplementation(() => process); // no real listener in the test runner
    const django = vi.fn();
    vi.stubGlobal("fetch", django);
    const { GET } = await import("./route");
    const ok = GET();
    expect(ok.status).toBe(200);
    expect(ok.headers.get("Cache-Control")).toBe("no-store");
    const sigterm = once.mock.calls.find(([event]) => event === "SIGTERM")?.[1] as () => void;
    sigterm();
    const going = GET();
    expect(going.status).toBe(503);
    expect(await going.json()).toEqual({ status: "draining" });
    expect(django).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
