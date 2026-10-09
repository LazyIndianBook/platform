"use client";

// A solution's or a question's editor: the Markdown and LaTeX source on the left, the text as the site will draw it on
// the right, redrawn as one types (deferred, so typing stays quick); under them the save bar (Save the draft, Undo my
// changes, whether all is saved) with a warning before leaving with changes unsaved, and what was typed kept in
// sessionStorage until it is saved (a session that ends costs nothing). A save first parses every formula with KaTeX
// (throwOnError on): what it refuses is named with its line and nothing is sent; the API then checks again
// (content/latex.py) and its words go beside the field. Saving writes the draft, never the live text; the draft is
// then submitted for review, discarded, or (a reviewer) the last publish undone. The record's state decides which.
import { useRouter } from "next/navigation";
import { useDeferredValue, useEffect, useState, useSyncExternalStore } from "react";

import { ConfirmDialog } from "@/components/data/confirm-typed";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { Markdown, type MathProblem, mathProblems } from "@/components/modules/content/markdown";
import { ContentState } from "@/components/modules/content/tables";
import { useCan } from "@/components/shell/manifest";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import {
  type ContentQuestion,
  type ContentSolution,
  draftAction,
  draftOf,
  type Drafted,
  updateQuestion,
  updateSolution,
} from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { P } from "@/lib/modules";

const words = copy.content.editor;
const KEEP = "examleaf-admin:content-editor:";

type Values = Record<string, string>;

/** The fields a kind of record edits here, as text: their saved value (the draft's, else the live one's). */
function savedValues(kind: Drafted, record: ContentSolution | ContentQuestion): Values {
  const draft = draftOf(record);
  const pick = (field: string, live: unknown) => {
    const value = field in draft ? draft[field] : live;
    return Array.isArray(value) ? value.join("\n") : String(value ?? "");
  };
  if (kind === "solutions") return { body_md: pick("body_md", (record as ContentSolution).body_md) };
  const question = record as ContentQuestion;
  return {
    text_md: pick("text_md", question.text_md),
    table_md: pick("table_md", question.table_md),
    options_json: pick("options_json", question.options_json),
    marks_text: pick("marks_text", question.marks_text),
    tags: question.tags.join(", "),
  };
}

function readKeptRaw(key: string): string | null {
  try {
    return window.sessionStorage.getItem(KEEP + key);
  } catch {
    return null;
  }
}

const noSubscription = () => () => {};

function keep(key: string, values: Values | null) {
  try {
    if (values) window.sessionStorage.setItem(KEEP + key, JSON.stringify(values));
    else window.sessionStorage.removeItem(KEEP + key);
  } catch {
    // storage off: nothing kept
  }
}

export function Editor({ kind, record }: { kind: Drafted; record: ContentSolution | ContentQuestion }) {
  const router = useRouter();
  const can = useCan();
  const key = `${kind}-${record.id}`;
  const saved = savedValues(kind, record);
  const [values, setValues] = useState<Values>(saved);
  const [problems, setProblems] = useState<MathProblem[]>([]);
  const { run, busy, error } = useAction();
  const dirty = Object.keys(saved).some((field) => values[field] !== saved[field]);
  const source = kind === "solutions" ? values.body_md : [values.text_md, values.table_md].filter(Boolean).join("\n\n");
  const preview = useDeferredValue(source);
  const draft = draftOf(record);
  const changePermission = kind === "solutions" ? P.solutionsChange : P.questionsChange;
  const editable = can(changePermission);

  // what was typed and not saved before a reload or a new sign-in: offered back (sessionStorage, this tab only)
  const keptRaw = useSyncExternalStore(
    noSubscription,
    () => readKeptRaw(key),
    () => null,
  );
  const kept = keptRaw ? (JSON.parse(keptRaw) as Values) : null;
  const restorable = kept !== null && Object.keys(saved).some((field) => (kept[field] ?? saved[field]) !== values[field]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    const leaving = (event: MouseEvent) => {
      const link = (event.target as Element | null)?.closest("a[href]");
      if (!link || link.getAttribute("target") === "_blank" || event.defaultPrevented) return;
      if (!window.confirm(words.leave)) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", warn);
    document.addEventListener("click", leaving, true);
    return () => {
      window.removeEventListener("beforeunload", warn);
      document.removeEventListener("click", leaving, true);
    };
  }, [dirty]);

  const change = (field: string, value: string) => {
    const next = { ...values, [field]: value };
    setValues(next);
    keep(key, next);
  };

  const save = () => {
    const texts = kind === "solutions" ? [values.body_md] : [values.text_md, values.table_md, values.options_json];
    const found = texts.flatMap((text) => mathProblems(text));
    setProblems(found);
    if (found.length) return;
    run(async () => {
      if (kind === "solutions") await updateSolution(record.id, values.body_md);
      else
        await updateQuestion(record.id, {
          text_md: values.text_md,
          table_md: values.table_md,
          marks_text: values.marks_text,
          options_json: values.options_json.split("\n").map((option) => option.trim()).filter(Boolean),
          tags: values.tags.split(",").map((tag) => tag.trim()).filter(Boolean),
        });
      keep(key, null);
      toast.success(words.saved);
      router.refresh();
    });
  };

  const fieldId = (field: string) => `editor-${record.id}-${field}`;
  const area = (field: string, label: string, rows: number, help?: string) => (
    <Field id={fieldId(field)} label={label} help={help} error={fieldError(error, field)}>
      <Textarea
        name={field}
        rows={rows}
        value={values[field]}
        onChange={(event) => change(field, event.target.value)}
        spellCheck={false}
        readOnly={!editable}
        className="font-mono text-[15px] leading-relaxed"
        data-no-draft=""
      />
    </Field>
  );

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-2">
        <ContentState state={record.state ?? "published"} />
        {Object.keys(draft).length && record.state !== "published" ? (
          <span className="text-sm text-muted-foreground">{copy.content.changed}</span>
        ) : null}
      </div>
      {record.state === "in_review" ? <Alert variant="info" title={words.inReview} /> : <Alert variant="info" title={words.draftNote} />}
      {restorable && kept && editable ? (
        <Alert variant="warning" title={words.keptTitle}>
          <p>
            <Button variant="secondary" size="sm" onClick={() => setValues({ ...saved, ...kept })}>
              {words.keptRestore}
            </Button>
          </p>
        </Alert>
      ) : null}
      <form
        noValidate
        aria-label={kind === "solutions" ? copy.content.reviews.fieldNames.body_md : copy.content.reviews.fieldNames.text_md}
        onSubmit={(event) => {
          event.preventDefault();
          save();
        }}
        className="flex flex-col gap-4"
      >
        <ErrorSummary
          error={error}
          labels={{
            body_md: copy.content.reviews.fieldNames.body_md,
            text_md: copy.content.reviews.fieldNames.text_md,
            table_md: words.table,
            options_json: words.options,
            marks_text: words.marks,
            tags: words.tags,
          }}
          idPrefix={`editor-${record.id}-`}
        />
        {problems.length ? (
          <Alert variant="error" role="alert" title={words.mathTitle}>
            <ul className="m-0 flex list-none flex-col gap-1 p-0">
              {problems.map((problem, index) => (
                <li key={index}>{words.mathLine(problem.line, problem.message)}</li>
              ))}
            </ul>
          </Alert>
        ) : null}
        <div className="grid gap-5 min-[1100px]:grid-cols-2">
          <div className="flex min-w-0 flex-col gap-4">
            {kind === "solutions" ? (
              area("body_md", words.source, 18, words.sourceHelp)
            ) : (
              <>
                {area("text_md", words.source, 8, words.sourceHelp)}
                {area("table_md", words.table, 4)}
                {area("options_json", words.options, 4, words.optionsHelp)}
                <div className="grid gap-4 min-[560px]:grid-cols-2">
                  <Field id={fieldId("marks_text")} label={words.marks} error={fieldError(error, "marks_text")}>
                    <Input
                      name="marks_text"
                      value={values.marks_text}
                      onChange={(event) => change("marks_text", event.target.value)}
                      readOnly={!editable}
                      className="font-mono"
                      data-no-draft=""
                    />
                  </Field>
                  <Field id={fieldId("tags")} label={words.tags} help={words.tagsHelp} error={fieldError(error, "tags")}>
                    <Input
                      name="tags"
                      value={values.tags}
                      onChange={(event) => change("tags", event.target.value)}
                      readOnly={!editable}
                      data-no-draft=""
                    />
                  </Field>
                </div>
              </>
            )}
          </div>
          <section aria-labelledby={`${fieldId("preview")}-title`} className="flex min-w-0 flex-col gap-2">
            <h3 id={`${fieldId("preview")}-title`} className="m-0 text-[15px] font-semibold">
              {words.preview}
            </h3>
            <p className="m-0 text-sm text-muted-foreground">{words.previewLead}</p>
            <div className="min-w-0 rounded-lg border border-border bg-card p-4" aria-live="off">
              <Markdown source={preview} />
            </div>
          </section>
        </div>
        {editable ? (
          <div className="sticky bottom-0 z-10 -mx-1 flex flex-wrap items-center justify-between gap-3 border-t border-border bg-background px-1 py-3">
            <p className="m-0 text-sm text-muted-foreground" aria-live="polite">
              {dirty ? words.unsaved : words.upToDate}
            </p>
            <div className="flex flex-wrap gap-2.5">
              <Button
                variant="secondary"
                size="sm"
                disabled={!dirty || busy}
                onClick={() => {
                  setValues(saved);
                  setProblems([]);
                  keep(key, null);
                }}
              >
                {words.discardChanges}
              </Button>
              <Button type="submit" size="sm" busy={busy} disabled={!dirty}>
                {words.save}
              </Button>
            </div>
          </div>
        ) : null}
      </form>
      <DraftActions kind={kind} record={record} dirty={dirty} />
    </div>
  );
}

/** What can be done with the saved draft: submit it, discard it; undo the last publish (a reviewer). */
function DraftActions({ kind, record, dirty }: { kind: Drafted; record: ContentSolution | ContentQuestion; dirty: boolean }) {
  const router = useRouter();
  const can = useCan();
  const { run, busy, error } = useAction();
  const draft = draftOf(record);
  const change = can(kind === "solutions" ? P.solutionsChange : P.questionsChange);
  const hasDraft = Object.keys(draft).length > 0;
  return (
    <div className="flex flex-col gap-3">
      <ErrorSummary error={error} />
      {change && record.state === "draft" && hasDraft ? (
        <p className="m-0 text-[15px] text-muted-foreground">{words.submitLead}</p>
      ) : null}
      <div className="flex flex-wrap gap-2.5">
        {change && record.state === "draft" && hasDraft ? (
          <Button
            busy={busy}
            disabled={dirty}
            onClick={() =>
              run(async () => {
                await draftAction(kind, record.id, "submit");
                toast.success(words.submitted);
                router.refresh();
              })
            }
          >
            {words.submit}
          </Button>
        ) : null}
        {change && hasDraft ? (
          <ConfirmDialog
            triggerLabel={words.discardDraft}
            title={words.discardTitle}
            text={words.discardText}
            confirmLabel={words.discardDraft}
            success={words.discarded}
            onConfirm={() => draftAction(kind, record.id, "discard")}
          />
        ) : null}
        {can(P.papersPublish) && record.published_at ? (
          <ConfirmDialog
            triggerLabel={words.rollback}
            title={words.rollbackTitle}
            text={words.rollbackText}
            confirmLabel={words.rollback}
            success={words.rolledBack}
            onConfirm={() => draftAction(kind, record.id, "rollback")}
          />
        ) : null}
      </div>
    </div>
  );
}
