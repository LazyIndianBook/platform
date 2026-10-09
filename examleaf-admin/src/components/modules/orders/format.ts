// The Orders module's small readings of what the API sends: rupees (decimal strings) as the console prints money, and
// the tone of each kind of state for its chip. The words are the API's (status_label) or copy.ts's tables.
import type { Tone } from "@/components/data/status-chip";
import type { OrderDetail } from "@/lib/api/staff";
import { formatInr } from "@/lib/format";

/** "1710.00" → "₹1,710"; "1710.50" → "₹1,710.50"; nothing → "Not known". */
export function rupees(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return formatInr(null);
  const amount = Number(value);
  return formatInr(Number.isFinite(amount) ? amount : null);
}

/** Rupees as whole paise (integers: no float sums of money). */
export const paise = (value: string | number) => Math.round(Number(value) * 100);

const TONES: Record<string, Tone> = {
  // orders
  pending: "waiting",
  paid: "moving",
  packed: "moving",
  shipped: "moving",
  delivered: "done",
  cancelled: "stopped",
  refunded: "stopped",
  // returns
  requested: "waiting",
  approved: "good",
  declined: "bad",
  label_sent: "moving",
  received: "moving",
  restocked: "done",
  damaged: "done",
  // refunds and payments
  processed: "done",
  captured: "good",
  created: "waiting",
  authorized: "moving",
  failed: "bad",
  // quotes
  new: "waiting",
  quoted: "moving",
  ordered: "done",
  closed: "stopped",
};

export function stateTone(state: string): Tone {
  return TONES[state] ?? "stopped";
}

export const riskTone = (bucket: string): Tone =>
  bucket === "high" ? "bad" : bucket === "medium" ? "waiting" : "good";

/** Whether the API lists this action for the person (`actions`: the state machine's moves and their permissions). */
export const hasAction = (order: Pick<OrderDetail, "actions">, name: string) =>
  order.actions.some((action) => action.name === name);

/** Whether an order's Danger section has anything for this person: cancel, refund or a return. */
export const hasDanger = (order: Pick<OrderDetail, "actions">) =>
  ["cancel", "refund", "return"].some((name) => hasAction(order, name));
