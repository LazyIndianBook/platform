// The revision course as the API answers it, drawn without any state (the pages and their islands share these): what
// is open to the student (learn/entitlements/), a plan's days (learn/plan/, me/learning/), the pass plan, the app's
// store links. Only the API's own numbers.
import Link from "next/link";

import { QrCode } from "@/components/account/qr-code";
import { buttonVariants } from "@/components/ui/button";
import type { components } from "@/lib/api/schema";
import { withNext } from "@/lib/auth/next-url";
import { formatDate } from "@/lib/dates";

export type Entitlement = components["schemas"]["Entitlement"];

export type Plan = components["schemas"]["Plan"];
type AppLinksConfig = components["schemas"]["AppLinksConfig"];
type Day = { date: string; minutes: number; clips: { id: number; title: string; duration: number }[] };

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** "2026-10-09" → "Thu 9 Oct": a plan's day as the design writes it (the weekday from the date itself, no time zone). */
export function dayLabel(date: string): string {
  const [year, month, day] = date.split("-").map(Number);
  return `${WEEKDAYS[new Date(Date.UTC(year, month - 1, day)).getUTCDay()]} ${formatDate(date).replace(/ \d{4}$/, "")}`;
}

export const clipMinutes = (seconds: number) => Math.max(1, Math.round(seconds / 60));

/** A plan's days as ruled rows: the day and its minutes in the mono voice, the clips in a line. */
export function DayList({ days, label }: { days: Day[]; label: string }) {
  return (
    <ol aria-label={label} className="m-0 list-none p-0">
      {days.map((day) => (
        <li
          key={day.date}
          className="grid grid-cols-[104px_minmax(0,1fr)] gap-3 border-b border-border py-2.5 max-nav:grid-cols-1 max-nav:gap-0.5"
        >
          <span className="font-mono text-[13px] leading-normal font-medium">
            {dayLabel(day.date)}
            <span className="text-muted-foreground nav:block">
              <span className="nav:hidden"> · </span>
              {day.minutes} min
            </span>
          </span>
          <span className="text-sm leading-normal text-ink/85">
            {day.clips.map((clip) => `${clip.title} (${clipMinutes(clip.duration)} min)`).join(" · ")}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** Each subject open to the student, ruled: open (or ended) and until when. */
export function EntitlementList({ entitlements, today }: { entitlements: Entitlement[]; today: string }) {
  return (
    <dl className="m-0 flex flex-col border-t border-border">
      {entitlements.map((item) => {
        const ended = Boolean(item.valid_until && item.valid_until < today);
        return (
          <div
            key={item.id}
            className="flex flex-wrap items-baseline justify-between gap-x-3 border-b border-border py-2.5 text-[15px]"
          >
            <dt>
              <strong>{item.subject_name ?? "Every subject"}</strong> · {ended ? "ended" : "open"}
            </dt>
            <dd className="m-0 text-muted-foreground">
              {item.valid_until ? `${ended ? "on" : "until"} ${formatDate(item.valid_until)}` : "with no end date"}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

const SHOWN_DAYS = 7;

/** The plan for the exam day: the first week's clips, what did not fit, and the quickest way to the pass marks. */
export function PlanView({ plan, subjectName }: { plan: Plan; subjectName: (id: number) => string }) {
  const later = plan.days.length - SHOWN_DAYS;
  return (
    <div className="flex flex-col gap-3 text-[15px] [&_p]:m-0">
      <p>
        <strong>{plan.days_left}</strong> day{plan.days_left === 1 ? "" : "s"} to your exam on{" "}
        {formatDate(plan.exam_date, "long")}, at {plan.minutes_per_day} minutes a day.
      </p>
      {plan.days.length ? (
        <DayList days={plan.days.slice(0, SHOWN_DAYS)} label="Your first days" />
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
          <div key={row.subject} className="flex flex-col gap-1 border-t border-border pt-3">
            <p className="font-semibold">
              {subjectName(row.subject)}: the pass mark is {row.pass_marks}. These chapters give {Number(row.marks)}{" "}
              marks for the least watching:
            </p>
            <ul className="m-0 pl-5">
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

/** The app stores' links from the server's config (config/ app_links), each with its QR code for a phone's camera on
 *  a desktop when `qr` (G6); a line saying the app is coming while no store has it. */
export function AppLinks({ links, qr = false }: { links: AppLinksConfig | null | undefined; qr?: boolean }) {
  const stores = [
    { store: "Google Play", url: links?.android },
    { store: "the App Store", url: links?.ios },
  ].filter((item): item is { store: string; url: string } => Boolean(item.url));
  if (!stores.length) return <p className="m-0 text-[15px] text-ink/85">The app is coming to the stores soon.</p>;
  return (
    <ul className="m-0 flex list-none flex-wrap gap-5 p-0">
      {stores.map(({ store, url }) => (
        <li key={url} className="flex flex-col items-start gap-3">
          {qr ? (
            <span className="max-nav:hidden">
              <QrCode text={url} label={`QR code of ExamLeaf on ${store}, for your phone's camera`} size={112} />
            </span>
          ) : null}
          <a
            href={url}
            rel="noopener noreferrer"
            target="_blank"
            className={buttonVariants({ variant: "secondary", size: "sm" })}
          >
            ExamLeaf on {store}
          </a>
        </li>
      ))}
    </ul>
  );
}

export function LogInToUse({ path }: { path: string }) {
  return (
    <p className="m-0 text-[15px]">
      Have a code printed in your book, or bought the course?{" "}
      <Link href={withNext("/account/login/", path)}>Log in</Link> to use it, or{" "}
      <Link href={withNext("/account/signup/", path)}>register</Link> (free).
    </p>
  );
}
