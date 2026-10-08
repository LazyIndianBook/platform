// /account/record/<id>/edit/: Edit on My record (Django's attempt_form.html): the saved marks of one attempt, changed
// with PATCH attempts/<id>/ (the paper stays). Someone else's attempt, or one deleted, is not found.
import Link from "next/link";
import { notFound } from "next/navigation";

import { MarksForm } from "@/components/account/marks-form";
import { PageHead, Problem } from "@/components/account/parts";
import { Card, CardContent, CardFooter } from "@/components/ui/card";
import { settle } from "@/lib/api/account";
import { ApiError, unwrap } from "@/lib/api/errors";
import { personalFetch, serverApi } from "@/lib/api/server";
import { pageMetadata } from "@/lib/seo/metadata";

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

  return (
    <>
      <PageHead title={`${attempt.paper} — your marks`} />
      <Card>
        <CardContent>
          <MarksForm paper={attempt.paper} fullMarks={attempt.full_marks} attempt={attempt} />
        </CardContent>
        <CardFooter>
          <Link href={`/s/${attempt.paper}/`} className="inline-flex min-h-11 items-center font-semibold">
            Back to the solutions
          </Link>
          <Link href="/account/record/" className="inline-flex min-h-11 items-center font-semibold">
            My record
          </Link>
        </CardFooter>
      </Card>
    </>
  );
}
