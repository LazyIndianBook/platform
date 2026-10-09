// @vitest-environment node
// register() makes an abort read its Error's stack at once, so that V8 lets the stack's frames go (instrumentation.ts
// says why: they chained every request to the next).
import { afterEach, describe, expect, it, vi } from "vitest";

import { register } from "./instrumentation";

const abort = AbortController.prototype.abort;
const prepare = Error.prepareStackTrace;
afterEach(() => {
  AbortController.prototype.abort = abort;
  Error.prepareStackTrace = prepare;
  vi.unstubAllEnvs();
});

describe("register", () => {
  it("reads the stack of the Error an AbortController is aborted with, and aborts as before", () => {
    vi.stubEnv("NEXT_RUNTIME", "nodejs");
    register();
    const formatted = vi.fn(() => "formatted");
    Error.prepareStackTrace = formatted; // V8 calls it the first time a stack is read
    const reason = new Error("This render completed successfully.");
    const controller = new AbortController();
    controller.abort(reason);
    expect(formatted).toHaveBeenCalledTimes(1);
    expect(controller.signal.aborted).toBe(true);
    expect(controller.signal.reason).toBe(reason);

    const plain = new AbortController();
    plain.abort(); // no Error given: the platform's own reason, untouched
    expect(plain.signal.reason).toMatchObject({ name: "AbortError" });
  });

  it("leaves AbortController alone outside Node's runtime", () => {
    vi.stubEnv("NEXT_RUNTIME", "edge");
    register();
    expect(AbortController.prototype.abort).toBe(abort);
  });
});
