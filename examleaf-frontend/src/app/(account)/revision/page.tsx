// /revision/: the revision course (Django's learn/revision.html; the course itself is in the app). For everyone: what
// it is, each subject's chapters with the Board's marks and past questions, what is free. Signed in: what is open
// (learn/entitlements/), each chapter's state and free clip, the book-code form and a plan for the exam date.
// Public and indexed (sitemap.ts); the signed-in parts are read with the visitor's cookies, never cached.
import Link from "next/link";

import { ConsentPending, Problem } from "@/components/account/parts";
import { AppLinks, EntitlementList, LogInToUse } from "@/components/revision/course";
import { FreeClip, PlanPreview, RedeemForm } from "@/components/revision/islands";
import { Accordion } from "@/components/ui/accordion";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Table, TableCell, TableHead } from "@/components/ui/table";
import { getMe, getSubjects } from "@/lib/api/account";
import { ApiError, unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { personalFetch, publicFetch, serverApi } from "@/lib/api/server";
import { withNext } from "@/lib/auth/next-url";
import { getSessionUser } from "@/lib/auth/session";
import { dateInIndia } from "@/lib/dates";
import { pageMetadata } from "@/lib/seo/metadata";

export const metadata = pageMetadata({
  title: "Revision course",
  path: "/revision/",
  description:
    "The ExamLeaf revision course for the Assam Board (ASSEB) Class 12 examination: every chapter revised in short clips, flash cards and one-mark quiz questions, in the ExamLeaf app.",
});

type Chapter = components["schemas"]["Chapter"];
const failed = (error: unknown) => (error instanceof ApiError ? error : new ApiError(0, "unavailable", ""));

export default async function RevisionPage() {
  const path = "/revision/";
  const user = await getSessionUser();
  const options = user ? await personalFetch() : publicFetch("chapters");
  const [chapters, subjects, entitlements, learner, me] = await Promise.all([
    unwrap(serverApi.GET("/api/v1/learn/chapters/", { params: { query: { page_size: 200 } }, ...options })).catch(
      failed,
    ),
    getSubjects().catch(() => []),
    user ? unwrap(serverApi.GET("/api/v1/learn/entitlements/", options)).catch(failed) : null,
    user ? unwrap(serverApi.GET("/api/v1/learn/settings/", options)).catch(() => null) : null,
    user ? getMe().catch(() => null) : null,
  ]);
  const name = (id: number) => subjects.find((subject) => subject.id === id)?.name ?? "Subject";
  const bySubject = new Map<number, Chapter[]>();
  if (!(chapters instanceof ApiError)) {
    for (const chapter of chapters.results)
      bySubject.set(chapter.subject, [...(bySubject.get(chapter.subject) ?? []), chapter]);
  }

  return (
    <section className="pt-7 pb-(--section)">
      <div className="container-site flex flex-col gap-6">
        <Breadcrumb trail={[{ label: "Home", href: "/" }, { label: "Revision course" }]} />
        <div className="flex max-w-(--measure) flex-col gap-2 [&>*]:m-0">
          <p className="text-[15px] font-semibold text-muted-foreground">In the ExamLeaf app · ASSEB Class 12</p>
          <h1>Revision course</h1>
          <p className="text-lead">
            Each chapter revised in 10 to 15 minutes: short clips on its concepts, formulas, shortcuts and the questions
            the Board likes to ask, then flash cards and one-mark quiz questions. The app plans what to watch each day
            until your exam, the chapters worth the most marks first.
          </p>
        </div>

        <div className="flex flex-wrap items-start gap-8">
          <div className="flex min-w-0 flex-[999_1_600px] flex-col gap-4 [&>h2]:m-0 [&>p]:m-0">
            <h2 className="text-title">Chapters and their marks</h2>
            <p className="text-muted-foreground">
              The marks the Board gives each chapter, and how many of its questions the Board has set in past papers.
            </p>
            {chapters instanceof ApiError ? (
              <Problem error={chapters} what="The course's chapters" retry={path} />
            ) : bySubject.size ? (
              [...bySubject].map(([subject, rows], index) => (
                <Accordion
                  key={subject}
                  summary={`${name(subject)} · ${rows.length} chapter${rows.length === 1 ? "" : "s"}`}
                  open={index === 0}
                >
                  <Table caption={`${name(subject)}: each chapter's marks and past questions`}>
                    <thead>
                      <tr>
                        <TableHead numeric>Ch.</TableHead>
                        <TableHead>Chapter</TableHead>
                        <TableHead numeric>Marks</TableHead>
                        <TableHead numeric>Past questions</TableHead>
                        {user ? <TableHead>For you</TableHead> : null}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((chapter) => (
                        <tr key={chapter.id}>
                          <TableCell numeric>{chapter.number}</TableCell>
                          <TableCell className="min-w-56">
                            <span className="block">{chapter.title}</span>
                            <span className="block text-[15px] text-muted-foreground">
                              {chapter.clips} clip{chapter.clips === 1 ? "" : "s"}, {chapter.minutes} min
                            </span>
                            {user ? (
                              <FreeClip chapter={chapter.id} title={chapter.title} />
                            ) : (
                              <Link
                                href={withNext("/account/login/", path)}
                                className="inline-flex min-h-11 items-center text-[15px] font-semibold"
                              >
                                Log in to watch its free clip
                              </Link>
                            )}
                          </TableCell>
                          <TableCell numeric>{Number(chapter.weight ?? 0)}</TableCell>
                          <TableCell numeric>{chapter.frequency ?? 0}</TableCell>
                          {user ? (
                            <TableCell>
                              {chapter.entitled ? (
                                <Badge variant="easy">Open</Badge>
                              ) : (
                                <span className="text-[15px]">
                                  Locked{chapter.free_cards ? "; its flash cards are free" : ""}
                                </span>
                              )}
                              {chapter.progress ? (
                                <span className="block text-[15px] text-muted-foreground">
                                  {chapter.progress}% watched
                                </span>
                              ) : null}
                            </TableCell>
                          ) : null}
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </Accordion>
              ))
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
            <h2 className="text-title">What is free</h2>
            <p>
              Log in with your ExamLeaf account: the first clip of every chapter is free, and so are the flash cards of
              each subject&apos;s first chapter. A code printed in your ExamLeaf book, or the course bought in the{" "}
              <Link href="/shop/">shop</Link>, opens the whole subject for a year.
            </p>
          </div>

          <aside className="flex min-w-0 flex-[1_1_300px] flex-col gap-6" aria-label="Your course">
            <Card>
              <CardHeader>
                <CardTitle>Your course</CardTitle>
              </CardHeader>
              <CardContent>
                {!user ? (
                  <LogInToUse path={path} />
                ) : (
                  <>
                    {entitlements instanceof ApiError ? (
                      entitlements.status === 403 ? (
                        <Alert variant="warning">
                          <p>{entitlements.message}</p>
                        </Alert>
                      ) : (
                        <Problem error={entitlements} what="What is open to you" retry={path} />
                      )
                    ) : entitlements?.results.length ? (
                      <EntitlementList entitlements={entitlements.results} today={dateInIndia()} />
                    ) : (
                      <p>Nothing is open in your account yet, apart from the free clips.</p>
                    )}
                    {me?.consent_pending ? (
                      <ConsentPending what="you can watch the free clips but not use a book code" />
                    ) : null}
                    <RedeemForm />
                  </>
                )}
              </CardContent>
            </Card>
            {user && !(entitlements instanceof ApiError && entitlements.status === 403) ? (
              <Card>
                <CardHeader>
                  <CardTitle>Plan to your exam</CardTitle>
                  <CardDescription>
                    The clips you have not watched, day by day, the chapters worth the most marks first.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <PlanPreview
                    examDate={learner?.exam_date ?? null}
                    minutesPerDay={learner?.minutes_per_day ?? 30}
                    subjects={subjects.map((subject) => ({ id: subject.id, name: subject.name }))}
                  />
                </CardContent>
              </Card>
            ) : null}
            <Card>
              <CardHeader>
                <CardTitle>Get the app</CardTitle>
                <CardDescription>Log in there with the same email address as on this site.</CardDescription>
              </CardHeader>
              <CardContent>
                <AppLinks />
              </CardContent>
            </Card>
          </aside>
        </div>
      </div>
    </section>
  );
}
