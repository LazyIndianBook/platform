// The triage's steps: each state offers what the API allows from it (reported: confirm, fixed online, reject;
// confirmed: fixed online, in a printing, reject; fixed online: in a printing; rejected: reopen; fixed in a printing:
// nothing more), a rejection with its reason, a fix in printing with the print run, and the reporter told only once it
// is fixed and they left an address.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { type ContentReportDetail, reportStep, tellReporter } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { navigation } from "@/test/navigation";

import { ReportSteps } from "./report-actions";

vi.mock("@/lib/api/staff", async (original) => ({
  ...(await original<typeof import("@/lib/api/staff")>()),
  reportStep: vi.fn(),
  tellReporter: vi.fn(),
}));

const words = copy.content.reports;

const report = (row: Partial<ContentReportDetail> = {}): ContentReportDetail => ({
  id: 2601,
  kind: "solution",
  target_id: 2402,
  subject: "PHY",
  paper: 2201,
  paper_code: "PHY-E01",
  question: 2302,
  question_label: "2(c)",
  step: 2,
  printing: "PHY-2027-1",
  category: "wrong_answer",
  note: "",
  email: "",
  reporter: null,
  teacher_verified: false,
  state: "reported",
  fixed_in: "",
  fixed_at: null,
  resolved_at: null,
  staff_note: "",
  reporter_told_at: null,
  public: false,
  created: "2026-10-08T10:00:00Z",
  can_tell: false,
  handled_by: null,
  linked: { paper_id: 2201, question_id: 2302, solution_id: 2402 },
  ...row,
});

const buttons = () => screen.queryAllByRole("button").map((button) => button.textContent);

beforeEach(() => {
  vi.mocked(reportStep).mockReset();
  vi.mocked(tellReporter).mockReset();
  navigation.router.refresh = vi.fn();
});

describe("ReportSteps", () => {
  it.each([
    ["reported", [words.confirm, words.fixOnline, words.reject]],
    ["confirmed", [words.fixOnline, words.fixInPrinting, words.reject]],
    ["fixed_online", [words.fixInPrinting]],
    ["rejected", [words.reopen]],
    ["fixed_in_printing", []],
  ] as const)("offers from %s only the steps that follow from it", (state, expected) => {
    render(<ReportSteps report={report({ state })} />);
    expect(buttons()).toEqual(expected);
  });

  it("confirms in one press, and the page is drawn again", async () => {
    vi.mocked(reportStep).mockResolvedValueOnce(report({ state: "confirmed" }) as never);
    render(<ReportSteps report={report()} />);
    await userEvent.click(screen.getByRole("button", { name: words.confirm }));
    expect(reportStep).toHaveBeenCalledWith(2601, "confirm");
    expect(navigation.router.refresh).toHaveBeenCalled();
  });

  it("rejects with the reason, and fixes in a printing with its label", async () => {
    vi.mocked(reportStep).mockResolvedValue(report() as never);
    const { unmount } = render(<ReportSteps report={report({ state: "confirmed" })} />);
    await userEvent.click(screen.getByRole("button", { name: words.reject }));
    await userEvent.type(screen.getByRole("textbox", { name: words.reason }), "The scheme gives 1 mark there.");
    await userEvent.click(screen.getByRole("dialog").querySelector("button[type=submit]")!);
    expect(reportStep).toHaveBeenCalledWith(2601, "reject", { staff_note: "The scheme gives 1 mark there." });
    unmount();

    render(<ReportSteps report={report({ state: "fixed_online" })} />);
    await userEvent.click(screen.getByRole("button", { name: words.fixInPrinting }));
    await userEvent.type(screen.getByRole("textbox", { name: words.printing }), "PHY-2027-2");
    await userEvent.click(screen.getByRole("dialog").querySelector("button[type=submit]")!);
    expect(reportStep).toHaveBeenCalledWith(2601, "fix-in-printing", { fixed_in: "PHY-2027-2" });
  });

  it("tells the reporter once it is fixed and only if they left an address", async () => {
    vi.mocked(tellReporter).mockResolvedValueOnce(report() as never);
    const { unmount } = render(<ReportSteps report={report({ state: "fixed_online", can_tell: false })} />);
    expect(screen.queryByRole("button", { name: words.tell })).toBeNull();
    unmount();
    render(<ReportSteps report={report({ state: "fixed_online", can_tell: true, email: "re•••@example.com" })} />);
    await userEvent.click(screen.getByRole("button", { name: words.tell }));
    await userEvent.click(screen.getByRole("dialog").querySelector("button[type=submit]")!);
    expect(tellReporter).toHaveBeenCalledWith(2601);
  });
});
