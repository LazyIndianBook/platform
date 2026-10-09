"use client";

// "Report a mistake" under each worked solution of /s/<code>/ and under a clip of the revision course (POST
// /api/v1/reports/). One tap opens it: a native <details>, so it works before any script and never opens by itself.
// Then what is wrong (one of six kinds), for a solution of several steps the step, an optional note and an optional
// email address (only to say when it is fixed; the server deletes it then). The page fills in what it is about: the
// paper and the question, or the clip, and the print run a printed QR code carried (?printing=). Turnstile while the
// server has it on, and a honeypot; the server's limits (5 an hour, 20 a day) are said in words with the time to try
// again. The bot check loads only once a form is opened: a paper has dozens of solutions.
import { useState } from "react";

import { retryAt, secondsIn } from "@/app/(public)/retry-at";
import { ErrorSummary } from "@/components/auth/error-summary";
import { CHECKING, useTurnstile } from "@/components/auth/turnstile";
import { useConfig } from "@/components/providers/config-provider";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Radio } from "@/components/ui/choice";
import { Field, FieldError } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { api, ApiError, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type Category = components["schemas"]["ReaderCategoryEnum"];

/** What a report is about: a question and its solution on a paper (by their codes), or a clip of the course. */
export type MistakeTarget =
  { kind: "solution" | "question"; paper: string; question: string; steps?: number } | { kind: "clip"; clip: number };

const KINDS: { value: Category; label: string; clip?: string }[] = [
  { value: "wrong_answer", label: "A wrong answer or step", clip: "Something in it is wrong" },
  { value: "typo", label: "A typing or spelling mistake" },
  { value: "marks", label: "The marks or the marking scheme" },
  { value: "unclear", label: "Hard to follow" },
  { value: "display", label: "Maths or a picture does not show" },
  { value: "other", label: "Something else" },
];
const PRINTING = /^[A-Za-z0-9][A-Za-z0-9-]{0,39}$/; // the print run's label, as the server checks it
const CHOOSE = "Choose what is wrong.";

const slug = (text: string) =>
  text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

/** The print run a printed QR code carried (?printing=PHY-2027-1), or "" when it is missing or not a label. */
export function printingOf(value: string | string[] | undefined): string {
  const text = (Array.isArray(value) ? value[0] : value)?.trim() ?? "";
  return PRINTING.test(text) ? text : "";
}

export function ReportMistake({ target, printing = "" }: { target: MistakeTarget; printing?: string }) {
  const [opened, setOpened] = useState(false);
  return (
    <details className="report-mistake" onToggle={(event) => event.currentTarget.open && setOpened(true)}>
      <summary className="inline-flex min-h-11 cursor-pointer list-none items-center font-sans text-[15px] font-semibold text-primary underline underline-offset-3 hover:text-red-ink [&::-webkit-details-marker]:hidden">
        Report a mistake
      </summary>
      {opened ? <MistakeForm target={target} printing={printingOf(printing)} /> : null}
    </details>
  );
}

function MistakeForm({ target, printing }: { target: MistakeTarget; printing: string }) {
  const id = target.kind === "clip" ? `report-clip-${target.clip}` : `report-${slug(target.question) || "q"}`;
  const siteKey = useConfig()?.auth.turnstile_site_key ?? null;
  const [values, setValues] = useState({ category: "", step: "", note: "", email: "", website: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const bot = useTurnstile(siteKey, error);
  const [sent, setSent] = useState<string | null>(null);
  const kinds = target.kind === "clip" ? KINDS.filter((kind) => kind.value !== "marks") : KINDS;
  const steps = target.kind === "clip" ? 0 : (target.steps ?? 0);
  const set = (name: keyof typeof values, value: string) => setValues((all) => ({ ...all, [name]: value }));
  const fieldError = (name: string) => error?.fields[name] ?? null;

  async function send(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (!values.category) {
      setError(new ApiError(400, "invalid", CHOOSE, { category: [CHOOSE] }));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const where =
        target.kind === "clip"
          ? { clip: target.clip }
          : {
              paper: target.paper,
              question: target.question,
              step: target.kind === "solution" && values.step ? Number(values.step) : null,
            };
      const body = {
        kind: target.kind,
        ...where,
        printing,
        category: values.category as Category,
        note: values.note.trim(),
        email: values.email.trim(),
        website: values.website,
        ...(siteKey ? { turnstile: bot.token } : {}),
      };
      setSent((await unwrap(api.POST("/api/v1/reports/", { body }))).detail);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? inWords(caught)
          : new ApiError(0, "unavailable", "That did not work. Please try again."),
      );
    } finally {
      setBusy(false);
    }
  }

  if (sent)
    return (
      <Alert variant="success" title="Thank you" className="mt-2 max-w-[34rem]">
        <p>{sent}</p>
      </Alert>
    );
  // the summary's links lead to this form's own fields (a paper has many forms: their ids carry the question's)
  const shown =
    error &&
    new ApiError(
      error.status,
      error.code,
      error.message,
      Object.fromEntries(Object.entries(error.fields).map(([name, messages]) => [`${id}-${name}`, messages])),
      error.body,
    );
  const labels = Object.fromEntries(
    Object.entries({
      category: "What is wrong",
      step: "Which step",
      note: "What you found",
      email: "Your email address",
      question: "The question",
      clip: "The clip",
      printing: "The print run",
      turnstile: "Bot check",
    }).map(([name, label]) => [`${id}-${name}`, label]),
  );
  return (
    <form
      onSubmit={send}
      noValidate
      aria-label="Report a mistake"
      className="mt-2 flex max-w-[34rem] flex-col gap-4 rounded-lg border border-border bg-card p-5 font-sans max-nav:p-4"
    >
      <ErrorSummary error={shown} labels={labels} />
      <fieldset
        id={`${id}-category`}
        className="m-0 flex min-w-0 flex-col border-0 p-0"
        aria-describedby={fieldError("category") ? `${id}-category-error` : undefined}
      >
        <legend className="mb-1 p-0 text-[15px] leading-snug font-semibold text-foreground">What is wrong?</legend>
        {kinds.map((kind) => (
          <Radio
            key={kind.value}
            name={`${id}-category`}
            value={kind.value}
            checked={values.category === kind.value}
            onChange={() => set("category", kind.value)}
            aria-invalid={fieldError("category") ? true : undefined}
          >
            {target.kind === "clip" && kind.clip ? kind.clip : kind.label}
          </Radio>
        ))}
        {fieldError("category") ? (
          <FieldError id={`${id}-category-error`}>{fieldError("category")!.join(" ")}</FieldError>
        ) : null}
      </fieldset>
      {steps > 1 ? (
        <Field id={`${id}-step`} label="Which step" optional error={fieldError("step")}>
          <Select value={values.step} onChange={(event) => set("step", event.target.value)}>
            <option value="">The whole solution</option>
            {Array.from({ length: steps }, (_, index) => (
              <option key={index} value={index + 1}>
                Step {index + 1}
              </option>
            ))}
          </Select>
        </Field>
      ) : null}
      <Field
        id={`${id}-note`}
        label="What you found"
        optional
        help="Up to 1,000 characters. No links, please."
        error={fieldError("note")}
      >
        <Textarea rows={3} maxLength={1000} value={values.note} onChange={(event) => set("note", event.target.value)} />
      </Field>
      <Field
        id={`${id}-email`}
        label="Your email address"
        optional
        help="Only to tell you once it is fixed. We delete it then."
        error={fieldError("email")}
      >
        <Input
          type="email"
          autoComplete="email"
          value={values.email}
          onChange={(event) => set("email", event.target.value)}
        />
      </Field>
      {/* the honeypot: people never see it, bots fill it in */}
      <input
        type="text"
        name="website"
        tabIndex={-1}
        autoComplete="off"
        aria-hidden="true"
        className="hidden"
        value={values.website}
        onChange={(event) => set("website", event.target.value)}
      />
      {bot.widget}
      <div>
        <Button type="submit" busy={busy || bot.waiting}>
          {bot.waiting ? CHECKING : "Send the report"}
        </Button>
      </div>
    </form>
  );
}

/** A refusal in words: the limit's 429 says when to try again. */
function inWords(error: ApiError): ApiError {
  if (error.status !== 429) return error;
  const at = retryAt(secondsIn(error.message));
  return new ApiError(429, error.code, `That is as many reports as we take for now. You can try again at ${at}.`);
}
