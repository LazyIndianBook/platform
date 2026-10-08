// The revision course on the website (proposed, behind config/ web_course), with the API mocked: the quiz shows no
// verdict before the server's answer and Check sends one answer however often it is pressed; the flash cards' keys;
// the settings take the API's words for minutes out of 10 to 300; with the flag off every page is a 404 and no link
// to them is drawn.
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notFound } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CardsPage from "@/app/(account)/revision/[subject]/[chapter]/cards/page";
import ChapterPage, { generateMetadata } from "@/app/(account)/revision/[subject]/[chapter]/page";
import QuizPage from "@/app/(account)/revision/[subject]/[chapter]/quiz/page";
import ReviseAgainPage from "@/app/(account)/account/learning/revise-again/page";
import { ConfigProvider } from "@/components/providers/config-provider";
import { api } from "@/lib/api/client";
import { getConfig, type SiteConfig } from "@/lib/api/config";
import { serverApi } from "@/lib/api/server";
import { requireUser } from "@/lib/auth/session";

import { ChapterLink, ReviseAgainLink } from "./course-links";
import { CardDeck } from "./flash-cards";
import { type Question, QuizRun } from "./quiz";
import { CourseSettings } from "./settings-form";

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  api: { GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn() },
}));
vi.mock("@/lib/api/config", () => ({ getConfig: vi.fn() }));
vi.mock("@/lib/api/server", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/server")>()),
  serverApi: { GET: vi.fn() },
}));
vi.mock("@/lib/auth/session", () => ({ requireUser: vi.fn(), getSessionUser: vi.fn() }));

const answer = <T,>(data: T, status = 200) => ({ data, response: new Response(null, { status }) });
const refusal = (error: unknown, status: number) => ({ error, response: new Response(null, { status }) });

beforeEach(() => {
  vi.clearAllMocks();
  window.sessionStorage.clear();
});

const QUESTIONS: Question[] = [
  {
    id: 4,
    kind: "fill_blank",
    text: "In a balanced Wheatstone bridge, the galvanometer's current is ___.",
    options: [],
  },
  { id: 5, kind: "mcq", text: "The SI unit of resistivity is", options: ["(i) Ω", "(ii) Ω m"] },
];
const quiz = () =>
  render(
    <QuizRun
      title="Current Electricity · Quiz"
      questions={QUESTIONS}
      close={{ href: "/revision/physics/3/", label: "Back to the chapter" }}
      draftKey="test"
    />,
  );

describe("QuizRun", () => {
  it("shows no verdict before the server answers, then its right answer and explanation", async () => {
    let reply!: (value: unknown) => void;
    vi.mocked(api.POST).mockReturnValue(new Promise((resolve) => (reply = resolve)) as never);
    quiz();
    await userEvent.type(screen.getByLabelText("Your answer"), "maximum");
    await userEvent.click(screen.getByRole("button", { name: "Check" }));

    expect(api.POST).toHaveBeenCalledWith("/api/v1/learn/quiz/{id}/attempt/", {
      params: { path: { id: 4 } },
      body: { answer: "maximum" },
    });
    expect(screen.queryByText(/NOT QUITE|RIGHT/)).toBeNull();
    expect(screen.queryByText(/same potential/)).toBeNull();
    expect(screen.queryByText("✗ 0")).toBeNull();

    await act(async () =>
      reply(
        answer({
          correct: false,
          right_answer: "Zero",
          explanation: "The two ends are at the same potential.",
          explanation_html: "<p>The two ends are at the same potential.</p>",
        }),
      ),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("NOT QUITE · ANSWER: Zero");
    expect(screen.getByText("The two ends are at the same potential.")).toBeInTheDocument();
    expect(screen.getByLabelText("Your answer")).toHaveAttribute("readonly");
    expect(screen.getByRole("button", { name: "Next question" })).toBeInTheDocument();
  });

  it("keeps Check busy while the answer is out: pressing it again sends nothing", async () => {
    let reply!: (value: unknown) => void;
    vi.mocked(api.POST).mockReturnValue(new Promise((resolve) => (reply = resolve)) as never);
    quiz();
    await userEvent.type(screen.getByLabelText("Your answer"), "zero");
    const check = screen.getByRole("button", { name: "Check" });
    await userEvent.click(check);
    expect(check).toHaveAttribute("aria-busy", "true");
    await userEvent.click(check);
    await userEvent.type(screen.getByLabelText("Your answer"), "{Enter}");
    expect(api.POST).toHaveBeenCalledOnce();

    await act(async () =>
      reply(answer({ correct: true, right_answer: "Zero", explanation: "", explanation_html: "" })),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("RIGHT");
    expect(api.POST).toHaveBeenCalledOnce();
  });

  it("counts the server's verdicts in the result", async () => {
    vi.mocked(api.POST)
      .mockResolvedValueOnce(
        answer({ correct: true, right_answer: "Zero", explanation: "", explanation_html: "" }) as never,
      )
      .mockResolvedValueOnce(
        answer({ correct: false, right_answer: "(ii) Ω m", explanation: "", explanation_html: "" }) as never,
      );
    quiz();
    await userEvent.type(screen.getByLabelText("Your answer"), "0");
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    await userEvent.click(await screen.findByRole("button", { name: "Next question" }));
    await userEvent.click(screen.getByRole("radio", { name: "(i) Ω" }));
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    expect(api.POST).toHaveBeenLastCalledWith("/api/v1/learn/quiz/{id}/attempt/", {
      params: { path: { id: 5 } },
      body: { answer: "1" },
    });
    await userEvent.click(await screen.findByRole("button", { name: "See your result" }));
    expect(screen.getByRole("heading", { name: "1 of 2 right" })).toBeInTheDocument();
    expect(screen.getByText("The one you missed comes back in Revise again tomorrow.")).toBeInTheDocument();
  });
});

describe("QuizRun while a parent's consent is awaited", () => {
  it("is off and says why, with the parent's link: nothing is sent", async () => {
    render(
      <QuizRun
        title="Quiz"
        questions={QUESTIONS}
        close={{ href: "/", label: "Back" }}
        draftKey="test"
        consentPending
      />,
    );
    expect(screen.getByRole("button", { name: "Check" })).toBeDisabled();
    expect(screen.getByLabelText("Your answer")).toBeDisabled();
    expect(screen.getByRole("link", { name: "Send them the link again" })).toHaveAttribute("href", "/account/privacy/");
    await userEvent.type(screen.getByLabelText("Your answer"), "zero{Enter}");
    expect(api.POST).not.toHaveBeenCalled();
  });
});

describe("CardDeck", () => {
  it("turns with Space and is answered with 1 and 2, each answer saved before the next card", async () => {
    vi.mocked(api.POST).mockResolvedValue(answer(undefined, 201) as never);
    render(
      <CardDeck
        title="Current Electricity · Flash cards"
        cards={[
          { id: 1, front: "SI unit of resistivity?", back: "Ω m" },
          { id: 2, front: "Balanced bridge?", back: "P/Q = R/S" },
        ]}
        close={{ href: "/revision/physics/3/", label: "Back to the chapter" }}
      />,
    );
    expect(screen.getByText("FRONT")).toBeInTheDocument();
    await userEvent.keyboard("2"); // not before the card is turned
    expect(api.POST).not.toHaveBeenCalled();

    await userEvent.keyboard(" ");
    expect(screen.getByText("BACK")).toBeInTheDocument();
    expect(screen.getByText("Ω m")).toBeInTheDocument();
    await userEvent.keyboard("2");
    expect(api.POST).toHaveBeenCalledWith("/api/v1/learn/flash-cards/{id}/review/", {
      params: { path: { id: 1 } },
      body: { known: true },
    });
    expect(await screen.findByText("Balanced bridge?")).toBeInTheDocument();
    expect(screen.getByText("Card 2 of 2")).toBeInTheDocument();

    await userEvent.keyboard(" ");
    await userEvent.keyboard("1");
    expect(api.POST).toHaveBeenLastCalledWith("/api/v1/learn/flash-cards/{id}/review/", {
      params: { path: { id: 2 } },
      body: { known: false },
    });
    expect(await screen.findByRole("heading", { name: "You knew 1 of 2" })).toBeInTheDocument();
    expect(api.POST).toHaveBeenCalledTimes(2);
  });

  it("stays on the card when the API refuses the answer", async () => {
    vi.mocked(api.POST).mockResolvedValue(
      refusal({ detail: "That is a day's worth of answers: carry on tomorrow." }, 429) as never,
    );
    render(
      <CardDeck title="Deck" cards={[{ id: 1, front: "Front", back: "Back" }]} close={{ href: "/", label: "Back" }} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Show the back" }));
    await userEvent.click(screen.getByRole("button", { name: "I knew it" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That is a day's worth of answers: carry on tomorrow.");
    expect(screen.getByText("BACK")).toBeInTheDocument();
  });
});

describe("CourseSettings", () => {
  it.each([
    ["301", 301, "Ensure this value is less than or equal to 300."],
    ["5", 5, "Ensure this value is greater than or equal to 10."],
  ])("sends %s minutes as typed and shows the API's refusal in its words", async (typed, sent, words) => {
    vi.mocked(api.PATCH).mockResolvedValue(refusal({ minutes_per_day: [words] }, 400) as never);
    render(
      <CourseSettings
        settings={{ exam_date: "2027-02-20", minutes_per_day: 30, reminders: false }}
        planLine={null}
        consentPending={false}
      />,
    );
    const minutes = screen.getByLabelText("Minutes a day");
    await userEvent.clear(minutes);
    await userEvent.type(minutes, typed);
    await userEvent.click(screen.getByRole("button", { name: "Save and re-plan" }));
    expect(api.PATCH).toHaveBeenCalledWith("/api/v1/learn/settings/", {
      body: { exam_date: "2027-02-20", minutes_per_day: sent, reminders: false },
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(`Minutes a day: ${words}`);
    expect(minutes).toHaveAttribute("aria-invalid", "true");
    expect(document.getElementById("minutes_per_day-error")).toHaveTextContent(words);
  });

  it("is off and says why while a parent's consent is awaited", () => {
    render(<CourseSettings settings={{ minutes_per_day: 30 }} planLine={null} consentPending />);
    expect(screen.getByLabelText("Minutes a day")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save and re-plan" })).toBeDisabled();
    expect(screen.getByRole("link", { name: "Send them the link again" })).toHaveAttribute("href", "/account/privacy/");
  });
});

describe("the flag (config/ web_course)", () => {
  const params = Promise.resolve({ subject: "physics", chapter: "3" });
  const pages = [
    ["the chapter", () => ChapterPage({ params, searchParams: Promise.resolve({}) })],
    ["its metadata", () => generateMetadata({ params, searchParams: Promise.resolve({}) })],
    ["the flash cards", () => CardsPage({ params })],
    ["the quiz", () => QuizPage({ params })],
    ["Revise again", () => ReviseAgainPage({ searchParams: Promise.resolve({}) })],
  ] as const;

  it.each([
    ["off", { web_course: false }],
    ["unread", null],
  ])("%s: every page is a 404, before anything else is asked", async (_, config) => {
    vi.mocked(getConfig).mockResolvedValue(config as SiteConfig | null);
    vi.mocked(notFound).mockImplementation(() => {
      throw new Error("NEXT_HTTP_ERROR_FALLBACK;404");
    });
    for (const [, page] of pages) await expect(page()).rejects.toThrow("NEXT_HTTP_ERROR_FALLBACK;404");
    expect(notFound).toHaveBeenCalledTimes(pages.length);
    expect(requireUser).not.toHaveBeenCalled();
    expect(serverApi.GET).not.toHaveBeenCalled();
  });

  it("draws the links only while it is on", () => {
    const links = (config: Partial<SiteConfig> | null) =>
      render(
        <ConfigProvider value={config as SiteConfig | null}>
          <ChapterLink subject="PHY" chapter={3} />
          <ReviseAgainLink />
        </ConfigProvider>,
      );
    const off = links({ web_course: false });
    expect(screen.queryByRole("link")).toBeNull();
    off.unmount();
    const unread = links(null);
    expect(screen.queryByRole("link")).toBeNull();
    unread.unmount();
    links({ web_course: true });
    expect(screen.getByRole("link", { name: "Open the chapter" })).toHaveAttribute("href", "/revision/physics/3/");
    expect(screen.getByRole("link", { name: "Revise again today" })).toHaveAttribute(
      "href",
      "/account/learning/revise-again/",
    );
  });
});
