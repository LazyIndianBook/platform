// Learning's parts (GET me/learning/): a chapter's progress bar and the Continue card, with the API's data and
// without it, and the streak in words.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api/client";

import { ContinueCard, type Learning, ProgressBar, streakWords } from "./learning";

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  api: { GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() },
}));

beforeEach(() => vi.clearAllMocks());

const bar = (container: HTMLElement) => container.querySelector<HTMLElement>("[data-bar]")!;

describe("ProgressBar", () => {
  it("draws the share watched and says it in words", () => {
    const { container } = render(<ProgressBar done={3} total={6} />);
    expect(screen.getByText("3 of 6 clips")).toBeInTheDocument();
    expect(bar(container).style.width).toBe("50%");
    expect(bar(container).parentElement).toHaveAttribute("aria-hidden", "true"); // the words carry it
  });

  it("is empty, and says so, for a chapter without clips yet", () => {
    const { container } = render(<ProgressBar done={0} total={0} />);
    expect(screen.getByText("No clips yet")).toBeInTheDocument();
    expect(bar(container).style.width).toBe("0%");
  });
});

const next: NonNullable<Learning["continue_watching"]> = {
  clip: {
    id: 42,
    order: 2,
    title: "Gauss's law in one picture",
    kind: "concept",
    duration: 150,
    free: false,
    locked: false,
    seconds_watched: 30,
  },
  revision: { id: 3, title: "Electric charges in 13 minutes" },
  chapter: { id: 7, subject: 1, subject_name: "Physics", number: 1, title: "Electric Charges and Fields" },
};

describe("ContinueCard", () => {
  it("shows the next clip with its chapter and plays it here, honest that the app keeps the progress", async () => {
    vi.mocked(api.GET).mockResolvedValue({
      data: { ...next.clip, hls_url: "https://examleaf.in/learn/hls/x/master.m3u8", poster_url: "" },
      response: new Response(null, { status: 200 }),
    } as never);
    render(<ContinueCard next={next} hasAppLinks />);
    expect(screen.getByText("Physics · Ch. 1 Electric Charges and Fields")).toBeInTheDocument();
    expect(screen.getByText("Gauss's law in one picture")).toBeInTheDocument();
    expect(screen.getByText("Concept · 3 min · Electric charges in 13 minutes")).toBeInTheDocument();
    expect(screen.getByText(/Watching here is not counted/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Get the app" })).toHaveAttribute("href", "/revision/#app");

    await userEvent.click(screen.getByRole("button", { name: "Play it here: Gauss's law in one picture" }));
    expect(api.GET).toHaveBeenCalledWith("/api/v1/learn/clips/{id}/", { params: { path: { id: 42 } } });
    expect(await screen.findByLabelText("Gauss's law in one picture")).toHaveProperty("tagName", "VIDEO");
  });

  it("says what opens a locked clip instead of a player, and that the app is not out yet", () => {
    render(<ContinueCard next={{ ...next, clip: { ...next.clip, locked: true } }} hasAppLinks={false} />);
    expect(screen.getByText(/This clip opens with the course/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
    render(<ContinueCard next={next} hasAppLinks={false} />);
    expect(screen.getByText(/The app is coming to the stores soon/)).toBeInTheDocument();
  });

  it("points to the free clips before any clip was watched", () => {
    render(<ContinueCard next={null} hasAppLinks />);
    expect(screen.getByText(/Nothing to continue yet/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Revision course" })).toHaveAttribute("href", "/revision/#chapters");
  });
});

describe("streakWords", () => {
  it("is a quiet line: the days in a row, the last day after a break, nothing before the first", () => {
    expect(streakWords({ days: 3, today: true, last_day: "2026-10-08" })).toBe("3 days of revision in a row.");
    expect(streakWords({ days: 1, today: false, last_day: "2026-10-07" })).toBe(
      "1 day of revision in a row, up to yesterday.",
    );
    expect(streakWords({ days: 0, today: false, last_day: "2026-10-01" })).toBe("Last revised on 1 Oct 2026.");
    expect(streakWords({ days: 0, today: false, last_day: null })).toBeNull();
  });
});
