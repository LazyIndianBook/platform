"use client";

// "Record your marks" (the #record card of a solutions page; Edit on My record): the date, the marks out of the
// paper's full marks, the minutes taken and what to revise. Checked here with the backend's own messages
// (practice/forms.py) before POST attempts/ (PATCH attempts/<id>/ to edit); the API has the last word, and its
// refusals (a parent's consent still awaited, 20 attempts of one paper a day) come back in the summary.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { ErrorSummary } from "@/components/auth/error-summary";
import { fieldError } from "@/components/auth/use-auth-action";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FormGrid } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { api, personal } from "@/lib/api/client";
import { ApiError, type FieldErrors } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { dateInIndia, formatDate } from "@/lib/dates";

import { useAction } from "./use-action";

type Attempt = components["schemas"]["Attempt"];
export type MarksValues = { date: string; marks_obtained: string; time_taken_minutes: string; notes: string };

const NOTES_MAX = 2000;
const LABELS = {
  date: "Date",
  marks_obtained: "Marks obtained",
  time_taken_minutes: "Time taken",
  notes: "What to revise",
};

/** The website form's checks and words; {} when the marks can be sent. */
export function validateMarks(values: MarksValues, fullMarks: number): FieldErrors {
  const errors: FieldErrors = {};
  if (!/^\d{4}-\d{2}-\d{2}$/.test(values.date)) errors.date = ["Enter the date you sat the paper."];
  const marks = values.marks_obtained.trim();
  if (!marks) errors.marks_obtained = ["Enter the marks you gave yourself."];
  else if (/^-\d/.test(marks)) errors.marks_obtained = ["Marks cannot be below 0."];
  else if (!/^\d+(\.\d+)?$/.test(marks)) errors.marks_obtained = ["Enter the marks as a number, such as 52.5."];
  else if (!/^\d+(\.\d)?$/.test(marks)) errors.marks_obtained = ["Use one decimal place at most, such as 52.5."];
  else if (Number(marks) > fullMarks) errors.marks_obtained = [`At most ${fullMarks}, the paper's full marks.`];
  const minutes = values.time_taken_minutes.trim();
  if (minutes && !/^\d+$/.test(minutes)) errors.time_taken_minutes = ["Enter the minutes as a number, such as 170."];
  if (values.notes.length > NOTES_MAX)
    errors.notes = [`At most 2,000 characters: this has ${values.notes.length.toLocaleString("en-IN")}.`];
  return errors;
}

type MarksFormProps = { paper: string; fullMarks: number; attempt?: Attempt };

export function MarksForm({ paper, fullMarks, attempt }: MarksFormProps) {
  const router = useRouter();
  const { run, busy, error, setError } = useAction();
  const [saved, setSaved] = useState<Attempt | null>(null);
  const [blank, setBlank] = useState(0); // a fresh form after each save

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const text = (name: keyof MarksValues) => String(form.get(name) ?? "");
    const values = {
      date: text("date"),
      marks_obtained: text("marks_obtained"),
      time_taken_minutes: text("time_taken_minutes"),
      notes: text("notes"),
    };
    const problems = validateMarks(values, fullMarks);
    const first = Object.values(problems)[0]?.[0];
    if (first) {
      setError(new ApiError(400, "invalid", first, problems));
      return;
    }
    const body = {
      date: values.date,
      marks_obtained: values.marks_obtained.trim(),
      time_taken_minutes: values.time_taken_minutes.trim() ? Number(values.time_taken_minutes) : null,
      notes: values.notes,
    };
    let answer: Attempt | undefined;
    const ok = await run(async () => {
      answer = attempt
        ? await personal(api.PATCH("/api/v1/attempts/{id}/", { params: { path: { id: attempt.id } }, body }))
        : await personal(api.POST("/api/v1/attempts/", { body: { paper, ...body } }));
    });
    if (!ok || !answer) return;
    if (attempt) {
      toast.success("Saved to your record.");
      router.push("/account/record/");
      return;
    }
    setSaved(answer);
    setBlank((count) => count + 1);
    router.refresh(); // My record's numbers elsewhere on the page, if any
  }

  return (
    <div className="flex flex-col gap-4">
      {saved ? (
        <Alert variant="success" title="Saved to your record">
          <p>
            {saved.paper}: {Number(saved.marks_obtained)}/{saved.full_marks} ({saved.percent}%) on{" "}
            {formatDate(saved.date ?? dateInIndia())}. <Link href="/account/record/">See My record</Link>.
          </p>
        </Alert>
      ) : null}
      <ErrorSummary error={error} labels={LABELS} />
      <form key={blank} className="flex flex-col gap-4" noValidate onSubmit={submit}>
        <FormGrid>
          <Field id="date" label="Date" required error={fieldError(error, "date")}>
            <Input name="date" type="date" defaultValue={attempt?.date ?? dateInIndia()} />
          </Field>
          <Field
            id="marks_obtained"
            label={`Marks obtained (out of ${fullMarks})`}
            required
            error={fieldError(error, "marks_obtained")}
          >
            <Input
              name="marks_obtained"
              inputMode="decimal"
              autoComplete="off"
              defaultValue={attempt ? String(Number(attempt.marks_obtained)) : ""}
            />
          </Field>
          <Field
            id="time_taken_minutes"
            label="Time taken (minutes)"
            optional
            error={fieldError(error, "time_taken_minutes")}
          >
            <Input
              name="time_taken_minutes"
              inputMode="numeric"
              autoComplete="off"
              defaultValue={attempt?.time_taken_minutes ?? ""}
            />
          </Field>
        </FormGrid>
        <Field id="notes" label="What to revise" optional error={fieldError(error, "notes")}>
          <Textarea name="notes" rows={2} maxLength={NOTES_MAX} defaultValue={attempt?.notes ?? ""} />
        </Field>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" busy={busy}>
            Save to my record
          </Button>
        </div>
      </form>
    </div>
  );
}
