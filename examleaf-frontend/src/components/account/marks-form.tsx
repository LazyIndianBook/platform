"use client";

// "Record your marks" (the #record card of a solutions page; Edit on My record), Direction A. Same fields, checks
// and API calls as before (date, marks out of the paper's full marks with one decimal, minutes, what to revise;
// POST attempts/ or PATCH attempts/<id>/; the API has the last word: consent pending, 20 a day).
// Added for robustness and the signature moment:
// - a draft of the four fields is kept in sessionStorage while the request is in flight, so a session that ended
//   (401 → log in and back, sessionMiddleware) brings the typed marks back on this page; it is cleared on success;
// - after the server confirms, the score is circled in red ink ([data-mark-landed], 220 ms, globals.css; still with
//   reduced motion) next to the success message. Nothing is shown as saved before the server answers.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "@/components/ui/toaster";

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
const FIELDS: (keyof MarksValues)[] = ["date", "marks_obtained", "time_taken_minutes", "notes"];

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

const draftKey = (paper: string, attempt?: Attempt) => `examleaf:marks-draft:${paper}:${attempt?.id ?? "new"}`;

function readDraft(key: string): Partial<MarksValues> | null {
  try {
    const raw = window.sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as Partial<MarksValues>) : null;
  } catch {
    return null; // storage off (private mode, quota): the form simply starts as usual
  }
}

function writeDraft(key: string, values: MarksValues | null) {
  try {
    if (values) window.sessionStorage.setItem(key, JSON.stringify(values));
    else window.sessionStorage.removeItem(key);
  } catch {
    /* storage unavailable: nothing to keep */
  }
}

type MarksFormProps = { paper: string; fullMarks: number; attempt?: Attempt };

export function MarksForm({ paper, fullMarks, attempt }: MarksFormProps) {
  const router = useRouter();
  const { run, busy, error, setError } = useAction();
  const [saved, setSaved] = useState<Attempt | null>(null);
  const [blank, setBlank] = useState(0); // a fresh form after each save
  const formRef = useRef<HTMLFormElement>(null);
  const key = draftKey(paper, attempt);

  // after a log-in round trip, put back what was typed (client only, after hydration: no mismatch)
  useEffect(() => {
    const draft = readDraft(key);
    const form = formRef.current;
    if (!draft || !form) return;
    for (const name of FIELDS) {
      const field = form.elements.namedItem(name) as HTMLInputElement | HTMLTextAreaElement | null;
      if (field && typeof draft[name] === "string") field.value = draft[name]!;
    }
  }, [key, blank]);

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
    writeDraft(key, values);
    let answer: Attempt | undefined;
    const ok = await run(async () => {
      answer = attempt
        ? await personal(api.PATCH("/api/v1/attempts/{id}/", { params: { path: { id: attempt.id } }, body }))
        : await personal(api.POST("/api/v1/attempts/", { body: { paper, ...body } }));
    });
    if (!ok || !answer) return; // the draft stays for the next try
    writeDraft(key, null);
    if (attempt) {
      toast.success("Saved to your record.");
      router.push("/account/record/");
      return;
    }
    setSaved(answer);
    setBlank((count) => count + 1);
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-4">
      {saved ? (
        <div className="flex items-center gap-5">
          <span
            data-mark-landed=""
            aria-hidden="true"
            className="flex size-16 flex-none -rotate-6 items-center justify-center rounded-full border-2 border-red-ink font-mono text-xl font-semibold text-red-ink"
          >
            {Number(saved.marks_obtained)}
          </span>
          <Alert variant="success" title="Saved to your record" className="flex-1">
            <p>
              {saved.paper}: {Number(saved.marks_obtained)}/{saved.full_marks} ({saved.percent}%) on{" "}
              {formatDate(saved.date ?? dateInIndia())}. <Link href="/account/record/">See My record</Link>.
            </p>
          </Alert>
        </div>
      ) : null}
      <ErrorSummary error={error} labels={LABELS} />
      <form ref={formRef} key={blank} className="flex flex-col gap-4" noValidate onSubmit={submit}>
        <FormGrid>
          <Field id="date" label="Date" required error={fieldError(error, "date")}>
            <Input name="date" type="date" defaultValue={attempt?.date ?? dateInIndia()} max={dateInIndia()} />
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
              className="font-mono"
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
              className="font-mono"
              defaultValue={attempt?.time_taken_minutes ?? ""}
            />
          </Field>
        </FormGrid>
        <Field id="notes" label="What to revise" optional error={fieldError(error, "notes")}>
          <Textarea
            name="notes"
            rows={2}
            maxLength={NOTES_MAX}
            className="font-head text-[17px]"
            defaultValue={attempt?.notes ?? ""}
          />
        </Field>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" busy={busy}>
            Save to my record
          </Button>
          <span className="text-sm text-muted-foreground">Half marks are fine: 52.5.</span>
        </div>
      </form>
    </div>
  );
}
