"use client";

// The revision course's islands: the book-code form (POST learn/redeem/: 5 tries an hour per student and per address),
// the plan preview for an exam date (GET learn/plan/), the exam date and minutes a day of Learning (PATCH
// learn/settings/), and a clip fetched when asked for and played with hls.js (its light build, about 120 KB gzipped),
// which loads only then (a browser without Media Source Extensions plays HLS itself and never downloads it).
import { Play } from "lucide-react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "@/components/ui/toaster";

import { useAction } from "@/components/account/use-action";
import { ErrorSummary } from "@/components/auth/error-summary";
import { fieldError } from "@/components/auth/use-auth-action";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldError } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { api, personal } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { dateInIndia, formatDate } from "@/lib/dates";

import { type Plan, PlanView } from "./course";

const USED = /used already/i; // learn/services.py redeem(): "This code has been used already."
const UNKNOWN = /not valid/i; // "This code is not valid. Check it against the one printed in your book."

/** A refusal of a book code in the design's words (Learning, book-code states): used, not recognised, or over the
 *  limit (the API's 429 says only how many seconds are left). Other refusals keep the API's own words. */
export function codeProblem(error: ApiError | null): ApiError | null {
  if (!error) return null;
  if (error.status === 429) {
    const seconds = Number(/(\d+) seconds?/.exec(error.message)?.[1]);
    const wait = seconds ? ` Try again in about ${Math.max(1, Math.ceil(seconds / 60))} minutes.` : " Try again later.";
    return new ApiError(429, error.code, `That is 5 tries this hour, the most a code can have.${wait}`);
  }
  const said = error.fields.code?.join(" ") ?? "";
  const words = USED.test(said)
    ? "This code has already been used. Each code opens one account. If it's yours, log in with that account."
    : UNKNOWN.test(said)
      ? "We don't recognise that code. Check it against the page in your book; it has 12 characters."
      : null;
  return words ? new ApiError(error.status, error.code, words, { code: [words] }) : error;
}

/** The code printed in a book (or the course bought): opens its subject. Disabled, with the reason beside it, while
 *  a parent's consent is awaited (the API refuses the code then). */
export function RedeemForm({ disabled = false }: { disabled?: boolean }) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  const [form, setForm] = useState(0);
  const [opened, setOpened] = useState<components["schemas"]["Entitlement"] | null>(null);
  const shown = codeProblem(error);
  const problem = fieldError(shown, "code");
  return (
    <div className="flex flex-col gap-3">
      {opened ? (
        <Alert
          variant="success"
          title={
            opened.valid_until
              ? `${opened.subject_name ?? "Every subject"} is open until ${formatDate(opened.valid_until)}.`
              : `${opened.subject_name ?? "Every subject"} is open.`
          }
        >
          <p>Every clip, card and quiz question.</p>
        </Alert>
      ) : null}
      <ErrorSummary error={shown} labels={{ code: "Code from your book" }} />
      <form
        key={form}
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          const code = String(new FormData(event.currentTarget).get("code") ?? "").trim();
          let answer: components["schemas"]["Entitlement"] | undefined;
          setOpened(null);
          const ok = await run(async () => {
            answer = await personal(api.POST("/api/v1/learn/redeem/", { body: { code } }));
          });
          if (!ok || !answer) return;
          setOpened(answer);
          setForm((count) => count + 1);
          router.refresh();
        }}
      >
        <fieldset disabled={disabled} className="m-0 flex min-w-0 flex-col gap-1.5 border-0 p-0">
          <label htmlFor="code" className="text-[15px] leading-snug font-semibold">
            Code from your book
          </label>
          <div className="flex gap-2">
            <Input
              id="code"
              name="code"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              maxLength={40}
              className="font-mono"
              aria-invalid={problem ? true : undefined}
              aria-describedby={problem ? "code-help code-error" : "code-help"}
            />
            <Button type="submit" busy={busy} className="px-4">
              Open
            </Button>
          </div>
          <p id="code-help" className="m-0 text-sm leading-relaxed text-muted-foreground">
            As printed in your book, such as <span className="whitespace-nowrap">7KQM-3XPA-9TRW</span>. Five tries an
            hour.
          </p>
          {problem ? <FieldError id="code-error">{problem.join(" ")}</FieldError> : null}
        </fieldset>
      </form>
    </div>
  );
}

export const MINUTES = [15, 30, 45, 60, 90, 120];

const minuteOptions = (current: number) => [...new Set([...MINUTES, current])].sort((a, b) => a - b);

export function PlanPreview({
  examDate,
  minutesPerDay,
  subjects,
}: {
  examDate: string | null;
  minutesPerDay: number;
  subjects: { id: number; name: string }[];
}) {
  const { run, busy, error } = useAction();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [tomorrow] = useState(() => dateInIndia(new Date(Date.now() + 86_400_000)));
  // the API's own words point at learn/settings/: say what the student can do here
  const shown =
    error?.fields.exam_date && !error.unavailable
      ? new ApiError(400, "invalid", "Choose the day of your exam: a date after today.", {
          exam_date: ["Choose the day of your exam: a date after today."],
        })
      : error;
  return (
    <>
      <ErrorSummary error={shown} labels={{ exam_date: "Exam date", minutes: "Minutes a day" }} />
      <form
        className="flex flex-wrap items-end gap-3"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          const query = { exam_date: String(form.get("exam_date") ?? ""), minutes: Number(form.get("minutes")) };
          await run(async () => {
            setPlan(await personal(api.GET("/api/v1/learn/plan/", { params: { query } })));
          });
        }}
      >
        <Field
          id="exam_date"
          label="Exam date"
          required
          className="flex-[1_1_160px]"
          error={fieldError(shown, "exam_date")}
        >
          <Input name="exam_date" type="date" min={tomorrow} defaultValue={examDate ?? ""} />
        </Field>
        <Field id="minutes" label="Minutes a day" className="flex-[1_1_120px]" error={fieldError(shown, "minutes")}>
          <Select name="minutes" defaultValue={MINUTES.includes(minutesPerDay) ? minutesPerDay : 30}>
            {MINUTES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </Select>
        </Field>
        <Button type="submit" variant="secondary" busy={busy}>
          Show my plan
        </Button>
      </form>
      {plan ? (
        <div aria-live="polite">
          <PlanView plan={plan} subjectName={(id) => subjects.find((s) => s.id === id)?.name ?? "This subject"} />
        </div>
      ) : null}
    </>
  );
}

type Clip = components["schemas"]["Clip"];

// the player's code loads with the first clip asked for, not with the page (Lighthouse review L2)
const HlsVideo = dynamic(() => import("./hls-video").then((module) => module.HlsVideo), { ssr: false });

const spinner =
  "size-5 rounded-full border-2 border-current border-r-transparent motion-safe:animate-[el-spin_0.8s_linear_infinite]";

/** A chapter's free clip (the chapter list's free_preview), or with a `label` any clip open to the student (Continue):
 *  its links, asked for when wanted (they last 10 minutes), and the vertical player. `look`: a link in a list, a
 *  button, or a stage the size of a poster with a round play button (Learning). */
export function FreeClip({
  clip: id,
  title,
  label = "Watch the free clip",
  look = "link",
}: {
  clip: number | null;
  title: string;
  label?: string;
  look?: "link" | "button" | "stage";
}) {
  const [clip, setClip] = useState<Clip | null>(null);
  const { run, busy, error } = useAction();
  const load = () =>
    run(async () => {
      if (id !== null) setClip(await personal(api.GET("/api/v1/learn/clips/{id}/", { params: { path: { id } } })));
    });

  if (clip) return <HlsVideo key={clip.hls_url} clip={clip} reload={load} />;
  const problem = error ? <p className="m-0 text-[15px] font-semibold text-destructive">{error.message}</p> : null;
  if (id === null) {
    return (
      <p className="m-0 text-sm text-muted-foreground">No free clip in this chapter: the code in your book opens it.</p>
    );
  }
  if (look === "stage") {
    return (
      <div className="flex flex-col gap-2">
        <button
          type="button"
          aria-busy={busy || undefined}
          onClick={() => (busy ? undefined : load())}
          className="flex aspect-video w-full cursor-pointer items-center justify-center bg-paper-2 text-white active:translate-y-px aria-busy:cursor-progress"
        >
          <span aria-hidden="true" className="flex size-16 items-center justify-center rounded-full bg-night">
            {busy ? <span className={spinner} /> : <Play className="ml-1 size-6 fill-current" />}
          </span>
          <span className="sr-only">
            {label}: {title}
          </span>
        </button>
        {problem}
      </div>
    );
  }
  return (
    <div className="flex flex-col items-start gap-1">
      <Button
        variant={look === "button" ? "primary" : "ghost"}
        size={look === "button" ? "default" : "sm"}
        busy={busy}
        onClick={load}
        className={look === "link" ? "-my-2.5 -ml-4 min-h-11 text-sm" : "max-nav:w-full"}
      >
        <span>
          {label}
          <span className="sr-only">: {title}</span>
        </span>
      </Button>
      {problem}
    </div>
  );
}

const PICK_A_DAY = "Choose the day of your exam: a date after today.";

/** The exam date and the minutes a day (PATCH learn/settings/) for Learning's next days, which the page reads again
 *  once they are saved. */
export function ExamDateForm({ examDate, minutesPerDay = 30 }: { examDate: string | null; minutesPerDay?: number }) {
  const router = useRouter();
  const { run, busy, error, setError } = useAction();
  const [tomorrow] = useState(() => dateInIndia(new Date(Date.now() + 86_400_000)));
  return (
    <>
      <ErrorSummary error={error} labels={{ exam_date: "Exam date", minutes_per_day: "Minutes a day" }} />
      <form
        className="flex flex-col gap-3"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          const date = String(form.get("exam_date") ?? "");
          if (!date || date < tomorrow) {
            setError(new ApiError(400, "invalid", PICK_A_DAY, { exam_date: [PICK_A_DAY] }));
            return;
          }
          const body = { exam_date: date, minutes_per_day: Number(form.get("minutes_per_day")) };
          const ok = await run(() => personal(api.PATCH("/api/v1/learn/settings/", { body })));
          if (!ok) return;
          toast.success(
            `Your plan is saved: the exam on ${formatDate(date, "long")}, ${body.minutes_per_day} minutes a day.`,
          );
          router.refresh();
        }}
      >
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(150px,100%),1fr))] gap-3">
          <Field id="exam_date" label="Exam date" error={fieldError(error, "exam_date")}>
            <Input name="exam_date" type="date" min={tomorrow} defaultValue={examDate ?? ""} />
          </Field>
          <Field id="minutes_per_day" label="Minutes a day" error={fieldError(error, "minutes_per_day")}>
            <Select name="minutes_per_day" defaultValue={minutesPerDay}>
              {minuteOptions(minutesPerDay).map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div>
          <Button type="submit" variant="secondary" busy={busy}>
            Save the plan
          </Button>
        </div>
      </form>
    </>
  );
}
