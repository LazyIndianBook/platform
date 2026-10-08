// /c/<token>/: a parent's link (email or SMS, valid 7 days) to confirm the account of a student under 18, through
// GET and POST /api/v1/parent-consent/<token>/. "I agree" is a server action, so it works without any script on the
// parent's phone; the page names the student only to whoever holds the link, and is never indexed or cached.
import { CircleCheck } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Unavailable } from "@/components/site/unavailable";
import { Alert } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SubmitButton } from "@/components/ui/submit-button";
import { unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { personalFetch, serverApi } from "@/lib/api/server";

export const metadata: Metadata = {
  title: "A parent's consent",
  description: "A parent or guardian confirms the ExamLeaf account of a student under 18.",
  robots: { index: false, follow: false },
};

type ParentLink = components["schemas"]["ParentLink"];
type Props = { params: Promise<{ token: string }> };

async function load(token: string): Promise<ParentLink | null> {
  const response = await serverApi
    .GET("/api/v1/parent-consent/{token}/", { params: { path: { token } }, ...(await personalFetch()) })
    .catch(() => null);
  if (!response) return null;
  // 400 is an expired or replaced link: its body says so
  return response.data ?? (response.response.status === 400 ? (response.error as ParentLink) : null) ?? null;
}

export default async function ParentConsentPage({ params }: Props) {
  const { token } = await params;
  const link = await load(token);
  if (!link) return <Unavailable what="This page" retry={`/c/${token}/`} />;

  async function agree() {
    "use server";
    await unwrap(
      serverApi.POST("/api/v1/parent-consent/{token}/", { params: { path: { token } }, ...(await personalFetch()) }),
    );
    redirect(`/c/${token}/`);
  }

  return (
    <section className="pt-7 pb-(--section)">
      <div className="container-site max-w-[calc(38rem+2*var(--gutter))]">
        <Card>
          <CardHeader>
            <CardTitle as="h1" className="text-h1-card">
              A parent&apos;s consent
            </CardTitle>
          </CardHeader>
          <CardContent>
            {link.status === "expired" ? (
              <>
                <Alert variant="warning" title="This link does not work any more">
                  <p>
                    A link works for {link.days} days, and only the latest one sent. Ask{" "}
                    {link.first_name || "your child"} to send a new one: on My account, they press Send the link again.
                  </p>
                </Alert>
                <p>
                  Cannot reach them? <Link href="/contact/">Contact us</Link> and we will help.
                </p>
                <p className="text-muted-foreground">
                  Are you the student? <Link href="/account/login/?next=/account/">Log in</Link> and send the link again
                  from My account.
                </p>
              </>
            ) : link.status === "confirmed" ? (
              <>
                <Alert variant="success">
                  <p>
                    Thank you. {link.student_name}&apos;s account is confirmed: they can now save their marks and order
                    books.
                  </p>
                </Alert>
                <p className="text-muted-foreground">
                  Nothing more to do: you can close this page. To see what we keep, read the{" "}
                  <Link href="/privacy/">privacy notice</Link>; for anything else,{" "}
                  <Link href="/contact/">contact us</Link>.
                </p>
              </>
            ) : (
              <>
                <p>
                  <strong>{link.student_name}</strong> ({link.student_email}) has registered at ExamLeaf and gave your{" "}
                  {link.contact === "phone" ? "mobile number" : "email address"} as their parent&apos;s or
                  guardian&apos;s. ExamLeaf keeps their name, email address, class, board, district and date of birth,
                  and the marks they save, so that they can use the free solutions of the ExamLeaf sample papers.
                </p>
                <p>
                  <Link href="/privacy/" target="_blank" rel="noopener">
                    Read the privacy notice
                  </Link>
                  : what we keep, why, for how long, and how you can see, correct or delete it.
                </p>
                <form action={agree}>
                  <SubmitButton size="lg">
                    <CircleCheck aria-hidden="true" />I am their parent or guardian, and I agree
                  </SubmitButton>
                </form>
                <p className="text-muted-foreground">
                  If you do not agree, you need not do anything: the account cannot save marks or order books. To have
                  it deleted, <Link href="/contact/">write to us</Link>.
                </p>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
