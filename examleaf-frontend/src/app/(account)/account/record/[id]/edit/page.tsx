// /account/record/<id>/edit/: Edit on My record (Account artboard "Record edit", Gaps "Record form full"): the saved
// marks of one attempt (all four fields: date, marks with one decimal, minutes, what to revise) through MarksForm,
// which PATCHes attempts/<id>/ (the paper stays); and Delete this record (DELETE attempts/<id>/). Someone else's
// attempt, or one deleted, is not found.
import Link from "next/link";
import { notFound } from "next/navigation";

import { DeleteAttempt } from "@/components/account/delete-attempt";
import { MarksForm } from "@/components/account/marks-form";
import { PageHead, Problem } from "@/components/account/parts";
import { settle } from "@/lib/api/account";
import { ApiError, unwrap } from "@/lib/api/errors";
import { personalFetch, serverApi } from "@/lib/api/server";
import { pageMetadata } from "@/lib/seo/metadata";
import { shortCode, subjectOf } from "@/lib/site";

export const metadata = pageMetadata({ title: "Record marks", path: "/account/record/", noindex: true });

export default async function EditAttemptPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const path = `/account/record/${id}/edit/`;
  const attempt = await settle(
    unwrap(
      serverApi.GET("/api/v1/attempts/{id}/", { params: { path: { id: Number(id) } }, ...(await personalFetch()) }),
    ),
    path,
  );
  if (attempt instanceof ApiError && attempt.status === 404) notFound();
  if (attempt instanceof ApiError) return <Problem error={attempt} what="These marks" retry={path} />;
  const subject = subjectOf(attempt.subject)?.name ?? attempt.subject;
  const code = shortCode(attempt.paper);

  return (
    <div className="flex max-w-[34rem] flex-col gap-4">
      <nav aria-label="Breadcrumb" className="text-[15px] text-muted-foreground">
        <Link href="/account/record/" className="font-semibold">
          My record
        </Link>{" "}
        / {subject} {code}
      </nav>
      <PageHead title={`${subject}, Paper ${code}`} />
      <MarksForm paper={attempt.paper} fullMarks={attempt.full_marks} attempt={attempt} />
      <div className="flex flex-wrap items-center gap-x-6 border-t border-border pt-2">
        <DeleteAttempt id={attempt.id} paper={attempt.paper} />
        <Link href={`/s/${attempt.paper}/`} className="inline-flex min-h-11 items-center text-[15px] font-semibold">
          The paper&apos;s solutions
        </Link>
      </div>
    </div>
  );
}
