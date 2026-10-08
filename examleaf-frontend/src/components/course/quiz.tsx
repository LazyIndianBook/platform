"use client";

// A chapter's one-mark quiz (Quiz question, Quiz feedback, Quiz result, Phone quiz). Each answer is checked on the
// server (POST learn/quiz/<id>/attempt/): right or wrong, the right answer and the explanation appear only with its
// reply, never before; Check is busy while the answer is out and a second press sends nothing. The result counts the
// server's verdicts. What was chosen or typed, and the verdicts so far, survive a log-in round trip in this tab. While
// a parent's consent is awaited the API checks nothing, so Check is off and the page says why.
import { cn } from "cn";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { ConsentPending } from "@/components/account/parts";
import { useAction } from "@/components/account/use-action";
import { Button, buttonVariants } from "@/components/ui/button";
import { FieldError } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api, personal } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { focusHere } from "@/lib/utils";

import { readDraft, writeDraft } from "./draft";
import { inWords } from "./flash-cards";
import { Count, FocusBar } from "./focus-bar";
import { escapeHtml, MathHtml } from "./math-html";

type Checked = components["schemas"]["Checked"];
/** A quiz item with its Markdown drawn on the server (no answer: the list never has one). */
export type Question = {
  id: number;
  kind: components["schemas"]["QuizItemKindEnum"];
  text: React.ReactNode;
  options: React.ReactNode[];
};
type Draft = { at: number; replies: Record<number, Checked>; choice: string };

const KIND = { mcq: "MULTIPLE CHOICE", true_false: "TRUE OR FALSE", fill_blank: "FILL IN THE BLANK" };
const TRUE_FALSE: [string, string][] = [
  ["true", "True"],
  ["false", "False"],
];

export function QuizRun({
  title,
  questions,
  close,
  draftKey,
  consentPending = false,
}: {
  title: string;
  questions: Question[];
  close: { href: string; label: string };
  /** Where this quiz's draft is kept in the tab (one per chapter, or Revise again's). */
  draftKey: string;
  consentPending?: boolean;
}) {
  const [at, setAt] = useState(0);
  const [replies, setReplies] = useState<Record<number, Checked>>({});
  const [choice, setChoice] = useState("");
  const { run, busy, error, setError } = useAction();
  const sending = useRef(false);
  const focusable = useRef<HTMLDivElement>(null);
  const [moved, setMoved] = useState(0); // after a verdict or the next question, focus follows (not on the first load)
  const question = questions[at];
  const reply = question ? replies[question.id] : undefined;
  const right = Object.values(replies).filter((answer) => answer.correct).length;

  // after a log-in round trip: the question, the verdicts so far and what was chosen or typed come back
  useEffect(() => {
    const draft = readDraft<Draft>(draftKey);
    const fits = (index: number) => index >= (draft?.at ?? 0) || Boolean(draft?.replies[questions[index].id]);
    if (!draft || draft.at >= questions.length || !questions.every((_, index) => fits(index))) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- once, after hydration: the tab's storage is the browser's
    setAt(draft.at);
    setReplies(draft.replies);
    setChoice(draft.choice);
  }, [draftKey, questions]);

  useEffect(() => {
    if (moved) focusHere(focusable.current);
  }, [moved]);

  async function check(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!question || reply || sending.current || consentPending) return;
    const answer = choice.trim();
    if (!answer) {
      const words = question.kind === "fill_blank" ? "Type your answer first." : "Choose an answer first.";
      setError(new ApiError(400, "invalid", words, { answer: [words] }));
      return;
    }
    sending.current = true;
    writeDraft(draftKey, { at, replies, choice } satisfies Draft);
    let checked: Checked | undefined;
    await run(async () => {
      checked = await personal(
        api.POST("/api/v1/learn/quiz/{id}/attempt/", { params: { path: { id: question.id } }, body: { answer } }),
      );
    });
    sending.current = false;
    if (!checked) return;
    const all = { ...replies, [question.id]: checked };
    setReplies(all);
    writeDraft(draftKey, { at: at + 1, replies: all, choice: "" } satisfies Draft);
    setMoved((count) => count + 1);
  }

  function next() {
    setAt((index) => index + 1);
    setChoice("");
    setError(null);
    setMoved((count) => count + 1);
    if (at + 1 >= questions.length) writeDraft(draftKey, null);
  }

  function again() {
    writeDraft(draftKey, null);
    setAt(0);
    setReplies({});
    setChoice("");
    setMoved((count) => count + 1);
  }

  if (!question) {
    const missed = questions.length - right;
    return (
      <>
        <FocusBar title={title} short="Quiz" close={close.href} status="Done" />
        <div className="mx-auto grid w-full max-w-[720px] grid-cols-[64px_minmax(0,1fr)_72px] pt-9 pb-10 max-nav:grid-cols-[minmax(0,1fr)] max-nav:pt-6">
          <span
            aria-hidden="true"
            className="pt-1.5 pl-6 font-mono text-[15px] font-semibold text-red-ink max-nav:hidden"
          >
            Σ
          </span>
          <div className="flex flex-col gap-3.5 border-l-[3px] border-double border-red-ink px-6 max-nav:border-0 max-nav:px-4 [&_p]:m-0">
            <div ref={focusable} className="flex items-center justify-between gap-4">
              <h2 className="text-[34px] leading-[1.05]">
                {right} of {questions.length} right
              </h2>
              <span
                aria-hidden="true"
                className="flex size-[52px] flex-none -rotate-6 items-center justify-center rounded-full border-2 border-red-ink font-mono text-base font-semibold text-red-ink nav:hidden"
              >
                {right}
              </span>
            </div>
            <p className="text-[15px] leading-[1.55] text-ink/85">
              {missed === 0
                ? "Every answer right."
                : `The ${inWords(missed)} you missed ${missed === 1 ? "comes" : "come"} back in Revise again tomorrow.`}
            </p>
            <ol className="m-0 list-none border-t-[1.5px] border-foreground p-0">
              {questions.map((item, index) => {
                const correct = replies[item.id]?.correct;
                return (
                  <li
                    key={item.id}
                    className="grid min-h-[42px] grid-cols-[36px_minmax(0,1fr)_36px] items-center gap-2.5 border-b border-border py-2 text-sm"
                  >
                    <span className="font-mono text-[13px] font-semibold text-muted-foreground">Q{index + 1}</span>
                    <div className="min-w-0 [overflow-wrap:anywhere] [&_p]:inline">{item.text}</div>
                    <span className={cn("text-right font-mono font-semibold", correct ? "text-easy" : "text-hard")}>
                      <span aria-hidden="true">{correct ? "✓" : "✗"}</span>
                      <span className="sr-only">{correct ? "right" : "wrong"}</span>
                    </span>
                  </li>
                );
              })}
            </ol>
            <div className="flex flex-wrap gap-2.5">
              <Link href={close.href} className={buttonVariants({ className: "flex-1" })}>
                {close.label}
              </Link>
              <Button variant="secondary" onClick={again}>
                Try again
              </Button>
            </div>
          </div>
          <span className="flex justify-center pt-1.5 max-nav:hidden">
            <span
              aria-hidden="true"
              className="flex size-[52px] -rotate-6 items-center justify-center rounded-full border-2 border-red-ink font-mono text-base font-semibold text-red-ink"
            >
              {right}
            </span>
          </span>
        </div>
      </>
    );
  }

  const choices: [string, React.ReactNode][] =
    question.kind === "mcq"
      ? question.options.map((option, index) => [String(index + 1), option])
      : question.kind === "true_false"
        ? TRUE_FALSE
        : [];
  const verdict = reply ? (reply.correct ? "text-easy" : "text-hard") : "";
  const mark = reply ? (reply.correct ? "✓ 1" : "✗ 0") : "[1]";
  const fieldErrors = error?.fields.answer;

  return (
    <>
      <FocusBar
        title={title}
        short="Quiz"
        close={close.href}
        status={<Count at={at + 1} of={questions.length} noun="Question" />}
      />
      <div className="mx-auto grid w-full max-w-[720px] grid-cols-[64px_minmax(0,1fr)_56px] pt-9 pb-10 max-nav:grid-cols-[minmax(0,1fr)] max-nav:pt-[22px]">
        <span
          aria-hidden="true"
          className="pt-1.5 pl-6 font-mono text-[15px] font-semibold text-red-ink max-nav:hidden"
        >
          Q{at + 1}
        </span>
        <form
          noValidate
          onSubmit={check}
          className="flex flex-col gap-4 border-l-[3px] border-double border-red-ink px-6 max-nav:gap-3 max-nav:border-0 max-nav:px-4 [&_p]:m-0"
        >
          <p className="flex justify-between gap-4 font-mono text-[11px] leading-none font-medium tracking-[0.06em] text-muted-foreground">
            <span>
              <span className="nav:hidden">Q{at + 1} · </span>
              {KIND[question.kind]}
            </span>
            <span aria-hidden="true" className={cn("nav:hidden", verdict)}>
              {mark}
            </span>
          </p>
          <div
            id={`question-${question.id}`}
            ref={reply ? undefined : focusable}
            className="font-read text-[21px] leading-[1.6] max-nav:text-xl max-nav:leading-[1.55] [&_p+p]:mt-3"
          >
            {question.text}
          </div>
          {consentPending ? <ConsentPending what="the quiz cannot check your answers" /> : null}
          {choices.length ? (
            <div
              role="radiogroup"
              aria-labelledby={`question-${question.id}`}
              className="flex flex-col gap-4 max-nav:gap-3"
            >
              {choices.map(([value, label]) => {
                const chosen = choice === value;
                return (
                  <label
                    key={value}
                    className={cn(
                      "flex min-h-14 cursor-pointer items-center gap-3.5 border bg-card px-4 font-read text-lg leading-[1.4] max-nav:min-h-[54px] max-nav:gap-3 max-nav:px-3.5 max-nav:text-[17px]",
                      "has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-ring",
                      chosen
                        ? cn(
                            "border-2 px-[15px] max-nav:px-[13px]",
                            reply ? (reply.correct ? "border-easy" : "border-hard") : "border-foreground",
                          )
                        : "border-border",
                      reply && "cursor-default",
                    )}
                  >
                    <input
                      type="radio"
                      name="answer"
                      value={value}
                      checked={chosen}
                      disabled={Boolean(reply) || consentPending}
                      onChange={() => setChoice(value)}
                      className="size-[22px] shrink-0 accent-primary"
                    />
                    <span className="min-w-0">{label}</span>
                  </label>
                );
              })}
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              <label htmlFor="answer" className="sr-only">
                Your answer
              </label>
              <Input
                id="answer"
                name="answer"
                value={choice}
                readOnly={Boolean(reply)}
                disabled={consentPending}
                onChange={(event) => setChoice(event.target.value)}
                autoComplete="off"
                spellCheck={false}
                aria-invalid={fieldErrors ? true : undefined}
                aria-describedby={fieldErrors ? "answer-error" : undefined}
                className={cn(
                  "min-h-[54px] font-read text-lg",
                  reply && (reply.correct ? "border-2 border-easy" : "border-2 border-hard"),
                )}
              />
            </div>
          )}
          {fieldErrors ? <FieldError id="answer-error">{fieldErrors.join(" ")}</FieldError> : null}
          {error?.code === "consent_pending" ? (
            <ConsentPending what="the quiz cannot check your answers" />
          ) : error && !fieldErrors ? (
            <FieldError role="alert">{error.message}</FieldError>
          ) : null}
          {reply ? (
            <div ref={focusable} role="status" className="flex flex-col gap-1.5 border border-border bg-card p-4">
              <p className={cn("font-mono text-[13px] leading-snug font-semibold", verdict)}>
                {reply.correct ? "RIGHT" : "NOT QUITE · ANSWER: "}
                {reply.correct ? null : (
                  <MathHtml inline html={escapeHtml(reply.right_answer)} className="[overflow-wrap:anywhere]" />
                )}
              </p>
              {reply.explanation_html ? (
                <MathHtml
                  html={reply.explanation_html}
                  className="font-read text-[17px] leading-[1.6] text-ink/85 [&_p]:m-0 [&_p+p]:mt-2"
                />
              ) : null}
            </div>
          ) : null}
          {reply ? (
            <Button type="button" size="lg" block className="min-h-[54px]" onClick={next}>
              {at + 1 < questions.length ? "Next question" : "See your result"}
            </Button>
          ) : (
            <Button
              type="submit"
              size="lg"
              block
              busy={busy}
              disabled={consentPending}
              className="mt-1.5 min-h-[54px] max-nav:mt-1"
            >
              Check
            </Button>
          )}
        </form>
        <span
          aria-hidden="true"
          className={cn(
            "pt-2 text-center font-mono max-nav:hidden",
            reply ? cn("text-[15px] font-semibold", verdict) : "text-sm font-medium text-muted-foreground",
          )}
        >
          {mark}
        </span>
      </div>
    </>
  );
}
