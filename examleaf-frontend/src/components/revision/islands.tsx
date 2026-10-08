"use client";

// The revision page's islands: the book-code form (POST learn/redeem/: 5 tries an hour per student and per address),
// the plan preview for an exam date (GET learn/plan/), and a chapter's free clip, fetched when asked for and played
// with hls.js (its light build, about 120 KB gzipped), which loads only then (a browser without Media Source
// Extensions plays HLS itself and never downloads it).
import { CirclePlay, KeyRound } from "lucide-react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "@/components/ui/toaster";

import { useAction } from "@/components/account/use-action";
import { ErrorSummary } from "@/components/auth/error-summary";
import { fieldError } from "@/components/auth/use-auth-action";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { api, personal } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { dateInIndia, formatDate } from "@/lib/dates";

import { type Plan, PlanView } from "./course";

/** A refusal over the limit, in words: the API's 429 says only how many seconds are left. */
export function codeProblem(error: ApiError | null): ApiError | null {
  if (error?.status !== 429) return error;
  const seconds = Number(/(\d+) seconds?/.exec(error.message)?.[1]);
  const wait = seconds ? ` Try again in about ${Math.max(1, Math.ceil(seconds / 60))} minutes.` : " Try again later.";
  return new ApiError(429, error.code, `That is 5 tries this hour, the most a code can have.${wait}`);
}

export function RedeemForm() {
  const router = useRouter();
  const { run, busy, error } = useAction();
  const [form, setForm] = useState(0);
  const shown = codeProblem(error);
  return (
    <>
      <ErrorSummary error={shown} labels={{ code: "Book code" }} />
      <form
        key={form}
        className="flex flex-col gap-3"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          const code = String(new FormData(event.currentTarget).get("code") ?? "").trim();
          let opened: components["schemas"]["Entitlement"] | undefined;
          const ok = await run(async () => {
            opened = await personal(api.POST("/api/v1/learn/redeem/", { body: { code } }));
          });
          if (!ok || !opened) return;
          const what = opened.subject_name ?? "Every subject";
          toast.success(
            opened.valid_until ? `${what} is open until ${formatDate(opened.valid_until)}.` : `${what} is open.`,
          );
          setForm((count) => count + 1);
          router.refresh();
        }}
      >
        <Field
          id="code"
          label="Book code"
          required
          help="As printed in your book, such as 7KQM-3XPA-9TRW. Five tries an hour."
          error={fieldError(shown, "code")}
        >
          <Input name="code" autoComplete="off" autoCapitalize="characters" spellCheck={false} maxLength={40} />
        </Field>
        <div>
          <Button type="submit" busy={busy}>
            <KeyRound aria-hidden="true" />
            <span>Use the code</span>
          </Button>
        </div>
      </form>
    </>
  );
}

const MINUTES = [15, 30, 45, 60, 90, 120];

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
        <Button type="submit" variant="secondary" busy={busy} className="min-h-12">
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

/** A chapter's free clip (the chapter list's free_preview), or with a `label` any clip open to the student (Learning's
 *  Continue): its links, asked for when wanted (they last 10 minutes), and the player. */
export function FreeClip({
  clip: id,
  title,
  label = "Watch the free clip",
}: {
  clip: number | null;
  title: string;
  label?: string;
}) {
  const [clip, setClip] = useState<Clip | null>(null);
  const { run, busy, error } = useAction();
  const load = () =>
    run(async () => {
      if (id !== null) setClip(await personal(api.GET("/api/v1/learn/clips/{id}/", { params: { path: { id } } })));
    });

  if (clip) return <HlsVideo key={clip.hls_url} clip={clip} reload={load} />;
  return (
    <div className="flex flex-col items-start gap-1">
      {id === null ? (
        <p className="m-0 text-[15px] text-muted-foreground">
          No free clip in this chapter: the code in your book opens it.
        </p>
      ) : (
        <Button variant="ghost" size="sm" busy={busy} onClick={load}>
          <CirclePlay aria-hidden="true" />
          <span>
            {label}
            <span className="sr-only">: {title}</span>
          </span>
        </Button>
      )}
      {error ? <p className="m-0 text-[15px] font-semibold text-destructive">{error.message}</p> : null}
    </div>
  );
}

const PICK_A_DAY = "Choose the day of your exam: a date after today.";

/** The exam date (PATCH learn/settings/) for Learning's next three days, which the page reads again once it is saved. */
export function ExamDateForm({ examDate }: { examDate: string | null }) {
  const router = useRouter();
  const { run, busy, error, setError } = useAction();
  const [tomorrow] = useState(() => dateInIndia(new Date(Date.now() + 86_400_000)));
  return (
    <>
      <ErrorSummary error={error} labels={{ exam_date: "Exam date" }} />
      <form
        className="flex flex-wrap items-end gap-3"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault();
          const date = String(new FormData(event.currentTarget).get("exam_date") ?? "");
          if (!date || date < tomorrow) {
            setError(new ApiError(400, "invalid", PICK_A_DAY, { exam_date: [PICK_A_DAY] }));
            return;
          }
          const ok = await run(() => personal(api.PATCH("/api/v1/learn/settings/", { body: { exam_date: date } })));
          if (!ok) return;
          toast.success(`Your exam date is saved: ${formatDate(date, "long")}.`);
          router.refresh();
        }}
      >
        <Field id="exam_date" label="Exam date" className="flex-[1_1_160px]" error={fieldError(error, "exam_date")}>
          <Input name="exam_date" type="date" min={tomorrow} defaultValue={examDate ?? ""} />
        </Field>
        <Button type="submit" variant="secondary" busy={busy} className="min-h-12">
          Save the date
        </Button>
      </form>
    </>
  );
}
