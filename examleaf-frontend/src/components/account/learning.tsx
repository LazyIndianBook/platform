// Learning's parts (/account/learning/ and My account, GET me/learning/), drawn from the API's numbers without any
// state: a chapter's progress bar (CSS, no chart library), the quiz's share right, the clip to continue with, a
// subject's chapters with the QUIZ column, the plan's next days, the streak in words. Nothing here moves (motion.md:
// reading surfaces stay still); the only islands are the player (FreeClip) and the plan's form, both in
// revision/islands.
import Link from "next/link";

import { CompactEmpty } from "@/components/account/parts";
import { DayList } from "@/components/revision/course";
import { FreeClip } from "@/components/revision/islands";
import { Badge } from "@/components/ui/badge";
import type { components } from "@/lib/api/schema";
import { formatDate } from "@/lib/dates";

export type Learning = components["schemas"]["Learning"];
type Continue = components["schemas"]["Continue"];
type Subject = components["schemas"]["LearningSubject"];
type NextDays = components["schemas"]["NextDays"];
type Streak = components["schemas"]["Streak"];

const KIND: Record<components["schemas"]["ClipKindEnum"], string> = {
  concept: "Concept",
  trick: "Trick",
  shortcut: "Shortcut",
  formula: "Formula",
  pattern: "Question pattern",
  mistake: "Common mistake",
  pyq: "Previous-year question",
};

const minutes = (seconds: number) => Math.max(1, Math.round(seconds / 60));
const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/** Clips watched of a chapter's clips: the bar is drawing only, the words beside it say it. */
export function ProgressBar({ done, total }: { done: number; total: number }) {
  const share = total ? Math.min(100, Math.round((100 * done) / total)) : 0;
  return (
    <div className="flex items-center gap-3">
      <span aria-hidden="true" className="h-2 min-w-16 flex-1 overflow-hidden bg-rule-soft">
        <span data-bar="" className="block h-full bg-primary" style={{ width: `${share}%` }} />
      </span>
      <span className="w-24 shrink-0 text-right text-sm text-muted-foreground tabular-nums">
        {total ? `${done} of ${plural(total, "clip")}` : "No clips yet"}
      </span>
    </div>
  );
}

/** The quiz's share right, in words (green only repeats a good share; a weak one stays calm): none before an answer. */
export function QuizBadge({ accuracy, answers }: { accuracy: number | null; answers: number }) {
  if (accuracy === null) return null;
  return (
    <Badge variant={accuracy >= 75 ? "easy" : "muted"}>
      Quiz {accuracy}% right<span className="sr-only"> of {plural(answers, "answer")}</span>
    </Badge>
  );
}

/** The QUIZ column's figure: the share right in the mono voice, green when good, a dash before any answer. */
function QuizScore({ accuracy, answers }: { accuracy: number | null; answers: number }) {
  if (accuracy === null) {
    return (
      <span className="font-mono text-[15px] text-muted-foreground">
        —<span className="sr-only">no quiz answer yet</span>
      </span>
    );
  }
  return (
    <span className={`font-mono text-[15px] font-semibold ${accuracy >= 75 ? "text-easy" : "text-foreground"}`}>
      <span className="sr-only">Quiz </span>
      {accuracy}%<span className="sr-only"> right of {plural(answers, "answer")}</span>
    </span>
  );
}

const eyebrow = "m-0 font-mono text-xs leading-none font-medium tracking-[0.08em] text-red-ink uppercase";

/** The next clip of the revision watched last: played here when it is free or open, else what opens it. `compact` is
 *  My account's card (a button); Learning gives it a stage the size of a poster. */
export function ContinueCard({
  next,
  hasAppLinks,
  compact = false,
}: {
  next: Continue | null;
  hasAppLinks: boolean;
  compact?: boolean;
}) {
  if (!next) {
    return (
      <CompactEmpty
        title="Nothing to continue yet"
        actions={<Link href="/revision/#chapters">Open the Revision course →</Link>}
      >
        <p>The first clip of every chapter is free: pick one in the Revision course.</p>
      </CompactEmpty>
    );
  }
  const { clip, chapter, revision } = next;
  const where = `${chapter.subject_name} · Ch. ${chapter.number} ${chapter.title}`;
  const what = `${KIND[clip.kind]} · ${minutes(clip.duration)} min · ${revision.title}`;
  const locked = (
    <p className="m-0 text-[15px] leading-normal">
      This clip opens with the course: use the code printed in your book on the{" "}
      <Link href="/revision/">Revision course</Link> page, or get the course in the <Link href="/shop/">shop</Link>.
    </p>
  );
  if (compact) {
    return (
      <div className="flex min-w-0 flex-col gap-2 border border-border bg-card p-6 max-nav:p-4 [&_p]:m-0">
        <h2 className={eyebrow}>Continue</h2>
        <p className="text-sm text-muted-foreground">{where}</p>
        <p className="font-head text-[22px] leading-tight font-semibold max-nav:text-xl">{clip.title}</p>
        <p className="text-sm text-muted-foreground">{what}</p>
        <div className="mt-1.5">
          {clip.locked ? locked : <FreeClip clip={clip.id} title={clip.title} label="Play it here" look="button" />}
        </div>
      </div>
    );
  }
  return (
    <div className="flex min-w-0 flex-col gap-3 [&_p]:m-0">
      {clip.locked ? null : <FreeClip clip={clip.id} title={clip.title} label="Play it here" look="stage" />}
      <h2 className={eyebrow}>Continue</h2>
      <p className="font-head text-[26px] leading-tight font-semibold max-nav:text-[21px]">{clip.title}</p>
      <p className="text-[15px] text-muted-foreground max-nav:text-[13px]">
        {where} · {what}
      </p>
      {clip.locked ? (
        locked
      ) : (
        <p className="text-[15px] leading-normal text-muted-foreground">
          Watching here is not counted: the ExamLeaf app keeps your progress, quiz and flash cards.{" "}
          {hasAppLinks ? <Link href="/revision/#app">Get the app</Link> : "The app is coming to the stores soon."}
        </p>
      )}
    </div>
  );
}

function subjectLine(subject: Subject, until?: string | null) {
  return [
    `${subject.clips_watched} of ${plural(subject.clips_total, "clip")} watched, ${subject.minutes_watched} min`,
    subject.last_activity ? `last on ${formatDate(subject.last_activity)}` : null,
    until ? `open until ${formatDate(until)}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

/** A subject open to the student: its clips, minutes and the day it ends, then each chapter's bar and quiz. */
export function SubjectProgress({ subject, until }: { subject: Subject; until?: string | null }) {
  return (
    <section aria-labelledby={`subject-${subject.id}`} className="flex flex-col">
      <div className="grid grid-cols-[minmax(0,1fr)_56px] border-t-[1.5px] border-foreground nav:grid-cols-[minmax(0,1fr)_140px]">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 pt-4 pb-2 [&>*]:m-0">
          <h2 id={`subject-${subject.id}`} className="text-[26px] leading-[1.2] max-nav:text-xl">
            {subject.name}
          </h2>
          <p className="text-[15px] text-muted-foreground max-nav:text-[13px]">{subjectLine(subject, until)}</p>
        </div>
        <span aria-hidden="true" className="pt-5 text-center font-mono text-xs text-muted-foreground">
          QUIZ
        </span>
      </div>
      <ul aria-label={`${subject.name}: each chapter`} className="m-0 list-none p-0">
        {subject.chapters.map((chapter) => (
          <li
            key={chapter.id}
            className="grid grid-cols-[minmax(0,1fr)_56px] border-b border-border nav:grid-cols-[minmax(0,1fr)_140px]"
          >
            <div className="grid items-center gap-x-6 gap-y-1.5 py-3 lg:grid-cols-[minmax(0,1fr)_260px]">
              <span className="font-semibold max-nav:text-sm">
                Ch. {chapter.number} {chapter.title}
              </span>
              <ProgressBar done={chapter.clips_watched} total={chapter.clips_total} />
            </div>
            <span className="flex items-center justify-center">
              <QuizScore accuracy={chapter.quiz_accuracy} answers={chapter.quiz_answers} />
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** A subject the student tried the free clips of: one bar and a line. */
export function SubjectSummary({ subject }: { subject: Subject }) {
  return (
    <section aria-labelledby={`subject-${subject.id}`} className="flex flex-col gap-2 border-t border-foreground pt-3">
      <h2 id={`subject-${subject.id}`} className="m-0 text-xl leading-[1.2]">
        {subject.name}
      </h2>
      <ProgressBar done={subject.clips_watched} total={subject.clips_total} />
      <p className="m-0 text-sm text-muted-foreground">
        {subject.entitled ? "Open" : "Free clips only"}
        {subject.quiz_accuracy === null ? "" : ` · Quiz ${subject.quiz_accuracy}% right`}
      </p>
    </section>
  );
}

/** The plan's first days (or the API's reason there are none). */
export function NextDaysList({ plan }: { plan: NextDays }) {
  if (!plan.days.length) return <p className="m-0 text-[15px] text-ink/85">{plan.hint}</p>;
  return <DayList days={plan.days} label="Your next days" />;
}

/** The streak as a quiet line, or nothing before the first day. */
export function streakWords(streak: Streak): string | null {
  if (streak.days)
    return `${plural(streak.days, "day")} of revision in a row${streak.today ? "" : ", up to yesterday"}.`;
  return streak.last_day ? `Last revised on ${formatDate(streak.last_day)}.` : null;
}

/** A summary of it all in a few lines (kept for callers outside My account, which draws its own cards). */
export function LearningSummary({ learning }: { learning: Learning }) {
  const watched = learning.subjects.reduce((sum, subject) => sum + subject.clips_watched, 0);
  const total = learning.subjects.reduce((sum, subject) => sum + subject.clips_total, 0);
  const next = learning.continue_watching;
  const lines = [
    next ? `Next: ${next.clip.title} (${next.chapter.subject_name}, Ch. ${next.chapter.number})` : null,
    total ? `${watched} of ${plural(total, "clip")} watched` : null,
    learning.revise_again.due_today ? `${learning.revise_again.due_today} to revise again today` : null,
    streakWords(learning.streak),
  ].filter((line): line is string => line !== null);
  if (!lines.length) {
    return <p>Nothing watched yet. The first clip of every chapter is free, and your progress shows here.</p>;
  }
  return (
    <ul className="m-0 flex flex-col gap-1 pl-5">
      {lines.map((line) => (
        <li key={line}>{line}</li>
      ))}
    </ul>
  );
}
