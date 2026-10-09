"use client";

// Book codes (course/codes/): the lookup box (POST codes/lookup/: a typed or scanned code answered in one line, by its
// hash, never kept; audited and throttled) with, for an unused code, voiding it after "VOID" is typed, and for a
// redeemed one the way to the learner's page; a print run's codes made by a job (POST codes/batches/: the printer's
// file is its maker's to download for 24 hours, then deleted); the print runs as a list; and on a print run's page,
// marking it dispatched, voiding it (its label typed: every unused code stops working) and making again the codes of
// a run whose job failed.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ConfirmTyped } from "@/components/data/confirm-typed";
import { type Column, DataTable } from "@/components/data/data-table";
import { JobProgress } from "@/components/data/job-progress";
import { ActionForm, formText } from "@/components/forms/action-form";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { useCan } from "@/components/shell/manifest";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { toast } from "@/components/ui/toaster";
import {
  type CourseBatch,
  type CourseBatchDetail,
  type CourseCodeLookup,
  type Job,
  lookUpCode,
  makeBatch,
  markDispatched,
  remakeBatch,
  type SavedView,
  searchProducts,
  voidBatch,
  voidCode,
} from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { formatDate, fromLocalInput } from "@/lib/format";
import { P } from "@/lib/modules";

import { FormDialog } from "./form-dialog";
import { BatchChip, CodeChip, options, subjectOptions } from "./shared";

const words = copy.course.codes;
const SUBJECTS = [...subjectOptions, { value: "ALL", label: words.subjectAll }];

export function CodeLookup() {
  const can = useCan();
  const [code, setCode] = useState("");
  const [answer, setAnswer] = useState<CourseCodeLookup | null>(null);
  const { run, busy, error } = useAction();
  const look = (value: string) =>
    run(async () => {
      setAnswer(null);
      setAnswer(await lookUpCode(value));
    });
  const redeemer = answer?.redeemed_by;
  return (
    <div className="flex flex-col gap-3">
      <form
        noValidate
        className="flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (code.trim()) void look(code);
        }}
      >
        <Field id="code-lookup" label={words.codeField} help={words.codeHelp} error={fieldError(error, "code")}>
          <Input
            name="code"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            data-no-draft=""
            className="w-72 max-w-full font-mono"
          />
        </Field>
        <Button type="submit" busy={busy}>
          {words.lookupButton}
        </Button>
      </form>
      <ErrorSummary error={error} />
      {answer ? (
        <Alert variant={answer.state === "unknown" ? "warning" : "info"} title={<CodeChip state={answer.state} />}>
          <p>{answer.line}</p>
          <span className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-2">
            {redeemer && can(P.accessView) ? (
              <Link href={`/course/learners/${redeemer.id}/`} prefetch={false} className="font-semibold">
                {words.openLearner}
              </Link>
            ) : null}
            {redeemer && can(P.usersView) ? (
              <Link href={`/users/${redeemer.id}/`} className="font-semibold">
                {words.openCustomer}
              </Link>
            ) : null}
            {answer.batch && can(P.batchesView) ? (
              <Link href={`/course/codes/${encodeURIComponent(answer.batch)}/`}>{answer.batch}</Link>
            ) : null}
            {answer.state === "unused" && can(P.codesVoid) ? (
              <ConfirmTyped
                label={words.voidCodeTyped}
                triggerLabel={words.voidCode}
                triggerVariant="destructive"
                title={words.voidCodeTitle}
                text={words.voidCodeText}
                confirmLabel={words.voidCode}
                reason
                success={words.voided}
                onConfirm={({ reason }) => voidCode(code, reason)}
                onDone={() => void look(code)}
              />
            ) : null}
          </span>
        </Alert>
      ) : null}
    </div>
  );
}

/** The books whose slug, title or ISBN match what is typed (2 letters or more), as the input's suggestions; nothing
 *  when the search is not the person's (the slug can still be typed). */
function useBooks(typed: string) {
  const [books, setBooks] = useState<{ slug: string; title: string }[]>([]);
  useEffect(() => {
    const query = typed.trim();
    if (query.length < 2) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      searchProducts(query, controller.signal)
        .then((rows) => setBooks(rows.map((row) => ({ slug: row.slug, title: row.title }))))
        .catch(() => setBooks([]));
    }, 300);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [typed]);
  return books;
}

export function MakeBatch() {
  const [book, setBook] = useState("");
  const books = useBooks(book);
  const [made, setMade] = useState<{ batch: CourseBatch; job: Job } | null>(null);
  const id = "course-batch";
  return (
    <div className="flex flex-col gap-5">
      <ActionForm
        id={id}
        submitLabel={words.makeButton}
        success={words.started}
        labels={{
          label: words.label,
          subject: words.subject,
          count: words.count,
          product: words.book,
          note: words.note,
        }}
        onSubmit={(form) =>
          makeBatch({
            label: formText(form, "label"),
            subject: formText(form, "subject"),
            count: Number(formText(form, "count")),
            product: formText(form, "product"),
            note: formText(form, "note"),
          })
        }
        onDone={(result) => {
          setMade(result as { batch: CourseBatch; job: Job });
          setBook("");
        }}
      >
        {(error) => (
          <>
            <FormGrid>
              <Field id={`${id}-label`} label={words.label} help={words.labelHelp} error={fieldError(error, "label")}>
                <Input name="label" autoComplete="off" maxLength={40} className="font-mono" />
              </Field>
              <Field id={`${id}-subject`} label={words.subject} error={fieldError(error, "subject")}>
                <Select name="subject" defaultValue="PHY">
                  {SUBJECTS.map((subject) => (
                    <option key={subject.value} value={subject.value}>
                      {subject.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field id={`${id}-count`} label={words.count} help={words.countHelp} error={fieldError(error, "count")}>
                <Input name="count" type="number" inputMode="numeric" min={1} max={100000} />
              </Field>
            </FormGrid>
            <Field id={`${id}-product`} label={words.book} help={words.bookHelp} error={fieldError(error, "product")}>
              <Input
                name="product"
                list={`${id}-books`}
                value={book}
                onChange={(event) => setBook(event.target.value)}
                autoComplete="off"
                className="font-mono"
              />
            </Field>
            <datalist id={`${id}-books`}>
              {books.map((each) => (
                <option key={each.slug} value={each.slug}>
                  {each.title}
                </option>
              ))}
            </datalist>
            <Field
              id={`${id}-note`}
              label={words.note}
              help={words.noteHelp}
              optional
              error={fieldError(error, "note")}
            >
              <Textarea name="note" rows={2} />
            </Field>
          </>
        )}
      </ActionForm>
      {made ? (
        <div className="flex flex-col gap-2" aria-label={copy.course.batch.generation}>
          <p className="m-0 font-semibold">
            <Link href={`/course/codes/${encodeURIComponent(made.batch.key)}/`}>{made.batch.label}</Link>
          </p>
          <JobProgress key={made.job.id} job={made.job} />
        </div>
      ) : null}
    </div>
  );
}

export function BatchesTable({
  rows,
  next,
  previous,
  views,
}: {
  rows: CourseBatch[];
  next: string | null;
  previous: string | null;
  views: SavedView[] | null;
}) {
  const columns: Column<CourseBatch>[] = [
    { key: "label", label: words.columns.label, render: (batch) => <span className="font-mono">{batch.label}</span> },
    {
      key: "subject",
      label: words.columns.subject,
      render: (batch) => (batch.subject ? labelOf(copy.content.subjects, batch.subject) : words.every),
    },
    {
      key: "book",
      label: words.columns.book,
      render: (batch) => batch.product?.title ?? copy.common.none,
      wrap: true,
      hidden: true,
    },
    { key: "printed", label: words.columns.printed, render: (batch) => batch.printed, numeric: true },
    { key: "redeemed", label: words.columns.redeemed, render: (batch) => batch.redeemed, numeric: true },
    { key: "void", label: words.columns.void, render: (batch) => batch.void, numeric: true },
    { key: "state", label: words.columns.state, render: (batch) => <BatchChip state={batch.state} /> },
    {
      key: "dispatched",
      label: words.columns.dispatched,
      render: (batch) => (batch.dispatched_at ? formatDate(batch.dispatched_at) : copy.course.batch.notYet),
    },
  ];
  return (
    <DataTable
      listKey="course-batches"
      caption={words.title}
      rows={rows}
      columns={columns}
      rowId={(batch) => String(batch.id)}
      rowHref={(batch) => `/course/codes/${encodeURIComponent(batch.key)}/`}
      next={next}
      previous={previous}
      views={views}
      filters={[
        { name: "q", label: words.filters.q, type: "search" },
        { name: "subject", label: words.filters.subject, type: "select", options: SUBJECTS },
        { name: "state", label: words.filters.state, type: "select", options: options(words.batchStates) },
      ]}
      empty={{ title: words.emptyTitle, text: words.emptyText }}
    />
  );
}

/** A print run's own actions: dispatched, voided (typed), its codes made again after a failed job. */
export function BatchActions({ batch }: { batch: CourseBatchDetail }) {
  const can = useCan();
  const router = useRouter();
  const remaking = useAction();
  const [job, setJob] = useState<Job | null>(null);
  const b = copy.course.batch;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2.5">
        {batch.state === "ready" && can(P.batchesChange) ? (
          <FormDialog
            triggerLabel={b.dispatch}
            triggerVariant="primary"
            title={b.dispatchTitle}
            text={b.dispatchText}
            submitLabel={b.dispatchButton}
            success={b.dispatched}
            labels={{ at: b.dispatchedAt }}
            onSubmit={(form) => {
              const at = String(form.get("at") ?? "");
              return markDispatched(batch.key, at ? fromLocalInput(at) : null);
            }}
          >
            {(id, error) => (
              <Field
                id={`${id}-at`}
                label={b.dispatchedAt}
                help={b.dispatchedHelp}
                optional
                error={fieldError(error, "at")}
              >
                <Input name="at" type="datetime-local" />
              </Field>
            )}
          </FormDialog>
        ) : null}
        {batch.state === "failed" && can(P.codesMake) && !job ? (
          <Button
            size="sm"
            busy={remaking.busy}
            onClick={() =>
              remaking.run(async () => {
                setJob(await remakeBatch(batch.id));
                toast.success(words.started);
              })
            }
          >
            {b.remake}
          </Button>
        ) : null}
        {batch.state !== "void" && can(P.codesVoid) ? (
          <ConfirmTyped
            label={batch.label}
            triggerLabel={b.voidButton}
            triggerVariant="destructive"
            title={b.voidTitle}
            text={b.voidText}
            confirmLabel={b.voidButton}
            reason
            success={b.voided}
            onConfirm={({ reason }) => voidBatch(batch.key, reason)}
          />
        ) : null}
      </div>
      <ErrorSummary error={remaking.error} />
      {job ? <JobProgress key={job.id} job={job} onDone={() => router.refresh()} /> : null}
    </div>
  );
}
