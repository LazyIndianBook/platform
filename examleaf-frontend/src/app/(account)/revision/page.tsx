// /revision/ (Account artboard "Revision course", Phone "Phone revision course"; Django's learn/revision.html; the
// course itself is in the app): for everyone, what it is, each subject's chapters with the Board's marks and past
// questions in the mono voice, what is free. Signed in: what is open (learn/entitlements/), each chapter's state and
// free clip, the book-code form (used and unrecognised codes said in words), a plan for the exam date. Every chapter
// is listed with its marks; one without a published revision yet is "Coming soon". #chapters, #plan and #app are its
// sections. Public and indexed (sitemap.ts); the signed-in parts are read with the visitor's cookies, never cached.
import "./revision.css";

import Link from "next/link";

import { ConsentPending, goLink, Problem } from "@/components/account/parts";
import { AppLinks, EntitlementList, LogInToUse } from "@/components/revision/course";
import { FreeClip, PlanPreview, RedeemForm } from "@/components/revision/islands";
import { Accordion } from "@/components/ui/accordion";
import { Alert } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { getMe, getSubjects } from "@/lib/api/account";
import { getConfig } from "@/lib/api/config";
import { ApiError, unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { personalFetch, publicFetch, serverApi } from "@/lib/api/server";
import { withNext } from "@/lib/auth/next-url";
import { getSessionUser } from "@/lib/auth/session";
import { dateInIndia } from "@/lib/dates";
import { breadcrumbJsonLd, JsonLd } from "@/lib/seo/json-ld";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({
  title: "Revision course",
  path: "/revision/",
  description:
    "The ExamLeaf revision course for the Assam Board (ASSEB) Class 12 examination: every chapter revised in short clips, flash cards and one-mark quiz questions, in the ExamLeaf app.",
});

type Chapter = components["schemas"]["Chapter"];
const failed = (error: unknown) => (error instanceof ApiError ? error : new ApiError(0, "unavailable", ""));
const asideTitle = "m-0 text-[22px] leading-[1.2] max-nav:text-lg";

/** What a chapter is for this student: coming, open (and how much watched), or locked. */
function forYou(chapter: Chapter): { text: string; tone: string } {
  if (!chapter.has_revision) return { text: "Coming soon", tone: "text-muted-foreground" };
  if (chapter.entitled) {
    return { text: `Open${chapter.progress ? ` · ${chapter.progress}% watched` : ""}`, tone: "text-easy" };
  }
  return { text: `Locked${chapter.free_cards ? "; its flash cards are free" : ""}`, tone: "text-foreground" };
}

export default async function RevisionPage() {
  const path = "/revision/";
  const user = await getSessionUser();
  const options = user ? await personalFetch() : publicFetch("chapters");
  const [chapters, subjects, entitlements, learner, me, config] = await Promise.all([
    unwrap(serverApi.GET("/api/v1/learn/chapters/", { params: { query: { page_size: 200 } }, ...options })).catch(
      failed,
    ),
    getSubjects().catch(() => []),
    user ? unwrap(serverApi.GET("/api/v1/learn/entitlements/", options)).catch(failed) : null,
    user ? unwrap(serverApi.GET("/api/v1/learn/settings/", options)).catch(() => null) : null,
    user ? getMe().catch(() => null) : null,
    getConfig(),
  ]);
  const name = (id: number) => subjects.find((subject) => subject.id === id)?.name ?? "Subject";
  const bySubject = new Map<number, Chapter[]>();
  if (!(chapters instanceof ApiError)) {
    for (const chapter of chapters.results)
      bySubject.set(chapter.subject, [...(bySubject.get(chapter.subject) ?? []), chapter]);
  }
  const refused = entitlements instanceof ApiError && entitlements.status === 403;

  return (
    <div className="revision">
      <JsonLd
        data={breadcrumbJsonLd([
          { name: "Home", path: "/" },
          { name: "Revision course", path: "/revision/" },
        ])}
      />
      <div className="rv-margin" aria-hidden="true">
        ▶
      </div>

      <div className="rv-hero flex flex-col gap-[22px] [&>*]:m-0">
        <p className="label-mono uppercase max-nav:text-[11px]">In the ExamLeaf app · ASSEB Class 12</p>
        <h1 className="text-[clamp(36px,5vw,60px)] leading-none">Revision course</h1>
        <p className="max-w-[36em] text-lg leading-[1.65] text-ink/85 max-nav:text-[15px] max-nav:leading-relaxed">
          Each chapter revised in 10 to 15 minutes: short clips on its concepts, formulas, shortcuts and the questions
          the Board likes to ask, then flash cards and one-mark quiz questions. The app plans what to watch each day
          until your exam, the chapters worth the most marks first.
        </p>
      </div>

      {/* desktops: the right column; phones: between the course's promise and its chapters */}
      <div className="rv-aside">
        <section aria-labelledby="course-title" className="rv-course">
          <h2 id="course-title" className={asideTitle}>
            Your course
          </h2>
          {!user ? (
            <LogInToUse path={path} />
          ) : (
            <>
              {entitlements instanceof ApiError ? (
                refused ? (
                  <Alert variant="warning">
                    <p>{entitlements.message}</p>
                  </Alert>
                ) : (
                  <Problem error={entitlements} what="What is open to you" retry={path} />
                )
              ) : entitlements?.results.length ? (
                <EntitlementList entitlements={entitlements.results} today={dateInIndia()} />
              ) : (
                <p className="m-0 text-[15px]">Nothing is open in your account yet, apart from the free clips.</p>
              )}
              {me?.consent_pending ? (
                <ConsentPending
                  what="you can watch the free clips but not use a book code"
                  contact={me.parent_contact}
                />
              ) : null}
              <RedeemForm disabled={Boolean(me?.consent_pending)} />
            </>
          )}
        </section>
        <section id="plan" aria-labelledby="plan-title" className="rv-plan scroll-mt-4">
          <h2 id="plan-title" className={asideTitle}>
            Plan to your exam
          </h2>
          <p className="m-0 text-[15px] leading-normal text-ink/85">
            The clips you have not watched, day by day, the chapters worth the most marks first.
          </p>
          {user && !refused ? (
            <>
              <PlanPreview
                examDate={learner?.exam_date ?? null}
                minutesPerDay={learner?.minutes_per_day ?? 30}
                subjects={subjects.map((subject) => ({ id: subject.id, name: subject.name }))}
              />
              <Link href="/account/learning/" className={goLink}>
                See your plan in Learning →
              </Link>
            </>
          ) : user ? null : (
            <Link href={withNext("/account/login/", path)} className={goLink}>
              Log in to plan your days →
            </Link>
          )}
        </section>

        <section id="app" aria-labelledby="app-title" className="rv-app scroll-mt-4">
          <h2 id="app-title" className={asideTitle}>
            Get the app
          </h2>
          <p className="m-0 text-[15px] text-ink/85">Log in there with the same email address as on this site.</p>
          <AppLinks links={config?.app_links} qr />
        </section>
      </div>

      <div className="rv-chapters flex flex-col gap-4 [&>h2]:m-0 [&>p]:m-0">
        <h2 id="chapters" className="scroll-mt-4 text-[30px] leading-[1.15] max-nav:text-2xl">
          Chapters and their marks
        </h2>
        <p className="text-[15px] text-muted-foreground">
          The marks the Board gives each chapter, and how many of its questions the Board has set in past papers.
        </p>
        {chapters instanceof ApiError ? (
          <Problem error={chapters} what="The course's chapters" retry={path} />
        ) : bySubject.size ? (
          <div className="border-t-[1.5px] border-foreground [&_details.accordion:first-child]:border-t-0">
            {[...bySubject].map(([subject, rows], index) => (
              <Accordion
                key={subject}
                summary={`${name(subject)} · ${rows.length} chapter${rows.length === 1 ? "" : "s"}`}
                open={index === 0}
              >
                <div
                  aria-hidden="true"
                  className="grid grid-cols-[48px_minmax(0,1fr)_70px_110px_150px] gap-3 border-b border-foreground py-2 font-mono text-xs text-muted-foreground max-nav:hidden"
                >
                  <span>CH.</span>
                  <span>CHAPTER</span>
                  <span className="text-right">MARKS</span>
                  <span className="text-right">PAST Qs</span>
                  <span>{user ? "FOR YOU" : ""}</span>
                </div>
                <ol
                  aria-label={`${name(subject)}: each chapter`}
                  className="m-0 list-none p-0 max-nav:border-t max-nav:border-border"
                >
                  {rows.map((chapter) => {
                    const state = forYou(chapter);
                    return (
                      <li
                        key={chapter.id}
                        className="grid grid-cols-[minmax(0,1fr)_44px] items-start gap-2 border-b border-border py-2.5 text-[15px] nav:grid-cols-[48px_minmax(0,1fr)_70px_110px_150px] nav:gap-3 nav:py-3"
                      >
                        <span className="font-mono max-nav:hidden">{chapter.number}</span>
                        <span className="flex min-w-0 flex-col items-start gap-0.5">
                          {/* WEB COURSE (config.web_course): the LMS package mounts the chapter's own page here, the
                              title becoming <Link href={`/revision/<subject>/${chapter.number}/`}>, with <subject>
                              the subject's slug in its routes. Not linked yet: nothing is handed over. */}
                          <span className="font-semibold">
                            <span className="nav:hidden">{chapter.number}. </span>
                            {chapter.title}
                          </span>
                          <span className="text-sm text-muted-foreground max-nav:hidden">
                            {chapter.has_revision
                              ? `${chapter.clips} clip${chapter.clips === 1 ? "" : "s"}, ${chapter.minutes} min`
                              : "Coming soon"}
                          </span>
                          {user || !chapter.has_revision ? (
                            <span className={`text-[13px] nav:hidden ${state.tone}`}>{state.text}</span>
                          ) : null}
                          {!chapter.has_revision ? null : user ? (
                            <FreeClip clip={chapter.free_preview} title={chapter.title} label="Watch its free clip" />
                          ) : (
                            <Link
                              href={withNext("/account/login/", path)}
                              className="inline-flex min-h-11 items-center text-sm font-bold"
                            >
                              Log in to watch its free clip
                            </Link>
                          )}
                        </span>
                        <span className="text-right font-mono max-nav:text-sm max-nav:leading-[1.4] max-nav:font-semibold max-nav:text-red-ink">
                          <span aria-hidden="true" className="nav:hidden">
                            [
                          </span>
                          {Number(chapter.weight ?? 0)}
                          <span aria-hidden="true" className="nav:hidden">
                            ]
                          </span>
                          <span className="sr-only"> marks</span>
                        </span>
                        <span className="text-right font-mono max-nav:hidden">
                          {chapter.frequency ?? 0}
                          <span className="sr-only"> past questions</span>
                        </span>
                        <span className={`text-sm font-semibold max-nav:hidden ${state.tone}`}>
                          {user ? state.text : chapter.has_revision ? "" : state.text}
                        </span>
                      </li>
                    );
                  })}
                </ol>
              </Accordion>
            ))}
          </div>
        ) : (
          <EmptyState
            art="sheet"
            title="The chapters are being prepared"
            action={
              <Link href="/#books" className={buttonVariants({ variant: "primary" })}>
                Choose a book
              </Link>
            }
          >
            <p>The course opens subject by subject. The papers and their free solutions are ready now.</p>
          </EmptyState>
        )}
        <h2 className="mt-3 text-[26px] leading-[1.15] max-nav:text-xl">What is free</h2>
        <p className="max-w-[40em] text-base leading-[1.7] text-ink/85">
          Log in with your ExamLeaf account: the first clip of every chapter is free, and so are the flash cards of each
          subject&apos;s first chapter. A code printed in your ExamLeaf book, or the course bought in the{" "}
          <Link href="/shop/">shop</Link>, opens the whole subject for a year.
        </p>
      </div>
    </div>
  );
}
