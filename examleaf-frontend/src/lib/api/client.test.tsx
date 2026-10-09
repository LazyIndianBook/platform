// The browser's calls never wait for good: no answer in 30 s is status 0 and the busy button lets go; a change that
// timed out says it may have gone through (nothing sends it again by itself); a call the page cancelled stays an
// AbortError. The timeout is AbortSignal.timeout(30 s), fired by hand here.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LookupForm } from "@/components/shop/lookup-form";
import { auth } from "@/lib/auth/headless";

import { ANSWER_TIMEOUT_MS, api, unwrap } from "./client";
import { UNCONFIRMED_MESSAGE } from "./errors";

// an absolute base before the imports: Node's Request (in jsdom too) has no page to resolve "/api/v1/…" against
vi.hoisted(() => {
  process.env.NEXT_PUBLIC_API_BASE = "http://localhost:3000";
});
afterAll(() => {
  delete process.env.NEXT_PUBLIC_API_BASE;
});

/** Django takes the call and never answers: only the call's signal ends it (at once if it has already gone off). */
const hung = vi.fn(
  (input: Request | string, init?: RequestInit) =>
    new Promise<Response>((_, reject) => {
      const signal = init?.signal ?? (input as Request).signal;
      if (signal?.aborted) reject(signal.reason);
      signal?.addEventListener("abort", () => reject(signal.reason));
    }),
);
let timeout: AbortController;
const timedOut = () => timeout.abort(new DOMException("signal timed out", "TimeoutError"));

beforeEach(() => {
  hung.mockClear();
  timeout = new AbortController();
  vi.spyOn(AbortSignal, "timeout").mockImplementation(() => timeout.signal);
  vi.stubGlobal("fetch", hung);
  document.cookie = "csrftoken=c1"; // no CSRF cookie call first
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("a browser call with no answer", () => {
  it("fails as cannot be reached once the 30 s are up, when it only reads", async () => {
    const call = unwrap(api.GET("/api/v1/books/"));
    timedOut();
    await expect(call).rejects.toMatchObject({ status: 0, message: expect.stringContaining("cannot be reached") });
    expect(AbortSignal.timeout).toHaveBeenCalledWith(ANSWER_TIMEOUT_MS);
  });

  it("says a change may have gone through, through the API and allauth alike", async () => {
    const lookup = unwrap(api.POST("/api/v1/orders/lookup/", { body: { number: "EL-1", email: "a@b.in" } }));
    const login = auth.login({ email: "a@b.in", password: "secret-1" });
    timedOut();
    await expect(lookup).rejects.toMatchObject({ status: 0, message: UNCONFIRMED_MESSAGE });
    await expect(login).rejects.toMatchObject({ status: 0, message: UNCONFIRMED_MESSAGE });
    expect(hung).toHaveBeenCalledTimes(2); // neither sent again
  });

  it("stays an AbortError when the page cancelled it", async () => {
    const controller = new AbortController();
    const call = unwrap(api.GET("/api/v1/cart/", { signal: controller.signal }));
    // the browser's own reason, a DOMException of the page (Node's AbortController would make one of its own realm)
    controller.abort(new DOMException("signal is aborted without reason", "AbortError"));
    await expect(call).rejects.toMatchObject({ name: "AbortError" });
  });

  it("keeps the button busy and deaf to a second press, then lets go with the words when the time is up", async () => {
    const user = userEvent.setup();
    render(<LookupForm />);
    await user.type(screen.getByLabelText(/Order number/), "EL-2026-000123");
    await user.type(screen.getByLabelText(/Email address used/), "rahul@example.com");
    const send = screen.getByRole("button", { name: "Send me the link" });
    await user.click(send);
    await user.click(send); // the second press sends nothing
    expect(send).toHaveAttribute("aria-busy", "true");
    expect(hung).toHaveBeenCalledTimes(1);

    timedOut();
    expect(await screen.findByText(UNCONFIRMED_MESSAGE)).toBeInTheDocument();
    expect(send).not.toHaveAttribute("aria-busy");
    expect(hung).toHaveBeenCalledTimes(1); // never sent again by itself
  });
});
