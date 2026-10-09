// Where a record the API names (its target_type, a Django model's label, and target_id) opens in the console. A
// person's account (accounts.user) is a customer's page, or a staff member's when the action is about staff
// (staff.grant_role …). An order opens by its id as well as its number (the API takes either); a refund on its order.
// Records of modules the console does not have yet open nowhere.
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
  "shop.order": (id) => `/orders/${id}/`,
  "shop.returnrequest": (id) => `/orders/returns/${id}/`,
  "shop.quoterequest": (id) => `/orders/quotes/${id}/`,
  // Phase B: a person's page (a temporary role ended), their offboarding's checklist, a connection, the system's pages
  "staff.person": (id) => `/people/${id}/?tab=access`,
  "staff.offboarding": (id) => `/people/${id}/?tab=offboarding`,
  "integrations.connection": (id) => `/settings/connections/${id}/`,
  "integrations.integrationaccount": () => "/settings/connections/",
  "ops.messagetemplate": () => "/settings/templates/",
  "staff.scriptinventory": () => "/system/scripts/",
  system: (id) => (id === "backups" || id === "dependencies" ? `/system/${id}/` : "/system/"),
  // the content module (a review, a reported mistake, a book's legal deposit, a paper)
  "content.reviewtask": (id) => `/content/reviews/${id}/`,
  "content.errorreport": (id) => `/content/reports/${id}/`,
  "content.book": (id) => `/content/books/${id}/`,
  "content.paper": (id) => `/content/papers/${id}/`,
  "support.ticket": (id) => `/support/tickets/${id}/`,
  // a mention's inbox item names "ticket id:person id"; it opens the ticket
  "support.mention": (id) => `/support/tickets/${encodeURIComponent(decodeURIComponent(id).split(":")[0])}/`,
  // Finance: a payment, a settlement (or a day's fetch, named by its day: that day's settlements); a B2B invoice's link
  // on the links' list (it has no page of its own)
  "shop.payment": (id) => `/finance/payments/${id}/`,
  "shop.settlement": (id) =>
    /^\d+$/.test(id) ? `/finance/settlements/${id}/` : `/finance/settlements/?date_from=${id}&date_to=${id}`,
  "shop.invoicepaymentlink": () => "/finance/payment-links/?kind=invoice",
};

export function targetHref(type: string | null | undefined, id: string | null | undefined, action = ""): string | null {
  if (!type || !id) return null;
  if (type === "accounts.user" && action.startsWith("staff.")) return `/people/${encodeURIComponent(id)}/`;
  const page = PAGES[type];
  return page ? page(encodeURIComponent(id)) : null;
}
