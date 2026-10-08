"use client";

// Course settings (Revise again and settings): PATCH learn/settings/ with the exam date, the minutes a day and the daily
// reminder. The API checks them (10 to 300 minutes) and its words show in the summary and beside the field; the form
// adds no rule of its own. Saved, the page is read again, so the plan's line under the form is the API's new plan.
// What was typed survives a log-in round trip in this tab; while a parent's consent is awaited the form is off.
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ConsentPending } from "@/components/account/parts";
import { useAction } from "@/components/account/use-action";
import { ErrorSummary } from "@/components/auth/error-summary";
import { fieldError } from "@/components/auth/use-auth-action";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/choice";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";
import { api, personal } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { dateInIndia } from "@/lib/dates";

import { readDraft, writeDraft } from "./draft";

type Values = { exam_date: string; minutes_per_day: string; reminders: boolean };

const DRAFT = "examleaf:course:settings";
const LABELS = { exam_date: "Your exam date", minutes_per_day: "Minutes a day", reminders: "Daily reminder" };

export function CourseSettings({
  settings,
  planLine,
  consentPending,
}: {
  settings: components["schemas"]["Learner"];
  /** The plan for the saved settings in words (from learn/plan/), or nothing to say. */
  planLine: string | null;
  consentPending: boolean;
}) {
  const router = useRouter();
  const { run, busy, error } = useAction();
  const form = useRef<HTMLFormElement>(null);
  const [tomorrow] = useState(() => dateInIndia(new Date(Date.now() + 86_400_000)));

  useEffect(() => {
    const draft = readDraft<Values>(DRAFT);
    const fields = form.current?.elements;
    if (!draft || !fields) return;
    (fields.namedItem("exam_date") as HTMLInputElement).value = draft.exam_date;
    (fields.namedItem("minutes_per_day") as HTMLInputElement).value = draft.minutes_per_day;
    (fields.namedItem("reminders") as HTMLInputElement).checked = draft.reminders;
  }, []);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const values: Values = {
      exam_date: String(data.get("exam_date") ?? ""),
      minutes_per_day: String(data.get("minutes_per_day") ?? "").trim(),
      reminders: data.get("reminders") === "on",
    };
    writeDraft(DRAFT, values);
    const minutes = /^\d+$/.test(values.minutes_per_day) ? Number(values.minutes_per_day) : values.minutes_per_day;
    const ok = await run(() =>
      personal(
        api.PATCH("/api/v1/learn/settings/", {
          // anything but a whole number goes as typed, for the API to answer in its own words
          body: {
            exam_date: values.exam_date || null,
            minutes_per_day: minutes as number,
            reminders: values.reminders,
          },
        }),
      ),
    );
    if (!ok) return;
    writeDraft(DRAFT, null);
    toast.success("Your course settings are saved.");
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-4 self-start border-[1.5px] border-foreground bg-card p-7 max-nav:p-5 [&_p]:m-0">
      <h2 className="font-head text-2xl leading-[1.15] tracking-normal">Course settings</h2>
      {consentPending ? <ConsentPending what="your course settings cannot be saved" /> : null}
      <ErrorSummary error={error} labels={LABELS} />
      <form ref={form} noValidate onSubmit={submit}>
        <fieldset disabled={consentPending} className="m-0 flex min-w-0 flex-col gap-4 border-0 p-0">
          <Field
            id="exam_date"
            label="Your exam date"
            help="From the Board's timetable once it's out."
            error={fieldError(error, "exam_date")}
          >
            <Input name="exam_date" type="date" min={tomorrow} defaultValue={settings.exam_date ?? ""} />
          </Field>
          <Field
            id="minutes_per_day"
            label="Minutes a day"
            help="10 to 300"
            error={fieldError(error, "minutes_per_day")}
          >
            <Input
              name="minutes_per_day"
              inputMode="numeric"
              autoComplete="off"
              defaultValue={settings.minutes_per_day ?? 30}
              className="w-24 font-mono text-[17px]"
            />
          </Field>
          <div className="border-t border-border pt-2">
            <Switch
              id="reminders"
              name="reminders"
              defaultChecked={settings.reminders ?? false}
              labelClassName="text-[15px]"
            >
              Daily reminder in the app
            </Switch>
          </div>
          {planLine ? <p className="text-sm leading-normal text-muted-foreground">{planLine}</p> : null}
          <Button type="submit" block busy={busy} className="min-h-[50px]">
            Save and re-plan
          </Button>
        </fieldset>
      </form>
    </div>
  );
}
