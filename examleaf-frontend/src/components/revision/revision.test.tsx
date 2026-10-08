// The revision page's state from the API: what is open to the student (entitlements), the pass plan, and the book
// code's limit in words.
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/errors";

import { EntitlementList, type Plan, PlanView } from "./course";
import { codeProblem } from "./islands";

describe("EntitlementList", () => {
  it("says until when each subject is open, which one ended, and what opened it", () => {
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
    expect(within(row("Physics")).getByRole("definition")).toHaveTextContent(
      "Open until 8 Oct 2027 · from a book code",
    );
    expect(within(row("Chemistry")).getByRole("definition")).toHaveTextContent("Ended on 7 Oct 2026 · from a purchase");
    expect(within(row("Every subject")).getByRole("definition")).toHaveTextContent("Open · from a staff grant");
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
    const days = screen.getByRole("list", { name: "Your first days" });
    expect(within(days).getAllByText(/· 28 min$/)).toHaveLength(7);
    expect(screen.getByText("8 Oct 2026 · 28 min")).toBeInTheDocument();
    expect(screen.getByText("Clip 1 (2 min)")).toBeInTheDocument();
    expect(screen.queryByText(/Clip 15/)).toBeNull(); // the eighth day is not shown
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
});

describe("codeProblem", () => {
  it("turns the API's throttle into the limit in words, and leaves other refusals alone", () => {
    const throttled = new ApiError(429, "throttled", "Request was throttled. Expected available in 1800 seconds.");
    expect(codeProblem(throttled)?.message).toBe(
      "That is 5 tries this hour, the most a code can have. Try again in about 30 minutes.",
    );
    const invalid = new ApiError(400, "invalid", "This code is not valid.", { code: ["This code is not valid."] });
    expect(codeProblem(invalid)).toBe(invalid);
    expect(codeProblem(null)).toBeNull();
  });
});
