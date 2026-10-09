// Dates, times, durations and the clocks of the console, always in India's time zone and written out by hand (as the
// public site's src/lib/dates.ts), so the server and every browser print the same thing.
import { copy } from "@/lib/copy";

const ZONE = "Asia/Kolkata";

const parts = (moment: Date) =>
  Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: ZONE,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(moment)
      .map((part) => [part.type, part.value]),
  ) as Record<string, string>;

const toDate = (value: string | number | Date) => (value instanceof Date ? value : new Date(value));

/** "8 Oct 2026" (a date "2026-10-08", a time with its offset, or a Date). */
export function formatDate(value: string | number | Date): string {
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [year, month, day] = value.split("-").map(Number);
    return `${day} ${copy.time.months[month - 1].slice(0, 3)} ${year}`;
  }
  const date = toDate(value);
  if (Number.isNaN(date.getTime())) return copy.common.unknown;
  const { year, month, day } = parts(date);
  return `${Number(day)} ${copy.time.months[Number(month) - 1].slice(0, 3)} ${year}`;
}

/** "14:05" in India. */
export function formatTime(value: string | number | Date): string {
  const date = toDate(value);
  if (Number.isNaN(date.getTime())) return copy.common.unknown;
  const { hour, minute } = parts(date);
  return `${hour}:${minute}`;
}

/** "8 Oct 2026, 14:05" in India. */
export function formatDateTime(value: string | number | Date | null | undefined): string {
  if (value === null || value === undefined || value === "") return copy.common.never;
  const date = toDate(value);
  if (Number.isNaN(date.getTime())) return copy.common.unknown;
  return copy.time.at(formatDate(date), formatTime(date));
}

/** A datetime-local input's value ("2026-10-08T14:05") for a moment, in India. */
export function toLocalInput(value: string | number | Date): string {
  const { year, month, day, hour, minute } = parts(toDate(value));
  return `${year}-${month}-${day}T${hour}:${minute}`;
}

/** A datetime-local input's value, read as India's time, as ISO 8601 with the offset the API speaks. */
export function fromLocalInput(value: string): string {
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value) ? `${value}:00+05:30` : value;
}

/** "3 h 20 min", "2 d 4 h", "12 min": a length of time in milliseconds (rounded up to the minute). */
export function formatDuration(milliseconds: number): string {
  const minutes = Math.max(0, Math.ceil(Math.abs(milliseconds) / 60_000));
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  return copy.time.duration(days, hours, minutes % 60);
}

/** "5 minutes ago", "just now". */
export function formatAgo(value: string | number | Date, now = Date.now()): string {
  const elapsed = now - toDate(value).getTime();
  if (Number.isNaN(elapsed)) return copy.common.unknown;
  const minutes = Math.floor(elapsed / 60_000);
  if (minutes < 1) return copy.time.justNow;
  if (minutes < 60) return copy.time.minutesAgo(minutes);
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return copy.time.hoursAgo(hours);
  return copy.time.daysAgo(Math.floor(hours / 24));
}

export type Urgency = "ok" | "soon" | "overdue" | "done";

/** How a clock stands: overdue once due has passed, soon in the last quarter of its window (from `start`), else ok. */
export function urgency(start: string | null, due: string | null, now = Date.now()): Urgency {
  if (!due) return "ok";
  const end = new Date(due).getTime();
  if (now >= end) return "overdue";
  const begin = start ? new Date(start).getTime() : NaN;
  const window = end - begin;
  if (Number.isFinite(window) && window > 0 && (end - now) / window <= 0.25) return "soon";
  return "ok";
}

/** "3 h 20 min left" or "overdue by 2 h". */
export function remaining(due: string, now = Date.now()): string {
  const left = new Date(due).getTime() - now;
  return left >= 0 ? copy.time.left(formatDuration(left)) : copy.time.overdue(formatDuration(left));
}

export function formatNumber(value: number | null | undefined): string {
  return value === null || value === undefined ? copy.common.unknown : value.toLocaleString("en-IN");
}

/** 1536 → "1.5 KB", 734003200 → "700 MB". */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return copy.common.unknown;
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = bytes;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${unit ? size.toFixed(size < 10 ? 1 : 0) : size} ${units[unit]}`;
}

/** Money as the API sends it (rupees, a number or a decimal string): ₹2,500. */
export function formatInr(value: number | null | undefined): string {
  if (value === null || value === undefined) return copy.common.unknown;
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(value).replace(/\.00$/, "");
}
