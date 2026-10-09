"use client";

// A quiz item's actions (course/items/{id}/): its text, options, answer key, explanation and metadata to change
// (PATCH: a version in its history), "Needs checking" (POST …/flag/: a report in the content triage, once while one is
// open), deleting it into the bin with five seconds to undo, and restoring it from there.
import { useRouter } from "next/navigation";

import { ActionForm, formText } from "@/components/forms/action-form";
import { ErrorSummary } from "@/components/forms/error-summary";
import { fieldError, useAction } from "@/components/forms/use-action";
import { UndoNotice, useUndo } from "@/components/modules/orders/undo";
import { Button } from "@/components/ui/button";
import { Field, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { toast } from "@/components/ui/toaster";
import { changeItem, type CourseItem, deleteRow, flagItem, type Schemas } from "@/lib/api/staff";
import { copy } from "@/lib/copy";

import { FormDialog } from "./form-dialog";
import { tagsOf } from "./shared";

const words = copy.course.item;

/** The options as the form shows them, one a line. */
export const optionLines = (options: unknown) => (Array.isArray(options) ? options.map(String).join("\n") : "");

/** The form's options: one a line, the empty lines dropped. */
export const optionsOf = (typed: string) =>
  typed
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

export function ItemEdit({ item }: { item: CourseItem }) {
  const id = `item-${item.id}`;
  return (
    <ActionForm
      id={id}
      submitLabel={words.save}
      success={words.saved}
      saveBar
      labels={{
        kind: words.kindField,
        text: words.textField,
        options: words.optionsField,
        answer: words.answerField,
        explanation: words.explanationField,
        topic: words.topicField,
        marks: words.marksField,
        difficulty: words.difficultyField,
        bloom: words.bloomField,
        tags: words.tagsField,
      }}
      onSubmit={(form) =>
        changeItem(item.id, {
          kind: formText(form, "kind") as Schemas["QuizItemKindEnum"],
          text: String(form.get("text") ?? ""),
          options: optionsOf(String(form.get("options") ?? "")),
          answer: formText(form, "answer"),
          explanation: String(form.get("explanation") ?? ""),
          topic: formText(form, "topic"),
          marks: Number(formText(form, "marks")),
          difficulty: formText(form, "difficulty") as Schemas["QuizItemDifficultyEnum"] | "",
          bloom: formText(form, "bloom") as Schemas["QuizItemBloomEnum"] | "",
          tags: tagsOf(formText(form, "tags")),
        })
      }
    >
      {(error) => (
        <>
          <Field id={`${id}-kind`} label={words.kindField} error={fieldError(error, "kind")}>
            <Select name="kind" defaultValue={item.kind}>
              {Object.entries(copy.course.itemKinds).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field id={`${id}-text`} label={words.textField} error={fieldError(error, "text")}>
            <Textarea name="text" rows={4} defaultValue={item.text} />
          </Field>
          <Field
            id={`${id}-options`}
            label={words.optionsField}
            help={words.optionsHelp}
            error={fieldError(error, "options")}
          >
            <Textarea name="options" rows={4} defaultValue={optionLines(item.options)} />
          </Field>
          <Field
            id={`${id}-answer`}
            label={words.answerField}
            help={words.answerHelp}
            error={fieldError(error, "answer")}
          >
            <Input name="answer" defaultValue={item.answer} autoComplete="off" className="font-mono" />
          </Field>
          <Field id={`${id}-explanation`} label={words.explanationField} error={fieldError(error, "explanation")}>
            <Textarea name="explanation" rows={4} defaultValue={item.explanation} />
          </Field>
          <FormGrid>
            <Field id={`${id}-topic`} label={words.topicField} error={fieldError(error, "topic")}>
              <Input name="topic" defaultValue={item.topic} autoComplete="off" />
            </Field>
            <Field id={`${id}-marks`} label={words.marksField} error={fieldError(error, "marks")}>
              <Input name="marks" type="number" inputMode="numeric" min={1} max={10} defaultValue={item.marks} />
            </Field>
            <Field id={`${id}-difficulty`} label={words.difficultyField} error={fieldError(error, "difficulty")}>
              <Select name="difficulty" defaultValue={item.difficulty ?? ""}>
                <option value="">{copy.course.notSet}</option>
                {Object.entries(copy.course.difficulties).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field id={`${id}-bloom`} label={words.bloomField} error={fieldError(error, "bloom")}>
              <Select name="bloom" defaultValue={item.bloom ?? ""}>
                <option value="">{copy.course.notSet}</option>
                {Object.entries(copy.course.blooms).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
          </FormGrid>
          <Field id={`${id}-tags`} label={words.tagsField} help={words.tagsHelp} error={fieldError(error, "tags")}>
            <Input name="tags" defaultValue={(item.tags ?? []).join(", ")} autoComplete="off" />
          </Field>
        </>
      )}
    </ActionForm>
  );
}

/** "Needs checking": the content triage gets a report of kind item_analysis (or the one open already). */
export function FlagItem({ item }: { item: Pick<CourseItem, "id"> }) {
  return (
    <FormDialog
      triggerLabel={words.flag}
      title={words.flagTitle}
      text={words.flagText}
      submitLabel={words.flagButton}
      labels={{ note: words.flagNote }}
      onSubmit={async (form) => {
        const answer = await flagItem(item.id, String(form.get("note") ?? "").trim());
        toast.success(answer.created ? words.flaggedNew : words.flaggedOpen);
      }}
    >
      {(id, error) => (
        <Field
          id={`${id}-note`}
          label={words.flagNote}
          optional
          help={words.flagNoteHelp}
          error={fieldError(error, "note")}
        >
          <Textarea name="note" rows={3} />
        </Field>
      )}
    </FormDialog>
  );
}

/** Into the bin after five seconds, unless undone (frequent, and restorable for 30 days). */
export function DeleteItem({ item }: { item: Pick<CourseItem, "id"> }) {
  const router = useRouter();
  const { run, error } = useAction();
  const { pending, start, undo } = useUndo();
  return (
    <span className="inline-flex flex-col gap-2">
      {pending ? (
        <UndoNotice pending={pending} undo={undo} undoLabel={copy.course.outline.undo} />
      ) : (
        <Button
          size="sm"
          variant="destructive"
          onClick={() =>
            start(words.deleting, () =>
              run(async () => {
                await deleteRow("items", item.id);
                toast.success(words.deleted);
                router.refresh();
              }),
            )
          }
        >
          {words.deleteButton}
        </Button>
      )}
      <ErrorSummary error={error} />
    </span>
  );
}
