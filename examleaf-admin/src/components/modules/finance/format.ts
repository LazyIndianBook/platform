// The Finance module's small words: money as the API sends it (decimal strings, null when not known yet), and the
// tone of each state's chip (the kit's voice: waiting, moving, done, stopped, bad). Nothing is decided here.
import type { Tone } from "@/components/data/status-chip";
import { copy } from "@/lib/copy";
import { formatInr } from "@/lib/format";

/** Rupees from the API's decimal string; a dash's words when there is none. */
export const inr = (value: string | null | undefined) =>
  value === null || value === undefined || value === "" ? copy.common.none : formatInr(Number(value));

const TONES: Record<string, Tone> = {
  // payments
  created: "waiting",
  authorized: "moving",
  captured: "done",
  refunded: "stopped",
  failed: "bad",
  // links
  sent: "waiting",
  paid: "done",
  cancelled: "stopped",
  expired: "stopped",
  // settlements
  fetched: "waiting",
  matched: "good",
  posted: "done",
  mismatched: "bad",
  // refunds and change requests
  pending: "waiting",
  processed: "done",
  approved: "good",
  executed: "done",
  rejected: "bad",
};

export const toneOfFinance = (state: string): Tone => TONES[state] ?? "stopped";
