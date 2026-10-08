// /account/learning/: the revision course as the student has used it (GET me/learning/, read per request and never
// stored): the clip to continue with, the plan's next three days with the exam date, the revise-again queue, progress
// per subject and chapter, what is open, and the streak as a quiet line. A server component; islands only for the
// player and the exam-date form. The quiz, flash cards and the progress itself are kept by the app.
import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { ContinueCard, NextDaysList, streakWords, SubjectProgress } from "@/components/account/learning";
import { CompactEmpty, ConsentPending, PageHead, Problem } from "@/components/account/parts";
import { EntitlementList } from "@/components/revision/course";
import { ExamDateForm } from "@/components/revision/islands";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { settle } from "@/lib/api/account";
import { ApiError, unwrap } from "@/lib/api/errors";
import { personalFetch, serverApi } from "@/lib/api/server";
import { dateInIndia, formatDate } from "@/lib/dates";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({
  title: "Learning",
  path: "/account/learning/",
  description: "Your revision course: where you left off, what you watched, what to revise and the days ahead.",
  noindex: true,
});

const goLink = "inline-flex min-h-11 items-center gap-1.5 font-semibold";

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

  return (
    <>
      <PageHead
        title="Learning"
        lead={streakWords(learning.streak) ?? "Where you left off, what you watched and what comes next."}
      />
      {learning.consent_pending ? (
        <ConsentPending what="you can watch and read here, but nothing you watch, answer or plan is saved" />
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Continue</CardTitle>
        </CardHeader>
        <CardContent>
          <ContinueCard next={learning.continue_watching} hasAppLinks={learning.has_app_links} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Your next three days</CardTitle>
          <CardDescription>
            {plan.exam_date && plan.days_left !== null
              ? `${plan.days_left} day${plan.days_left === 1 ? "" : "s"} to your exam on ${formatDate(plan.exam_date, "long")}, at ${plan.minutes_per_day} minutes a day: the clips you have not watched, the chapters worth the most marks first.`
              : "The clips you have not watched, day by day until your exam, the chapters worth the most marks first."}
          </CardDescription>
        </CardHeader>
        <CardContent className="gap-4">
          <NextDaysList plan={plan} />
          <ExamDateForm examDate={plan.exam_date} />
        </CardContent>
        <CardFooter>
          <Link href="/revision/#plan" className={goLink}>
            The whole plan, and the minimum to pass
            <ArrowRight aria-hidden="true" className="size-5" />
          </Link>
        </CardFooter>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Revise again</CardTitle>
          <CardDescription>
            The quiz questions and flash cards you got wrong come back 1, 3 and 7 days later, in the app.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {revise.due_today || revise.later ? (
            <p>
              <strong className="font-head text-[22px] tabular-nums">{revise.due_today}</strong> due today ·{" "}
              {revise.later} later
            </p>
          ) : (
            <CompactEmpty art="results">
              <p>Nothing to revise again. What you get wrong in the quiz and the flash cards comes back here.</p>
            </CompactEmpty>
          )}
        </CardContent>
        <CardFooter>
          <Link href={learning.has_app_links ? "/revision/#app" : "/revision/#chapters"} className={goLink}>
            {learning.has_app_links ? "Revise them in the app" : "The chapters and their quiz"}
            <ArrowRight aria-hidden="true" className="size-5" />
          </Link>
        </CardFooter>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Progress</CardTitle>
          <CardDescription>The subjects open to you, and those whose free clips you tried.</CardDescription>
        </CardHeader>
        <CardContent className="gap-6">
          {learning.subjects.length ? (
            learning.subjects.map((subject) => <SubjectProgress key={subject.id} subject={subject} />)
          ) : (
            <CompactEmpty art="attempts">
              <p>No clip watched yet. Each chapter shows how much of it you have watched, and your quiz score.</p>
            </CompactEmpty>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Your course</CardTitle>
        </CardHeader>
        <CardContent>
          {learning.entitlements.length ? (
            <EntitlementList entitlements={learning.entitlements} today={dateInIndia()} />
          ) : (
            <p>Nothing is open in your account yet, apart from the free clips.</p>
          )}
        </CardContent>
        <CardFooter>
          <Link href="/revision/" className={goLink}>
            {learning.entitlements.length ? "All chapters, and the app" : "Use the code printed in your book"}
            <ArrowRight aria-hidden="true" className="size-5" />
          </Link>
        </CardFooter>
      </Card>
    </>
  );
}
