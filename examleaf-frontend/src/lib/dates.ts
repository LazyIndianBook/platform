// Dates as the Django site prints them ("8 Oct 2026", "8 October 2026"), always in India's time zone, written out
// by hand so that the server and every browser print the same thing (Intl's month names differ: "Sept").
const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** Today, or any moment, in India as yyyy-mm-dd (a date input's value and the API's dates). */
export function dateInIndia(moment: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(moment);
}

/** A date ("2026-10-08"), a time with its offset, or seconds since 1970 (allauth's) as "8 Oct 2026" or, long,
 *  "8 October 2026". */
export function formatDate(value: string | number, style: "short" | "long" = "short"): string {
  const day =
    typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)
      ? value
      : dateInIndia(new Date(typeof value === "number" ? value * 1000 : value));
  const [year, month, date] = day.split("-").map(Number);
  const name = MONTHS[month - 1];
  return `${date} ${style === "long" ? name : name.slice(0, 3)} ${year}`;
}

/** Under 18 on the day, from a yyyy-mm-dd date (false while the date is incomplete): the consent rules of Register. */
export function isMinor(dateOfBirth: string, today = new Date()): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateOfBirth);
  if (!match) return false;
  const [year, month, day] = match.slice(1).map(Number);
  const birthdayPassed = today.getMonth() + 1 > month || (today.getMonth() + 1 === month && today.getDate() >= day);
  return today.getFullYear() - year - (birthdayPassed ? 0 : 1) < 18;
}
