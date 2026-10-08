// The bot check's hold on a form (useTurnstile, through the contact form): the button waits for the token and sends
// it; a refused send waits for a new one; a check without a token after 10 s lets the form send without one and
// offers to try again. Cloudflare's widget is a stand-in that hands over a token when told.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ConfigProvider } from "@/components/providers/config-provider";
import { ContactForm } from "@/components/site/contact-form";
import { api } from "@/lib/api/client";

import { CHECKING } from "./turnstile";

const widget = vi.hoisted(() => ({ onToken: (() => undefined) as (token: string) => void }));
vi.mock("./turnstile-widget", () => ({
  Turnstile: ({ onToken }: { onToken: (token: string) => void }) => {
    widget.onToken = onToken;
    return <div data-testid="turnstile" />;
  },
}));
vi.mock("@/lib/api/client", async (original) => ({
  ...(await original<typeof import("@/lib/api/client")>()),
  api: { POST: vi.fn() },
}));

const config = { auth: { turnstile_site_key: "1x00000000000000000000AA" } } as never;
const answer = (status: number, body: unknown) =>
  Promise.resolve({
    data: status < 400 ? body : undefined,
    error: status < 400 ? undefined : body,
    response: new Response(null, { status }),
  });

async function showForm() {
  render(
    <ConfigProvider value={config}>
      <ContactForm />
    </ConfigProvider>,
  );
  fireEvent.change(screen.getByLabelText(/^Your name/), { target: { value: "A Visitor" } });
  fireEvent.change(screen.getByLabelText(/^Email address/), { target: { value: "visitor@example.com" } });
  fireEvent.change(screen.getByLabelText(/^Message/), { target: { value: "Is the book in stock?" } });
  await screen.findByTestId("turnstile"); // the widget's code has loaded
}

const sent = () =>
  (vi.mocked(api.POST).mock.calls as unknown as [string, { body: { turnstile: string } }][]).map(
    ([, init]) => init.body.turnstile,
  );

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.useRealTimers());

describe("useTurnstile", () => {
  it("holds the button until the token comes, sends it, and waits for a new one after a refusal", async () => {
    vi.mocked(api.POST)
      .mockReturnValueOnce(answer(400, { turnstile: ["Wait until the check above says it is done."] }) as never)
      .mockReturnValueOnce(answer(200, { detail: "Thank you." }) as never);
    await showForm();
    fireEvent.click(screen.getByRole("button", { name: CHECKING }));
    expect(screen.getByRole("button", { name: CHECKING })).toHaveAttribute("aria-disabled", "true");
    expect(api.POST).not.toHaveBeenCalled();

    act(() => widget.onToken("token-1"));
    fireEvent.click(screen.getByRole("button", { name: "Send the message" }));
    expect(await screen.findByRole("button", { name: CHECKING })).toHaveAttribute("aria-disabled", "true");

    await screen.findByTestId("turnstile");
    act(() => widget.onToken("token-2"));
    fireEvent.click(screen.getByRole("button", { name: "Send the message" }));
    expect(await screen.findByText("Thank you.")).toBeVisible();
    expect(sent()).toEqual(["token-1", "token-2"]);
  });

  it("after 10 s without a token, offers the check again, then sends without one", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(api.POST).mockReturnValue(
      answer(400, { turnstile: ["Wait until the check above says it is done."] }) as never,
    );
    await showForm();
    act(() => vi.advanceTimersByTime(10_000));
    fireEvent.click(screen.getByRole("button", { name: "Try it again" }));
    expect(screen.getByRole("button", { name: CHECKING })).toHaveAttribute("aria-disabled", "true");

    act(() => vi.advanceTimersByTime(10_000));
    expect(screen.getByText(/The check did not finish/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Send the message" }));
    await screen.findByText(/Wait until the check above says it is done/);
    expect(sent()).toEqual([""]);
    expect(screen.getByRole("button", { name: CHECKING })).toHaveAttribute("aria-disabled", "true"); // a new check
  });
});
