// Small display helpers that server pages and client components share (a "use client" module's functions cannot be
// called from a server component, so they live here).
import type { Customer, Incident, LegalHold } from "@/lib/api/staff";
import { copy, labelOf } from "@/lib/copy";

/** A customer's class and board: "Class 12 · ASSEB". */
export const classOf = (user: Pick<Customer, "class_level" | "board">) =>
  [user.class_level ? labelOf(copy.users.classLevel, String(user.class_level)) : "", user.board]
    .filter(Boolean)
    .join(" · ");

/** An incident's state: open until it is closed. */
export const incidentState = (incident: Pick<Incident, "closed_at">) => (incident.closed_at ? "closed" : "open");

/** A member of staff as the API names one, by id (approvals, the inbox, the log keep no one's details): you, a
 *  colleague, or no one. */
export function staffLabel(id: number | null | undefined, me: number): string {
  if (!id) return copy.inbox.unassigned;
  return id === me ? copy.inbox.you : copy.inbox.staffMember(id);
}

/** A legal hold's state: in force, released by someone, or past its last day. */
export const holdState = (hold: Pick<LegalHold, "active" | "released_at">) =>
  hold.active ? "active" : hold.released_at ? "released" : "ended";

/** What a legal hold keeps, in words: the account by its number, or the record by its number or code. */
export const heldLabel = (hold: Pick<LegalHold, "user" | "target_label">) =>
  hold.user ? copy.legal.holdAccount(hold.user) : hold.target_label;
