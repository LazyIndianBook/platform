// What the support pages share, server and client alike (no hooks here): the queue's tabs as the API's filters, a
// ticket's words (its category, status, source, the clock it runs on) and its tone, and a member of staff's name from
// the agents the API lists.
import type { Tone } from "@/components/data/status-chip";
import type { Agent, Ticket, TicketFilters, TicketRecord } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";
import { staffLabel } from "@/lib/display";
import { P } from "@/lib/modules";

/** The queue's tabs, the first the default: the next deadline first, as the API sorts. */
export const TABS = ["due", "mine", "unassigned", "overdue", "waiting", "all"] as const;
export type Tab = (typeof TABS)[number];

export const tabOf = (value: string): Tab => TABS.find((tab) => tab === value) ?? "due";

/** A tab as the API's filters: the running tickets (new, open, waiting) but in All, which also has spam by status. */
export function tabFilters(tab: Tab): TicketFilters {
  switch (tab) {
    case "mine":
      return { mine: true, open: true };
    case "unassigned":
      return { unassigned: true, open: true };
    case "overdue":
      return { overdue: true };
    case "waiting":
      return { waiting: true };
    case "all":
      return {};
    default:
      return { open: true };
  }
}

const TONES: Record<string, Tone> = {
  new: "waiting",
  open: "moving",
  waiting_customer: "waiting",
  waiting_third_party: "waiting",
  resolved: "done",
  closed: "stopped",
  spam: "bad",
};

export const ticketTone = (status: string): Tone => TONES[status] ?? "stopped";
export const statusLabel = (status: string) => labelOf(copy.support.statuses, status);
export const categoryLabel = (category: string | null | undefined) =>
  category ? labelOf(copy.support.categories, category) : copy.support.notSorted;
export const sourceLabel = (source: string) => labelOf(copy.support.sources, source);

/** The clock a running ticket is on now: acknowledge until it is acknowledged, then resolve. */
export const clockLabel = (ticket: Pick<Ticket, "clock">) =>
  ticket.clock === "ack" ? copy.support.clockAck : copy.support.clockDue;

/** Who the requester is, in the queue: their name, else their masked address or number. */
export const requesterLabel = (ticket: Pick<Ticket, "requester">) =>
  ticket.requester.name || ticket.requester.email || ticket.requester.phone || copy.common.unknown;

/** A member of staff by id: you, a colleague by the name the agents list gives, or "Staff #id". */
export function agentName(agents: Agent[] | null, id: number | null | undefined, me: number): string {
  if (!id) return copy.inbox.unassigned;
  if (id === me) return copy.inbox.you;
  return agents?.find((agent) => agent.id === id)?.name ?? staffLabel(id, me);
}

type Can = (permission: string) => boolean;

/** Whether a data request may be started from this ticket: a grievance or privacy request without one yet. */
export const dataRequestOpen = (ticket: TicketRecord, can: Can) =>
  can(P.requestsHandle) &&
  !ticket.data_request &&
  (ticket.category === "grievance" || ticket.category === "privacy_request");

/** Whether the person may do anything from this ticket (the Actions section is drawn only then). */
export function hasActions(ticket: TicketRecord, can: Can): boolean {
  return Boolean(
    (ticket.sidebar.orders?.length && (can(P.refundOrder) || can(P.ordersChange) || can(P.ticketsHandle))) ||
    (ticket.sidebar.entitlements && can(P.accessExtend)) ||
    can(P.bookCodesView) ||
    dataRequestOpen(ticket, can),
  );
}
