"use client";

// A revision's review and publish (POST course/revisions/{id}/submit|approve|needs-changes|publish|unpublish/): the
// moves its `transitions` allow this reader now, as the API decides them (whoever submitted it never decides it: the
// API's own_edit). Submitting is one press; approving takes an optional comment, sending back what to change;
// publishing is now or at a time to come (India's time, within a year; a schedule waits for the five-minute task);
// back to draft asks first. Below them, the title and the target length.
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ConfirmDialog } from "@/components/data/confirm-typed";
import { ActionForm, formText } from "@/components/forms/action-form";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { Button } from "@/components/ui/button";
import { Radio } from "@/components/ui/choice";
import { Field, FieldLegend, FieldSet } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import { changeRevision, type CourseRevision, moveRevision } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { fromLocalInput, toLocalInput } from "@/lib/format";

import { FormDialog } from "./form-dialog";

const words = copy.course.revision;

/** The publish dialog's moment: null for now, else the local time typed, read as India's. */
export function publishMoment(when: string, at: string): string | null {
  return when === "later" && at ? fromLocalInput(at) : null;
}

function Publish({ revision }: { revision: CourseRevision }) {
  const [when, setWhen] = useState<"now" | "later">(revision.publish_at ? "later" : "now");
  return (
    <FormDialog
      triggerLabel={words.moves.publish}
      triggerVariant="primary"
      title={words.publishTitle}
      text={words.publishText}
      submitLabel={words.moves.publish}
      labels={{ publish_at: words.at }}
      onOpen={() => setWhen(revision.publish_at ? "later" : "now")}
      onSubmit={async (form) => {
        const at = publishMoment(when, String(form.get("publish_at") ?? ""));
        await moveRevision(revision.id, "publish", { publishAt: at ?? undefined });
        toast.success(at ? words.scheduled : words.done.publish);
      }}
    >
      {(id, error) => (
        <>
          <FieldSet className="p-3.5">
            <FieldLegend>{words.when}</FieldLegend>
            <Radio name="when" value="now" checked={when === "now"} onChange={() => setWhen("now")}>
              {words.now}
            </Radio>
            <Radio name="when" value="later" checked={when === "later"} onChange={() => setWhen("later")}>
              {words.later}
            </Radio>
          </FieldSet>
          {when === "later" ? (
            <Field id={`${id}-publish_at`} label={words.at} error={fieldError(error, "publish_at")}>
              <Input
                name="publish_at"
                type="datetime-local"
                defaultValue={revision.publish_at ? toLocalInput(revision.publish_at) : ""}
              />
            </Field>
          ) : null}
        </>
      )}
    </FormDialog>
  );
}

function Comment({
  revision,
  move,
  title,
  text,
  required,
}: {
  revision: CourseRevision;
  move: "approve" | "needs_changes";
  title: string;
  text: string;
  required?: boolean;
}) {
  const label = required ? words.changesComment : words.comment;
  return (
    <FormDialog
      triggerLabel={words.moves[move]}
      triggerVariant={move === "approve" ? "primary" : "secondary"}
      title={title}
      text={text}
      submitLabel={words.moves[move]}
      success={words.done[move]}
      labels={{ comment: label }}
      onSubmit={(form) => moveRevision(revision.id, move, { comment: String(form.get("comment") ?? "").trim() })}
    >
      {(id, error) => (
        <Field
          id={`${id}-comment`}
          label={label}
          optional={!required}
          help={words.commentHelp}
          error={fieldError(error, "comment")}
        >
          <Textarea name="comment" rows={4} aria-required={required || undefined} />
        </Field>
      )}
    </FormDialog>
  );
}

export function RevisionActions({ revision }: { revision: CourseRevision }) {
  const router = useRouter();
  const submitting = useAction();
  const moves = revision.transitions;
  if (!moves.length) return <p className="m-0 text-[15px] text-muted-foreground">{words.noMoves}</p>;
  return (
    <div className="flex flex-col gap-3">
      <ErrorSummary error={submitting.error} />
      <div className="flex flex-wrap items-center gap-2.5">
        {moves.includes("submit") ? (
          <Button
            size="sm"
            busy={submitting.busy}
            onClick={() =>
              submitting.run(async () => {
                await moveRevision(revision.id, "submit", {});
                toast.success(words.done.submit);
                router.refresh();
              })
            }
          >
            {words.moves.submit}
          </Button>
        ) : null}
        {moves.includes("approve") ? (
          <Comment revision={revision} move="approve" title={words.approveTitle} text={words.approveText} />
        ) : null}
        {moves.includes("publish") ? <Publish revision={revision} /> : null}
        {moves.includes("needs_changes") ? (
          <Comment revision={revision} move="needs_changes" title={words.backTitle} text={words.backText} required />
        ) : null}
        {moves.includes("unpublish") ? (
          <ConfirmDialog
            triggerLabel={words.moves.unpublish}
            title={words.unpublishTitle}
            text={words.unpublishText}
            confirmLabel={words.moves.unpublish}
            success={words.done.unpublish}
            onConfirm={() => moveRevision(revision.id, "unpublish", {})}
          />
        ) : null}
      </div>
    </div>
  );
}

/** The revision's title and target length (PATCH course/revisions/{id}/). */
export function RevisionEdit({ revision }: { revision: CourseRevision }) {
  return (
    <ActionForm
      id={`revision-${revision.id}`}
      submitLabel={words.saveEdit}
      success={words.saved}
      labels={{ title: words.titleField, target_minutes: words.targetField }}
      saveBar
      onSubmit={(form) =>
        changeRevision(revision.id, {
          title: formText(form, "title"),
          target_minutes: Number(formText(form, "target_minutes")),
        })
      }
    >
      {(error) => (
        <>
          <Field id={`revision-${revision.id}-title`} label={words.titleField} error={fieldError(error, "title")}>
            <Input name="title" defaultValue={revision.title} autoComplete="off" />
          </Field>
          <Field
            id={`revision-${revision.id}-target_minutes`}
            label={words.targetField}
            help={words.targetHelp}
            error={fieldError(error, "target_minutes")}
          >
            <Input
              name="target_minutes"
              type="number"
              inputMode="numeric"
              min={1}
              max={60}
              defaultValue={revision.target_minutes}
              className="w-32"
            />
          </Field>
        </>
      )}
    </ActionForm>
  );
}
