// Where a record the API names (its target_type, a Django model's label, and target_id) opens in the console. A
// person's account (accounts.user) is a customer's page, or a staff member's when the action is about staff
// (staff.grant_role …). An order opens by its id as well as its number (the API takes either); a refund on its order.
// Records of modules the console does not have yet (papers) open nowhere.
const PAGES: Record<string, (id: string) => string> = {
  "staff.changerequest": (id) => `/approvals/${id}/`,
  "staff.datarequest": (id) => `/privacy/requests/${id}/`,
  "staff.incident": (id) => `/privacy/incidents/${id}/`,
  "accounts.user": (id) => `/users/${id}/`,
  "shop.order": (id) => `/orders/${id}/`,
  "shop.returnrequest": (id) => `/orders/returns/${id}/`,
  "shop.quoterequest": (id) => `/orders/quotes/${id}/`,
};

export function targetHref(type: string | null | undefined, id: string | null | undefined, action = ""): string | null {
  if (!type || !id) return null;
  if (type === "accounts.user" && action.startsWith("staff.")) return `/people/${encodeURIComponent(id)}/`;
  const page = PAGES[type];
  return page ? page(encodeURIComponent(id)) : null;
}
