// Where a record the API names (its target_type, a Django model's label, and target_id) opens in the console. A
// person's account (accounts.user) is a customer's page, or a staff member's when the action is about staff
// (staff.grant_role …). Records of modules the console does not have yet (orders, papers) open nowhere.
const PAGES: Record<string, (id: string) => string> = {
  "staff.changerequest": (id) => `/approvals/${id}/`,
  "staff.datarequest": (id) => `/privacy/requests/${id}/`,
  "staff.incident": (id) => `/privacy/incidents/${id}/`,
  "accounts.user": (id) => `/users/${id}/`,
  "shop.hsncode": (id) => `/tax/hsn/${id}/`,
  "shop.taxthreshold": () => "/tax/",
  "accounts.legalhold": (id) => `/privacy/holds/${id}/`,
  // a processor's task (its id and the erasure's or the consent's: "41:erasure:7"), on the register
  "staff.processorrecord": () => "/privacy/processors/",
  // the self-audit (its id), or the year it is due for ("year:2027"): the page opens the year due
  "staff.darkpatternaudit": () => "/privacy/dark-pattern-audit/",
};

export function targetHref(type: string | null | undefined, id: string | null | undefined, action = ""): string | null {
  if (!type || !id) return null;
  if (type === "accounts.user" && action.startsWith("staff.")) return `/people/${encodeURIComponent(id)}/`;
  const page = PAGES[type];
  return page ? page(encodeURIComponent(id)) : null;
}
