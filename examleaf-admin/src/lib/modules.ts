// The console's modules and the permissions it looks for in the session manifest, in one place: the codenames the
// backend's catalogue names (examleaf-web/staff/catalogue.py, API.md "Every staff endpoint and field"), never made up
// here. A module is drawn when the person holds any of its permissions; nothing is drawn for the others. That is the
// only thing the console does with permissions: it hides what the manifest says the person cannot use. The API checks
// every call again and its answer is the truth. Where the API names the permission an object needs (a change request's
// `checker`, a setting's `permission`), the console reads it from there.
import { copy } from "@/lib/copy";
import type { Manifest } from "@/lib/api/staff";

/** The capability codenames the console reads (Django "app_label.codename"; staff.* is the staff app's). */
export const P = {
  inboxView: "staff.view_inbox",
  approvalsView: "staff.view_changerequest",
  approvalsAsk: "staff.add_changerequest",
  refundOrder: "staff.refund_order",
  auditView: "staff.view_auditlog",
  auditExport: "staff.export_auditlog",
  jobsView: "staff.view_job",
  savedViewsView: "staff.view_savedview",
  savedViewsAdd: "staff.add_savedview",
  savedViewsChange: "staff.change_savedview",
  savedViewsDelete: "staff.delete_savedview",
  // notes (the backend's Note model, coming: Django's own verbs)
  notesView: "staff.view_note",
  notesAdd: "staff.add_note",
  usersView: "accounts.view_user",
  usersReveal: "staff.reveal_contact",
  usersSuspend: "staff.suspend_user",
  usersUnlock: "staff.unlock_user",
  usersResendVerification: "staff.resend_verification",
  usersEndSessions: "staff.end_user_sessions",
  usersPasswordReset: "staff.initiate_password_reset",
  usersResetMfa: "staff.reset_user_mfa",
  usersImpersonate: "staff.impersonate_user",
  peopleView: "staff.view_staff",
  /** Invitations, roles, scopes, sessions and offboarding (OWNER's). */
  peopleAssign: "staff.assign_role",
  requestsView: "staff.view_datarequest",
  requestsHandle: "staff.handle_data_request",
  requestsExport: "staff.export_personal_data",
  incidentsView: "staff.view_incident",
  incidentsManage: "staff.manage_incident",
  processorsView: "staff.view_processorrecord",
  processorsAdd: "staff.add_processorrecord",
  settingsView: "staff.view_sitesetting",
  flagsView: "staff.view_featureflag",
  flagsChange: "staff.manage_flags",
  apiKeysView: "staff.view_apikey",
  apiKeysManage: "staff.manage_api_keys",
  systemView: "staff.view_system",
  maintenance: "staff.toggle_maintenance",
  reconcile: "staff.replay_webhook",
  // the shipping desk and the insights: catalogued by the staff app (staff/catalogue.py)
  parcelsView: "staff.view_parcels",
  parcelsBook: "staff.book_parcel",
  exceptionsAct: "staff.act_on_exception",
  codView: "staff.view_cod",
  codReconcile: "staff.reconcile_cod",
  pickupLocations: "staff.manage_pickup_locations",
  insightsView: "staff.view_insights",
  signalsAcknowledge: "staff.acknowledge_signal",
  // the ERPNext sync (the backend's erp app): no page of its own here yet; they open the ERPNext links
  erpView: "erp.view_sync",
  erpReplay: "erp.replay_sync",
  erpResolve: "erp.resolve_difference",
  // content (the backend's content/staff_api.py): books, papers, drafts and their review, reported mistakes, imports,
  // legal deposits
  booksView: "content.view_book",
  booksAdd: "content.add_book",
  booksChange: "content.change_book",
  papersView: "content.view_paper",
  papersChange: "content.change_paper",
  papersPublish: "staff.publish_paper",
  questionsView: "content.view_question",
  questionsChange: "content.change_question",
  solutionsView: "content.view_solution",
  solutionsChange: "content.change_solution",
  reviewsView: "content.view_reviewtask",
  reportsView: "content.view_errorreport",
  reportsTriage: "staff.triage_report",
  contentImport: "staff.import_content",
  depositsView: "content.view_legaldeposit",
  depositsAdd: "content.add_legaldeposit",
} as const;

/** Whether the manifest lists the permission (the shell's only use of permissions: what to draw). */
export function has(manifest: Pick<Manifest, "permissions"> | null | undefined, permission: string): boolean {
  return Boolean(manifest?.permissions.includes(permission));
}

export const hasAny = (manifest: Pick<Manifest, "permissions"> | null | undefined, permissions: readonly string[]) =>
  permissions.some((permission) => has(manifest, permission));

export type ModuleGroup = keyof typeof copy.nav.groups;

export type Module = {
  key: keyof typeof copy.nav.modules;
  href: string;
  group: ModuleGroup;
  /** Any of these shows the module; empty: every staff member. */
  any: readonly string[];
  /** Planned for the next phase: the honest empty state of /[module]/. */
  soon?: boolean;
  /** A page of ERPNext (the path under NEXT_PUBLIC_ERP_URL): a link out. */
  erp?: string;
};

const SHIPPING = [P.parcelsView, P.parcelsBook, P.exceptionsAct, P.codView, P.codReconcile, P.pickupLocations];
const ERP = [P.erpView, P.erpReplay, P.erpResolve];

// The order of the plan's information architecture (section 8). The planned modules are drawn for the permissions of
// the data they will show (the shop's, content's, the course's, accounts' TeacherProfile, the shipping and insights
// apps'). The ERPNext links are the sync's (the erp app's permissions): its desk asks for its own sign-in and roles.
export const MODULES: readonly Module[] = [
  { key: "home", href: "/", group: "work", any: [] },
  { key: "inbox", href: "/inbox/", group: "work", any: [P.inboxView] },
  { key: "approvals", href: "/approvals/", group: "work", any: [P.approvalsView] },
  { key: "audit", href: "/audit/", group: "work", any: [P.auditView] },
  { key: "orders", href: "/orders/", group: "shop", any: ["shop.view_order"], soon: true },
  { key: "shipping", href: "/shipping/", group: "shop", any: SHIPPING, soon: true },
  { key: "catalogue", href: "/catalogue/", group: "shop", any: ["shop.view_product"], soon: true },
  { key: "marketing", href: "/marketing/", group: "shop", any: ["shop.view_coupon", "shop.view_offer"], soon: true },
  { key: "content", href: "/content/", group: "learning", any: [P.booksView, P.papersView, P.reportsView] },
  { key: "course", href: "/course/", group: "learning", any: ["learn.view_chapter"], soon: true },
  { key: "users", href: "/users/", group: "customers", any: [P.usersView] },
  { key: "partners", href: "/partners/", group: "customers", any: ["accounts.view_teacherprofile"], soon: true },
  { key: "requests", href: "/privacy/requests/", group: "privacy", any: [P.requestsView] },
  { key: "incidents", href: "/privacy/incidents/", group: "privacy", any: [P.incidentsView] },
  { key: "processors", href: "/privacy/processors/", group: "privacy", any: [P.processorsView] },
  { key: "insights", href: "/insights/", group: "reports", any: [P.insightsView, P.signalsAcknowledge], soon: true },
  { key: "people", href: "/people/", group: "staff", any: [P.peopleView] },
  { key: "accessReview", href: "/people/access-review/", group: "staff", any: [P.peopleView] },
  { key: "apiKeys", href: "/settings/api-keys/", group: "staff", any: [P.apiKeysView] },
  { key: "settings", href: "/settings/", group: "system", any: [P.settingsView, P.flagsView] },
  { key: "system", href: "/system/", group: "system", any: [P.systemView] },
  { key: "finance", href: "/app/accounting", group: "erp", any: ERP, erp: "/app/accounting" },
  { key: "tax", href: "/app/gst-india", group: "erp", any: ERP, erp: "/app/gst-india" },
  { key: "inventory", href: "/app/stock", group: "erp", any: ERP, erp: "/app/stock" },
  { key: "purchases", href: "/app/buying", group: "erp", any: ERP, erp: "/app/buying" },
  { key: "crm", href: "/app/crm", group: "erp", any: ERP, erp: "/app/crm" },
];

/** The modules a manifest opens, in order; the ERPNext links only when its address is set. */
export function visibleModules(manifest: Pick<Manifest, "permissions">, erpUrl: string): Module[] {
  return MODULES.filter(
    (module) => (!module.erp || erpUrl) && (module.any.length === 0 || hasAny(manifest, module.any)),
  );
}

/** The link of a module: the console's path, or the ERPNext page under its base. */
export function moduleHref(module: Module, erpUrl: string): string {
  return module.erp ? `${erpUrl}${module.erp}` : module.href;
}

/** The modules drawn under their groups, in the groups' order. */
export function groupedModules(manifest: Pick<Manifest, "permissions">, erpUrl: string) {
  const visible = visibleModules(manifest, erpUrl);
  return (Object.keys(copy.nav.groups) as ModuleGroup[])
    .map((group) => ({ group, modules: visible.filter((module) => module.group === group) }))
    .filter((entry) => entry.modules.length > 0);
}

/** A "coming in the next phase" module by its path segment (/orders/ → orders), when the manifest opens it. */
export function soonModule(segment: string, manifest: Pick<Manifest, "permissions">): Module | null {
  const found = MODULES.find((entry) => entry.soon && entry.href === `/${segment}/`);
  return found && hasAny(manifest, found.any) ? found : null;
}
