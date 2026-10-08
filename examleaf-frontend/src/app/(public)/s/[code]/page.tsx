// /s/<code>/: the address inside every printed QR code (any case; a wrong case redirects to the canonical code).
// Signed in, or on a book's open sample, or while the solutions are open to everyone (config
// solutions_require_login): the worked solutions, Markdown and maths drawn on the server (no maths script on the
// phone), marks in the margin, marking tables, "Diagram expected" lines, print styles. Otherwise the register / log-in
// wall that keeps this page as the destination.
import "katex/dist/katex.min.css";
import "./solutions.css";

import { ArrowRight, CircleCheck, Pencil } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound, permanentRedirect } from "next/navigation";
import { Fragment } from "react";

import { MarkdownBlock, MarkdownInline } from "@/components/solutions/markdown";
import { Unavailable } from "@/components/site/unavailable";
import { Accordion } from "@/components/ui/accordion";
import { Alert } from "@/components/ui/alert";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { QrCard } from "@/components/ui/qr-card";
import { getBook, getPaperByQr, getSolutions, type Paper, type Question } from "@/lib/api/catalogue";
import { getConfig } from "@/lib/api/config";
import { ApiError } from "@/lib/api/errors";
import { withNext } from "@/lib/auth/next-url";
import { getSessionUser } from "@/lib/auth/session";
import { pageMetadata } from "@/lib/seo/metadata";
import { shortCode, subjectOf, TIERS } from "@/lib/site";

type Props = { params: Promise<{ code: string }> };

async function load(code: string): Promise<Paper | null | "unavailable"> {
  try {
    return await getPaperByQr(code);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    return "unavailable";
  }
}

const slug = (label: string) =>
  label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { code } = await params;
  const paper = await load(code);
  if (!paper || paper === "unavailable") return { title: paper ? "Solutions" : "Page not found" };
  const subject = subjectOf(paper.subject)?.name ?? paper.subject;
  return pageMetadata({
    title: `${subject} Sample Paper ${shortCode(paper.code)}: solutions`,
    path: `/s/${paper.code}/`,
    description: `Worked solutions with the marking steps to ExamLeaf Sample Paper ${shortCode(paper.code)} (${subject}, ${TIERS[paper.tier]}), Assam Board Class 12.`,
  });
}

type Header = { lines?: string[]; allotment?: string[] };

export default async function PaperPage({ params }: Props) {
  const { code } = await params;
  const paper = await load(decodeURIComponent(code));
  if (paper === null) notFound();
  if (paper === "unavailable") return <Unavailable what="This paper's solutions" retry={`/s/${code}/`} />;
  if (paper.code !== decodeURIComponent(code)) permanentRedirect(`/s/${paper.code}/`);

  const [config, user, book] = await Promise.all([
    getConfig(),
    getSessionUser(),
    getBook(paper.book).catch(() => null),
  ]);
  const path = `/s/${paper.code}/`;
  const subject = subjectOf(paper.subject);
  const subjectName = subject?.name ?? paper.subject;
  const requireLogin = config?.solutions_require_login ?? true;
  const open = Boolean(user) || !requireLogin || Boolean(paper.is_sample);

  let questions: Question[] | null = null;
  let gate: "login" | "confirm" | null = open ? null : "login";
  if (open) {
    try {
      questions = await getSolutions(paper.code, Boolean(user));
    } catch (error) {
      if (!(error instanceof ApiError) || error.unavailable)
        return <Unavailable what="This paper's solutions" retry={path} />;
      gate = error.status === 403 ? "confirm" : "login";
    }
  }

  const sample = book?.papers.find((item) => item.is_sample);
  const header = (paper.header ?? {}) as Header;
  const facts = [
    { label: "Full marks", value: paper.full_marks },
    { label: "Pass marks", value: paper.pass_marks },
    { label: "Time", value: paper.time_text },
  ];
  const eyebrow = `Sample Paper ${shortCode(paper.code)} · ${TIERS[paper.tier]} · ${book?.subject.board ?? "ASSEB"} Class ${book?.subject.class_level ?? 12}`;
  const trail = [
    { label: "Home", href: "/" },
    { label: subjectName, href: `/books/${paper.book}/` },
    { label: `Paper ${shortCode(paper.code)}` },
  ];

  if (gate) {
    return (
      <section className="paper-page pt-7 pb-(--section)">
        <div className="container-site">
          <Breadcrumb trail={trail} />
          <QrCard
            subject={subject?.key ?? "physics"}
            subjectName={subjectName}
            tier={paper.tier}
            code={paper.code}
            eyebrow={eyebrow}
            title={`Solutions to Sample Paper ${shortCode(paper.code)} — ${subjectName}`}
            facts={facts}
          />
          <Card className="mt-6 max-w-[44rem]">
            <CardContent>
              {gate === "confirm" ? (
                <Alert variant="warning" title="Confirm your email address first">
                  <p>We emailed you a 6-digit code when you registered. Type it in, and the solutions open.</p>
                  <p>
                    <Link
                      href={withNext("/account/verify-email/", path)}
                      className="inline-flex min-h-11 items-center font-semibold"
                    >
                      Enter the code
                    </Link>
                  </p>
                </Alert>
              ) : (
                <>
                  <p>
                    Free for registered students. Register once with your email address; after that every QR code in
                    your ExamLeaf book opens its solutions.
                  </p>
                  <div className="flex flex-wrap gap-3">
                    <Link
                      href={withNext("/account/signup/", path)}
                      className={buttonVariants({ variant: "accent", size: "lg" })}
                    >
                      Register
                    </Link>
                    <Link
                      href={withNext("/account/login/", path)}
                      className={buttonVariants({ variant: "secondary", size: "lg" })}
                    >
                      Log in
                    </Link>
                  </div>
                  {sample && sample.code !== paper.code ? (
                    <p>
                      Not sure yet? <Link href={`/s/${sample.code}/`}>Paper {shortCode(sample.code)}</Link> of this book
                      is open to everyone: read its solutions without an account.
                    </p>
                  ) : null}
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </section>
    );
  }

  const list = questions ?? [];
  const groups = list.filter(
    (question, index) =>
      question.group_label &&
      (index === 0 ||
        list[index - 1].group_label !== question.group_label ||
        list[index - 1].part_label !== question.part_label),
  );

  return (
    <section className="paper-page pt-7 pb-(--section)">
      <div className="container-site">
        <Breadcrumb trail={trail} />
        <QrCard
          subject={subject?.key ?? "physics"}
          subjectName={subjectName}
          tier={paper.tier}
          code={paper.code}
          eyebrow={eyebrow}
          title={`${subjectName}: solutions`}
          facts={facts}
        />
        <div className="paper-actions mt-5 mb-6 flex flex-wrap items-center gap-3">
          <a href="#record" className={buttonVariants({ variant: "secondary" })}>
            <Pencil aria-hidden="true" />
            <span>Record your marks</span>
          </a>
          <Link href={`/books/${paper.book}/`} className="inline-flex min-h-11 items-center gap-1.5 font-semibold">
            <span>All {subjectName} papers</span>
            <ArrowRight aria-hidden="true" className="size-5" />
          </Link>
        </div>
        {header.lines?.length || header.allotment?.length ? (
          <Accordion summary="Instructions and allotment of marks">
            {header.lines?.map((line) => (
              <p key={line}>
                <MarkdownInline>{line}</MarkdownInline>
              </p>
            ))}
            {header.allotment?.map((table) => (
              <MarkdownBlock key={table}>{table}</MarkdownBlock>
            ))}
          </Accordion>
        ) : null}

        <div className="flex flex-wrap items-start gap-8">
          <div className="min-w-0 flex-[999_1_600px]">
            {list.length ? (
              list.map((question, index) => {
                const previous = list[index - 1];
                const newPart = question.part_label && question.part_label !== previous?.part_label;
                const newGroup =
                  question.group_label &&
                  (question.group_label !== previous?.group_label || question.part_label !== previous?.part_label);
                const GroupTag = question.part_label ? "h3" : "h2";
                return (
                  <Fragment key={question.label}>
                    {newPart ? <h2 className="part">{question.part_label}</h2> : null}
                    {newGroup ? (
                      <GroupTag className="group" id={`g-${slug(question.label)}`}>
                        <MarkdownInline>{question.group_label!}</MarkdownInline>
                      </GroupTag>
                    ) : null}
                    {question.is_alternative ? <p className="or">Or</p> : null}
                    <article className="question" id={`q-${slug(question.label)}`}>
                      <span className="qno">{question.is_alternative ? "" : question.number}</span>
                      <div className="qtext">
                        <MarkdownBlock>{question.text}</MarkdownBlock>
                        {question.table ? <MarkdownBlock>{question.table}</MarkdownBlock> : null}
                        {question.options?.length ? (
                          <ul className="options">
                            {question.options.map((option) => (
                              <li key={option}>
                                <MarkdownInline>{option}</MarkdownInline>
                              </li>
                            ))}
                          </ul>
                        ) : null}
                      </div>
                      {question.marks ? <p className="marks">[{question.marks}]</p> : null}
                      {question.solution ? (
                        <div className="solution">
                          <p className="solution-label flex items-center gap-1.5 font-head text-sm leading-tight font-bold text-accent">
                            <CircleCheck aria-hidden="true" className="size-[18px]" />
                            Solution
                          </p>
                          <MarkdownBlock>{question.solution.markdown}</MarkdownBlock>
                        </div>
                      ) : null}
                    </article>
                  </Fragment>
                );
              })
            ) : (
              <EmptyState
                art="sheet"
                title="The solutions are on their way"
                action={
                  <Link href={`/books/${paper.book}/`} className={buttonVariants({ variant: "primary" })}>
                    All {subjectName} papers
                  </Link>
                }
              >
                <p>This paper&apos;s worked solutions are still being set. The other {subjectName} papers are ready.</p>
              </EmptyState>
            )}

            <Card id="record" className="record-card mt-12 scroll-mt-4">
              <CardHeader>
                <CardTitle>Record your marks</CardTitle>
                <CardDescription>Mark your answers against these solutions, then save your score.</CardDescription>
              </CardHeader>
              <CardContent>
                {user ? (
                  <p>
                    Your scores and your average for each tier are in <Link href="/account/record/">My record</Link>.
                  </p>
                ) : (
                  <p>
                    To keep your scores in My record, <Link href={withNext("/account/login/", path)}>log in</Link> or{" "}
                    <Link href={withNext("/account/signup/", path)}>register</Link> (free).
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          <aside className="rail min-w-0 flex-[1_1_260px]" aria-label="On this paper">
            <Card>
              <CardContent>
                <h2 className="m-0 font-head text-[17px] leading-snug font-bold">On this paper</h2>
                <ul className="m-0 list-none p-0">
                  {groups.map((question) => (
                    <li key={question.label}>
                      <a href={`#g-${slug(question.label)}`} className="flex min-h-11 items-center font-semibold">
                        Questions from {question.number}
                      </a>
                    </li>
                  ))}
                  <li>
                    <a href="#record" className="flex min-h-11 items-center font-semibold">
                      Record your marks
                    </a>
                  </li>
                </ul>
              </CardContent>
            </Card>
          </aside>
        </div>
      </div>
    </section>
  );
}
