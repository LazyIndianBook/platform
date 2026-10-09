// The Catalogue module's small readings of what the API sends (a discount in words, a state's tone) and of what its
// forms hold (slugs typed in a box, a bundle's books a line each, the fields a change sends): no request here. The
// rules themselves are the API's: these only shape what is sent and drawn.
import type { Tone } from "@/components/data/status-chip";
import { copy } from "@/lib/copy";
import { formatInr } from "@/lib/format";

/** "10.00" per cent → "10% off"; "50.00" rupees → "₹50 off". */
export function discountText(kind: string, value: string | number): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return copy.common.unknown;
  return kind === "fixed" ? copy.catalogue.rupeesOff(formatInr(amount)) : copy.catalogue.percentOff(String(amount));
}

/** "1710.00" → "₹1,710"; nothing → "Not known". */
export function rupees(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return formatInr(null);
  const amount = Number(value);
  return formatInr(Number.isFinite(amount) ? amount : null);
}

/** A rate's states as the API keeps them (a list of codes). */
export const statesOf = (rate: { states: unknown }): string[] =>
  Array.isArray(rate.states) ? rate.states.map(String) : [];

/** A coupon's or an offer's state now. */
export const TERM_TONES: Record<string, Tone> = {
  live: "good",
  scheduled: "waiting",
  ended: "stopped",
  inactive: "stopped",
};
/** A product's copies against the low-stock line. */
export const STOCK_TONES: Record<string, Tone> = { in_stock: "good", low: "waiting", out: "bad", none: "stopped" };

/** Slugs typed one a line or between commas, each once, in the order typed. */
export function slugsOf(text: string): string[] {
  return [
    ...new Set(
      text
        .split(/[\s,]+/)
        .map((slug) => slug.trim().toLowerCase())
        .filter(Boolean),
    ),
  ];
}

export type BundleLine = { product: string; quantity: number };

/** A bundle's books typed a line each: the slug, then its copies after a comma or a space (1 when none). The first
 *  line that cannot be read is named; the API checks the rest (the books, the copies, each once). */
export function bundleLinesOf(text: string): { lines: BundleLine[]; problem: string | null } {
  const lines: BundleLine[] = [];
  for (const [index, raw] of text.split("\n").entries()) {
    const line = raw.trim();
    if (!line) continue;
    const match = /^([-a-z0-9_]+)(?:\s*[,×*]\s*|\s+)?(\d+)?$/i.exec(line);
    if (!match) return { lines: [], problem: copy.catalogue.bundleLineProblem(index + 1) };
    lines.push({ product: match[1].toLowerCase(), quantity: match[2] ? Number(match[2]) : 1 });
  }
  return { lines, problem: null };
}

/** A bundle's lines as the box shows them, one a line. */
export const bundleText = (lines: BundleLine[]) => lines.map((line) => `${line.product}, ${line.quantity}`).join("\n");

const DECIMAL = /^-?\d+(\.\d+)?$/;
const MOMENT = /^\d{4}-\d{2}-\d{2}T/;

/** Whether two values of a field say the same thing: lists as sets, maps key by key, money as numbers ("10" and
 *  "10.00"), moments as moments (an offset or another), nothing as nothing (null, "" or an empty list). */
export function same(before: unknown, after: unknown): boolean {
  const empty = (value: unknown) => value === null || value === undefined || value === "";
  const map = (value: unknown): value is Record<string, unknown> =>
    Boolean(value) && typeof value === "object" && !Array.isArray(value);
  if (map(before) || map(after)) {
    const one = map(before) ? before : {};
    const other = map(after) ? after : {};
    return [...new Set([...Object.keys(one), ...Object.keys(other)])].every((key) => same(one[key], other[key]));
  }
  if (Array.isArray(before) || Array.isArray(after)) {
    const sorted = (value: unknown) => (Array.isArray(value) ? value.map(String).sort().join("\n") : "");
    return sorted(before) === sorted(after);
  }
  if (empty(before) || empty(after)) return empty(before) && empty(after);
  if (typeof before === "string" && typeof after === "string") {
    if (DECIMAL.test(before) && DECIMAL.test(after)) return Number(before) === Number(after);
    // a datetime-local box keeps minutes: a moment with seconds is the same moment to the minute
    if (MOMENT.test(before) && MOMENT.test(after))
      return Math.floor(Date.parse(before) / 60_000) === Math.floor(Date.parse(after) / 60_000);
  }
  return String(before) === String(after);
}

/** The fields of `after` that differ from `before`: what a change sends (its approval reads them alone). */
export function changedOnly<T extends Record<string, unknown>>(before: Record<string, unknown>, after: T): Partial<T> {
  return Object.fromEntries(Object.entries(after).filter(([name, value]) => !same(before[name], value))) as Partial<T>;
}

/** A version's value in words: lists joined, yes or no, nothing as a dash. */
export function shown(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length ? value.map(shown).join(", ") : "—";
  if (typeof value === "boolean") return value ? copy.common.yes : copy.common.no;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** A whole number a form holds, or null when its box is empty (the API says what is wrong with anything else). */
export function wholeOrNull(form: FormData, name: string): number | null {
  const value = String(form.get(name) ?? "").trim();
  return value === "" ? null : Number(value);
}
