// "Report a mistake": closed until the reader opens it (the bot check loads only then); what it sends for a solution
// (the paper, the question, the step, the print run, the kind, the note, the address) and for a clip; the kind asked
// for before anything is sent; the limit's refusal said with the time to try again; the print run read from the
// address only when it is a print run's label.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConfigProvider } from "@/components/providers/config-provider";
import { api } from "@/lib/api/client";

import { type MistakeTarget, printingOf, ReportMistake } from "./report-mistake";

const widget = vi.hoisted(() => ({ onToken: (() => undefined) as (token: string) => void }));
vi.mock("@/components/auth/turnstile-widget", () => ({
  Turnstile: ({ onToken }: { onToken: (token: string) => void }) => {
    widget.onToken = onToken;
    return <div data-testid="turnstile" />;
  },
}));
vi.mock("@/lib/api/client", async (original) => ({
  ...(await original<typeof import("@/lib/api/client")>()),
  api: { POST: vi.fn() },
}));

const answer = (status: number, body: unknown) =>
  Promise.resolve({
    data: status < 400 ? body : undefined,
    error: status < 400 ? undefined : body,
    response: new Response(null, { status }),
  });
const SOLUTION: MistakeTarget = { kind: "solution", paper: "PHY-E01", question: "2(c)", steps: 3 };

function show(target: MistakeTarget = SOLUTION, printing = "", siteKey: string | null = null) {
  render(
    <ConfigProvider value={{ auth: { turnstile_site_key: siteKey } } as never}>
      <ReportMistake target={target} printing={printing} />
    </ConfigProvider>,
  );
}

/** The reader's tap on "Report a mistake": the <details> opens (jsdom does not toggle it from the summary). */
function open() {
  const details = screen.getByText("Report a mistake", { selector: "summary" }).closest("details")!;
  act(() => {
    details.open = true;
    details.dispatchEvent(new Event("toggle"));
  });
}

const body = () =>
  (vi.mocked(api.POST).mock.calls[0] as unknown as [string, { body: Record<string, unknown> }])[1].body;

beforeEach(() => vi.clearAllMocks());

describe("ReportMistake", () => {
  it("stays closed until the reader opens it, and loads the bot check only then", async () => {
    show(SOLUTION, "", "1x00000000000000000000AA");
    expect(screen.getByText("Report a mistake", { selector: "summary" })).toBeVisible();
    expect(screen.queryByRole("form", { name: "Report a mistake" })).toBeNull();
    expect(screen.queryByTestId("turnstile")).toBeNull();
    open();
    expect(screen.getByRole("form", { name: "Report a mistake" })).toBeVisible();
    expect(await screen.findByTestId("turnstile")).toBeInTheDocument();
  });

  it("sends the paper, the question, the step, the print run and what is wrong, then thanks the reader", async () => {
    vi.mocked(api.POST).mockReturnValueOnce(
      answer(201, { reference: 31, detail: "Thank you: we will check it, and fix it if it is wrong." }) as never,
    );
    show(SOLUTION, "PHY-2027-1", "1x00000000000000000000AA");
    open();
    await screen.findByTestId("turnstile");
    act(() => widget.onToken("token-1"));
    fireEvent.click(screen.getByRole("radio", { name: "A wrong answer or step" }));
    fireEvent.change(screen.getByLabelText(/^Which step/), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText(/^What you found/), { target: { value: "6/12 is 0.5 A, not 5 A." } });
    fireEvent.change(screen.getByLabelText(/^Your email address/), { target: { value: " reader@example.com " } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Send the report" })));
    expect(api.POST).toHaveBeenCalledWith("/api/v1/reports/", expect.anything());
    expect(body()).toEqual({
      kind: "solution",
      paper: "PHY-E01",
      question: "2(c)",
      step: 2,
      printing: "PHY-2027-1",
      category: "wrong_answer",
      note: "6/12 is 0.5 A, not 5 A.",
      email: "reader@example.com",
      website: "",
      turnstile: "token-1",
    });
    expect(await screen.findByText("Thank you: we will check it, and fix it if it is wrong.")).toBeVisible();
    expect(screen.queryByRole("form", { name: "Report a mistake" })).toBeNull();
  });

  it("asks what is wrong before sending anything", () => {
    show();
    open();
    fireEvent.click(screen.getByRole("button", { name: "Send the report" }));
    expect(api.POST).not.toHaveBeenCalled();
    expect(screen.getAllByText(/Choose what is wrong\./).length).toBeGreaterThan(0);
    expect(screen.getByRole("radio", { name: "Hard to follow" })).toHaveAttribute("aria-invalid", "true");
  });

  it("says when to try again once the limit is reached", async () => {
    vi.mocked(api.POST).mockReturnValueOnce(
      answer(429, { detail: "Request was throttled. Expected available in 1800 seconds." }) as never,
    );
    show();
    open();
    fireEvent.click(screen.getByRole("radio", { name: "Something else" }));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Send the report" })));
    expect(
      await screen.findByText(/^That is as many reports as we take for now\. You can try again at \d\d:\d\d\.$/),
    ).toBeVisible();
  });

  it("reports a clip by its number, with no step and no marks to choose", async () => {
    vi.mocked(api.POST).mockReturnValueOnce(answer(201, { reference: 32, detail: "Thank you." }) as never);
    show({ kind: "clip", clip: 41 });
    open();
    expect(screen.queryByRole("radio", { name: "The marks or the marking scheme" })).toBeNull();
    expect(screen.queryByLabelText(/^Which step/)).toBeNull();
    fireEvent.click(screen.getByRole("radio", { name: "Maths or a picture does not show" }));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Send the report" })));
    expect(body()).toMatchObject({ kind: "clip", clip: 41, printing: "", category: "display" });
    expect(body()).not.toHaveProperty("paper");
  });
});

describe("printingOf", () => {
  it("keeps a print run's label and drops anything else", () => {
    expect(printingOf("PHY-2027-1")).toBe("PHY-2027-1");
    expect(printingOf(["CHE-2027-2", "x"])).toBe("CHE-2027-2");
    expect(printingOf("PHY 2027/1")).toBe("");
    expect(printingOf("-x")).toBe("");
    expect(printingOf(undefined)).toBe("");
  });
});
