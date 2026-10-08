// The account's islands (package 8C): the 6-digit code step of a new mobile number or email address, the marks
// form's checks (the website form's words) and its save through the API, Download my data's count of records, and
// My record's tier averages.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { tierAverages } from "@/lib/api/account";
import { api } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

import { MarksForm, validateMarks } from "./marks-form";
import { howMany } from "./privacy-forms";
import { CodeStep } from "./security-forms";

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  api: { GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() },
}));

beforeEach(() => vi.clearAllMocks());

// input-otp looks for a password manager's badge beside its boxes; jsdom draws nothing, so nothing is there
document.elementFromPoint = () => null;

describe("CodeStep (the OTP input of a new mobile number or email address)", () => {
  it("takes digits only and confirms once six are in", async () => {
    const confirm = vi.fn().mockResolvedValue(undefined);
    render(<CodeStep sentTo="+91 98640 12345" name="code" confirm={confirm} resend={vi.fn()} restart={vi.fn()} />);
    expect(screen.getByText(/We have sent a 6-digit code to \+91 98640 12345/)).toBeInTheDocument();
    const box = screen.getByRole("textbox", { name: /code/i });
    expect(box).toHaveAttribute("autocomplete", "one-time-code");
    const confirmButton = screen.getByRole("button", { name: "Confirm" });
    expect(confirmButton).toBeDisabled();

    await userEvent.type(box, "12ab34");
    expect(box).toHaveValue("1234");
    expect(confirmButton).toBeDisabled();
    await userEvent.type(box, "56");
    expect(confirmButton).toBeEnabled();
    await userEvent.click(confirmButton);
    expect(confirm).toHaveBeenCalledWith("123456");
  });

  it("puts a wrong code's error beside the boxes, and asks for a new code", async () => {
    const wrong = new ApiError(400, "incorrect_code", "Incorrect code.", { code: ["Incorrect code."] });
    const resend = vi.fn().mockResolvedValue(undefined);
    render(
      <CodeStep
        sentTo="a@example.com"
        name="code"
        confirm={vi.fn().mockRejectedValue(wrong)}
        resend={resend}
        restart={vi.fn()}
      />,
    );
    const box = screen.getByRole("textbox", { name: /code/i });
    await userEvent.type(box, "000000");
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect code.");
    expect(box).toHaveAttribute("aria-invalid", "true");
    await userEvent.click(screen.getByRole("button", { name: "Send a new code" }));
    expect(resend).toHaveBeenCalledOnce();
  });
});

describe("validateMarks", () => {
  const good = { date: "2026-10-08", marks_obtained: "52.5", time_taken_minutes: "170", notes: "" };
  const marks = (value: string) => validateMarks({ ...good, marks_obtained: value }, 70).marks_obtained;

  it("lets good marks through and refuses the others in the website form's words", () => {
    expect(validateMarks(good, 70)).toEqual({});
    expect(validateMarks({ ...good, marks_obtained: "0", time_taken_minutes: "" }, 70)).toEqual({});
    expect(marks("70")).toBeUndefined();
    expect(marks("")).toEqual(["Enter the marks you gave yourself."]);
    expect(marks("-1")).toEqual(["Marks cannot be below 0."]);
    expect(marks("fifty")).toEqual(["Enter the marks as a number, such as 52.5."]);
    expect(marks("52.25")).toEqual(["Use one decimal place at most, such as 52.5."]);
    expect(marks("70.5")).toEqual(["At most 70, the paper's full marks."]);
    expect(validateMarks({ ...good, date: "" }, 70).date).toEqual(["Enter the date you sat the paper."]);
    expect(validateMarks({ ...good, time_taken_minutes: "2 h" }, 70).time_taken_minutes).toEqual([
      "Enter the minutes as a number, such as 170.",
    ]);
    expect(validateMarks({ ...good, notes: "x".repeat(2001) }, 70).notes?.[0]).toMatch(/^At most 2,000 characters/);
  });
});

describe("MarksForm", () => {
  it("marks the boxes to fix and sends nothing", async () => {
    render(<MarksForm paper="PHY-E01" fullMarks={70} />);
    await userEvent.type(screen.getByLabelText(/Marks obtained \(out of 70\)/), "75");
    await userEvent.click(screen.getByRole("button", { name: "Save to my record" }));
    expect(screen.getByRole("alert")).toHaveTextContent("At most 70, the paper's full marks.");
    expect(screen.getByLabelText(/Marks obtained/)).toHaveAttribute("aria-invalid", "true");
    expect(api.POST).not.toHaveBeenCalled();
  });

  it("saves the attempt and says what was saved", async () => {
    vi.mocked(api.POST).mockResolvedValue({
      data: { id: 9, paper: "PHY-E01", date: "2026-10-08", marks_obtained: "52.5", full_marks: 70, percent: 75 },
      response: new Response(null, { status: 201 }),
    } as never);
    render(<MarksForm paper="PHY-E01" fullMarks={70} />);
    await userEvent.type(screen.getByLabelText(/Marks obtained/), "52.5");
    await userEvent.type(screen.getByLabelText(/What to revise/), "optics");
    await userEvent.click(screen.getByRole("button", { name: "Save to my record" }));
    expect(await screen.findByText(/PHY-E01: 52.5\/70 \(75%\) on 8 Oct 2026/)).toBeInTheDocument();
    expect(api.POST).toHaveBeenCalledWith("/api/v1/attempts/", {
      body: expect.objectContaining({
        paper: "PHY-E01",
        marks_obtained: "52.5",
        time_taken_minutes: null,
        notes: "optics",
      }),
    });
    expect(screen.getByLabelText(/Marks obtained/)).toHaveValue(""); // a fresh form for the next paper
  });

  it("shows the API's refusal, such as a parent's consent still awaited", async () => {
    const refusal =
      "Your parent or guardian has not confirmed your account yet: marks can be saved once they have (see My account).";
    vi.mocked(api.POST).mockResolvedValue({
      error: { non_field_errors: [refusal] },
      response: new Response(null, { status: 400 }),
    } as never);
    render(<MarksForm paper="PHY-E01" fullMarks={70} />);
    await userEvent.type(screen.getByLabelText(/Marks obtained/), "40");
    await userEvent.click(screen.getByRole("button", { name: "Save to my record" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(refusal);
  });
});

describe("Download my data and My record", () => {
  it("counts a part's records as Django's how_many does", () => {
    expect(howMany([1, 2, 3])).toBe(3);
    expect(howMany({ items: [1, 2], payments: [1] })).toBe(3);
    expect(howMany({ full_name: "A" })).toBe(1);
    expect(howMany({})).toBe(0);
    expect(howMany(null)).toBe(0);
  });

  it("averages each tier as Django rounds it, with no average for a tier without papers", () => {
    const attempts = [
      { tier: "E", percent: 75 },
      { tier: "E", percent: 74 },
      { tier: "M", percent: 71 },
    ];
    expect(tierAverages(attempts)).toEqual([
      { tier: "E", count: 2, average: 74 }, // 74.5: Python's round() goes to the even 74
      { tier: "M", count: 1, average: 71 },
      { tier: "H", count: 0, average: null },
    ]);
  });
});
