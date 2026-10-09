// The console's modules and the permissions it looks for in the session manifest, in one place: the backend's
// staff/permissions.py names the same codenames (reconcile them here). A module is drawn when the person holds any of
// its permissions; nothing is drawn for the others. That is the only thing the console does with permissions: it hides
// what the manifest says the person cannot use. The API checks every call again and its answer is the truth.
import { copy } from "@/lib/copy";
import type { Manifest } from "@/lib/api/staff";

/** The capability codenames the console reads (Django "app.codename"; staff.* is the staff app's). */
export const P = {
  inboxView: "staff.view_inboxitem",
  inboxChange: "staff.change_inboxitem",
  approvalsView: "staff.view_changerequest",
  approvalsDecide: "staff.approve_changerequest",
  approvalsExecute: "staff.execute_changerequest",
  auditView: "staff.view_auditevent",
  auditExport: "staff.export_auditevent",
  usersView: "accounts.view_user",
  usersExport: "accounts.export_user",
  usersReveal: "accounts.reveal_contact",
  usersSuspend: "accounts.suspend_user",
  usersUnlock: "accounts.unlock_user",
  usersResendVerification: "accounts.resend_verification",
  usersEndSessions: "accounts.end_user_sessions",
  usersPasswordReset: "accounts.initiate_password_reset",
  usersResetMfa: "accounts.reset_user_mfa",
  usersImpersonate: "accounts.impersonate_user",
  peopleView: "staff.view_staff",
  peopleInvite: "staff.invite_staff",
  peopleRoles: "staff.change_staff_roles",
  peopleScopes: "staff.change_staff_scopes",
  peopleSessions: "staff.end_staff_sessions",
  peopleOffboard: "staff.offboard_staff",
  accessReview: "staff.view_accessreview",
  requestsView: "staff.view_datarequest",
  requestsAdd: "staff.add_datarequest",
  requestsChange: "staff.change_datarequest",
  incidentsView: "staff.view_incident",
  incidentsAdd: "staff.add_incident",
  incidentsChange: "staff.change_incident",
  processorsView: "staff.view_processor",
  processorsAdd: "staff.add_processor",
  settingsView: "staff.view_sitesetting",
  settingsChange: "staff.change_sitesetting",
  flagsView: "staff.view_featureflag",
  flagsChange: "staff.change_featureflag",
  apiKeysView: "staff.view_apikey",
  apiKeysAdd: "staff.add_apikey",
  apiKeysRevoke: "staff.revoke_apikey",
  systemView: "staff.view_system",
  maintenance: "staff.change_maintenance",
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

// The order of the plan's information architecture (section 8). The ERPNext paths are the desk's workspaces and the
// Frappe CRM and Helpdesk apps; the base comes from NEXT_PUBLIC_ERP_URL.
export const MODULES: readonly Module[] = [
  { key: "home", href: "/", group: "work", any: [] },
  { key: "inbox", href: "/inbox/", group: "work", any: [P.inboxView] },
  { key: "approvals", href: "/approvals/", group: "work", any: [P.approvalsView] },
  { key: "audit", href: "/audit/", group: "work", any: [P.auditView] },
  { key: "orders", href: "/orders/", group: "shop", any: ["shop.view_order"], soon: true },
  { key: "catalogue", href: "/catalogue/", group: "shop", any: ["shop.view_product"], soon: true },
  { key: "marketing", href: "/marketing/", group: "shop", any: ["shop.view_coupon", "shop.view_offer"], soon: true },
  {
    key: "content",
    href: "/content/",
    group: "learning",
    any: ["content.view_book", "content.view_paper"],
    soon: true,
  },
  { key: "course", href: "/course/", group: "learning", any: ["learn.view_chapter"], soon: true },
  { key: "users", href: "/users/", group: "customers", any: [P.usersView] },
  { key: "requests", href: "/privacy/requests/", group: "privacy", any: [P.requestsView] },
  { key: "incidents", href: "/privacy/incidents/", group: "privacy", any: [P.incidentsView] },
  { key: "processors", href: "/privacy/processors/", group: "privacy", any: [P.processorsView] },
  { key: "people", href: "/people/", group: "staff", any: [P.peopleView] },
  { key: "accessReview", href: "/people/access-review/", group: "staff", any: [P.accessReview] },
  { key: "apiKeys", href: "/settings/api-keys/", group: "staff", any: [P.apiKeysView] },
  { key: "settings", href: "/settings/", group: "system", any: [P.settingsView, P.flagsView] },
  { key: "system", href: "/system/", group: "system", any: [P.systemView] },
  { key: "finance", href: "/app/accounting", group: "erp", any: ["erp.view_finance"], erp: "/app/accounting" },
  { key: "tax", href: "/app/gst-india", group: "erp", any: ["erp.view_tax"], erp: "/app/gst-india" },
  { key: "inventory", href: "/app/stock", group: "erp", any: ["erp.view_inventory"], erp: "/app/stock" },
  { key: "purchases", href: "/app/buying", group: "erp", any: ["erp.view_purchases"], erp: "/app/buying" },
  { key: "crm", href: "/crm", group: "erp", any: ["erp.view_crm"], erp: "/crm" },
  { key: "support", href: "/helpdesk", group: "erp", any: ["erp.view_support"], erp: "/helpdesk" },
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
