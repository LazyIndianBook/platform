// Where a record the API names ({type, id, url}) opens in the console: its own `url` when that is a path of the
// console, else the page of its type. Records of modules the console does not have yet (orders, papers) open nowhere.
import type { TargetRef } from "@/lib/api/staff";
import { safeNext } from "@/lib/auth/next-url";

const PAGES: Record<string, (id: string) => string> = {
  change_request: (id) => `/approvals/${id}/`,
  data_request: (id) => `/privacy/requests/${id}/`,
  incident: (id) => `/privacy/incidents/${id}/`,
  user: (id) => `/users/${id}/`,
  staff: (id) => `/people/${id}/`,
};

export function targetHref(target: Pick<TargetRef, "type" | "id" | "url"> | null): string | null {
  if (!target) return null;
  const own = target.url ? safeNext(target.url, "") : "";
  if (own) return own;
  const page = PAGES[target.type];
  return page ? page(encodeURIComponent(target.id)) : null;
}
