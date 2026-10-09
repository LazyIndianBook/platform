// Months and financial years as the tax pages pick them: "2026-10" for a month, "2026-27" for India's April-to-March
// year, both in India's time (format.ts's clock). The API checks every value again; these only build the choices.
import { copy } from "@/lib/copy";

const ZONE = "Asia/Kolkata";

/** The month a moment falls in, in India: "2026-10". */
export function monthOf(moment: number | Date): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: ZONE, year: "numeric", month: "2-digit" }).formatToParts(
    typeof moment === "number" ? new Date(moment) : moment,
  );
  const value = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return `${value("year")}-${value("month")}`;
}

/** A month `by` months later (or earlier): "2026-10", -1 → "2026-09". */
export function shiftMonth(month: string, by: number): string {
  const [year, number] = month.split("-").map(Number);
  const index = year * 12 + (number - 1) + by;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
}

/** "October 2026". */
export function monthLabel(month: string): string {
  const [year, number] = month.split("-").map(Number);
  return `${copy.time.months[number - 1]} ${year}`;
}

/** Whether a value is a month ("2026-10"). */
export const isMonth = (value: string) => /^\d{4}-(0[1-9]|1[0-2])$/.test(value);

/** The financial year a month falls in: "2026-10" → "2026-27", "2027-03" → "2026-27". */
export function yearOf(month: string): string {
  const [year, number] = month.split("-").map(Number);
  const start = number >= 4 ? year : year - 1;
  return `${start}-${String((start + 1) % 100).padStart(2, "0")}`;
}

/** Whether a value is a financial year ("2026-27"). */
export const isYear = (value: string) =>
  /^\d{4}-\d{2}$/.test(value) && Number(value.slice(5)) === (Number(value.slice(0, 4)) + 1) % 100;

/** The months of a financial year, April to March. */
export function monthsOf(year: string): string[] {
  const start = Number(year.slice(0, 4));
  return Array.from({ length: 12 }, (_, index) => shiftMonth(`${start}-04`, index));
}

/** The last `count` months up to the one of `now`, newest first (for the GSTR-1 export and the lists' filters). */
export function recentMonths(now: number, count = 18): string[] {
  const current = monthOf(now);
  return Array.from({ length: count }, (_, index) => shiftMonth(current, -index));
}

/** This financial year and the `count` before it, newest first. */
export function recentYears(now: number, count = 3): string[] {
  const start = Number(yearOf(monthOf(now)).slice(0, 4));
  return Array.from(
    { length: count + 1 },
    (_, index) => `${start - index}-${String((start - index + 1) % 100).padStart(2, "0")}`,
  );
}

/** A GSTR-1 export's period in words: "September 2026", or "July 2026 to September 2026" for a quarter. */
export const periodLabel = (month: string, months: number) =>
  months === 3 ? copy.tax.period(monthLabel(shiftMonth(month, -2)), monthLabel(month)) : monthLabel(month);
