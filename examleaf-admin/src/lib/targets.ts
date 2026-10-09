// Where a record the API names (its target_type, a Django model's label, and target_id) opens in the console. A
// person's account (accounts.user) is a customer's page, or a staff member's when the action is about staff
// (staff.grant_role …). Records of modules the console does not have yet (orders, papers) open nowhere.
const PAGES: Record<string, (id: string) => string> = {
  "staff.changerequest": (id) => `/approvals/${id}/`,
  "staff.datarequest": (id) => `/privacy/requests/${id}/`,
  "staff.incident": (id) => `/privacy/incidents/${id}/`,
  "accounts.user": (id) => `/users/${id}/`,
  "support.ticket": (id) => `/support/tickets/${id}/`,
  // a mention's inbox item names "ticket id:person id"; it opens the ticket
  "support.mention": (id) => `/support/tickets/${encodeURIComponent(decodeURIComponent(id).split(":")[0])}/`,
};

export function targetHref(type: string | null | undefined, id: string | null | undefined, action = ""): string | null {
  if (!type || !id) return null;
  if (type === "accounts.user" && action.startsWith("staff.")) return `/people/${encodeURIComponent(id)}/`;
  const page = PAGES[type];
  return page ? page(encodeURIComponent(id)) : null;
}
