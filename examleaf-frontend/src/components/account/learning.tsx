// Learning's parts (/account/learning/, GET me/learning/), drawn from the API's numbers without any state: a chapter's
// progress bar (CSS, no chart library), the quiz's share right, the clip to continue with, a subject's chapters, the
// plan's next days, the streak in words, and My account's summary of it all. Nothing here moves (motion.md: reading
// surfaces stay still); the only islands are the player (FreeClip) and the exam-date form, both in revision/islands.
import Link from "next/link";

import { CompactEmpty } from "@/components/account/parts";
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
      <span aria-hidden="true" className="h-2 min-w-16 flex-1 overflow-hidden rounded-pill bg-muted">
        <span data-bar="" className="block h-full rounded-pill bg-primary" style={{ width: `${share}%` }} />
      </span>
      <span className="shrink-0 text-[15px] text-muted-foreground tabular-nums">
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

/** The next clip of the revision watched last: played here when it is free or open, else what opens it. */
export function ContinueCard({ next, hasAppLinks }: { next: Continue | null; hasAppLinks: boolean }) {
  if (!next) {
    return (
      <CompactEmpty art="sheet">
        <p>
          Nothing to continue yet. The first clip of every chapter is free: pick one in the{" "}
          <Link href="/revision/#chapters">Revision course</Link>.
        </p>
      </CompactEmpty>
    );
  }
  const { clip, chapter, revision } = next;
  return (
    <div className="flex flex-col gap-3 [&_p]:m-0">
      <div className="flex flex-col gap-1">
        <p className="text-[15px] text-muted-foreground">
          {chapter.subject_name} · Ch. {chapter.number} {chapter.title}
        </p>
        <p className="font-head text-[19px] leading-snug font-bold">{clip.title}</p>
        <p className="text-[15px] text-muted-foreground">
          {KIND[clip.kind]} · {minutes(clip.duration)} min · {revision.title}
        </p>
      </div>
      {clip.locked ? (
        <p>
          This clip opens with the course: use the code printed in your book on the{" "}
          <Link href="/revision/">Revision course</Link> page, or get the course in the <Link href="/shop/">shop</Link>.
        </p>
      ) : (
        <>
          <FreeClip clip={clip.id} title={clip.title} label="Play it here" />
          <p className="text-[15px] text-muted-foreground">
            Watching here is not counted: the ExamLeaf app keeps your progress, quiz and flash cards.{" "}
            {hasAppLinks ? <Link href="/revision/#app">Get the app</Link> : "The app is coming to the stores soon."}
          </p>
        </>
      )}
    </div>
  );
}

/** A subject's clips, minutes and quiz, then a bar for each chapter. */
export function SubjectProgress({ subject }: { subject: Subject }) {
  return (
    <section aria-labelledby={`subject-${subject.id}`} className="flex flex-col gap-3 [&_p]:m-0">
      <div className="flex flex-wrap items-center gap-2">
        <h3 id={`subject-${subject.id}`} className="m-0 text-[19px]">
          {subject.name}
        </h3>
        <QuizBadge accuracy={subject.quiz_accuracy} answers={subject.quiz_answers} />
        {subject.entitled ? null : <Badge>Free clips only</Badge>}
      </div>
      <p className="text-[15px] text-muted-foreground">
        {subject.clips_watched} of {plural(subject.clips_total, "clip")} watched, {subject.minutes_watched} min
        {subject.last_activity ? ` · last on ${formatDate(subject.last_activity)}` : ""}
      </p>
      <ul aria-label={`${subject.name}: each chapter`} className="m-0 flex list-none flex-col gap-3 p-0">
        {subject.chapters.map((chapter) => (
          <li key={chapter.id} className="flex flex-col gap-1.5">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
              <span className="font-semibold">
                Ch. {chapter.number} {chapter.title}
              </span>
              <QuizBadge accuracy={chapter.quiz_accuracy} answers={chapter.quiz_answers} />
            </div>
            <ProgressBar done={chapter.clips_watched} total={chapter.clips_total} />
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The plan's first days (or the API's reason there are none), as the revision page's plan draws its days. */
export function NextDaysList({ plan }: { plan: NextDays }) {
  if (!plan.days.length) return <p className="m-0">{plan.hint}</p>;
  return (
    <ol aria-label="Your next days" className="m-0 flex list-none flex-col gap-2 p-0">
      {plan.days.map((day) => (
        <li key={day.date} className="rounded-lg border border-border px-3 py-2">
          <span className="font-semibold">
            {formatDate(day.date)} · {day.minutes} min
          </span>
          <ul className="m-0 pl-5 text-[15px]">
            {day.clips.map((clip) => (
              <li key={clip.id}>
                {clip.title} ({minutes(clip.duration)} min)
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ol>
  );
}

/** The streak as a quiet line, or nothing before the first day. */
export function streakWords(streak: Streak): string | null {
  if (streak.days)
    return `${plural(streak.days, "day")} of revision in a row${streak.today ? "" : ", up to yesterday"}.`;
  return streak.last_day ? `Last revised on ${formatDate(streak.last_day)}.` : null;
}

/** My account's Learning card: what comes next, what was watched, what is due again; or where to begin. */
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
