// The revision page's state from the API: what is open to the student (entitlements), the pass plan, the book code's
// refusals in the design's words (used, not recognised, the limit), its form disabled while a parent's consent is
// awaited, and the app's store links.
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/errors";

import { AppLinks, dayLabel, EntitlementList, type Plan, PlanView } from "./course";
import { codeProblem, RedeemForm } from "./islands";

describe("EntitlementList", () => {
  it("says which subject is open and until when, and which one ended", () => {
    const created = "2026-10-01T10:00:00+05:30";
    render(
      <EntitlementList
        today="2026-10-08"
        entitlements={[
          { id: 1, subject: 1, subject_name: "Physics", source: "book_code", valid_until: "2027-10-08", created },
          { id: 2, subject: 2, subject_name: "Chemistry", source: "purchase", valid_until: "2026-10-07", created },
          { id: 3, subject: null, source: "grant", valid_until: null, created },
        ]}
      />,
    );
    const row = (name: string) => screen.getByText(name).closest("div")!;
    expect(row("Physics")).toHaveTextContent("Physics · open");
    expect(within(row("Physics")).getByRole("definition")).toHaveTextContent("until 8 Oct 2027");
    expect(row("Chemistry")).toHaveTextContent("Chemistry · ended");
    expect(within(row("Chemistry")).getByRole("definition")).toHaveTextContent("on 7 Oct 2026");
    expect(within(row("Every subject")).getByRole("definition")).toHaveTextContent("with no end date");
  });
});

const clip = (id: number, title: string) => ({ id, chapter: 3, title, kind: "concept" as const, duration: 140 });

describe("PlanView", () => {
  const plan: Plan = {
    exam_date: "2027-02-20",
    days_left: 135,
    minutes_per_day: 30,
    days: Array.from({ length: 9 }, (_, day) => ({
      date: `2026-10-${String(8 + day).padStart(2, "0")}`,
      minutes: 28,
      clips: [clip(day * 2 + 1, `Clip ${day * 2 + 1}`), clip(day * 2 + 2, `Clip ${day * 2 + 2}`)],
    })),
    not_scheduled: [12],
    minimum_to_pass: [
      {
        subject: 1,
        pass_marks: 21,
        marks: "32.0",
        chapters: [
          { id: 9, number: 9, title: "Ray Optics", weight: "7.0", minutes: 14, marks_per_minute: "0.5", clips: [] },
        ],
      },
    ],
  };

  it("shows the days left, the first week's clips, what did not fit and the quickest way to the pass mark", () => {
    render(<PlanView plan={plan} subjectName={(id) => (id === 1 ? "Physics" : "?")} />);
    expect(screen.getByText(/days to your exam on 20 February 2027, at 30 minutes a day/)).toHaveTextContent("135");
    const days = within(screen.getByRole("list", { name: "Your first days" })).getAllByRole("listitem");
    expect(days).toHaveLength(7); // the eighth day is not shown
    expect(days[0]).toHaveTextContent("Thu 8 Oct · 28 min");
    expect(days[0]).toHaveTextContent("Clip 1 (2 min) · Clip 2 (2 min)");
    expect(screen.queryByText(/Clip 15/)).toBeNull();
    expect(screen.getByText(/And 2 more days/)).toBeInTheDocument();
    expect(screen.getByText(/1 chapter does not fit before the exam/)).toBeInTheDocument();
    expect(screen.getByText(/Physics: the pass mark is 21. These chapters give 32 marks/)).toBeInTheDocument();
    expect(screen.getByText("Ch. 9 Ray Optics: 7 marks, 14 min")).toBeInTheDocument();
  });

  it("says so when no clip is ready to plan", () => {
    render(<PlanView plan={{ ...plan, days: [], not_scheduled: [], minimum_to_pass: [] }} subjectName={() => ""} />);
    expect(screen.getByText(/Nothing to plan yet/)).toBeInTheDocument();
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("writes a day as the design does, its weekday from the date itself", () => {
    expect(dayLabel("2026-10-09")).toBe("Fri 9 Oct");
    expect(dayLabel("2027-02-20")).toBe("Sat 20 Feb");
  });
});

describe("The book code", () => {
  it("turns the API's refusals into the design's words, and leaves the others alone", () => {
    const throttled = new ApiError(429, "throttled", "Request was throttled. Expected available in 1800 seconds.");
    expect(codeProblem(throttled)?.message).toBe(
      "That is 5 tries this hour, the most a code can have. Try again in about 30 minutes.",
    );
    const used = new ApiError(400, "invalid", "This code has been used already.", {
      code: ["This code has been used already."],
    });
    expect(codeProblem(used)?.fields.code).toEqual([
      "This code has already been used. Each code opens one account. If it's yours, log in with that account.",
    ]);
    const unknown = "This code is not valid. Check it against the one printed in your book.";
    expect(codeProblem(new ApiError(400, "invalid", unknown, { code: [unknown] }))?.message).toBe(
      "We don't recognise that code. Check it against the page in your book; it has 12 characters.",
    );
    const format = "A book code has 12 letters and digits, like 7KQM-3XPA-9TRW.";
    const shape = new ApiError(400, "invalid", format, { code: [format] });
    expect(codeProblem(shape)).toBe(shape);
    expect(codeProblem(null)).toBeNull();
  });

  it("is disabled while a parent's consent is awaited", () => {
    render(<RedeemForm disabled />);
    expect(screen.getByLabelText("Code from your book")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Open" })).toBeDisabled();
  });
});

describe("AppLinks", () => {
  it("links each store the config names, with its QR code on a desktop; says the app is coming otherwise", () => {
    const { rerender } = render(
      <AppLinks links={{ android: "https://play.google.com/store/apps/details?id=in.examleaf", ios: null }} qr />,
    );
    expect(screen.getByRole("link", { name: "ExamLeaf on Google Play" })).toHaveAttribute(
      "href",
      "https://play.google.com/store/apps/details?id=in.examleaf",
    );
    expect(screen.getByRole("img", { name: /QR code of ExamLeaf on Google Play/ })).toBeInTheDocument();
    expect(screen.queryByText(/App Store/)).toBeNull();
    rerender(<AppLinks links={{ android: null, ios: null }} qr />);
    expect(screen.getByText("The app is coming to the stores soon.")).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
  });
});
