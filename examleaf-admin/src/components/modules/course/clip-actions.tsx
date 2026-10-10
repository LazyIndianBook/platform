"use client";

// A clip's actions (course/clips/{id}/): Retry beside the failure's reason (POST …/retry/: its video processed again,
// no new upload), its details (PATCH: title, kind, notes, the free-preview flag, tags), deleting it into the bin once
// its title is typed (its video and HLS files kept 30 days), and restoring it from there. Also a quiz item's and a
// card's way back from the bin: the same restore.
import { useRouter } from "next/navigation";

import { ConfirmTyped } from "@/components/data/confirm-typed";
import { ActionForm, formText } from "@/components/forms/action-form";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/choice";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { toast } from "@/components/ui/toaster";
import {
  changeClip,
  type CourseClip,
  type CourseRowKind,
  deleteRow,
  restoreRow,
  retryClip,
  type Schemas,
} from "@/lib/api/staff";
import { copy } from "@/lib/copy";

import { tagsOf } from "./shared";

const words = copy.course.clip;

export function RetryClip({ clip }: { clip: Pick<CourseClip, "id"> }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  return (
    <span className="inline-flex flex-col gap-2">
      <Button
        size="sm"
        busy={busy}
        title={words.retryHelp}
        onClick={() =>
          run(async () => {
            await retryClip(clip.id);
            toast.success(words.retried);
            router.refresh();
          })
        }
      >
        {words.retry}
      </Button>
      <ErrorSummary error={error} />
    </span>
  );
}

/** Out of the bin, back at its place (within 30 days). */
export function RestoreRow({ kind, id, name }: { kind: CourseRowKind; id: number; name: string }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  return (
    <span className="inline-flex flex-col gap-2">
      <Button
        size="sm"
        busy={busy}
        onClick={() =>
          run(async () => {
            await restoreRow(kind, id);
            toast.success(words.restored);
            router.refresh();
          })
        }
      >
        {words.restore}
        <span className="sr-only">: {name}</span>
      </Button>
      <ErrorSummary error={error} />
    </span>
  );
}

export function DeleteClip({ clip }: { clip: Pick<CourseClip, "id" | "title"> }) {
  return (
    <ConfirmTyped
      label={clip.title}
      triggerLabel={words.deleteButton}
      triggerVariant="destructive"
      title={words.deleteTitle}
      text={words.deleteText}
      confirmLabel={words.deleteButton}
      success={words.deleted}
      onConfirm={() => deleteRow("clips", clip.id)}
    />
  );
}

export function ClipEdit({ clip }: { clip: CourseClip }) {
  const id = `clip-${clip.id}`;
  return (
    <ActionForm
      id={id}
      submitLabel={words.save}
      success={words.saved}
      saveBar
      labels={{
        title: words.titleField,
        kind: words.kindField,
        notes: words.notesField,
        is_free_preview: words.freeField,
        tags: words.tagsField,
      }}
      onSubmit={(form) =>
        changeClip(clip.id, {
          title: formText(form, "title"),
          kind: formText(form, "kind") as Schemas["ClipKindEnum"],
          notes: String(form.get("notes") ?? ""),
          is_free_preview: form.get("is_free_preview") === "on",
          tags: tagsOf(formText(form, "tags")),
        })
      }
    >
      {(error) => (
        <>
          <Field id={`${id}-title`} label={words.titleField} error={fieldError(error, "title")}>
            <Input name="title" defaultValue={clip.title} autoComplete="off" />
          </Field>
          <Field id={`${id}-kind`} label={words.kindField} error={fieldError(error, "kind")}>
            <Select name="kind" defaultValue={clip.kind}>
              {Object.entries(copy.course.clipKinds).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field id={`${id}-notes`} label={words.notesField} help={words.notesHelp} error={fieldError(error, "notes")}>
            <Textarea name="notes" rows={6} defaultValue={clip.notes} />
          </Field>
          <Checkbox name="is_free_preview" defaultChecked={clip.is_free_preview}>
            {words.freeField}
          </Checkbox>
          <Field id={`${id}-tags`} label={words.tagsField} help={words.tagsHelp} error={fieldError(error, "tags")}>
            <Input name="tags" defaultValue={(clip.tags ?? []).join(", ")} autoComplete="off" />
          </Field>
        </>
      )}
    </ActionForm>
  );
}
