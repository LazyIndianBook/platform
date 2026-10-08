// /c/<token>/: a parent's link (email or SMS, valid 7 days) to confirm the account of a student under 18, through
// GET and POST /api/v1/parent-consent/<token>/. "I give my consent" is a server action, so it works without any script
// on the parent's phone; the page names the student only to whoever holds the link, and is never indexed or cached.
// Direction A (ExamLeaf A - Public.dc.html, "Parent link"; Gaps, "Expired links" (G5); Phone parent link): the facts
// as a ruled list beside the answer card. The API has no "I don't consent": that answer is to do nothing, as the
// link's email says, so the card says so instead of offering a button that would do nothing.
import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Unavailable } from "@/components/site/unavailable";
import { Alert } from "@/components/ui/alert";
import { Sheet } from "@/components/ui/band";
import { buttonVariants } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/choice";
import { SubmitButton } from "@/components/ui/submit-button";
import { ApiError, unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { personalFetch, serverApi } from "@/lib/api/server";

import { retryAt, secondsIn } from "../../retry-at";

export const metadata: Metadata = {
  title: "A parent's consent",
  description: "A parent or guardian confirms the ExamLeaf account of a student under 18.",
  robots: { index: false, follow: false },
};

type ParentLink = components["schemas"]["ParentLink"];
type Answer = ParentLink | { status: "throttled"; seconds: number };
type Props = { params: Promise<{ token: string }>; searchParams: Promise<{ wait?: string }> };

/** The link's state (pending, confirmed, or expired: a 400 whose body says so), throttled (429) with the wait, or
 *  null when Django cannot be reached. */
async function load(token: string): Promise<Answer | null> {
  const response = await serverApi
    .GET("/api/v1/parent-consent/{token}/", { params: { path: { token } }, ...(await personalFetch()) })
    .catch(() => null);
  if (!response) return null;
  if (response.response.status === 429)
    return { status: "throttled", seconds: Number(response.response.headers.get("Retry-After")) || 60 };
  return response.data ?? (response.response.status === 400 ? (response.error as ParentLink) : null) ?? null;
}

const FACT = "grid grid-cols-[200px_minmax(0,1fr)] gap-x-4 border-b border-border py-3.5 max-nav:grid-cols-1";

export default async function ParentConsentPage({ params, searchParams }: Props) {
  const { token } = await params;
  const { wait } = await searchParams;
  const link = await load(token);
  if (!link) return <Unavailable what="This page" retry={`/c/${token}/`} />;

  async function agree() {
    "use server";
    try {
      await unwrap(
        serverApi.POST("/api/v1/parent-consent/{token}/", { params: { path: { token } }, ...(await personalFetch()) }),
      );
    } catch (error) {
      // too many tries from this connection: say when to try again, never retry by itself
      if (error instanceof ApiError && error.status === 429) redirect(`/c/${token}/?wait=${secondsIn(error.message)}`);
      throw error;
    }
    redirect(`/c/${token}/`);
  }

  const first = link.status === "throttled" ? "" : (link.student_name ?? "").split(/\s+/)[0];
  const eyebrow = <p className="label-mono uppercase">For a parent or guardian</p>;

  return (
    <Sheet
      margin={link.status === "pending" || link.status === "confirmed" ? "✓" : "—"}
      className="max-nav:[&>.sheet-margin]:hidden"
      bodyClassName="max-nav:pt-6"
    >
      {link.status === "throttled" ? (
        <div className="flex max-w-[44rem] flex-col gap-4 [&>*]:m-0">
          {eyebrow}
          <h1 className="text-[clamp(32px,4vw,48px)] leading-[1.05]">Too many tries. Please wait a minute</h1>
          <p className="text-lg leading-relaxed text-ink/85">
            To keep this link safe, we limit how often it can be opened. You can try again at {retryAt(link.seconds)}.
          </p>
          <p>
            <Link href={`/c/${token}/`} className={buttonVariants({ variant: "secondary" })}>
              Try again
            </Link>
          </p>
        </div>
      ) : link.status === "expired" ? (
        <div className="flex max-w-[44rem] flex-col gap-4 [&>*]:m-0">
          {eyebrow}
          <h1 className="text-[clamp(32px,4vw,48px)] leading-[1.05]">This consent link has expired</h1>
          <p className="text-lg leading-relaxed text-ink/85">
            Links work for {link.days} days, for the parent&apos;s safety. {link.first_name || "The student"} can send a
            new one from their account, or you can write to us and we&apos;ll help.
          </p>
          <p>
            <Link href="/contact/" className={buttonVariants({ variant: "secondary", className: "max-nav:w-full" })}>
              Contact us
            </Link>
          </p>
          <p className="text-muted-foreground">
            Are you the student? <Link href="/account/login/?next=/account/">Log in</Link> and send the link again from
            My account.
          </p>
        </div>
      ) : link.status === "confirmed" ? (
        <div role="status" className="flex max-w-[44rem] flex-col gap-4 [&>*]:m-0">
          {eyebrow}
          <h1 className="text-[clamp(32px,4vw,52px)] leading-[1.05]">
            {first ? `${first}'s account is confirmed` : "The account is confirmed"}
          </h1>
          <p className="text-lg leading-relaxed text-ink/85">
            Thank you. {link.student_name} can now save their marks and order books.
          </p>
          <p className="text-muted-foreground">
            Nothing more to do: you can close this page. To see what we keep, read the{" "}
            <Link href="/privacy/">privacy notice</Link>; for anything else, <Link href="/contact/">contact us</Link>.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-[minmax(0,1fr)_380px] items-start gap-14 max-[1100px]:grid-cols-1 max-[1100px]:gap-6">
          <div className="flex min-w-0 flex-col gap-[18px] max-nav:gap-3.5 [&>*]:m-0">
            {eyebrow}
            <h1 className="text-[clamp(32px,4vw,52px)] leading-[1.05]">
              {first || "A student"} has registered on ExamLeaf
            </h1>
            <p className="max-w-[32em] text-lg leading-relaxed text-ink/85 max-nav:text-base">
              {first || "They"} {first ? "is" : "are"} under 18, so we need your consent before they can save their
              marks or order books. They can already read the solutions.
            </p>
            <dl className="m-0 border-t-[1.5px] border-foreground">
              <div className={FACT}>
                <dt className="text-muted-foreground">Student</dt>
                <dd className="m-0">
                  {link.student_name}
                  {link.student_email ? ` · ${link.student_email}` : ""}
                </dd>
              </div>
              <div className={FACT}>
                <dt className="text-muted-foreground">What we keep</dt>
                <dd className="m-0">
                  Their name, email address, class, board, district and date of birth, and the marks they save.
                </dd>
              </div>
              <div className={FACT}>
                <dt className="text-muted-foreground">What you can do later</dt>
                <dd className="m-0">
                  Withdraw your consent, or have the account deleted: <Link href="/contact/">write to us</Link>.
                </dd>
              </div>
            </dl>
            <p>
              <Link href="/privacy/" target="_blank" rel="noopener" className="font-bold">
                Read the privacy notice
              </Link>
            </p>
          </div>
          <form
            action={agree}
            aria-labelledby="answer-title"
            className="flex flex-col gap-4 border-[1.5px] border-foreground bg-card p-7 max-nav:p-5"
          >
            <h2 id="answer-title" className="m-0 font-head text-2xl leading-tight tracking-normal">
              Your answer
            </h2>
            {wait ? (
              <Alert variant="warning" title="Too many tries. Please wait a minute">
                <p>You can try again at {retryAt(Number(wait) || 60)}.</p>
              </Alert>
            ) : null}
            <Checkbox name="parent" required labelClassName="items-start leading-normal">
              I am {first ? `${first}'s` : "their"} parent or guardian and I have read the privacy notice.
            </Checkbox>
            <SubmitButton size="lg" block>
              I give my consent
            </SubmitButton>
            <p className="m-0 text-sm leading-normal text-muted-foreground">
              If you don&apos;t consent, you need not do anything: the account can&apos;t save marks or order books. To
              have it deleted, <Link href="/contact/">write to us</Link>.
            </p>
            <p className="m-0 text-sm leading-normal text-muted-foreground">
              This link works for {link.days} days from when it was sent.
            </p>
          </form>
        </div>
      )}
    </Sheet>
  );
}
