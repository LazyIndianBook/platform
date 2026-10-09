// How the reports write what they hold, pure and tested: rupees to the paisa with India's grouping, counts, a fraction
// as a percent, a period's label by its grain, a bar's width, and the sentence that sets a card beside the period
// before it. No figure is worked out here beyond a width: the API's numbers are drawn as they come.
import type { HomeCard } from "@/lib/api/staff";
import { copy } from "@/lib/copy";
import { formatDate, formatInr } from "@/lib/format";

const DASH = "–";
const MONEY = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const COUNT = new Intl.NumberFormat("en-IN");

type Figure = string | number | null | undefined;

const numberOf = (value: Figure) => (value === null || value === undefined || value === "" ? NaN : Number(value));

/** Rupees to the paisa (the API's decimal strings): ₹1,84,250.00; a dash for nothing. */
export function rupees(value: Figure): string {
  const amount = numberOf(value);
  return Number.isFinite(amount) ? MONEY.format(amount) : DASH;
}

/** A count with India's grouping: 1,84,250; a dash for nothing. */
export function count(value: Figure): string {
  const amount = numberOf(value);
  return Number.isFinite(amount) ? COUNT.format(amount) : DASH;
}

/** A decimal string to `places` decimals (a smoothed average): 12.4; a dash for nothing. */
export function decimal(value: Figure, places = 1): string {
  const amount = numberOf(value);
  return Number.isFinite(amount) ? COUNT.format(Number(amount.toFixed(places))) : DASH;
}

/** A fraction as a percent: "0.4000" is 40%, with `places` decimals when asked; a dash for nothing. */
export function percent(fraction: Figure, places = 0): string {
  const amount = numberOf(fraction);
  return Number.isFinite(amount) ? `${(amount * 100).toFixed(places)}%` : DASH;
}

/** A bar's width in percent of its box: the share of the largest figure, at least 2 for anything above nothing so that
 *  it can be seen, 0 for nothing (a cell that is hidden, or a figure that is not a number). */
export function barWidth(value: Figure, max: number): number {
  const amount = numberOf(value);
  if (!Number.isFinite(amount) || amount <= 0 || !(max > 0)) return 0;
  return Math.min(100, Math.max(2, Math.round((amount / max) * 100)));
}

/** The largest of the figures that are numbers (0 for none). */
export const maxOf = (values: Figure[]) => Math.max(0, ...values.map(numberOf).filter(Number.isFinite));

/** A period of a series by its grain: the day, "Week of 5 Oct 2026" or "October 2026". */
export function periodLabel(grain: string, start: string | null | undefined): string {
  if (!start) return DASH;
  if (grain === "week") return copy.reports.weekOf(formatDate(start));
  if (grain === "month") {
    const [year, month] = start.split("-").map(Number);
    return `${copy.time.months[month - 1]} ${year}`;
  }
  return formatDate(start);
}

/** What a card's total covers: "Today", "The last 7 days". */
export const lastDays = (days: number) => (days === 1 ? copy.reports.home.today : copy.reports.home.lastDays(days));

/** A card's figure as the card writes it: whole rupees, or a count. */
export function cardValue(card: Pick<HomeCard, "unit" | "value">): string {
  if (card.value === null) return DASH;
  return card.unit === "inr" ? formatInr(Number(card.value)) : count(card.value);
}

/** A total set beside the period before it, in a sentence: "Up ₹32,350 (21.3%) on the 30 days before (₹1,51,900)". */
export function comparisonWords(card: Pick<HomeCard, "unit" | "comparison">): string | null {
  const compared = card.comparison;
  if (!compared) return null;
  const move = Number(compared.difference);
  const write = (value: number) => (card.unit === "inr" ? formatInr(value) : count(value));
  const before = write(Number(compared.previous));
  const days = compared.period.days;
  if (!Number.isFinite(move)) return null;
  if (move === 0) return copy.reports.home.same(before, days);
  const share = compared.percent === null ? null : `${Math.abs(Number(compared.percent))}%`;
  return copy.reports.home[move > 0 ? "up" : "down"](write(Math.abs(move)), share, before, days);
}
