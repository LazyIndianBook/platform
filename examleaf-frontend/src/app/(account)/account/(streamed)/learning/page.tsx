// /account/learning/ (Account artboard "Learning", Phone "Phone learning"): the revision course as the student has used
// it (GET me/learning/, read per request and never stored): the clip to continue with on the vertical player, the plan
// to the exam (its date and minutes a day, the next three days) and the revise-again count, then each open subject's
// chapters with their bars and the QUIZ column, and the subjects tried for free. The streak is the quiet line on the
// right. A server component; islands only for the player and the plan's form. The quiz, flash cards and the progress
// itself are kept by the app.
import Link from "next/link";

import {
  ContinueCard,
  NextDaysList,
  streakWords,
  SubjectProgress,
  SubjectSummary,
} from "@/components/account/learning";
import { CompactEmpty, ConsentPending, goLink, PageHead, Problem, SectionHead } from "@/components/account/parts";
import { ReviseAgainLink } from "@/components/course/course-links";
import { ExamDateForm } from "@/components/revision/islands";
import { settle } from "@/lib/api/account";
import { ApiError, unwrap } from "@/lib/api/errors";
import { personalFetch, serverApi } from "@/lib/api/server";
import { dateInIndia } from "@/lib/dates";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({
  title: "Learning",
  path: "/account/learning/",
  description: "Your revision course: where you left off, what you watched, what to revise and the days ahead.",
  noindex: true,
});

export default async function LearningPage() {
  const path = "/account/learning/";
  const learning = await settle(unwrap(serverApi.GET("/api/v1/me/learning/", await personalFetch())), path);
  if (learning instanceof ApiError) {
    return (
      <>
        <PageHead title="Learning" />
        <Problem error={learning} what="Your learning" retry={path} />
      </>
    );
  }
  const { plan, revise_again: revise } = learning;
  const today = dateInIndia();
  const until = (subject: number) =>
    learning.entitlements.find(
      (item) => (item.subject === subject || item.subject == null) && (!item.valid_until || item.valid_until >= today),
    )?.valid_until;
  const open = learning.subjects.filter((subject) => subject.entitled);
  const tried = learning.subjects.filter((subject) => !subject.entitled);

  return (
    <>
      <PageHead title="Learning" aside={streakWords(learning.streak)} />
      {learning.consent_pending ? (
        <ConsentPending what="you can watch and read here, but nothing you watch, answer or plan is saved" />
      ) : null}

      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <ContinueCard next={learning.continue_watching} hasAppLinks={learning.has_app_links} />
        <section aria-labelledby="plan-title" className="flex flex-col gap-3.5">
          <SectionHead id="plan-title" title="Plan to your exam" />
          <ExamDateForm examDate={plan.exam_date} minutesPerDay={plan.minutes_per_day} />
          <NextDaysList plan={plan} />
          {revise.due_today ? (
            <p className="m-0 flex items-baseline gap-3 pt-1">
              <span className="font-head text-4xl leading-none font-semibold tabular-nums max-nav:text-3xl">
                {revise.due_today}
              </span>
              <span className="text-[15px] text-ink/85">to revise again today, in the app</span>
            </p>
          ) : (
            <p className="m-0 text-[15px] text-ink/85">
              Nothing to revise again today. What you get wrong in the quiz and the flash cards comes back 1, 3 and 7
              days later.
            </p>
          )}
          {revise.later ? (
            <p className="m-0 text-sm text-muted-foreground">
              {revise.later} more {revise.later === 1 ? "comes" : "come"} back on later days.
            </p>
          ) : null}
          {/* the web course's Revise again page: drawn only while config.web_course is on */}
          <ReviseAgainLink className={goLink}>Revise again here →</ReviseAgainLink>
          <Link href="/revision/#plan" className={goLink}>
            The whole plan, and the minimum to pass →
          </Link>
        </section>
      </div>

      {open.map((subject) => (
        <SubjectProgress key={subject.id} subject={subject} until={until(subject.id)} />
      ))}
      {tried.length ? (
        <div className="grid gap-6 lg:grid-cols-3">
          {tried.map((subject) => (
            <SubjectSummary key={subject.id} subject={subject} />
          ))}
        </div>
      ) : null}
      {learning.subjects.length ? null : (
        <CompactEmpty
          title="No clip watched yet"
          actions={
            <Link href="/revision/">
              {learning.entitlements.length ? "Open the Revision course →" : "Use the code printed in your book →"}
            </Link>
          }
        >
          <p>Each chapter shows how much of it you have watched, and your quiz score.</p>
          <p>
            {learning.entitlements.length
              ? "Your course is open: start with any chapter."
              : "Nothing is open in your account yet, apart from the free clips."}
          </p>
        </CompactEmpty>
      )}
    </>
  );
}
