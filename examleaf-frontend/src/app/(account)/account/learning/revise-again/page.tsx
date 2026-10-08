// /account/learning/revise-again/ (proposed, only while config/ has web_course on; Revise again and settings): what is
// due again today (learn/revise-again/: quiz questions and flash cards answered wrong, back 1, 3 and 7 days later, the
// longest waiting first) and the course settings (learn/settings/), with the plan they give (learn/plan/) in a line.
// Start goes through the due cards (?start=cards), then the due questions (?start=quiz), answered through the same
// endpoints as a chapter's; the API reschedules them. In the account's frame, never indexed. Outside the (streamed)
// group so that, with the flag off, the answer is a real 404 (README "Add a route").
import "katex/dist/katex.min.css";

import Link from "next/link";

import { Problem } from "@/components/account/parts";
import { deckCards, plural, quizQuestions } from "@/components/course/chapter";
import { requireCourse } from "@/components/course/data";
import { CardDeck } from "@/components/course/flash-cards";
import { QuizRun } from "@/components/course/quiz";
import { CourseSettings } from "@/components/course/settings-form";
import { MarkdownInline } from "@/components/solutions/markdown";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { getMe, getSubjects, settle } from "@/lib/api/account";
import { ApiError, unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { personalFetch, publicFetch, serverApi } from "@/lib/api/server";
import { dateInIndia, formatDate } from "@/lib/dates";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({
  title: "Revise again",
  path: "/account/learning/revise-again/",
  description: "The quiz questions and flash cards to revise again today, and your course settings.",
  noindex: true,
});

type Due<T> = T & { due: string };
type ReviseAgain = {
  quiz_items: Due<components["schemas"]["QuizItem"]>[];
  flash_cards: Due<components["schemas"]["FlashCard"]>[];
};
type Plan = components["schemas"]["Plan"];
type Props = { searchParams: Promise<{ start?: string | string[] }> };

const PATH = "/account/learning/revise-again/";
const DAY = 86_400_000;

/** The saved settings' plan in a line: when the clips not yet watched are done and what that leaves before the exam. */
function planLine(plan: Plan | null): string | null {
  if (!plan) return null;
  const pace = `At ${plan.minutes_per_day} minutes a day`;
  if (plan.not_scheduled.length) {
    const count = plan.not_scheduled.length;
    return `${pace}, ${plural(count, "chapter")} ${count === 1 ? "does" : "do"} not fit before your exam.`;
  }
  const last = plan.days.at(-1);
  if (!last) return null;
  const left = Math.round((Date.parse(plan.exam_date) - Date.parse(last.date)) / DAY) - 1;
  const leaves =
    left >= 7
      ? `which leaves ${plural(Math.floor(left / 7), "week")} to sit papers`
      : left > 0
        ? `which leaves ${plural(left, "day")} to sit papers`
        : "the day before your exam";
  return `${pace}, you finish the clips you have not watched by ${formatDate(last.date)}, ${leaves}.`;
}

export default async function ReviseAgainPage({ searchParams }: Props) {
  await requireCourse();
  const start = [(await searchParams).start].flat()[0];
  const options = await personalFetch();
  const [due, settings, plan, me, chapters, subjects] = await Promise.all([
    settle(
      unwrap(serverApi.GET("/api/v1/learn/revise-again/", options)) as Promise<unknown> as Promise<ReviseAgain>,
      PATH,
    ),
    settle(unwrap(serverApi.GET("/api/v1/learn/settings/", options)), PATH),
    unwrap(serverApi.GET("/api/v1/learn/plan/", options)).catch(() => null), // 400 without an exam date after today
    getMe().catch(() => null),
    unwrap(
      serverApi.GET("/api/v1/learn/chapters/", { params: { query: { page_size: 200 } }, ...publicFetch("chapters") }),
    )
      .then((list) => list.results)
      .catch(() => []),
    getSubjects().catch(() => []),
  ]);
  const consentPending = Boolean(me?.consent_pending);
  const back = { href: PATH, label: "Back to Revise again" };

  if (!(due instanceof ApiError) && start === "cards" && due.flash_cards.length) {
    return (
      <CardDeck
        title="Revise again · Flash cards"
        cards={deckCards(due.flash_cards)}
        close={back}
        next={due.quiz_items.length ? { href: `${PATH}?start=quiz`, label: "Go on to the quiz questions" } : undefined}
        consentPending={consentPending}
      />
    );
  }
  if (!(due instanceof ApiError) && start === "quiz" && due.quiz_items.length) {
    return (
      <QuizRun
        title="Revise again · Quiz"
        questions={quizQuestions(due.quiz_items)}
        close={back}
        draftKey="examleaf:course:quiz:revise-again"
        consentPending={consentPending}
      />
    );
  }

  const where = (id: number) => {
    const chapter = chapters.find((row) => row.id === id);
    const subject = subjects.find((row) => row.id === chapter?.subject);
    return chapter ? `${subject?.name ?? "Subject"} · Ch. ${chapter.number}` : "";
  };
  const today = dateInIndia();
  const when = (moment: string) =>
    dateInIndia(new Date(moment)) >= today ? "Due today" : `Due since ${formatDate(moment)}`;
  const rows =
    due instanceof ApiError
      ? []
      : [
          ...due.quiz_items.map(({ id, text, due, chapter }) => ({
            key: `q${id}`,
            label: "QUIZ",
            title: text,
            due,
            chapter,
          })),
          ...due.flash_cards.map(({ id, front, due, chapter }) => ({
            key: `c${id}`,
            label: "CARD",
            title: front,
            due,
            chapter,
          })),
        ].sort((a, b) => a.due.localeCompare(b.due));

  return (
    <div className="flex flex-wrap items-start gap-x-12 gap-y-8 [&_p]:m-0">
      <div className="flex min-w-0 flex-[1.3_1_420px] flex-col gap-4">
        <Breadcrumb
          trail={[{ label: "Learning", href: "/account/learning/" }, { label: "Revise again" }]}
          className="[&_ol]:mb-0"
        />
        <h1 className="text-[clamp(34px,4vw,44px)] leading-none">Revise again today</h1>
        <p className="text-base leading-relaxed text-ink/85">
          Things you got wrong or marked &quot;Not yet&quot; a few days ago, brought back before you forget them.
        </p>
        {due instanceof ApiError ? (
          <Problem error={due} what="What to revise again" retry={PATH} />
        ) : rows.length ? (
          <>
            <ol aria-label="Due again" className="m-0 list-none border-t-[1.5px] border-foreground p-0">
              {rows.map((row) => (
                <li
                  key={row.key}
                  className="grid min-h-14 grid-cols-[96px_minmax(0,1fr)_120px] items-center gap-3.5 border-b border-border py-2 text-[15px] max-nav:grid-cols-[52px_minmax(0,1fr)] max-nav:gap-x-3"
                >
                  <span className="font-mono text-xs font-medium tracking-[0.05em] text-red-ink">{row.label}</span>
                  <span className="flex min-w-0 flex-col gap-0.5">
                    <span className="font-semibold [overflow-wrap:anywhere]">
                      <MarkdownInline>{row.title}</MarkdownInline>
                    </span>
                    <span className="text-[13px] text-muted-foreground">{when(row.due)}</span>
                  </span>
                  <span className="text-right text-[13px] text-muted-foreground max-nav:col-start-2 max-nav:text-left">
                    {where(row.chapter)}
                  </span>
                </li>
              ))}
            </ol>
            <Link
              href={`${PATH}?start=${due.flash_cards.length ? "cards" : "quiz"}`}
              className={buttonVariants({ size: "lg", className: "self-start" })}
            >
              Start
            </Link>
          </>
        ) : (
          <EmptyState
            art="results"
            title="Nothing to revise again today"
            action={
              <Link href="/account/learning/" className={buttonVariants({ variant: "primary" })}>
                Back to Learning
              </Link>
            }
          >
            <p>
              What you get wrong in a quiz, and the flash cards you mark &quot;Not yet&quot;, come back here 1, 3 and 7
              days later.
            </p>
          </EmptyState>
        )}
      </div>
      <div className="flex min-w-0 flex-[1_1_320px] flex-col">
        {settings instanceof ApiError ? (
          <Problem error={settings} what="Your course settings" retry={PATH} />
        ) : (
          <CourseSettings settings={settings} planLine={planLine(plan)} consentPending={consentPending} />
        )}
      </div>
    </div>
  );
}
