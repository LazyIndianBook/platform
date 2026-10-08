// The revision course as the API answers it, drawn without any state (the page and its islands share these): what
// is open to the student (learn/entitlements/) and the pass plan (learn/plan/). Only the API's own numbers.
import Link from "next/link";

import type { components } from "@/lib/api/schema";
import { withNext } from "@/lib/auth/next-url";
import { formatDate } from "@/lib/dates";

export type Entitlement = components["schemas"]["Entitlement"];

type PlanClip = { id: number; chapter: number; title: string; kind: string; duration: number };
/** learn/plan/ (the schema says only "object": API.md "The pass plan" gives its shape). */
export type Plan = {
  exam_date: string;
  days_left: number;
  minutes_per_day: number;
  days: { date: string; minutes: number; clips: PlanClip[] }[];
  not_scheduled: number[];
  minimum_to_pass: {
    subject: number;
    pass_marks: number;
    marks: string;
    chapters: { id: number; number: number; title: string; weight: string; minutes: number; clips: PlanClip[] }[];
  }[];
};

const SOURCE: Record<Entitlement["source"], string> = {
  book_code: "a book code",
  purchase: "a purchase",
  grant: "a staff grant",
};

/** Each subject open to the student: until when (or that it ended), and what opened it. */
export function EntitlementList({ entitlements, today }: { entitlements: Entitlement[]; today: string }) {
  return (
    <dl className="m-0 flex flex-col gap-2">
      {entitlements.map((item) => {
        const ended = Boolean(item.valid_until && item.valid_until < today);
        return (
          <div key={item.id} className="flex flex-col">
            <dt className="font-semibold">{item.subject_name ?? "Every subject"}</dt>
            <dd className="m-0 text-muted-foreground">
              {ended
                ? `Ended on ${formatDate(item.valid_until!)}`
                : item.valid_until
                  ? `Open until ${formatDate(item.valid_until)}`
                  : "Open"}{" "}
              · from {SOURCE[item.source]}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

const SHOWN_DAYS = 7;
const minutes = (seconds: number) => Math.max(1, Math.round(seconds / 60));

/** The plan for the exam day: the first week's clips, what did not fit, and the quickest way to the pass marks. */
export function PlanView({ plan, subjectName }: { plan: Plan; subjectName: (id: number) => string }) {
  const later = plan.days.length - SHOWN_DAYS;
  return (
    <div className="flex flex-col gap-3 [&_p]:m-0">
      <p>
        <strong>{plan.days_left}</strong> day{plan.days_left === 1 ? "" : "s"} to your exam on{" "}
        {formatDate(plan.exam_date, "long")}, at {plan.minutes_per_day} minutes a day.
      </p>
      {plan.days.length ? (
        <ol aria-label="Your first days" className="m-0 flex list-none flex-col gap-2 p-0">
          {plan.days.slice(0, SHOWN_DAYS).map((day) => (
            <li key={day.date} className="rounded-lg border border-border px-3 py-2">
              <span className="font-semibold">
                {formatDate(day.date)} · {day.minutes} min
              </span>
              <ul className="m-0 pl-5 text-[15px]">
                {day.clips.map((clip) => (
                  <li key={clip.id}>
                    {clip.title} ({minutes(clip.duration)} min)
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      ) : (
        <p>
          Nothing to plan yet: no clip of the subjects open to you is ready. The chapters show theirs as they arrive.
        </p>
      )}
      {later > 0 ? (
        <p className="text-muted-foreground">
          And {later} more day{later === 1 ? "" : "s"}: the app shows each day&apos;s clips and keeps count of what you
          watched.
        </p>
      ) : null}
      {plan.not_scheduled.length ? (
        <p className="text-muted-foreground">
          {plan.not_scheduled.length} chapter{plan.not_scheduled.length === 1 ? " does" : "s do"} not fit before the
          exam: more minutes a day would fit {plan.not_scheduled.length === 1 ? "it" : "them"}.
        </p>
      ) : null}
      {plan.minimum_to_pass.map((row) =>
        row.chapters.length ? (
          <div key={row.subject} className="flex flex-col gap-1">
            <p className="font-semibold">
              {subjectName(row.subject)}: the pass mark is {row.pass_marks}. These chapters give {Number(row.marks)}{" "}
              marks for the least watching:
            </p>
            <ul className="m-0 pl-5 text-[15px]">
              {row.chapters.map((chapter) => (
                <li key={chapter.id}>
                  Ch. {chapter.number} {chapter.title}: {Number(chapter.weight)} marks, {chapter.minutes} min
                </li>
              ))}
            </ul>
          </div>
        ) : null,
      )}
    </div>
  );
}

/** The app stores' links: placeholders, clearly marked, until the server's config has them. */
export function AppLinks() {
  return (
    <dl className="m-0 flex flex-col gap-1">
      <div>
        <dt className="inline font-semibold">Android: </dt>
        <dd className="inline">
          <mark className="placeholder">[Google Play link]</mark>
        </dd>
      </div>
      <div>
        <dt className="inline font-semibold">iPhone: </dt>
        <dd className="inline">
          <mark className="placeholder">[App Store link]</mark>
        </dd>
      </div>
    </dl>
  );
}

export function LogInToUse({ path }: { path: string }) {
  return (
    <p>
      Have a code printed in your book, or bought the course?{" "}
      <Link href={withNext("/account/login/", path)}>Log in</Link> to use it, or{" "}
      <Link href={withNext("/account/signup/", path)}>register</Link> (free).
    </p>
  );
}
