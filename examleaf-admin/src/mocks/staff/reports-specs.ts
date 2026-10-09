// THE CARDS OF HOME, FOR THE STAFF API MOCK (reports.ts): each card's key, label, unit, group, link, the permissions it
// needs, the roles it is for and its definition, copied from examleaf-web's insights/metrics.py (SPECS: the function's
// docstring is the definition), so that the words on hover are the backend's. A card whose permissions the role does
// not hold is not drawn; the order is the registry's.
export type CardSpec = {
  key: string;
  label: string;
  unit: "inr" | "count";
  group: "measure" | "queue";
  href: string;
  needs: string[];
  roles: string[];
  compares: boolean;
  days: number | null;
  definition: string;
};

export const HOME_SPECS: CardSpec[] = [
  {
    key: "net_revenue",
    label: "Net revenue",
    unit: "inr",
    group: "measure",
    href: "/reports/sales/{period}",
    needs: ["staff.view_insights", "shop.view_payment", "shop.view_refund"],
    roles: ["ADMIN", "AUDITOR", "FINANCE", "OWNER"],
    compares: true,
    days: null,
    definition:
      "Money received less money returned in the period, in rupees, with the shipping and any GST charged: the payments first captured in it, less the refunds processed in it. A cash-on-delivery order counts when its parcel is delivered and the courier has the cash, not when it is placed. Test-mode payments are left out.",
  },
  {
    key: "orders_placed",
    label: "Orders",
    unit: "count",
    group: "measure",
    href: "/reports/sales/{period}",
    needs: ["shop.view_order"],
    roles: ["ADMIN", "AUDITOR", "OWNER"],
    compares: true,
    days: null,
    definition:
      "Orders placed in the period: paid online, or placed to pay on delivery, and not cancelled or refunded in full since. Test-mode orders are left out.",
  },
  {
    key: "orders_to_pack",
    label: "Orders to pack",
    unit: "count",
    group: "queue",
    href: "/orders/?tab=to_pack",
    needs: ["shop.view_order"],
    roles: ["ADMIN", "OWNER", "PACKER", "SALES", "SALES_REP"],
    compares: false,
    days: null,
    definition:
      'Orders waiting to be packed now: paid, or placed to pay on delivery, not packed and not on hold. The same orders as the Orders list\'s "To pack" tab; test-mode orders are left out.',
  },
  {
    key: "quotes_open",
    label: "Quotes open",
    unit: "count",
    group: "queue",
    href: "/orders/quotes/?status=new",
    needs: ["shop.view_quoterequest"],
    roles: ["ADMIN", "OWNER", "SALES", "SALES_REP"],
    compares: false,
    days: null,
    definition: 'Quotation requests from schools and booksellers that wait for a quotation (status "new").',
  },
  {
    key: "refunds_to_approve",
    label: "Refunds to approve",
    unit: "count",
    group: "queue",
    href: "/approvals/?who=awaiting",
    needs: ["staff.approve_refund"],
    roles: ["FINANCE", "OWNER"],
    compares: false,
    days: null,
    definition:
      "Refunds asked for above the asker's limit that wait for a second person's decision: change requests of \"order.refund\" still pending and not past their time, other than the person's own (nobody approves their own). Refunds of test-mode orders are left out.",
  },
  {
    key: "bank_refunds_to_pay",
    label: "Bank refunds to mark paid",
    unit: "count",
    group: "queue",
    href: "/inbox/?kind=bank_refund",
    needs: ["staff.approve_refund"],
    roles: ["FINANCE", "OWNER"],
    compares: false,
    days: null,
    definition:
      'Refunds to be transferred by bank or UPI that wait for FINANCE to make the transfer and mark them paid (status "requested", method bank). Refunds of test-mode orders are left out.',
  },
  {
    key: "cod_overdue",
    label: "COD overdue",
    unit: "count",
    group: "queue",
    href: "/reports/cod/",
    needs: ["staff.view_cod"],
    roles: ["ADMIN", "FINANCE", "OWNER"],
    compares: false,
    days: null,
    definition:
      "Cash-on-delivery remittances from the couriers that are overdue: the cash was collected on delivery and the courier's remittance is more than SHIPPING_COD_GRACE_DAYS working days past the day it was expected. Parcels of test-mode orders are left out.",
  },
  {
    key: "tickets_due",
    label: "Tickets due today",
    unit: "count",
    group: "queue",
    href: "/support/?tab=due",
    needs: ["support.view_ticket"],
    roles: ["ADMIN", "OWNER", "SUPPORT"],
    compares: false,
    days: null,
    definition:
      'Support tickets that are new, open or waiting whose next legal deadline falls later today (India\'s time). A ticket past its deadline is a breach and counts under "Tickets breached", not here. Spam, and tickets about a test-mode order, are left out.',
  },
  {
    key: "tickets_breached",
    label: "Tickets breached",
    unit: "count",
    group: "queue",
    href: "/support/?tab=overdue",
    needs: ["support.view_ticket"],
    roles: ["ADMIN", "OWNER", "SUPPORT"],
    compares: false,
    days: null,
    definition:
      'Support tickets that are new, open or waiting and already past a legal deadline (the acknowledgement or the resolution that applies): the list\'s "Overdue" tab. Spam, and tickets about a test-mode order, are left out.',
  },
  {
    key: "reports_open",
    label: "Reports open",
    unit: "count",
    group: "queue",
    href: "/content/reports/",
    needs: ["content.view_errorreport"],
    roles: ["ADMIN", "CONTENT_EDITOR", "OWNER", "REVIEWER"],
    compares: false,
    days: null,
    definition:
      'Mistakes in the content that wait for triage: reported by a reader or flagged by the quiz\'s item analysis, and neither fixed nor rejected (status "reported" or "confirmed"), within the subjects the person looks after. Spam is left out.',
  },
  {
    key: "items_flagged",
    label: "Items flagged",
    unit: "count",
    group: "queue",
    href: "/content/reports/?category=item_analysis",
    needs: ["content.view_errorreport"],
    roles: ["ADMIN", "CONTENT_EDITOR", "OWNER", "REVIEWER"],
    compares: false,
    days: null,
    definition:
      'Quiz items that the item analysis flagged (too easy, too hard, a distractor that the strong chose) and that nobody has looked at yet: the open reports of category "flagged by the item analysis", also counted under "Reports open".',
  },
  {
    key: "settlement_items_unmatched",
    label: "Settlement items unmatched",
    unit: "count",
    group: "queue",
    href: "/finance/settlements/",
    needs: ["shop.view_settlement"],
    roles: ["ADMIN", "AUDITOR", "FINANCE", "OWNER"],
    compares: false,
    days: null,
    definition:
      "Lines of Razorpay's settlements that match no payment and no refund of ours (an adjustment is not a line to match). FINANCE finds each one in the settlement it belongs to.",
  },
  {
    key: "codes_redeemed",
    label: "Codes redeemed",
    unit: "count",
    group: "measure",
    href: "/reports/codes/",
    needs: ["staff.view_insights", "learn.view_bookcode"],
    roles: ["ADMIN", "AUDITOR", "OWNER"],
    compares: true,
    days: null,
    definition:
      "Book codes redeemed in the period: the codes printed in the books that a student entered in the app for the course (a code is redeemed once).",
  },
  {
    key: "active_learners",
    label: "Active learners",
    unit: "count",
    group: "measure",
    href: "/reports/course-health/",
    needs: ["staff.view_insights", "learn.view_progress"],
    roles: ["ADMIN", "AUDITOR", "OWNER"],
    compares: true,
    days: 7,
    definition:
      "Customers' accounts with any course activity in the period (Home: the last 7 days): a clip watched, a quiz answer given or a flash card turned over. A count of accounts, never a list of them; staff accounts are left out.",
  },
];
