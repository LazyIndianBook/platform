// /s/<code>/: the address inside every printed QR code (any case; a wrong case redirects to the canonical code).
// Signed in, or on a book's open sample, or while the solutions are open to everyone (config
// solutions_require_login): the worked solutions, Markdown and maths drawn on the server (no maths script on the
// phone), print styles, and for a signed-in student the form that saves their marks to My record (#record).
// Otherwise the register / log-in wall that keeps this page as the destination.
// Direction A (ExamLeaf A - Public.dc.html, "A Solutions" and "Solutions logged out"; the phone artboards): the paper
// on a Sheet whose margin is its short code; each group's number hangs in the margin, its marks in the marks column,
// each question's allotted marks [2] beside it; a solution hangs off a thin red line with its marking steps ticked in
// the marks column and the total circled. "On this paper" is the rail from 1100 px, a sticky row of chips below it.
import "katex/dist/katex.min.css";
import "./solutions.css";

import { ArrowRight } from "lucide-react";
import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";
import { notFound, permanentRedirect } from "next/navigation";
import { Fragment } from "react";

import { MarksForm } from "@/components/account/marks-form";
import { MarkdownBlock, MarkdownInline, splitGroup, stepCount } from "@/components/solutions/markdown";
import { Unavailable } from "@/components/site/unavailable";
import { Accordion } from "@/components/ui/accordion";
import { Alert } from "@/components/ui/alert";
import { Sheet } from "@/components/ui/band";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { QrCard } from "@/components/ui/qr-card";
import { getBook, getPaperByQr, getSolutions, type Paper, type Question } from "@/lib/api/catalogue";
import { getConfig } from "@/lib/api/config";
import { ApiError } from "@/lib/api/errors";
import { withNext } from "@/lib/auth/next-url";
import { getSessionUser } from "@/lib/auth/session";
import { breadcrumbJsonLd, JsonLd } from "@/lib/seo/json-ld";
import { pageMetadata } from "@/lib/seo/metadata";
import { shortCode, SITE_URL, subjectOf, TIERS, type TierCode } from "@/lib/site";

import { retryAt, secondsIn } from "../../retry-at";

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

const TIER_ORDER: Record<TierCode, number> = { E: 0, M: 1, H: 2 };

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
type Group = { id: string; label: string; part: string; first: Question; questions: Question[] };

/** The questions in their printed groups (a new group at each new part or group heading). */
function grouped(list: Question[]): Group[] {
  const groups: Group[] = [];
  for (const question of list) {
    const last = groups.at(-1);
    const label = question.group_label ?? "";
    const part = question.part_label ?? "";
    if (last && last.label === label && last.part === part) last.questions.push(question);
    else groups.push({ id: `g-${slug(question.label)}`, label, part, first: question, questions: [question] });
  }
  return groups;
}

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
  let gate: "login" | "confirm" | "throttled" | null = open ? null : "login";
  let throttledUntil = "";
  if (open) {
    try {
      questions = await getSolutions(paper.code, Boolean(user));
    } catch (error) {
      if (!(error instanceof ApiError) || error.unavailable)
        return <Unavailable what="This paper's solutions" retry={path} />;
      gate = error.status === 403 ? "confirm" : error.status === 429 ? "throttled" : "login";
      if (gate === "throttled") throttledUntil = retryAt(secondsIn(error.message));
    }
  }

  const short = shortCode(paper.code);
  const inBook = (book?.papers ?? [])
    .filter((item) => item.is_published !== false)
    .sort((a, b) => TIER_ORDER[a.tier] - TIER_ORDER[b.tier] || a.number - b.number);
  const position = inBook.findIndex((item) => item.code === paper.code);
  const next = position >= 0 ? inBook[position + 1] : undefined;
  const sample = inBook.find((item) => item.is_sample);
  const header = (paper.header ?? {}) as Header;
  const facts = [
    { label: "Full marks", value: paper.full_marks },
    { label: "Pass marks", value: paper.pass_marks },
    { label: "Time", value: paper.time_text },
  ];
  const eyebrow = `${paper.code} · Sample Paper ${short} · ${TIERS[paper.tier]} · ${book?.subject.board ?? "ASSEB"} Class ${book?.subject.class_level ?? 12}`;
  const trail = [
    { label: "Home", href: "/" },
    { label: subjectName, href: `/books/${paper.book}/` },
    { label: `Paper ${short}` },
  ];
  const masthead = (
    <>
      <JsonLd data={breadcrumbJsonLd(trail.map((crumb) => ({ name: crumb.label, path: crumb.href ?? path })))} />
      <Breadcrumb trail={trail} className="max-nav:hidden" />
    </>
  );
  const qrCard = (
    <QrCard
      subject={subject?.key ?? "physics"}
      subjectName={subjectName}
      tier={paper.tier}
      code={paper.code}
      eyebrow={eyebrow}
      title={`${subjectName}: solutions`}
      facts={facts}
    />
  );

  if (gate) {
    // the wall (Solutions logged out): who arrived from a QR scan (no page of this site before) is told so
    const fromQr = !(await headers()).get("referer")?.startsWith(SITE_URL);
    return (
      <div className="paper-page">
        <Sheet margin={short} className="max-nav:[&>.sheet-margin]:hidden" bodyClassName="pt-7 max-nav:pt-4">
          {masthead}
          {qrCard}
          <div className="wall">
            <div className="wall-main">
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
              ) : gate === "throttled" ? (
                <>
                  <h2>Too many pages at once. Please wait a minute</h2>
                  <p className="lead">
                    To keep the site quick for everyone, we limit how often solutions can be opened from one connection.
                    You can try again at {throttledUntil}.
                  </p>
                  <p>
                    <Link href={path} className={buttonVariants({ variant: "secondary" })}>
                      Try again
                    </Link>
                  </p>
                </>
              ) : (
                <>
                  {fromQr ? <p className="wall-eyebrow">The QR code brought you here</p> : null}
                  <h2>Register once to open every solution, free</h2>
                  <p className="lead">
                    Free for registered students. You only need to register once, with your email address. After that,
                    every QR code in your book opens its paper&apos;s solutions straight away.
                  </p>
                  <div className="flex flex-wrap gap-3">
                    <Link
                      href={withNext("/account/signup/", path)}
                      className={buttonVariants({ size: "lg", className: "max-nav:w-full" })}
                    >
                      Register free
                    </Link>
                    <Link
                      href={withNext("/account/login/", path)}
                      className={buttonVariants({ variant: "secondary", size: "lg", className: "max-nav:w-full" })}
                    >
                      Log in
                    </Link>
                  </div>
                  <p className="text-[15px] text-muted-foreground">
                    You come straight back to Paper {short} afterwards.
                  </p>
                </>
              )}
            </div>
            <div className="wall-side">
              <p className="label-mono text-xs tracking-[0.06em] uppercase max-nav:hidden">What&apos;s on this page</p>
              <p className="max-nav:hidden">
                Every question of the paper, its worked solution, and the marks each step earns.
              </p>
              <p className="max-nav:hidden">A place to record your score, which goes to My record.</p>
              {sample && sample.code !== paper.code ? (
                <p className="wall-sample">
                  Not ready to register?{" "}
                  <Link href={`/s/${sample.code}/`} className="font-bold">
                    Paper {shortCode(sample.code)}
                  </Link>{" "}
                  is open to everyone.
                </p>
              ) : null}
            </div>
          </div>
        </Sheet>
      </div>
    );
  }

  const groups = grouped(questions ?? []);
  const chipName = (group: Group, index: number) => {
    const number = splitGroup(group.label).number;
    return number ? `Q${number.slice(0, -1)}` : `Q${index + 1}`;
  };

  return (
    <div className="paper-page">
      <Sheet margin={short} className="paper-sheet max-nav:[&>.sheet-margin]:hidden" bodyClassName="max-nav:pt-4">
        {masthead}
        <div className="paper-grid">
          <div className="paper-main">
            <div className="paper-head">
              {qrCard}
              <span aria-hidden="true" className="paper-col-label">
                Marks
              </span>
            </div>
            <div className="paper-actions">
              <a href="#record" className={buttonVariants({ variant: "secondary" })}>
                Record your marks
              </a>
              <Link href={`/books/${paper.book}/`} className="inline-flex min-h-11 items-center gap-1.5 font-bold">
                <span>All {subjectName} papers</span>
                <ArrowRight aria-hidden="true" className="size-5" />
              </Link>
            </div>

            {groups.length ? (
              <nav className="paper-chips" aria-label="Questions on this paper">
                {groups.map((group, index) => (
                  <a key={group.id} href={`#${group.id}`}>
                    {chipName(group, index)}
                  </a>
                ))}
                <a href="#record">Marks</a>
              </nav>
            ) : null}

            {header.lines?.length || header.allotment?.length ? (
              <Accordion summary="Instructions and allotment of marks">
                <div id="instructions" className="flex flex-col gap-3 [&>*]:m-0">
                  {header.lines?.map((line) => (
                    <p key={line}>
                      <MarkdownInline>{line}</MarkdownInline>
                    </p>
                  ))}
                  {header.allotment?.map((table) => (
                    <MarkdownBlock key={table}>{table}</MarkdownBlock>
                  ))}
                </div>
              </Accordion>
            ) : null}

            {groups.length ? (
              groups.map((group, index) => {
                const newPart = group.part && group.part !== groups[index - 1]?.part;
                const GroupTag = group.part ? "h3" : "h2";
                const heading = splitGroup(group.label);
                return (
                  <section key={group.id} id={group.id} className="qgroup" aria-labelledby={`${group.id}-h`}>
                    {newPart ? <h2 className="part">{group.part}</h2> : null}
                    {group.label ? (
                      <GroupTag className="group" id={`${group.id}-h`}>
                        <span className="group-text">
                          {heading.number ? <span className="group-no">{heading.number} </span> : null}
                          <MarkdownInline>{heading.text}</MarkdownInline>
                        </span>
                        {heading.marks ? <span className="group-marks">{heading.marks}</span> : null}
                      </GroupTag>
                    ) : (
                      <GroupTag className="group-sr sr-only" id={`${group.id}-h`}>
                        Questions from {group.first.number}
                      </GroupTag>
                    )}
                    {group.questions.map((question) => {
                      const steps = question.solution ? stepCount(question.solution.markdown) : 0;
                      return (
                        <Fragment key={question.label}>
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
                            {question.marks ? (
                              <p className="marks">
                                [{question.marks}]<span className="sr-only"> marks</span>
                              </p>
                            ) : null}
                            {question.solution ? (
                              <div className="solution">
                                <p className="solution-label">
                                  Solution{steps ? ` · ${steps} step${steps === 1 ? "" : "s"}` : ""}
                                </p>
                                <MarkdownBlock>{question.solution.markdown}</MarkdownBlock>
                              </div>
                            ) : null}
                          </article>
                        </Fragment>
                      );
                    })}
                  </section>
                );
              })
            ) : (
              <EmptyState
                art="sheet"
                title="The solutions are on their way"
                className="mt-8"
                action={
                  <Link href={`/books/${paper.book}/`} className={buttonVariants({ variant: "primary" })}>
                    All {subjectName} papers
                  </Link>
                }
              >
                <p>This paper&apos;s worked solutions are still being set. The other {subjectName} papers are ready.</p>
              </EmptyState>
            )}

            <section id="record" className="record-card" aria-labelledby="record-title">
              <div className="flex flex-col gap-1.5 [&>*]:m-0">
                <h2 id="record-title">Record your marks</h2>
                <p className="text-[15px] text-muted-foreground">
                  Your score goes to My record, with your average for each tier.
                </p>
              </div>
              {user ? (
                <MarksForm paper={paper.code} fullMarks={paper.full_marks} nextPaper={next?.code} />
              ) : (
                <p className="m-0">
                  To keep your scores in My record, <Link href={withNext("/account/login/", path)}>log in</Link> or{" "}
                  <Link href={withNext("/account/signup/", path)}>register</Link> (free).
                </p>
              )}
            </section>
          </div>

          <aside className="rail" aria-label="On this paper">
            <div className="rail-inner">
              <h2 className="label-mono text-xs tracking-[0.06em] uppercase">On this paper</h2>
              <ul>
                {header.lines?.length || header.allotment?.length ? (
                  <li>
                    <a href="#instructions">Instructions and allotment of marks</a>
                  </li>
                ) : null}
                {groups.map((group) => (
                  <li key={group.id}>
                    <a href={`#${group.id}`}>Questions from {group.first.number}</a>
                  </li>
                ))}
                <li>
                  <a href="#record">Record your marks</a>
                </li>
              </ul>
              {position >= 0 ? (
                <div className="rail-next">
                  <span>
                    Paper {position + 1} of {inBook.length} in this book
                  </span>
                  {next ? (
                    <Link href={`/s/${next.code}/`} className="font-bold">
                      Next: Paper {shortCode(next.code)} →
                    </Link>
                  ) : null}
                </div>
              ) : null}
            </div>
          </aside>
        </div>
      </Sheet>
    </div>
  );
}
