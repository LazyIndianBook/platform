// THE STAFF API MOCK, FOR DEVELOPMENT AND TESTS ONLY. It answers the staff API's real paths (/api/v1/staff/…, as
// examleaf-web's staff/api.py: its fields, filters, codes and rules) from the fixtures (fixtures.ts), for the browser
// through src/app/api/mock/staff/[...path]/route.ts (src/proxy.ts sends /api/v1/staff/ there) and for server components
// in-process (src/lib/api/server.ts). It refuses to answer without STAFF_API_MOCK=1, which next.config.ts sets only
// under `next dev`, so a production build can never reach it.
//
// Signing in is real: every request asks the Django backend whose session cookie it carries who is signed in
// (GET /api/v1/me/: 401 signed out, 403 mfa_setup_required for staff without two-step sign-in, the roles otherwise),
// and "confirm it's you" reads allauth's own record of when the session last authenticated. Each staff member gets a
// world of their own (kept on globalThis, so the route handler and the server components share it), changed by what
// they do, and the mock writes audit events as the backend would. The backend's rules it keeps: the permission of
// each endpoint (403 permission_denied), a recent authentication for high and critical ones (403
// reauthentication_required with allauth's flows), the role limits (202 with a change request above them), the
// maker never approving (403), the approver sending back the payload's hash (400 otherwise), separation of duties
// (400), 404 for what is not there. Dev-only cookies change what it answers: staff_mock_role=SUPPORT (another role),
// staff_mock_reauth_after=<epoch seconds> (an older authentication counts as stale), staff_mock_break_glass=1 (a
// break-glass account, which must give its reason first), staff_mock_policies=1 (a policy to acknowledge first).
import type { Note } from "@/lib/api/staff";

import * as taxRules from "./tax";
import {
  COLLEAGUES,
  createWorld,
  type MockJob,
  type MockPolicy,
  type MockSchemas,
  payloadHash,
  type World,
} from "./fixtures";
import { ordersJob, ordersJobPermission, ordersPermission, ordersRoute, type OrdersKit } from "./orders";
import { MANAGEMENT_PERMISSIONS, offerEndSessions, passkeyDue, routeManagement } from "./management";
import { contentPermission, contentRoute, startContentImport, type Tools } from "./content";
import { grievanceFile, type Kit, startGrievanceExport, supportPermission, supportRoute } from "./support-handler";
import { financePermission, financeRoute, startSettlementFetch } from "./finance";
import { reportFile, reportsPermission, reportsRoute, type ReportsKit, startReportExport } from "./reports";

type S = MockSchemas;

const OFF = "The staff API mock answers only under `next dev` with STAFF_API_MOCK=1 (src/mocks/staff/).";
const API = (process.env.API_INTERNAL_BASE ?? "http://localhost:8100").replace(/\/$/, "");
const ROOT = "/api/v1/staff/";
const REAUTH_SECONDS = 300;
const STAFF_ROLES = ["OWNER", "ADMIN", "FINANCE", "SALES", "SALES_REP", "PACKER", "SUPPORT", "CONTENT_EDITOR"].concat([
  "REVIEWER",
  "MARKETING",
  "AUDITOR",
]);
const PRIVILEGED = new Set(["OWNER", "ADMIN", "FINANCE", "AUDITOR"]);
// accounts/roles.py SOD_CONFLICTS
const CONFLICTS: [string, string][] = [
  ["FINANCE", "PACKER"],
  ["MARKETING", "FINANCE"],
  ...STAFF_ROLES.filter((role) => role !== "AUDITOR").map((role): [string, string] => ["AUDITOR", role]),
];
// settings.STAFF_IDLE_TIMEOUTS: 15 minutes for OWNER, ADMIN, FINANCE and PACKER, 30 for the others
const SHORT_IDLE_ROLES = new Set(["OWNER", "ADMIN", "FINANCE", "PACKER"]);

// The roles' permissions as accounts/roles.py gives them, as far as the console reads them.
const PANEL = ["staff.view_inbox", "staff.view_savedview", "staff.add_savedview", "staff.change_savedview"]
  .concat(["staff.delete_savedview", "staff.view_changerequest", "staff.view_job", "staff.add_job"])
  .concat(["staff.view_note", "staff.add_note"]);
const SUPPORT = [
  ...PANEL,
  "accounts.view_user",
  ...["accounts.view_teacherprofile", "accounts.change_teacherprofile"], // roles.py SUPPORT: teachers are verified here
  "content.view_errorreport", // the mistakes readers report: "did you get my report?"
  "shop.view_order",
  ...["staff.reveal_contact", "staff.unlock_user", "staff.resend_verification", "staff.end_user_sessions"],
  ...["staff.initiate_password_reset", "staff.reset_user_mfa", "staff.impersonate_user"],
  ...["staff.view_datarequest", "staff.handle_data_request", "staff.view_processorrecord"],
  ...["staff.refund_order", "staff.add_changerequest"],
  ...["accounts.view_legalhold", "accounts.view_nominee"], // legal and privacy: what holds an erasure
  ...["shop.view_product", "shop.view_invoice", "shop.view_creditnote", "shop.view_quoterequest"],
  ...["shop.view_returnrequest", "staff.handle_return"],
  ...["shop.view_payment", "shop.view_refund"], // Finance's payments and refunds, read (not its settlements)
  // support (roles.py SUPPORT): every ticket, the saved replies read; the course's entitlements and book codes
  ...["support.view_ticket", "support.note_ticket", "staff.handle_ticket", "support.view_savedreply"],
  ...["learn.view_entitlement", "learn.change_entitlement", "learn.view_bookcode"],
];
const FINANCE = [
  ...PANEL,
  "accounts.view_user",
  "shop.view_order",
  ...["staff.refund_order", "staff.approve_refund", "staff.record_offline_payment", "staff.approve_payment"],
  ...["staff.approve_discount", "staff.add_changerequest"],
  // tax: the HSN and SAC master, the series register, the thresholds and the calendar, cancelling, GSTR-1
  ...["shop.view_hsncode", "shop.change_hsncode", "shop.view_documentseries", "shop.view_taxthreshold"],
  ...["staff.cancel_document", "staff.run_gstr1"],
  ...["accounts.view_legalhold", "staff.manage_holds"], // legal holds: a chargeback, a dispute over money
  ...["shop.view_product", "shop.view_invoice", "shop.view_creditnote", "shop.view_returnrequest"],
  ...["shop.view_quoterequest", "shop.export_order"],
  "integrations.view_integrationaccount", // the connections' cards (the payment settings)
  // Finance (shop/staff_finance.py): payments, refunds, links and settlements; a day fetched, a line matched by hand
  ...["shop.view_payment", "shop.view_refund", "shop.view_settlement", "shop.view_settlementline"],
  ...["shop.view_invoicepaymentlink", "staff.reconcile_settlements", "staff.replay_webhook"],
  // Home and reports (roles.py FINANCE): the money cards, COD, the settlements, the sales lines; a report as a file
  ...["staff.view_insights", "shop.view_orderitem", "shop.view_payment", "shop.view_refund", "staff.view_cod"],
  ...["shop.view_settlement", "staff.export_report"],
];
// the Orders module's roles (accounts/roles.py): SALES runs the orders, SALES_REP makes staff orders and quotes, PACKER
// packs and receives returns
const SALES = [
  ...PANEL,
  "accounts.view_user",
  ...["shop.view_order", "shop.add_order", "shop.change_order", "shop.view_product", "shop.view_invoice"],
  ...["shop.view_creditnote", "shop.view_quoterequest", "shop.change_quoterequest", "shop.view_returnrequest"],
  ...["staff.refund_order", "staff.record_offline_payment", "staff.add_changerequest"],
  ...["staff.handle_return", "staff.receive_return", "staff.view_parcels"],
  ...["shop.view_payment", "shop.view_refund"], // Finance's payments, refunds and links (they make the links)
  ...["staff.view_insights", "shop.view_orderitem"], // the sales reports (roles.py SALES)
];
const SALES_REP = [
  ...PANEL,
  ...["shop.view_order", "shop.add_order", "shop.change_order", "shop.view_product"],
  ...["shop.view_quoterequest", "shop.change_quoterequest", "staff.add_changerequest"],
];
// roles.py CONTENT (the records, every verb) and CONTENT_PANEL (the content module's queues)
const CONTENT = ["book", "paper", "question", "solution"].flatMap((model) =>
  ["view", "add", "change", "delete"].map((verb) => `content.${verb}_${model}`),
);
const CONTENT_PANEL = ["content.view_reviewtask", "content.view_errorreport", "staff.triage_report"].concat([
  "content.view_legaldeposit",
]);
const OWNER_ONLY = ["staff.assign_role", "staff.manage_api_keys", "staff.break_glass"].concat([
  "staff.view_auditlog",
  "staff.export_auditlog",
]);
const MONEY_APPROVALS = ["staff.approve_refund", "staff.approve_payment", "staff.approve_discount"];
const EVERYTHING = [
  ...new Set([
    ...SUPPORT,
    ...FINANCE,
    ...OWNER_ONLY,
    ...["staff.view_staff", "staff.approve_role_change", "staff.approve_erasure", "staff.approve_export"],
    ...["staff.export_personal_data", "staff.view_incident", "staff.manage_incident", "staff.add_processorrecord"],
    ...["staff.view_sitesetting", "staff.manage_settings", "staff.view_featureflag", "staff.manage_flags"],
    ...["staff.toggle_maintenance", "staff.view_apikey", "staff.view_system", "staff.replay_webhook"],
    ...["staff.suspend_user", "shop.view_product", "shop.change_product", "shop.view_coupon", "shop.add_coupon"],
    ...CONTENT,
    ...CONTENT_PANEL,
    ...["content.add_legaldeposit", "staff.publish_paper", "staff.import_content", "learn.view_chapter"],
    ...["staff.view_parcels", "staff.book_parcel", "staff.view_insights", "erp.view_sync"],
    ...["pages.view_page", "pages.change_page", "staff.view_darkpatternaudit", "staff.manage_compliance"],
    ...SALES,
    ...["staff.pack_order", "staff.receive_return"],
    ...MANAGEMENT_PERMISSIONS, // the connections, the templates, the system's pages (management.ts)
    ...["support.add_savedreply", "support.change_savedreply", "support.delete_savedreply"],
    ...["staff.export_grievances", "shop.change_order"],
    ...["shop.view_orderitem", "learn.view_progress", "staff.view_cod", "staff.export_report"], // Home and reports
    ...["shop.view_payment", "shop.view_refund", "shop.view_settlement"],
  ]),
].sort();
const ROLE_PERMISSIONS: Record<string, string[]> = {
  OWNER: EVERYTHING,
  ADMIN: EVERYTHING.filter((perm) => !OWNER_ONLY.includes(perm) && !MONEY_APPROVALS.includes(perm)),
  FINANCE,
  SUPPORT,
  PACKER: ["staff.view_inbox", "staff.view_savedview", "shop.view_order", "staff.view_parcels"].concat([
    "staff.pack_order",
    "staff.book_parcel",
    "shop.view_product",
    "shop.view_returnrequest",
    "staff.receive_return",
    "staff.view_job",
    "staff.add_job",
  ]),
  SALES,
  SALES_REP,
  CONTENT_EDITOR: [
    ...PANEL,
    ...CONTENT,
    ...CONTENT_PANEL,
    ...["content.add_legaldeposit", "learn.view_chapter", "shop.view_product"],
    ...["support.view_ticket", "support.note_ticket"], // the content errors' tickets (ROLE_SCOPES), noted on
  ],
  REVIEWER: [
    ...PANEL,
    ...CONTENT.filter((perm) => perm.includes(".view_")),
    ...CONTENT_PANEL,
    ...["staff.publish_paper", "staff.import_content"],
  ],
  AUDITOR: [
    ...EVERYTHING.filter((perm) => perm.split(".")[1].startsWith("view_")),
    ...["staff.export_auditlog", "staff.export_grievances", "staff.export_report"],
  ],
};
// accounts/roles.py ROLE_LIMITS (null: none)
const LIMITS: Record<string, Record<string, number | null>> = {
  OWNER: { refund_inr: null, offline_inr: null, discount_percent: null, export_rows: null, bulk_rows: null },
  ADMIN: { refund_inr: 10000, offline_inr: 50000, discount_percent: 50, export_rows: 10000, bulk_rows: 1000 },
  FINANCE: { refund_inr: 10000, offline_inr: 50000, discount_percent: 50, export_rows: 10000, bulk_rows: 500 },
  SUPPORT: { refund_inr: 1000, offline_inr: 0, discount_percent: 0, export_rows: 100, bulk_rows: 50 },
  AUDITOR: { refund_inr: 0, offline_inr: 0, discount_percent: 0, export_rows: 5000, bulk_rows: 0 },
  SALES: { refund_inr: 2000, offline_inr: 5000, discount_percent: 20, export_rows: 500, bulk_rows: 100 },
  SALES_REP: { refund_inr: 0, offline_inr: 0, discount_percent: 10, export_rows: 200, bulk_rows: 50 },
  PACKER: { refund_inr: 0, offline_inr: 0, discount_percent: 0, export_rows: 0, bulk_rows: 100 },
};
// staff/catalogue.py: the high and critical permissions, which need a recent authentication
const RISKY = new Set([
  ...["staff.refund_order", "staff.approve_refund", "staff.approve_payment", "staff.approve_discount"],
  ...["staff.reveal_contact", "staff.suspend_user", "staff.reset_user_mfa", "staff.impersonate_user"],
  ...["staff.export_personal_data", "staff.approve_erasure", "staff.manage_incident", "staff.assign_role"],
  ...["staff.approve_role_change", "staff.manage_api_keys", "staff.export_auditlog", "staff.approve_export"],
  ...["staff.manage_settings", "staff.manage_flags", "staff.toggle_maintenance", "staff.cancel_document"],
  ...["staff.manage_holds", "staff.manage_compliance"],
  ...["staff.record_offline_payment", "shop.export_order"],
  ...["staff.import_content", "staff.export_grievances", "staff.export_report"],
]);
// the online-paid orders a refund may name (shop.Order with a captured Razorpay payment), rupees paid
const PAID_ORDERS: Record<string, { id: number; paid: number; shipped: boolean }> = {
  "EL-2026-000123": { id: 41, paid: 2500, shipped: true },
  "EL-2026-000130": { id: 44, paid: 1499, shipped: false },
  "EL-2026-000131": { id: 45, paid: 798, shipped: false },
};

type Store = { worlds: Record<string, World> };
const store: Store = ((globalThis as { __examleafStaffMock?: Store }).__examleafStaffMock ??= { worlds: {} });

type Who = { id: number; email: string; name: string; role: string; breakGlass: boolean };
type Body = Record<string, unknown>;
type Context = {
  request: Request;
  url: URL;
  parts: string[];
  method: string;
  world: World;
  who: Who;
  body: Body;
  permissions: string[];
};

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store", ...headers },
  });
const noContent = () => new Response(null, { status: 204, headers: { "Cache-Control": "no-store" } });
const notFound = () => json(404, { detail: "Not found.", code: "not_found" });
const invalid = (fields: Record<string, unknown>) => json(400, fields);
const refuse = (perm: string, detail = `You need the permission ${perm}.`) =>
  json(403, { detail, code: "permission_denied" });
const REAUTH = json.bind(null, 403, {
  detail: "Log in again or re-authenticate to do this.",
  code: "reauthentication_required",
  flows: [{ id: "reauthenticate" }, { id: "mfa_reauthenticate", types: ["totp"] }],
});

function cookie(request: Request, name: string): string | undefined {
  return (request.headers.get("Cookie") ?? "")
    .split(/;\s*/)
    .find((pair) => pair.startsWith(`${name}=`))
    ?.slice(name.length + 1);
}

/** Asks Django who is signed in, with the request's own cookies. */
async function signedIn(request: Request): Promise<Who | Response> {
  let response: Response;
  try {
    response = await fetch(`${API}/api/v1/me/`, {
      headers: { Cookie: request.headers.get("Cookie") ?? "", Accept: "application/json" },
      cache: "no-store",
    });
  } catch {
    return json(503, { detail: "The Django backend did not answer the mock's sign-in check." });
  }
  const body = (await response.json().catch(() => null)) as Body | null;
  if (response.status === 401)
    return json(401, { detail: "Authentication credentials were not provided.", code: "not_authenticated" });
  if (response.status === 403) return json(403, body ?? { detail: "", code: "permission_denied" });
  if (!response.ok || !body) return json(502, { detail: "The Django backend's answer was not understood." });
  const roles = Array.isArray(body.roles) ? body.roles.map(String) : [];
  const asked = cookie(request, "staff_mock_role");
  const role = asked && ROLE_PERMISSIONS[asked] ? asked : (roles.find((name) => ROLE_PERMISSIONS[name]) ?? "");
  const breakGlass = cookie(request, "staff_mock_break_glass") === "1";
  if (!role && !breakGlass) return json(403, { detail: "For staff only.", code: "permission_denied" });
  return {
    id: Number(body.id),
    email: String(body.email),
    name: String(body.full_name ?? body.email),
    role,
    breakGlass,
  };
}

/** When the session logged in and last authenticated (allauth's records), in seconds since 1970; 0 when unknown. */
async function authenticated(request: Request): Promise<{ first: number; last: number }> {
  try {
    const response = await fetch(`${API}/_allauth/browser/v1/auth/session`, {
      headers: { Cookie: request.headers.get("Cookie") ?? "", Accept: "application/json" },
      cache: "no-store",
    });
    const body = (await response.json()) as { data?: { methods?: { at?: number }[] } };
    const times = (body.data?.methods ?? []).map((method) => Number(method.at) || 0).filter(Boolean);
    return times.length ? { first: Math.min(...times), last: Math.max(...times) } : { first: 0, last: 0 };
  } catch {
    return { first: 0, last: 0 };
  }
}

async function recentlyAuthenticated(request: Request): Promise<boolean> {
  const { last } = await authenticated(request);
  const after = Number(cookie(request, "staff_mock_reauth_after") ?? 0);
  return last > after && Date.now() / 1000 - last < REAUTH_SECONDS;
}

/** Django's double-submit CSRF check: the X-CSRFToken header must match the csrftoken cookie. */
function csrfOk(request: Request): boolean {
  const token = cookie(request, "csrftoken");
  return Boolean(token) && request.headers.get("X-CSRFToken") === token;
}

const now = () => new Date().toISOString();
const text = (value: unknown) => (typeof value === "string" ? value.trim() : "");
const bool = (value: string | null) => value === "true" || value === "1";
const nextId = (world: World) => ++world.seq;
const byId = <T extends { id: number }>(rows: T[], id: string | undefined) => rows.find((row) => String(row.id) === id);

function limitOf(context: Context, name: string): number | null {
  if (context.who.breakGlass) return null;
  const limits = LIMITS[context.who.role] ?? {};
  return name in limits ? limits[name] : 0;
}

/** One page of the API's cursor pagination: `next`/`previous` are links with the cursor (an offset here). */
function paginate<T>(context: Context, rows: T[], size = Number(context.url.searchParams.get("page_size")) || 10) {
  const offset = Number(Buffer.from(context.url.searchParams.get("cursor") ?? "", "base64url").toString() || 0) || 0;
  const link = (at: number) => {
    const next = new URL(context.url.pathname.replace(/^\/api\/mock\/staff\//, ROOT), "http://localhost");
    context.url.searchParams.forEach((value, key) => next.searchParams.set(key, value));
    next.searchParams.set("cursor", Buffer.from(String(at)).toString("base64url"));
    return `${context.url.origin}${next.pathname}${next.search}`;
  };
  return json(200, {
    results: rows.slice(offset, offset + size),
    next: offset + size < rows.length ? link(offset + size) : null,
    previous: offset > 0 ? link(Math.max(0, offset - size)) : null,
  });
}

/** An audit event, as staff.audit.record writes one. */
function record(context: Context, action: string, extra: Partial<S["AuditEvent"]> = {}) {
  const id = nextId(context.world);
  const previous = context.world.audit[0]?.hash ?? "";
  context.world.audit.unshift({
    id,
    chain: /^(order|payment|refund|product|coupon)\./.test(action) ? "money" : "general",
    ts: now(),
    actor_id: context.who.id,
    actor_type: "staff",
    actor_roles: [context.who.role],
    on_behalf_of: null,
    break_glass: context.who.breakGlass,
    action,
    permission: "",
    target_type: "",
    target_id: "",
    target_label: "",
    outcome: "success",
    reason: "",
    change_request_id: null,
    request_id: `req-${id.toString(16)}`,
    ip: "127.0.0.x",
    user_agent: "",
    session_hash: "",
    changes: {},
    details: {},
    prev_hash: previous,
    hash: payloadHash({ id, action, previous }),
    ...extra,
  });
}

const target = (type: string, id: number | string, label: string) => ({
  target_type: type,
  target_id: String(id),
  target_label: label,
});

/** A change request that waits (staff.approvals.ask above the rule), with its inbox item, answered 202. */
function waiting(
  context: Context,
  row: Omit<
    S["ChangeRequest"],
    "id" | "payload_sha256" | "status" | "approvals" | "created" | "modified" | "expires_at" | "maker"
  >,
) {
  const id = nextId(context.world);
  const created = now();
  const changeRequest: S["ChangeRequest"] = {
    id,
    payload_sha256: payloadHash(row.payload),
    status: "pending",
    approvals: [],
    maker: context.who.id,
    created,
    modified: created,
    expires_at: new Date(Date.now() + 24 * 3_600_000).toISOString(),
    ...row,
  };
  context.world.changeRequests.unshift(changeRequest);
  context.world.inbox.unshift({
    id: nextId(context.world),
    kind: "approval",
    title: `${row.label}: ${row.target_label} waits for approval`,
    ...target("staff.changerequest", id, `Change request #${id}`),
    permission: row.checker,
    assignee: null,
    due_at: changeRequest.expires_at,
    overdue: false,
    snoozed_until: null,
    done_at: null,
    done_by: null,
    data: {},
    created,
  });
  record(context, `${row.action}.requested`, {
    ...target(row.target_type ?? "", row.target_id ?? "", row.target_label ?? ""),
    change_request_id: id,
    reason: row.reason,
    details: { rule: row.rule },
  });
  return json(202, changeRequest);
}

function manifest(context: Context, { first, last }: { first: number; last: number }) {
  const { world, who } = context;
  const permissions = [...context.permissions].sort();
  const body = {
    roles: who.breakGlass ? [] : [{ name: who.role, expires_at: null, granted_by: 1 }],
    permissions,
    scopes: {},
    role_scopes: who.role === "PACKER" ? { PACKER: { order_status: ["paid", "packed", "shipped", "placed"] } } : {},
    limits: Object.fromEntries(
      ["refund_inr", "offline_inr", "discount_percent", "export_rows", "bulk_rows"].map((name) => [
        name,
        limitOf(context, name),
      ]),
    ),
    // the mock's world is test data: the console shows its TEST band
    flags: { ...Object.fromEntries(world.flags.map((flag) => [flag.key, flag.value])), test_mode: true },
  };
  const until = world.impersonation && Date.parse(world.impersonation.until) > Date.now() ? world.impersonation : null;
  const policy = { policy: "acceptable_use", version: "2026-10" }; // STAFF_POLICIES: the key and the version in force
  return json(200, {
    user: { id: who.id, email: who.email, full_name: who.name, is_superuser: who.breakGlass },
    ...body,
    reauth_valid_until: last ? new Date((last + REAUTH_SECONDS) * 1000).toISOString() : null,
    idle_timeout_s: who.breakGlass || SHORT_IDLE_ROLES.has(who.role) ? 900 : 1800,
    absolute_expires_at: new Date(((first || Date.now() / 1000) + 8 * 3600) * 1000).toISOString(),
    impersonating: until
      ? {
          user_id: until.user,
          email: world.users.find((user) => user.id === until.user)?.email ?? "",
          until: until.until,
        }
      : null,
    manifest_version: payloadHash(body).slice(0, 16),
    // a break-glass session: its reason first, within a box of STAFF_BREAK_GLASS_HOURS (2) from the log-in
    break_glass: who.breakGlass
      ? {
          reason_required: !world.breakGlassReason,
          reason: world.breakGlassReason,
          ends_at: new Date(((first || Date.now() / 1000) + 2 * 3600) * 1000).toISOString(),
        }
      : null,
    policies_due:
      cookie(context.request, "staff_mock_policies") === "1" && !world.policiesAcknowledged.includes(policy.policy)
        ? [policy]
        : [],
    // a privileged role without a passkey adds one first (staff_mock_passkey=0); the offer to end the other sessions
    // after a second factor changed (staff_mock_factor_changed=1), once
    steps: passkeyDue(context.request, who.role, who.breakGlass) ? ["passkey_required"] : [],
    offer_end_sessions: offerEndSessions(context.request, world),
  });
}

/** Which permission a request needs, as each StaffView's `permissions` names it; null: any member of staff. */
function permissionFor(context: Context): string | null {
  const { method, parts } = context;
  const [area, a, b, c] = parts;
  const get = method === "GET";
  switch (area) {
    case "session":
    case "catalogue":
    case "policies":
      return null;
    case "inbox":
      return "staff.view_inbox";
    case "audit":
      return a === "export" ? "staff.export_auditlog" : "staff.view_auditlog";
    case "change-requests":
      return !a && method === "POST" ? "staff.add_changerequest" : "staff.view_changerequest";
    case "jobs": {
      // POST jobs/: the kind's own permission (staff.jobs.permission); the others: staff.view_job
      if (method !== "POST" || a) return "staff.view_job";
      const kind = context.body.kind;
      if (kind === "content_import") return "staff.import_content";
      if (kind === "grievance_export") return "staff.export_grievances";
      if (kind === "settlement_fetch") return "staff.reconcile_settlements";
      if (kind === "report_export") return "staff.export_report";
      return ordersJobPermission(kind) ?? "staff.add_job";
    }
    case "home": // insights/staff_home.py and staff_api.py: any member of staff's Home; the insights' reader's reports
    case "reports":
    case "insights":
      return reportsPermission(context);
    case "orders":
      return ordersPermission(method, parts);
    case "content":
      return contentPermission(method, parts);
    case "saved-views":
      return get
        ? "staff.view_savedview"
        : method === "POST"
          ? "staff.add_savedview"
          : method === "DELETE"
            ? "staff.delete_savedview"
            : "staff.change_savedview";
    case "settings":
      return get
        ? "staff.view_sitesetting"
        : a?.startsWith("MAINTENANCE_")
          ? "staff.toggle_maintenance"
          : "staff.manage_settings";
    case "flags":
      return get ? "staff.view_featureflag" : "staff.manage_flags";
    case "api-keys":
      return get ? "staff.view_apikey" : "staff.manage_api_keys";
    case "people":
      if (get) return "staff.view_staff";
      return b === "reset-mfa" ? "staff.reset_user_mfa" : "staff.assign_role";
    case "access-review":
      return "staff.view_staff";
    case "users": {
      if (get) return "accounts.view_user";
      const verbs: Record<string, string> = {
        reveal: "staff.reveal_contact",
        suspend: "staff.suspend_user",
        unsuspend: "staff.suspend_user",
        unlock: "staff.unlock_user",
        "resend-verification": "staff.resend_verification",
        "end-sessions": "staff.end_user_sessions",
        "password-reset": "staff.initiate_password_reset",
        "reset-mfa": "staff.reset_user_mfa",
        impersonate: "staff.impersonate_user",
      };
      return verbs[b ?? ""] ?? "accounts.view_user";
    }
    case "notes":
      return get ? "staff.view_note" : "staff.add_note";
    case "data-requests":
      if (get) return "staff.view_datarequest";
      return b === "export" ? "staff.export_personal_data" : "staff.handle_data_request";
    case "incidents":
      return get ? "staff.view_incident" : "staff.manage_incident";
    case "processors":
      return get ? "staff.view_processorrecord" : "staff.add_processorrecord";
    case "system":
      return a === "reconcile" ? "staff.replay_webhook" : "staff.view_system";
    case "tax": // shop/staff_tax.py
      if (a === "hsn") return get ? "shop.view_hsncode" : "shop.change_hsncode";
      if (a === "problems") return "shop.view_hsncode";
      if (a === "documents") return get ? "shop.view_documentseries" : "staff.cancel_document";
      if (a === "series") return "shop.view_documentseries";
      if (a === "gstr1") return "staff.run_gstr1";
      return "shop.view_taxthreshold"; // the thresholds and the calendar
    case "privacy": {
      // staff/privacy_api.py's permissions maps
      const verbs: Record<string, [string, string]> = {
        cockpit: ["staff.view_datarequest", "staff.view_datarequest"],
        retention: ["staff.view_datarequest", "staff.view_datarequest"],
        holds: ["accounts.view_legalhold", "staff.manage_holds"],
        nominees: ["accounts.view_user", "staff.reveal_contact"],
        deletions: ["staff.handle_data_request", "staff.handle_data_request"],
        policies: ["pages.view_page", "pages.change_page"],
        disclosures: ["staff.view_sitesetting", "staff.manage_settings"],
        "dark-pattern-audits": ["staff.view_darkpatternaudit", "staff.manage_compliance"],
      };
      const [reads, changes] = verbs[a ?? ""] ?? ["staff.view_system", "staff.view_system"];
      return get ? reads : changes;
    }
    case "support":
      return supportPermission(context);
    case "finance":
      return financePermission(context);
  }
  void c;
  return "staff.view_system";
}

/** Whether the action needs a recent authentication: its permission is high or critical (catalogue.needs_reauth),
 *  or it is an approval's or a run's (ChangeRequestViewSet.reauth), or an erasure. */
function needsReauth(context: Context, perm: string | null): boolean {
  const { method, parts } = context;
  const [area, , b] = parts;
  if (method === "GET") return false;
  if (area === "change-requests" && (b === "approve" || b === "execute")) return true;
  if (area === "change-requests" && !parts[1]) return RISKY.has("staff.refund_order");
  if (area === "data-requests" && b === "erase") return true;
  if (area === "users" && b === "impersonate" && parts[3] === "end") return false;
  return perm !== null && RISKY.has(perm);
}

async function route(context: Context): Promise<Response> {
  const { method, parts, world, url, body, who } = context;
  const [area, a, b, c] = parts;
  const query = (name: string) => url.searchParams.get(name) ?? "";
  const can = (perm: string) => context.permissions.includes(perm);
  const me = who.id;

  if (area === "session" && !a && method === "GET") return manifest(context, await authenticated(context.request));
  if (area === "session" && a === "reason" && method === "POST") {
    if (!who.breakGlass) return json(400, { non_field_errors: ["Only a break-glass session gives a reason."] });
    const reason = text(body.reason);
    if (reason.length < 10) return invalid({ reason: ["Say what happened: at least 10 characters."] });
    world.breakGlassReason = reason;
    record(context, "break_glass.reason", { reason });
    return json(200, { detail: "Recorded." });
  }
  if (area === "policies" && a === "ack" && method === "POST") {
    if (!text(body.policy) || !text(body.version)) return invalid({ policy: ["Name the policy and its version."] });
    world.policiesAcknowledged.push(text(body.policy));
    record(context, "policy.acknowledged", { details: { policy: body.policy, version: body.version } });
    return json(201, { policy: body.policy, version: body.version, acknowledged_at: now() });
  }
  if (area === "catalogue" && method === "GET") return json(200, { permissions: [], roles: [] });

  // Phase B: a passkey first (but for one's own sessions), then the role catalogue, access, offboarding, history, the
  // connections, the templates and the system's pages (management.ts)
  if (passkeyDue(context.request, who.role, who.breakGlass) && !(area === "people" && a === "me"))
    return json(403, {
      detail: "Add a passkey or a security key on the website's security page first (/account/security/).",
      code: "passkey_required",
    });
  const managed = await routeManagement(context, {
    json,
    noContent,
    notFound,
    invalid,
    refuse,
    reauth: () => REAUTH(),
    recentlyAuthenticated: () => recentlyAuthenticated(context.request),
    record: (action, extra) => record(context, action, extra as Partial<S["AuditEvent"]>),
    paginate: (rows, size) => paginate(context, rows, size),
    nextId: () => nextId(world),
  });
  if (managed) return managed;

  const perm = permissionFor(context);
  if (perm && !can(perm)) {
    record(context, "authz_fail", {
      outcome: "denied",
      details: { method, path: url.pathname, error: "permission_denied" },
    });
    return refuse(perm);
  }
  if (needsReauth(context, perm) && !(await recentlyAuthenticated(context.request))) return REAUTH();

  switch (area) {
    case "content":
      return contentRoute(toolsOf(context));

    case "inbox": {
      const visible = world.inbox.filter(
        (item) => item.assignee === me || (!item.assignee && (who.breakGlass || can(item.permission))),
      );
      const open = (item: S["InboxItem"]) => !item.done_at;
      const awake = (item: S["InboxItem"]) => !item.snoozed_until || Date.parse(item.snoozed_until) <= Date.now();
      if (method === "GET" && !a) {
        const rows = visible.filter(
          (item) =>
            (bool(url.searchParams.get("done")) ? !open(item) : open(item)) &&
            (bool(url.searchParams.get("snoozed")) || awake(item)) &&
            (!query("kind") || item.kind === query("kind")) &&
            (!bool(url.searchParams.get("mine")) || item.assignee === me),
        );
        return paginate(context, rows);
      }
      if (method === "GET" && a === "count") {
        const rows = visible.filter((item) => open(item) && awake(item));
        return json(200, {
          open: rows.length,
          overdue: rows.filter((item) => item.due_at && Date.parse(item.due_at) < Date.now()).length,
        });
      }
      const item = byId(visible, a);
      if (!item || method !== "POST") return notFound();
      if (b === "done") {
        item.done_at ??= now();
        item.done_by ??= me;
        return json(200, item);
      }
      if (b === "snooze") {
        const until = text(body.until);
        if (!until || Number.isNaN(Date.parse(until))) return invalid({ until: ["Enter a valid date/time."] });
        item.snoozed_until = until;
        return json(200, item);
      }
      if (b === "assign") {
        const assignee = body.assignee === null ? null : Number(body.assignee);
        if (assignee !== null && !world.people.some((person) => person.id === assignee))
          return invalid({ assignee: ["A member of staff who may act on it."] });
        item.assignee = assignee;
        return json(200, item);
      }
      return notFound();
    }

    case "audit": {
      const filters: Record<string, string> =
        a === "export"
          ? Object.fromEntries(
              Object.entries((body.filters as Record<string, unknown>) ?? {}).map(([key, value]) => [
                key,
                String(value),
              ]),
            )
          : Object.fromEntries(url.searchParams.entries());
      const known = ["actor", "action", "action_prefix", "since", "until", "change_request", "actor_type"].concat([
        "target_type",
        "target_id",
        "outcome",
        "request_id",
        "ip",
        "chain",
        "permission",
        "break_glass",
      ]);
      const rows = world.audit.filter((event) => {
        const ts = Date.parse(event.ts);
        const is = (name: string, value: unknown) => !filters[name] || String(value) === filters[name];
        return (
          is("actor", event.actor_id) &&
          is("action", event.action) &&
          (!filters.action_prefix || event.action.startsWith(filters.action_prefix)) &&
          is("actor_type", event.actor_type) &&
          is("target_type", event.target_type) &&
          is("target_id", event.target_id) &&
          is("outcome", event.outcome) &&
          is("change_request", event.change_request_id) &&
          (!filters.break_glass || event.break_glass === bool(filters.break_glass)) &&
          (!filters.since || ts >= Date.parse(filters.since)) &&
          (!filters.until || ts < Date.parse(filters.until))
        );
      });
      if (method === "POST" && a === "export") {
        const unknown = Object.keys(filters).filter((name) => !known.includes(name));
        if (unknown.length)
          return invalid({
            filters: Object.fromEntries(unknown.map((name) => [name, ["Not a filter of the audit log."]])),
          });
        const limit = limitOf(context, "export_rows");
        if (rows.length > 5000 || (limit !== null && rows.length > limit)) {
          const job = startJob(
            context,
            "audit_export",
            { filters },
            rows.map((row) => String(row.id)),
          );
          if (limit !== null && rows.length > limit) {
            const answer = await waiting(context, {
              action: "job.run",
              label: "Run a large job",
              ...target("staff.job", job.id, `Job #${job.id}`),
              payload: { job: job.id, kind: "audit_export", total: rows.length, params: { filters } },
              amount: null,
              reason: `Audit log export of ${rows.length} rows (job #${job.id})`,
              rule: `${rows.length} rows are above the limit of ${limit}.`,
              checker: "staff.approve_export",
            }).json();
            job.state = "queued";
            job.change_request_id = (answer as { id: number }).id;
          }
          return json(202, visibleJob(context, job));
        }
        record(context, "audit.exported", {
          permission: "staff.export_auditlog",
          details: { filters, rows: rows.length },
        });
        const lines = rows.map((row) => JSON.stringify(row)).join("\n");
        return new Response(lines ? `${lines}\n` : "", {
          headers: {
            "Content-Type": "application/x-ndjson",
            "Content-Disposition": `attachment; filename="audit-${now().slice(0, 10).replace(/-/g, "")}.jsonl"`,
            "Cache-Control": "no-store",
          },
        });
      }
      if (method !== "GET") return notFound();
      if (a) {
        const event = byId(world.audit, a);
        return event ? json(200, event) : notFound();
      }
      record(context, "audit.read", { details: { filters } });
      return paginate(
        context,
        rows.filter((row) => row.action !== "audit.read" || row.id !== world.audit[0].id),
        15,
      );
    }

    case "change-requests": {
      if (method === "GET" && !a) {
        const status = query("status");
        const mine = bool(url.searchParams.get("mine"));
        const awaiting = bool(url.searchParams.get("awaiting"));
        const rows = world.changeRequests.filter(
          (row) =>
            (!status || row.status === status) &&
            (!query("action") || row.action === query("action")) &&
            (!mine || row.maker === me) &&
            (!awaiting || (row.status === "pending" && row.maker !== me && can(row.checker))),
        );
        return paginate(context, rows);
      }
      if (method === "POST" && !a) {
        const action = text(body.action);
        const reason = text(body.reason);
        const order = PAID_ORDERS[text(body.target)];
        const fields: Record<string, string[]> = {};
        if (action !== "order.refund") fields.action = ["The mock asks for refunds only (order.refund)."];
        if (!reason) fields.reason = ["Say why."];
        if (!order) fields.target = ["No such order (or not one you may see)."];
        if (Object.keys(fields).length) return invalid(fields);
        if (!can("staff.refund_order")) return refuse("staff.refund_order", "Needs staff.refund_order.");
        const key = context.request.headers.get("Idempotency-Key") ?? "";
        const seen = key ? world.changeRequests.find((row) => (row as { _key?: string })._key === key) : undefined;
        if (seen) return json(seen.status === "pending" ? 202 : 200, seen);
        const payload = (body.payload as Record<string, unknown>) ?? {};
        const asked = payload.amount === undefined || payload.amount === "" ? order.paid : Number(payload.amount);
        if (!Number.isFinite(asked) || asked <= 0) return invalid({ amount: ["A number of rupees."] });
        const amount = order.shipped ? Math.min(asked, order.paid) : order.paid;
        const clean = { order: text(body.target), amount: amount.toFixed(2), cancel: !order.shipped };
        const limit = limitOf(context, "refund_inr");
        const row = {
          action: "order.refund",
          label: "Refund an order",
          ...target("shop.order", order.id, text(body.target)),
          payload: clean,
          amount: amount.toFixed(2),
          reason,
          checker: "staff.approve_refund",
        };
        if (limit !== null && amount > limit) {
          const answer = await waiting(context, {
            ...row,
            rule: `A refund of ₹${amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })} is above the limit of ₹${limit.toLocaleString("en-IN")}.`,
          });
          (world.changeRequests[0] as { _key?: string })._key = key;
          return answer;
        }
        const id = nextId(world);
        const done: S["ChangeRequest"] = {
          id,
          ...row,
          payload_sha256: payloadHash(clean),
          maker: me,
          rule: "Within the maker's limits: no approval needed.",
          status: "executed",
          expires_at: new Date(Date.now() + 24 * 3_600_000).toISOString(),
          approvals: [],
          result: { refund: nextId(world), amount: clean.amount, status: "pending" },
          executed_by: me,
          executed_at: now(),
          created: now(),
          modified: now(),
        };
        world.changeRequests.unshift(done);
        record(context, "order.refund.executed", {
          ...target("shop.order", order.id, text(body.target)),
          change_request_id: id,
        });
        return json(201, done);
      }
      const row = byId(world.changeRequests, a);
      if (!row) return notFound();
      if (method === "GET" && !b) return json(200, row);
      if (method !== "POST") return notFound();
      const label = target(row.target_type ?? "", row.target_id ?? "", row.target_label ?? "");
      if (b === "approve") {
        if (!can(row.checker)) return refuse(row.checker, `Needs ${row.checker}.`);
        if (row.maker === me) return refuse(row.checker, "Another person approves it: the maker never does.");
        if (row.status !== "pending") return invalid({ non_field_errors: ["Only a request waiting for approval."] });
        if (text(body.payload_sha256) !== row.payload_sha256)
          return invalid({ payload_sha256: ["The request is not the one you read: read it again."] });
        row.approvals.push({ user: me, decision: "approve", comment: text(body.comment), created: now() });
        row.status = "approved";
        row.modified = now();
        record(context, `${row.action}.approved`, { ...label, change_request_id: row.id, reason: text(body.comment) });
        return json(200, row);
      }
      if (b === "reject") {
        if (row.maker !== me && !can(row.checker))
          return refuse(row.checker, `Needs ${row.checker} (or to be its maker).`);
        if (row.status !== "pending") return invalid({ non_field_errors: ["Only a request waiting for approval."] });
        row.approvals.push({ user: me, decision: "reject", comment: text(body.comment), created: now() });
        row.status = "rejected";
        row.modified = now();
        record(context, `${row.action}.rejected`, { ...label, change_request_id: row.id, reason: text(body.comment) });
        return json(200, row);
      }
      if (b === "execute") {
        if (row.maker !== me && !can(row.checker))
          return refuse(row.checker, `Needs ${row.checker} (or to be its maker).`);
        if (row.status !== "approved") return invalid({ non_field_errors: ["Only an approved request runs, once."] });
        row.status = "executed";
        row.result =
          row.action === "product.price"
            ? { product: row.target_id, price: (row.payload as Body).price }
            : { done: true };
        row.executed_by = me;
        row.executed_at = now();
        row.modified = now();
        record(context, `${row.action}.executed`, { ...label, change_request_id: row.id });
        if (row.action === "job.run") {
          const job = byId(world.jobs, String((row.payload as Body).job));
          if (job) job.state = "running";
        }
        return json(200, row);
      }
      return notFound();
    }

    case "orders":
      return ordersRoute(ordersKit(context));

    case "home":
    case "reports":
    case "insights":
      return reportsRoute(context, REPORTS_KIT);

    case "jobs": {
      if (method === "POST" && !a) {
        const kind = text(body.kind);
        if (kind === "grievance_export") return startGrievanceExport(context, KIT);
        if (kind === "settlement_fetch")
          return startSettlementFetch(context, KIT, { ...((body.params ?? {}) as Body), dry_run: body.dry_run });
        if (kind === "report_export") return startReportExport(context, REPORTS_KIT);
        if (kind === "content_import") {
          const started = startContentImport(toolsOf(context));
          return started instanceof Response ? started : json(202, visibleJob(context, started));
        }
        if (!ordersJobPermission(kind))
          return invalid({ kind: ["The mock starts the orders' jobs and content imports only."] });
        return ordersJob(ordersKit(context), kind, (body.params ?? {}) as Body);
      }
      const mine = world.jobs.filter((job) => job.started_by === me || can("staff.view_system"));
      if (method === "GET" && !a) {
        const rows = mine.filter(
          (job) =>
            (!bool(url.searchParams.get("mine")) || job.started_by === me) &&
            (!query("state") || job.state === query("state")) &&
            (!query("kind") || job.kind === query("kind")),
        );
        return paginate(
          context,
          rows.map((job) => visibleJob(context, advance(job))),
        );
      }
      const job = byId(mine, a);
      if (!job) return notFound();
      if (method === "GET" && !b) return json(200, visibleJob(context, advance(job)));
      if (job.started_by !== me) return notFound();
      if (method === "POST" && b === "cancel") {
        if (["done", "failed", "cancelled"].includes(job.state))
          return invalid({ non_field_errors: ["The job has finished."] });
        job.cancel_requested = true;
        if (job.state === "queued") {
          job.state = "cancelled";
          job.finished_at = now();
          const waitingRequest = byId(world.changeRequests, String(job.change_request_id));
          if (waitingRequest?.status === "pending") waitingRequest.status = "rejected";
        }
        record(context, "job.cancelled", target("staff.job", job.id, `Job #${job.id}`));
        return json(200, visibleJob(context, job));
      }
      if (method === "GET" && b === "result") {
        const [, id, expires] = (query("token") || "x-0-0").split("-");
        if (id !== String(job.id) || Number(expires) < Date.now())
          return json(403, {
            detail: "This link has expired: read the job again for a new one.",
            code: "link_expired",
          });
        record(context, "job.result_downloaded", target("staff.job", job.id, `Job #${job.id}`));
        if (job.kind === "gstr1_export")
          // the mock's file: the period's document numbers (the backend zips the Offline Tool's seven CSV files)
          return new Response(["Document number", ...job._rows].join("\n") + "\n", {
            headers: {
              "Content-Type": "text/csv",
              "Content-Disposition": `attachment; filename="gstr1-docs-${job.id}.csv"`,
              "Cache-Control": "no-store",
            },
          });
        if (job.kind === "orders_print" || job.kind === "orders_export") {
          const csv = job.kind === "orders_export";
          return new Response(csv ? "number,created,status,total\n" : "%PDF-1.4\n%%EOF\n", {
            headers: {
              "Content-Type": csv ? "text/csv" : "application/pdf",
              "Content-Disposition": `attachment; filename="orders-${job.id}.${csv ? "csv" : "pdf"}"`,
              "Cache-Control": "no-store",
            },
          });
        }
        if (job.kind === "grievance_export") return grievanceFile(context, job);
        if (job.kind === "report_export") return reportFile(context, REPORTS_KIT, job);
        const rows = world.audit
          .slice(0, job.total || 20)
          .map((row) => JSON.stringify(row))
          .join("\n");
        return new Response(`${rows}\n`, {
          headers: {
            "Content-Type": "application/x-ndjson",
            "Content-Disposition": `attachment; filename="audit-export-${job.id}.jsonl"`,
            "Cache-Control": "no-store",
          },
        });
      }
      return notFound();
    }

    case "saved-views": {
      const roles = who.breakGlass ? [] : [who.role];
      const visible = world.savedViews.filter((view) => view.owner === me || (view.role && roles.includes(view.role)));
      if (method === "GET" && !a)
        return paginate(
          context,
          visible.filter((view) => !query("list_key") || view.list_key === query("list_key")),
          50,
        );
      const role = text(body.role);
      if (role && !roles.includes(role)) return invalid({ role: ["Share only with a role you hold."] });
      if (method === "POST" && !a) {
        const name = text(body.name);
        if (!name) return invalid({ name: ["This field may not be blank."] });
        const view: S["SavedView"] = {
          id: nextId(world),
          owner: me,
          role,
          list_key: text(body.list_key),
          name,
          filters: body.filters ?? {},
          columns: body.columns ?? [],
          sort: body.sort ?? "",
          created: now(),
          modified: now(),
        };
        world.savedViews.push(view);
        return json(201, view);
      }
      const view = byId(
        world.savedViews.filter((row) => row.owner === me),
        a,
      );
      if (!view) return notFound();
      if (method === "GET") return json(200, view);
      if (method === "PATCH" || method === "PUT") {
        for (const key of ["name", "filters", "columns", "sort", "role"] as const)
          if (key in body) (view as Record<string, unknown>)[key] = body[key];
        view.modified = now();
        return json(200, view);
      }
      if (method === "DELETE") {
        world.savedViews = world.savedViews.filter((row) => row !== view);
        return noContent();
      }
      return notFound();
    }

    case "settings":
    case "flags": {
      if (area === "settings") {
        if (method === "GET" && !a) return json(200, world.settings);
        const setting = world.settings.find((row) => row.key === a);
        if (!setting) return json(404, { detail: "No such setting.", code: "not_found" });
        if (method === "GET") return json(200, world.settingHistory[setting.key] ?? []);
        if (method !== "PUT") return notFound();
        const reason = text(body.reason);
        if (!reason) return invalid({ reason: ["This field may not be blank."] });
        if (!("value" in body)) return invalid({ value: ["This field is required."] });
        const value = body.value;
        const kind = setting.kind;
        if (value !== null) {
          if (kind === "bool" && typeof value !== "boolean") return invalid({ value: ["true or false."] });
          if (Array.isArray(kind) && !kind.includes(value)) return invalid({ value: [`One of ${kind.join(", ")}.`] });
          if (kind === "str" && typeof value !== "string") return invalid({ value: ["Text."] });
        }
        const from = text(body.effective_from) || now();
        const change = { key: setting.key, value, effective_from: from, changed_by: me, reason, created: now() };
        (world.settingHistory[setting.key] ??= []).unshift(change);
        record(context, "setting.changed", {
          permission: setting.permission,
          ...target("staff.sitesetting", nextId(world), setting.key),
          reason,
          changes: { [setting.key]: [setting.value, value] },
        });
        if (Date.parse(from) > Date.now() + 1000) {
          setting.scheduled = [...(setting.scheduled ?? []), { value, effective_from: from }];
        } else {
          setting.value = value === null ? setting.environment : value;
          setting.source = value === null ? "environment" : "database";
          setting.effective_from = from;
          setting.changed_by = me;
          setting.reason = reason;
          if (setting.key.startsWith("MAINTENANCE_")) {
            const maintenance = world.system.maintenance as { on: boolean; banner: string };
            if (setting.key === "MAINTENANCE_MODE") maintenance.on = setting.value === true;
            else maintenance.banner = String(setting.value ?? "");
          }
        }
        return json(200, setting);
      }
      if (method === "GET" && !a) return json(200, world.flags);
      if (!/^[A-Z][A-Z0-9_]*$/.test(a ?? "")) return json(404, { detail: "A flag's key.", code: "not_found" });
      if (method === "GET") return json(200, world.flagHistory[a] ?? []);
      if (method !== "PUT") return notFound();
      const reason = text(body.reason);
      if (!reason) return invalid({ reason: ["This field may not be blank."] });
      const change = {
        key: a,
        value: body.value ?? null,
        effective_from: text(body.effective_from) || now(),
        changed_by: me,
        reason,
        created: now(),
      };
      (world.flagHistory[a] ??= []).unshift(change);
      const flag = world.flags.find((row) => row.key === a);
      record(context, "flag.changed", {
        ...target("staff.featureflag", nextId(world), a),
        reason,
        changes: { [a]: [flag?.value ?? null, change.value] },
      });
      if (flag) {
        // a known switch set to null goes back to the environment's value (staff/config.py KNOWN_FLAGS)
        const back = change.value === null && flag.environment !== null;
        Object.assign(flag, {
          value: back ? flag.environment : change.value,
          effective_from: change.effective_from,
          changed_by: me,
          reason,
          source: back ? "environment" : "database",
        });
      } else
        world.flags.push({
          key: a,
          value: change.value,
          effective_from: change.effective_from,
          changed_by: me,
          reason,
          label: "",
          group: "flags",
          environment: null,
          source: "database",
        });
      return json(200, change);
    }

    case "api-keys": {
      if (method === "GET" && !a) return paginate(context, world.apiKeys, 50);
      if (method === "POST" && !a) {
        const name = text(body.name);
        const scopes = Array.isArray(body.scopes) ? body.scopes.map(String) : [];
        const fields: Record<string, string[]> = {};
        if (!name) fields.name = ["This field may not be blank."];
        if (!scopes.length) fields.scopes = ["At least one permission."];
        const wrong = scopes.find((scope) => !scope.includes(".view_") || !can(scope));
        if (wrong) fields.scopes = [`${wrong}: keys hold catalogued view permissions only.`];
        const expires = text(body.expires_at) || new Date(Date.now() + 365 * 86_400_000).toISOString();
        if (Date.parse(expires) > Date.now() + 366 * 86_400_000) fields.expires_at = ["Within the next 12 months."];
        if (Object.keys(fields).length) return invalid(fields);
        const prefix = `elk_${Math.random().toString(36).slice(2, 6)}`;
        const key: S["ApiKey"] = {
          id: nextId(world),
          name,
          prefix,
          key: `${prefix}_${crypto.randomUUID().replace(/-/g, "")}`,
          scopes,
          sponsor: Number(body.sponsor) || me,
          created_by: me,
          created: now(),
          expires_at: expires,
          allowed_ips: Array.isArray(body.allowed_ips) ? body.allowed_ips : [],
          last_used_at: null,
          last_used_ip: null,
          revoked_at: null,
          revoked_by: null,
        };
        world.apiKeys.unshift({ ...key, key: null });
        record(context, "authn_token_created", {
          ...target("staff.apikey", key.id, `API key ${prefix}`),
          details: { name, scopes },
        });
        return json(201, key);
      }
      const key = byId(world.apiKeys, a);
      if (!key) return notFound();
      if (method === "GET") return json(200, key);
      if (method === "POST" && b === "revoke") {
        if (!key.revoked_at) {
          key.revoked_at = now();
          key.revoked_by = me;
          record(context, "authn_token_revoked", target("staff.apikey", key.id, `API key ${key.prefix}`));
        }
        return json(200, key);
      }
      return notFound();
    }

    case "people": {
      if (method === "GET" && !a) return paginate(context, world.people, 50);
      if (method === "GET" && a === "invites" && !b) return paginate(context, world.invites, 50);
      if (method === "POST" && a === "invite") {
        const email = text(body.email);
        const role = text(body.role);
        const fields: Record<string, string[]> = {};
        if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) fields.email = ["Enter a valid email address."];
        if (!STAFF_ROLES.includes(role)) fields.role = [`"${role}" is not a valid choice.`];
        if (!text(body.reason)) fields.reason = ["This field may not be blank."];
        if (Object.keys(fields).length) return invalid(fields);
        if (PRIVILEGED.has(role))
          return waiting(context, {
            action: "staff.invite",
            label: "Invite to the staff",
            ...target("staff.staffinvite", "", `Invitation as ${role}`),
            payload: { email: email.toLowerCase(), role },
            amount: null,
            reason: text(body.reason),
            rule: `${role} is a privileged role: a second person approves the invitation.`,
            checker: "staff.approve_role_change",
          });
        const invite: S["StaffInvite"] = {
          id: nextId(world),
          email: `${email.slice(0, 2)}•••@${email.split("@")[1]}`,
          role,
          invited_by: me,
          created: now(),
          expires_at: new Date(Date.now() + 72 * 3_600_000).toISOString(),
          accepted_at: null,
          accepted_by: null,
          revoked_at: null,
        };
        world.invites.unshift(invite);
        record(context, "staff.invite.executed", {
          ...target("staff.staffinvite", invite.id, `Invitation as ${role}`),
        });
        return json(201, invite);
      }
      if (method === "DELETE" && a === "invites" && b) {
        const invite = byId(world.invites, b);
        if (!invite) return notFound();
        if (!invite.revoked_at && !invite.accepted_at) invite.revoked_at = now();
        record(context, "staff.invite_revoked", target("staff.staffinvite", invite.id, `Invitation #${invite.id}`));
        return noContent();
      }
      const person = byId(world.people, a);
      if (!person) return notFound();
      const label = target("accounts.user", person.id, `User #${person.id}`);
      if (method === "GET" && !b) return json(200, person);
      if (person.roles.includes("OWNER") && who.role !== "OWNER" && !who.breakGlass)
        return refuse("staff.assign_role", "Only an owner changes an owner's access.");
      if (b === "roles" && method === "POST") {
        const role = text(body.role);
        if (!STAFF_ROLES.includes(role)) return invalid({ role: [`"${role}" is not a valid choice.`] });
        if (!text(body.reason)) return invalid({ reason: ["This field may not be blank."] });
        const held = [...person.roles.filter((name) => name !== role), role];
        const pair = CONFLICTS.find(([one, two]) => held.includes(one) && held.includes(two));
        if (pair)
          return invalid({ role: [`${pair[0]} and ${pair[1]} may not be held by one person (separation of duties).`] });
        if (person.id === me || PRIVILEGED.has(role))
          return waiting(context, {
            action: "staff.grant_role",
            label: "Give a role",
            ...label,
            payload: { user: person.id, role, expires_at: body.expires_at ?? null },
            amount: null,
            reason: text(body.reason),
            rule:
              person.id === me
                ? "A role for yourself: a second person approves it (just-in-time elevation)."
                : `${role} is a privileged role: a second person approves it.`,
            checker: "staff.approve_role_change",
          });
        person.roles = held.sort();
        person.grants = [
          ...person.grants.filter((grant) => grant.role !== role),
          { role, granted_by: me, reason: text(body.reason), created: now(), expires_at: body.expires_at ?? null },
        ];
        record(context, "staff.role_granted", {
          ...label,
          reason: text(body.reason),
          changes: { roles: [held.filter((name) => name !== role), person.roles] },
        });
        return json(200, person);
      }
      if (b === "roles" && method === "DELETE" && c) {
        if (!person.roles.includes(c))
          return json(404, { detail: "The person does not hold this role.", code: "not_found" });
        person.roles = person.roles.filter((name) => name !== c);
        person.grants = person.grants.filter((grant) => grant.role !== c);
        record(context, "staff.role_revoked", {
          ...label,
          reason: query("reason"),
          changes: { roles: [[...person.roles, c], person.roles] },
        });
        return json(200, person);
      }
      if (b === "scopes" && method === "POST") {
        const kind = text(body.kind) as S["ScopeKindEnum"];
        const value = text(body.value);
        if (!["subject", "board_class", "order_status", "warehouse", "school", "ticket_queue"].includes(kind))
          return invalid({ kind: [`"${kind}" is not a valid choice.`] });
        if (!value) return invalid({ value: ["This field may not be blank."] });
        const scope: S["Scope"] = {
          id: nextId(world),
          kind,
          value,
          granted_by: me,
          created: now(),
          expires_at: (body.expires_at as string) ?? null,
        };
        person.scopes.push(scope);
        record(context, "staff.scope_added", { ...label, details: { kind, value } });
        return json(201, scope);
      }
      if (b === "scopes" && method === "DELETE" && c) {
        if (!person.scopes.some((scope) => String(scope.id) === c)) return notFound();
        person.scopes = person.scopes.filter((scope) => String(scope.id) !== c);
        record(context, "staff.scope_removed", label);
        return noContent();
      }
      if (b === "end-sessions" && method === "POST") {
        record(context, "staff.sessions_ended", label);
        return json(200, { sessions: 2, tokens: 1 });
      }
      if (b === "reset-mfa" && method === "POST") {
        if (!text(body.reason)) return invalid({ reason: ["This field may not be blank."] });
        return waiting(context, {
          action: "user.reset_mfa",
          label: "Reset a second factor",
          ...label,
          payload: { user: person.id },
          amount: null,
          reason: text(body.reason),
          rule: "A second factor is reset only with a second person's approval.",
          checker: "staff.approve_role_change",
        });
      }
      if (b === "offboard" && method === "POST") {
        if (!text(body.reason)) return invalid({ reason: ["This field may not be blank."] });
        const roles = person.roles;
        person.is_active = false;
        person.roles = [];
        person.grants = [];
        person.scopes = [];
        record(context, "staff.offboarded", { ...label, reason: text(body.reason), details: { roles } });
        return json(200, { roles, scopes: 0, api_keys: 0, change_requests: 0, sessions: 1, tokens: 0 });
      }
      return notFound();
    }

    case "access-review":
      return json(
        200,
        world.people.map((person) => ({
          id: person.id,
          email: person.email,
          roles: person.roles,
          grants: person.grants,
          scopes: person.scopes.reduce<Record<string, string[]>>((map, scope) => {
            (map[scope.kind] ??= []).push(scope.value);
            return map;
          }, {}),
          last_login: person.last_login ?? null,
          dormant: !person.last_login || Date.now() - Date.parse(person.last_login) > 45 * 86_400_000,
          mfa: person.mfa,
          permissions: (ROLE_PERMISSIONS[person.roles[0] ?? ""] ?? []).length,
          unused: person.id === COLLEAGUES.auditor ? ["staff.export_auditlog"] : [],
          last_used: {},
        })),
      );

    case "users": {
      if (method === "GET" && !a) {
        const q = query("q").toLowerCase();
        const rows = world.users.filter((user) => {
          const contact = world.contacts[String(user.id)];
          const found =
            !q ||
            (q.includes("@")
              ? contact?.email === q
              : /^\+?\d[\d\s-]{6,}$/.test(q)
                ? [contact?.phone, contact?.login_phone].some(
                    (phone) => phone && phone.endsWith(q.replace(/\D/g, "").slice(-10)),
                  )
                : q.length >= 3 && user.full_name.toLowerCase().includes(q));
          return (
            found &&
            (!query("class_level") || String(user.class_level) === query("class_level")) &&
            (!query("is_active") ||
              (user.status !== "suspended" && user.status !== "erased") === bool(query("is_active")))
          );
        });
        // the list's fields only (CustomerSerializer); the record adds the rest
        const LIST = [
          "id",
          "email",
          "phone",
          "full_name",
          "class_level",
          "board",
          "district",
          "under_18",
          "status",
        ].concat(["consent", "email_verified", "login_phone_verified", "created", "last_login"]);
        return paginate(
          context,
          rows.map((user) => Object.fromEntries(LIST.map((field) => [field, user[field as keyof typeof user]]))),
          8,
        );
      }
      const user = byId(world.users, a);
      if (!user) return notFound();
      const label = target("accounts.user", user.id, `User #${user.id}`);
      if (method === "GET" && !b) {
        record(context, "sensitive_read", { ...label, details: { what: "record", child: user.under_18 } });
        return json(200, user);
      }
      if (method !== "POST") return notFound();
      const reason = text(body.reason);
      switch (b) {
        case "reveal": {
          const show = Array.isArray(body.show) ? body.show.map(String) : [];
          const fields: Record<string, string[]> = {};
          if (!show.length) fields.show = ["This list may not be empty."];
          if (reason.length < 5) fields.reason = ["Ensure this field has at least 5 characters."];
          if (Object.keys(fields).length) return invalid(fields);
          const recent = world.audit.filter(
            (event) =>
              event.action === "sensitive_read" &&
              (event.details as Body)?.what === "reveal" &&
              Date.now() - Date.parse(event.ts) < 600_000,
          );
          if (recent.length >= 5)
            return json(
              429,
              { detail: "Request was throttled. Expected available in 60 seconds.", code: "throttled" },
              { "Retry-After": "60" },
            );
          record(context, "sensitive_read", {
            ...label,
            permission: "staff.reveal_contact",
            reason,
            details: { what: "reveal", fields: show, child: user.under_18 },
          });
          const contact = world.contacts[String(user.id)] ?? {
            email: "",
            phone: "",
            login_phone: "",
            parent_contact: "",
          };
          return json(
            200,
            Object.fromEntries(show.map((field) => [field, (contact as Record<string, string>)[field] || null])),
          );
        }
        case "suspend":
        case "unsuspend":
          if (!reason) return invalid({ reason: ["This field may not be blank."] });
          user.status = b === "suspend" ? "suspended" : "active";
          record(context, b === "suspend" ? "user.suspended" : "user.unsuspended", { ...label, reason });
          return json(200, user);
        case "unlock":
          user.locked = false;
          record(context, "user.unlocked", label);
          return json(200, { attempts_cleared: 5 });
        case "resend-verification":
          if (user.consent !== "pending")
            return invalid({ non_field_errors: ["No parent's link waits for this account."] });
          record(context, "user.parent_link_sent", label);
          return json(200, { detail: "The parent's link to confirm is on its way." });
        case "end-sessions":
          user.sessions = [];
          record(context, "user.sessions_ended", label);
          return json(200, { sessions: 1, tokens: 0 });
        case "password-reset":
          record(context, "user.password_reset_sent", label);
          return json(200, { detail: "A link to set a new password went to the account's address." });
        case "reset-mfa":
          if (!reason) return invalid({ reason: ["This field may not be blank."] });
          return waiting(context, {
            action: "user.reset_mfa",
            label: "Reset a second factor",
            ...label,
            payload: { user: user.id },
            amount: null,
            reason,
            rule: "A second factor is reset only with a second person's approval.",
            checker: "staff.reset_user_mfa",
          });
        case "impersonate": {
          if (c === "end") {
            if (
              !world.impersonation ||
              world.impersonation.token !== text(body.token) ||
              world.impersonation.user !== user.id
            )
              return invalid({ token: ["Not a token of yours for this account."] });
            world.impersonation = null;
            record(context, "user.impersonation_ended", label);
            return noContent();
          }
          const fields: Record<string, string[]> = {};
          if (reason.length < 5) fields.reason = ["Ensure this field has at least 5 characters."];
          if (!text(body.ticket)) fields.ticket = ["This field may not be blank."];
          if (Object.keys(fields).length) return invalid(fields);
          if (user.under_18)
            return json(403, {
              detail: "Accounts of students under 18 are never impersonated.",
              code: "permission_denied",
            });
          if (user.status !== "active") return invalid({ non_field_errors: ["The account is suspended or erased."] });
          const until = new Date(Date.now() + 15 * 60_000).toISOString();
          const token = `mock-${crypto.randomUUID()}`;
          world.impersonation = { token, user: user.id, until };
          record(context, "user.impersonation_started", {
            ...label,
            reason,
            details: { ticket: body.ticket, expires_at: until },
          });
          return json(200, { token, expires_at: until });
        }
      }
      return notFound();
    }

    case "notes": {
      if (method === "GET") {
        const rows = world.notes.filter(
          (note) => note.target_type === query("target_type") && note.target_id === query("target_id"),
        );
        return json(200, rows); // not paged: a record's notes
      }
      if (method === "POST") {
        const note: Note = {
          id: nextId(world),
          target_type: text(body.target_type),
          target_id: text(body.target_id),
          author: me,
          body: text(body.body),
          created: now(),
        };
        if (!note.body) return invalid({ body: ["This field may not be blank."] });
        world.notes.unshift(note);
        record(context, "note.created", target(note.target_type, note.target_id, `Note #${note.id}`));
        return json(201, note);
      }
      return notFound();
    }

    case "data-requests": {
      const mask = (contact: string) =>
        contact.includes("@") ? `${contact.slice(0, 2)}•••@${contact.split("@")[1]}` : `••••••${contact.slice(-4)}`;
      if (method === "GET" && !a) {
        const late = (row: S["DataRequest"]) => row.status !== "closed" && Date.parse(row.due_at) < Date.now();
        const rows = world.dataRequests.filter(
          (row) =>
            (!query("status") || row.status === query("status")) &&
            (!query("kind") || row.kind === query("kind")) &&
            (!query("overdue") || late(row) === bool(query("overdue"))),
        );
        return paginate(
          context,
          rows.map((row) => ({ ...row, requester: mask(row.requester) })),
        );
      }
      if (method === "POST" && !a) {
        const fields: Record<string, string[]> = {};
        for (const name of ["kind", "channel", "requester", "summary"])
          if (!text(body[name])) fields[name] = ["This field is required."];
        if (Object.keys(fields).length) return invalid(fields);
        const received = text(body.received_at) || now();
        const start = Date.parse(received);
        const row: S["DataRequest"] = {
          id: nextId(world),
          kind: text(body.kind) as S["DataRequest"]["kind"],
          channel: text(body.channel) as S["DataRequest"]["channel"],
          user: body.user === null || body.user === undefined ? null : Number(body.user),
          requester: text(body.requester),
          summary: text(body.summary),
          identity_verified: false,
          identity_note: "",
          verified_by: null,
          verified_at: null,
          received_at: new Date(start).toISOString(),
          ack_due_at: new Date(start + 48 * 3_600_000).toISOString(),
          acknowledged_at: null,
          ack_overdue: false,
          due_at: new Date(start + 30 * 86_400_000).toISOString(),
          overdue: false,
          status: "new",
          assignee: null,
          notes: text(body.notes),
          details: {},
          // the model's blank outcome, which the schema's enum leaves out (an open request's, as Django sends it)
          outcome: "" as S["DataRequest"]["outcome"],
          response: "",
          closed_at: null,
          closed_by: null,
          created_by: me,
        };
        world.dataRequests.unshift(row);
        record(context, "data_request.created", {
          ...target("staff.datarequest", row.id, `Data request #${row.id}`),
          details: { kind: row.kind },
        });
        return json(201, row);
      }
      const row = byId(world.dataRequests, a);
      if (!row) return notFound();
      const label = target("staff.datarequest", row.id, `Data request #${row.id}`);
      if (method === "GET" && !b) return json(200, row);
      if (method === "GET" && b === "response")
        return json(200, {
          subject: `Your ${row.kind} request (#${row.id})`,
          body: `We received your request on ${row.received_at?.slice(0, 10)}. ...\n\nData Protection Officer: dpo@examleaf.in`,
        });
      if (method === "GET" && b === "erasure-report") {
        if (row.kind !== "erasure" || !row.user)
          return invalid({ non_field_errors: ["Only for an erasure request about an account."] });
        return json(200, erasureReportOf(world, row));
      }
      if (method === "PATCH" && !b) {
        for (const key of ["notes", "assignee", "summary", "details"] as const)
          if (key in body) (row as Record<string, unknown>)[key] = body[key];
        record(context, "data_request.updated", label);
        return json(200, row);
      }
      if (method !== "POST") return notFound();
      if (b === "acknowledge") {
        if (!row.acknowledged_at) {
          row.acknowledged_at = now();
          if (row.status === "new") row.status = "acknowledged";
          record(context, "data_request.acknowledged", label);
        }
        return json(200, row);
      }
      if (b === "verify-identity") {
        const note = text(body.note);
        if (!note) return invalid({ note: ["This field may not be blank."] });
        Object.assign(row, { identity_verified: true, identity_note: note, verified_by: me, verified_at: now() });
        record(context, "data_request.identity_verified", { ...label, reason: note });
        return json(200, row);
      }
      if (b === "close") {
        if (row.status === "closed") return invalid({ non_field_errors: ["Closed already."] });
        const outcome = text(body.outcome);
        if (!["done", "refused", "withdrawn"].includes(outcome))
          return invalid({ outcome: [`"${outcome}" is not a valid choice.`] });
        if (!text(body.response)) return invalid({ response: ["This field may not be blank."] });
        Object.assign(row, {
          status: "closed",
          outcome,
          response: text(body.response),
          closed_at: now(),
          closed_by: me,
        });
        row.acknowledged_at ??= row.closed_at;
        record(context, "data_request.closed", { ...label, details: { outcome } });
        return json(200, row);
      }
      if (b === "erase") {
        if (row.kind !== "erasure" || !row.user)
          return invalid({ non_field_errors: ["Only for an erasure request about an account."] });
        const report = erasureReportOf(world, row);
        if (!report.can_erase) return json(400, report);
        if (!text(body.reason)) return invalid({ reason: ["This field may not be blank."] });
        return waiting(context, {
          action: "user.erase",
          label: "Erase an account",
          ...target("accounts.user", row.user, `User #${row.user}`),
          payload: { user: row.user, data_request: row.id },
          amount: null,
          reason: text(body.reason),
          rule: "An erasure started by staff: a second person approves it.",
          checker: "staff.approve_erasure",
        });
      }
      if (b === "export") {
        if (row.kind !== "access" || !row.user)
          return invalid({ non_field_errors: ["Only for an access request about an account."] });
        if (!row.identity_verified) return invalid({ non_field_errors: ["Verify the requester's identity first."] });
        record(context, "data_request.exported", { ...label, details: { to: "the account's address" } });
        return json(202, { detail: "The data goes by email to the account's own address." });
      }
      return notFound();
    }

    case "incidents": {
      if (method === "GET" && !a) {
        const rows = world.incidents.filter(
          (row) =>
            (!query("open") || !row.closed_at === bool(query("open"))) &&
            (!query("kind") || row.kind === query("kind")),
        );
        return paginate(context, rows);
      }
      if (method === "POST" && !a) {
        const fields: Record<string, string[]> = {};
        if (!text(body.title)) fields.title = ["This field may not be blank."];
        if (!text(body.kind)) fields.kind = ["This field is required."];
        const detected = text(body.detected_at) || now();
        if (Date.parse(detected) > Date.now() + 60_000) fields.detected_at = ["Not in the future."];
        if (Object.keys(fields).length) return invalid(fields);
        const start = Date.parse(detected);
        const row: S["Incident"] = {
          id: nextId(world),
          title: text(body.title),
          kind: text(body.kind) as S["Incident"]["kind"],
          detected_at: new Date(start).toISOString(),
          noticed_by: me,
          description: text(body.description),
          systems: text(body.systems),
          data_categories: text(body.data_categories),
          people_affected: typeof body.people_affected === "number" ? body.people_affected : null,
          children_affected: body.children_affected === true,
          cert_in_due: new Date(start + 6 * 3_600_000).toISOString(),
          cert_in_overdue: false,
          cert_in_reported_at: null,
          cert_in_reference: "",
          board_due: new Date(start + 72 * 3_600_000).toISOString(),
          board_overdue: false,
          board_notified_at: null,
          board_report_at: null,
          board_reference: "",
          notice_text: "",
          notices_sent: 0,
          notices_sent_at: null,
          actions: "",
          root_cause: "",
          closed_at: null,
          closed_by: null,
          created: now(),
        };
        world.incidents.unshift(row);
        record(context, "incident.created", {
          ...target("staff.incident", row.id, `Incident #${row.id}`),
          details: { kind: row.kind },
        });
        return json(201, row);
      }
      const row = byId(world.incidents, a);
      if (!row) return notFound();
      const label = target("staff.incident", row.id, `Incident #${row.id}`);
      if (method === "GET") return json(200, row);
      if (method === "PATCH") {
        for (const [key, value] of Object.entries(body))
          if (key in row && key !== "id") (row as Record<string, unknown>)[key] = value;
        record(context, "incident.updated", label);
        return json(200, row);
      }
      if (method === "POST" && b === "close") {
        if (!row.closed_at) {
          row.closed_at = now();
          row.closed_by = me;
          record(context, "incident.closed", label);
        }
        return json(200, row);
      }
      return notFound();
    }

    case "processors": {
      if (method === "GET" && !a) return paginate(context, world.processors, 50);
      if (method === "POST" && !a) {
        const fields: Record<string, string[]> = {};
        for (const name of ["name", "purpose", "data_categories", "country"])
          if (!text(body[name])) fields[name] = ["This field may not be blank."];
        if (Object.keys(fields).length) return invalid(fields);
        const row: S["Processor"] = {
          id: nextId(world),
          name: text(body.name),
          purpose: text(body.purpose),
          data_categories: text(body.data_categories),
          country: text(body.country),
          contract_signed_on: text(body.contract_signed_on) || null,
          contract_ends_on: text(body.contract_ends_on) || null,
          active: body.active !== false,
          notes: text(body.notes),
        };
        world.processors.push(row);
        record(context, "processor.created", target("staff.processorrecord", row.id, row.name));
        return json(201, row);
      }
      return notFound();
    }

    case "tax": {
      // shop/staff_tax.py: the master, the products that disagree, the documents, table 13, the card, the calendar
      const tax = world.tax;
      const today = taxRules.dayOf(Date.now());
      const month = query("month");
      if (month && !taxRules.MONTH.test(month)) return invalid({ month: ["A month: YYYY-MM."] });
      if (a === "hsn") {
        if (method === "GET" && !b) {
          const q = query("q").trim().toLowerCase();
          const rows = tax.codes
            .filter(
              (code) =>
                (!q || code.code.startsWith(q) || code.description.toLowerCase().includes(q)) &&
                (!query("kind") || code.kind === query("kind")) &&
                (!query("taxability") || code.today?.taxability === query("taxability")),
            )
            .sort((x, y) => x.code.localeCompare(y.code));
          return paginate(context, rows.map(taxRules.codeRow), Number(query("page_size")) || 50);
        }
        if (method === "POST" && !b) {
          const code = text(body.code);
          const kind = text(body.kind);
          const first = (body.first_rate ?? {}) as Body;
          const fields: Record<string, unknown> = {};
          if (!/^\d{4}(\d{2}){0,2}$/.test(code)) fields.code = ["An HSN or SAC code has 4, 6 or 8 digits."];
          if (!["hsn", "sac"].includes(kind)) fields.kind = [`"${kind}" is not a valid choice.`];
          if (!text(body.description)) fields.description = ["This field may not be blank."];
          if (text(body.uqc) && !/^[A-Z]{2,3}$/.test(text(body.uqc))) fields.uqc = ["A unit code of GSTR-1: NOS, NA …"];
          const rateFields = taxRules.rateProblems(first);
          if (rateFields) fields.first_rate = rateFields;
          if (Object.keys(fields).length) return invalid(fields);
          if ((kind === "sac") !== code.startsWith("99"))
            return invalid({ code: ["A SAC code begins with 99, an HSN code never does."] });
          if (tax.codes.some((row) => row.code === code))
            return invalid({ code: [`${code} is on the master already.`] });
          const created: S["HsnCodeDetail"] = {
            code,
            kind: kind as S["HsnCodeDetail"]["kind"],
            description: text(body.description),
            uqc: text(body.uqc) || "NOS",
            today: null,
            next_change: null,
            products: 0,
            created: now(),
            rates: [taxRules.newRate(first, nextId(world), me)],
            linked: [],
          };
          taxRules.refreshCode(created, today);
          tax.codes.push(created);
          record(context, "tax.code_added", {
            ...target("shop.hsncode", code, code),
            permission: "shop.change_hsncode",
            details: { rate: created.rates[0].rate, effective_from: created.rates[0].effective_from },
          });
          return json(201, created);
        }
        const code = tax.codes.find((row) => row.code === b);
        if (!code) return notFound();
        if (method === "GET" && !c) return json(200, code);
        if (method === "POST" && c === "rates") {
          const latest = [...code.rates].sort((x, y) => y.effective_from.localeCompare(x.effective_from))[0];
          const problems = taxRules.rateProblems(body, latest);
          if (problems) return invalid(problems);
          const added = taxRules.newRate(body, nextId(world), me);
          code.rates.push(added);
          taxRules.refreshCode(code, today);
          record(context, "tax.rate_added", {
            ...target("shop.hsncode", code.code, code.code),
            permission: "shop.change_hsncode",
            details: { rate: added.id, effective_from: added.effective_from, notification: added.notification },
          });
          return json(201, code);
        }
        return notFound();
      }
      if (a === "problems" && method === "GET") return json(200, tax.problems);
      if (a === "documents") {
        if (method === "GET" && !b) {
          const kind = query("kind") || "invoice";
          if (!["invoice", "credit_note"].includes(kind)) return invalid({ kind: ["invoice or credit_note."] });
          const type = query("document_type");
          if (type && !["tax_invoice", "bill_of_supply", "invoice_cum_bill_of_supply"].includes(type))
            return invalid({ document_type: ["One of: tax_invoice, bill_of_supply, invoice_cum_bill_of_supply."] });
          const cancelled = query("cancelled");
          const search = query("search").trim().slice(0, 20).toUpperCase();
          // tax.parse_key: a whole key (EL-2026-27-00041) is its number; anything else, a number's beginning
          const key = /^([A-Z0-9]{1,2})-(\d{4}-\d{2})-(\d{5})$/.exec(search);
          const number = key ? `${key[1]}/${key[2]}/${key[3]}` : search;
          const rows = tax.documents.filter(
            (row) =>
              row.kind === kind &&
              row.test === bool(url.searchParams.get("test")) &&
              (!query("series") || row.series === query("series").toUpperCase().slice(0, 2)) &&
              (!type || row.document_type === type) &&
              (!month || row.date.startsWith(month)) &&
              (!query("financial_year") || row.financial_year === query("financial_year")) &&
              (!["true", "1", "false", "0"].includes(cancelled) ||
                Boolean(row.cancelled_at) === ["true", "1"].includes(cancelled)) &&
              (!search || row.number.startsWith(number) || row.order === search),
          );
          return paginate(context, rows.map(taxRules.documentRow));
        }
        const document = tax.documents.find((row) => row.key === b);
        if (!document) return notFound();
        const documentTarget = target(
          document.kind === "credit_note" ? "shop.creditnote" : "shop.invoice",
          document.id,
          document.number,
        );
        if (method === "GET" && !c) return json(200, document);
        if (method === "GET" && c === "pdf") {
          record(context, "sensitive_read", { ...documentTarget, details: { what: "pdf" } });
          const pdf =
            "%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n";
          return new Response(pdf, {
            headers: {
              "Content-Type": "application/pdf",
              "Content-Disposition": `attachment; filename="ExamLeaf-${document.key}.pdf"`,
              "Cache-Control": "no-store",
            },
          });
        }
        if (method === "POST" && c === "cancel") {
          const reason = text(body.reason);
          if (reason.length < 5) return invalid({ reason: ["Ensure this field has at least 5 characters."] });
          if (document.cancelled_at)
            return invalid({ non_field_errors: [`${document.number} was cancelled already.`] });
          const live = tax.documents.filter(
            (row) => row.kind === "credit_note" && row.against === document.number && !row.cancelled_at,
          );
          if (document.kind === "invoice" && live.length)
            return invalid({
              non_field_errors: [`Cancel its credit notes first: ${live.map((row) => row.number).join(", ")}.`],
            });
          Object.assign(document, { cancelled_at: now(), cancel_reason: reason, cancelled_by: me });
          record(context, "tax.document_cancelled", {
            ...documentTarget,
            permission: "staff.cancel_document",
            reason,
            details: { document_type: document.document_type, series: document.series },
          });
          return json(200, taxRules.documentRow(document));
        }
        return notFound();
      }
      if (a === "series" && method === "GET") {
        const year = query("financial_year");
        if (year && !/^\d{4}-\d{2}$/.test(year)) return invalid({ financial_year: ["A financial year: 2026-27."] });
        const shown = year || taxRules.yearOf(month ? `${month}-01` : today);
        return json(200, {
          financial_year: shown,
          month: month || null,
          series_from: taxRules.SERIES_FROM,
          prefixes: taxRules.PREFIXES,
          rows: taxRules.seriesOf(tax, shown, month || null),
        });
      }
      if (a === "thresholds" && method === "GET") return json(200, tax.card);
      if (a === "calendar" && method === "GET") {
        const shown = month || today.slice(0, 7);
        return json(200, {
          month: shown,
          qrmp: tax.qrmp,
          items: taxRules.calendarOf(shown, tax.qrmp, today),
          crossed: tax.card.rows.filter((row) => row.crossed),
        });
      }
      if (a === "gstr1" && method === "POST") {
        const asked = text(body.month);
        const months = Number(body.months ?? 1);
        if (!taxRules.MONTH.test(asked)) return invalid({ month: ["A month: YYYY-MM."] });
        if (`${asked}-01` > today) return invalid({ month: ["A month that has begun."] });
        if (months !== 1 && months !== 3)
          return invalid({ months: [`"${String(body.months)}" is not a valid choice.`] });
        if (months === 3 && !taxRules.endsQuarter(asked))
          return invalid({ months: ["A quarter ends with June, September, December or March."] });
        const covered = taxRules.monthsCovered(asked, months);
        const rows = tax.documents
          .filter((row) => !row.test && covered.includes(row.date.slice(0, 7)))
          .map((row) => row.number);
        const job = startJob(context, "gstr1_export", { month: asked, months }, rows);
        job.dry_run = body.dry_run === true;
        return json(202, visibleJob(context, job));
      }
      return notFound();
    }
    case "privacy":
      return privacyRoute(context);

    case "system": {
      if (method === "GET" && !a) return json(200, world.system);
      if (method === "POST" && a === "reconcile") {
        const order = text(body.order);
        if (!order) return invalid({ order: ["This field may not be blank."] });
        if (!PAID_ORDERS[order]) return json(404, { detail: "No such order.", code: "not_found" });
        record(context, "order.reconciled", {
          ...target("shop.order", PAID_ORDERS[order].id, order),
          details: { paid: true },
        });
        return json(200, { order, paid: true });
      }
      return notFound();
    }

    case "support":
      return supportRoute(context, KIT);

    case "finance":
      return financeRoute(context, KIT);
  }
  return notFound();
}

// ---- Legal and privacy (staff/privacy_api.py) ----

const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September"].concat([
  "October",
  "November",
  "December",
]);
/** India's date today, "2026-10-09". */
const todayInIndia = () => new Date(Date.now() + 5.5 * 3_600_000).toISOString().slice(0, 10);
/** privacy.day: "31 March 2035". */
const longDay = (iso: string) => {
  const [year, month, day] = iso.slice(0, 10).split("-").map(Number);
  return `${day} ${MONTH_NAMES[month - 1]} ${year}`;
};
const addDays = (iso: string, days: number) =>
  new Date(Date.parse(`${iso.slice(0, 10)}T00:00:00Z`) + days * 86_400_000).toISOString().slice(0, 10);
/** LegalHold.Reason's display words, as the dry run's lines use them. */
const HOLD_REASONS: Record<string, string> = {
  dispute: "a dispute",
  chargeback: "a chargeback",
  claim: "a legal claim",
  investigation: "an investigation",
  other: "another reason (in the note)",
};
const HOLD_TARGET_TYPES = ["shop.creditnote", "shop.invoice", "shop.order", "shop.payment", "shop.refund"].concat([
  "staff.datarequest",
]);
const ORDER_IDS: Record<string, number> = {
  ...Object.fromEntries(Object.entries(PAID_ORDERS).map(([number, order]) => [number, order.id])),
  "EL-2026-000098": 40,
};
const DARK_PATTERN_LABELS: Record<string, string> = {
  false_urgency: "False urgency",
  basket_sneaking: "Basket sneaking",
  confirm_shaming: "Confirm shaming",
  forced_action: "Forced action",
  subscription_trap: "Subscription trap",
  interface_interference: "Interface interference",
  bait_and_switch: "Bait and switch",
  drip_pricing: "Drip pricing",
  disguised_advertisement: "Disguised advertisement",
  nagging: "Nagging",
  trick_question: "Trick question",
  saas_billing: "SaaS billing",
  rogue_malware: "Rogue malware",
};
const FIRST_CERTIFICATE_YEAR = 2027;
const capitalised = (words: string) => words.charAt(0).toUpperCase() + words.slice(1);

/** privacy._keep: one line of what an erasure keeps. */
function keepLine(
  kind: S["ErasureKeep"]["kind"],
  part: string,
  what: string,
  count: number,
  why: string,
  until: string | null,
): S["ErasureKeep"] {
  return {
    kind,
    part,
    what,
    count,
    why,
    until,
    line: `${until ? `kept until ${longDay(until)}` : "kept"}: ${what}, ${why}`,
  };
}

/** The active holds on an account, and on the data requests about it (privacy.user_holds). */
function holdsOn(world: World, user: number) {
  const requests = new Set(world.dataRequests.filter((row) => row.user === user).map((row) => String(row.id)));
  return world.holds.filter(
    (hold) =>
      hold.active && (hold.user === user || (hold.target_type === "staff.datarequest" && requests.has(hold.target_id))),
  );
}

/** The dry run of an erasure (privacy.erasure_report): what goes, what the law keeps and until when, what stops it. */
function erasureReportOf(world: World, row: S["DataRequest"]): S["ErasureReport"] {
  const user = row.user ?? 0;
  const today = todayInIndia();
  const keep = [
    keepLine(
      "books",
      "books:2026-27",
      "1 invoice of 2026-27 with the order behind it",
      1,
      "for GST and the Companies Act (8 financial years, or 72 months after the year's annual return)",
      "2035-03-31",
    ),
    keepLine(
      "processing_logs",
      "audit:general",
      "4 events in the staff audit log",
      4,
      "naming the account by its number only (the audit log: two years)",
      addDays(today, 730),
    ),
    ...holdsOn(world, user).map((hold) =>
      keepLine(
        "legal_hold",
        `hold:${hold.id}`,
        hold.user ? "the account" : hold.target_label,
        1,
        `under a legal hold (${HOLD_REASONS[hold.reason]})${hold.until ? "" : ", until released"}`,
        hold.until,
      ),
    ),
    keepLine(
      "consent",
      "consents",
      "1 consent record, without the address hash",
      1,
      "proof of the notice and the consent (DPDP s.6(10); the limitation period of 3 years)",
      addDays(today, 3 * 365),
    ),
  ];
  const blocks: string[] = [];
  if (user === 7101) blocks.push("An order is on its way: wait until it is delivered, cancelled or refunded.");
  if (!row.identity_verified) blocks.push("The requester's identity is not verified yet.");
  for (const hold of world.holds.filter((each) => each.active && each.user === user)) {
    const until = hold.until ? `until ${longDay(hold.until)}` : "until it is released";
    blocks.push(`A legal hold (${HOLD_REASONS[hold.reason]}, hold ${hold.id}) keeps the account ${until}.`);
  }
  const child = world.users.find((each) => each.id === user)?.under_18;
  const deletion = world.deletions.find((each) => each.user === user);
  const details = (row.details ?? {}) as Body;
  if (child && !deletion?.parent_confirmed_at && !details.parent_confirmed)
    blocks.push(
      "A student under 18: the parent or guardian confirms the erasure first (through the link sent to them, or staff record their confirmation with the evidence).",
    );
  const told = world.processors.filter((each) => each.active && each.holds_personal_data).map((each) => each.name);
  return {
    erase: [
      { part: "profile", what: "name, email address, phones, date of birth, district, parent's details", count: 1 },
      { part: "addresses", what: "saved addresses", count: 2 },
      { part: "answer_sheets", what: "answer sheets and their photos", count: 3 },
    ],
    keep,
    blocks,
    can_erase: blocks.length === 0,
    notes: told.length ? [`Once it is done, the inbox asks to tell: ${told.join(", ")}.`] : [],
  };
}

/** The year whose dark-pattern certificate is due next (compliance.audit_year). */
function auditYear() {
  const [year, month] = todayInIndia().split("-").map(Number);
  return Math.max(year + (month === 12 ? 1 : 0), FIRST_CERTIFICATE_YEAR);
}

function darkPatternState(world: World): S["PrivacyDarkPatternState"] {
  const year = auditYear();
  const audit = world.darkPatternAudits.find((row) => row.year === year);
  const today = todayInIndia();
  const shown = world.darkPatternAudits
    .filter((row) => row.completed_at && row.effective_from && row.effective_from <= today)
    .sort((a, b) => (b.effective_from ?? "").localeCompare(a.effective_from ?? ""))[0];
  return {
    year,
    due: `${year}-01-01`,
    audit: audit?.id ?? null,
    state: audit ? (audit.completed_at ? "completed" : "draft") : "missing",
    completed_at: audit?.completed_at ?? null,
    effective_from: audit?.effective_from ?? null,
    certificate_year: shown?.year ?? null,
  };
}

/** GET privacy/cockpit/ (staff.compliance.cockpit) from the world. */
function cockpitOf(world: World): S["Cockpit"] {
  const now = Date.now();
  const clocks: S["Clock"][] = [];
  const counts: Record<string, { open: number; overdue: number }> = {};
  const add = (row: Omit<S["Clock"], "overdue"> & { done?: boolean }) => {
    const { done, ...clock } = row;
    const overdue = Boolean(clock.due_at && !done && Date.parse(clock.due_at) < now);
    clocks.push({ ...clock, overdue });
    const count = (counts[clock.kind] ??= { open: 0, overdue: 0 });
    count.open += 1;
    count.overdue += overdue ? 1 : 0;
  };
  for (const request of world.dataRequests.filter((row) => row.status !== "closed")) {
    const target = {
      target_type: "staff.datarequest",
      target_id: String(request.id),
      target_label: `DR-${request.id}`,
    };
    const kind = capitalised(request.kind);
    if (!request.acknowledged_at)
      add({
        kind: "data_request_ack",
        label: `Acknowledge DR-${request.id} (${kind})`,
        rule: "48 hours (the E-Commerce Rules)",
        started_at: request.received_at ?? null,
        due_at: request.ack_due_at,
        account: request.user ?? null,
        ...target,
      });
    add({
      kind: "data_request_answer",
      label: `Answer DR-${request.id} (${kind})`,
      rule: "a month (the SPDI and E-Commerce Rules); 90 days for the DPDP rights from 13 May 2027",
      started_at: request.received_at ?? null,
      due_at: request.due_at,
      account: request.user ?? null,
      ...target,
    });
  }
  for (const incident of world.incidents.filter((row) => !row.closed_at)) {
    const target = {
      target_type: "staff.incident",
      target_id: String(incident.id),
      target_label: `Incident ${incident.id}`,
    };
    if (!incident.cert_in_reported_at)
      add({
        kind: "incident_cert_in",
        label: `Report incident ${incident.id} to CERT-In`,
        rule: "6 hours (CERT-In)",
        started_at: incident.detected_at ?? null,
        due_at: incident.cert_in_due,
        account: null,
        ...target,
      });
    if (!incident.board_report_at)
      add({
        kind: "incident_board",
        label: `The Board's report on incident ${incident.id}`,
        rule: "72 hours (DPDP r.7(2))",
        started_at: incident.detected_at ?? null,
        due_at: incident.board_due,
        account: null,
        ...target,
      });
  }
  const mode = world.settings.find((row) => row.key === "PARENTAL_CONSENT_MODE")?.value;
  if (mode === "verified")
    for (const user of world.users.filter((row) => row.under_18 && row.consent === "pending"))
      add({
        kind: "parent_consent",
        label: `A parent's consent awaited: account #${user.id}`,
        rule: "until then the account reads, and saves nothing",
        started_at: user.created,
        due_at: null,
        account: user.id,
        target_type: "accounts.user",
        target_id: String(user.id),
        target_label: `Account #${user.id}`,
      });
  for (const deletion of world.deletions.filter((row) => !row.parent_confirmed_at))
    add({
      kind: "deletion_parent",
      label: `A child's deletion waits for the parent: account #${deletion.user}`,
      rule: "erased once the parent or guardian confirms",
      started_at: deletion.requested_at,
      due_at: deletion.due_at,
      account: deletion.user,
      target_type: "accounts.deletionrequest",
      target_id: String(deletion.id),
      target_label: `Deletion ${deletion.id}`,
    });
  const dark = darkPatternState(world);
  if (dark.state !== "completed")
    add({
      kind: "dark_pattern_audit",
      label: `The dark-pattern self-audit and certificate for ${dark.year}`,
      rule: "once a year, the certificate shown from 1 January (the E-Commerce Rules)",
      started_at: null,
      due_at: new Date(`${dark.due}T00:00:00+05:30`).toISOString(),
      account: null,
      target_type: "staff.darkpatternaudit",
      target_id: String(dark.audit ?? dark.year),
      target_label: `Self-audit ${dark.year}`,
    });
  else counts.dark_pattern_audit = { open: 0, overdue: 0 };
  const far = now + 36_500 * 86_400_000;
  clocks.sort(
    (a, b) =>
      Number(b.overdue) - Number(a.overdue) ||
      (a.due_at ? Date.parse(a.due_at) : far) - (b.due_at ? Date.parse(b.due_at) : far),
  );
  const today = todayInIndia();
  const year = auditYear();
  const [thisYear, thisMonth] = today.split("-").map(Number);
  const quarter = Math.floor((thisMonth - 1) / 3 + 1) % 4;
  const calendar: S["PrivacyCalendarItem"][] = [
    {
      date: "2027-01-01",
      title: "The E-Commerce Rules' amendments in force",
      detail:
        "A copy of the complaint as recorded, the 30-day prior price, the dark-pattern self-audit and its certificate, membership of the National Consumer Helpline.",
      state: "2027-01-01" > today ? "upcoming" : "in_force",
    },
    {
      date: "2027-05-13",
      title: "The DPDP Rules in force",
      detail:
        "Rights answered within 90 days, a year of logs and processing records, a parent's verifiable consent with the age check, the breach notices.",
      state: "2027-05-13" > today ? "upcoming" : "in_force",
    },
    {
      date: `${year}-01-01`,
      title: `The dark-pattern certificate for ${year} on the website`,
      detail: "The 13 patterns answered, the certificate completed and in force.",
      state: dark.state === "completed" ? "done" : `${year}-01-01` > today ? "upcoming" : "overdue",
    },
    {
      date: `${thisYear + (quarter === 0 ? 1 : 0)}-${String(quarter * 3 + 1).padStart(2, "0")}-01`,
      title: "The quarterly access review",
      detail: "Who holds which role and scope: People, Access review.",
      state: "upcoming",
    },
    { date: today, title: "The quarterly restore drill", detail: "None recorded in the panel yet.", state: "overdue" },
  ];
  if (`${year - 1}-12-01` > today)
    calendar.push({
      date: `${year - 1}-12-01`,
      title: `Start the dark-pattern self-audit for ${year}`,
      detail: "The inbox reminds those who keep the compliance duties.",
      state: "upcoming",
    });
  return {
    now: new Date(now).toISOString(),
    clocks,
    counts,
    support: { installed: false, error: "" },
    consents: world.consentsByVersion,
    dark_pattern: dark,
    calendar: calendar.sort((a, b) => a.date.localeCompare(b.date)),
    inbox: world.inbox.filter((item) => !item.done_at && ["processor_task", "compliance"].includes(item.kind)).length,
  };
}

/** A legal page's answer (staff/privacy_api.py policy_of). */
function policyOf(policy: MockPolicy, detail: boolean) {
  const today = todayInIndia();
  const known = policy.versions.map((version) => ({ ...version, upcoming: version.effective_from > today }));
  const current = known.filter((version) => !version.upcoming).at(-1)!;
  const versions = known.map(({ markdown, ...version }) => {
    void markdown;
    return { ...version, in_force: version.number === current.number };
  });
  const body = {
    id: policy.id,
    slug: policy.slug,
    title: current.title,
    version: current.version,
    number: current.number,
    effective_from: current.effective_from,
    summary: current.summary,
    updated: policy.updated,
    placeholders: policy.placeholders,
    scheduled: versions.find((version) => version.upcoming) ?? null,
  };
  return detail
    ? ({ ...body, versions: [...versions].reverse(), markdown: current.markdown } satisfies S["PolicyDetail"])
    : ({ ...body, versions: versions.filter((version) => !version.upcoming).length } satisfies S["Policy"]);
}

/** A version against the one before it (pages.versions.diff), line by line: what left, then what came. */
function policyDiffOf(policy: MockPolicy, number: number): S["PolicyDiff"] | null {
  const current = policy.versions.find((version) => version.number === number);
  if (!current) return null;
  const previous = policy.versions.find((version) => version.number === number - 1) ?? null;
  const before = previous ? previous.markdown.split("\n") : [];
  const after = current.markdown.split("\n");
  const removed = before.filter((line) => !after.includes(line));
  const added = after.filter((line) => !before.includes(line));
  const lines: S["PolicyDiffLine"][] = [
    { kind: "hunk", text: `@@ -1,${before.length} +1,${after.length} @@` },
    ...removed.map((text) => ({ kind: "removed" as const, text })),
    ...added.map((text) => ({ kind: "added" as const, text })),
  ];
  return {
    number,
    version: current.version,
    previous: previous?.number ?? null,
    effective_from: current.effective_from,
    summary: current.summary,
    title: current.title,
    title_changed: Boolean(previous && previous.title !== current.title),
    added: added.length,
    removed: removed.length,
    lines: added.length || removed.length ? lines : [],
  };
}

function privacyRoute(context: Context): Response | Promise<Response> {
  const { method, parts, world, url, body, who } = context;
  const [, a, b, c] = parts;
  const query = (name: string) => url.searchParams.get(name) ?? "";
  const me = who.id;
  const today = todayInIndia();

  switch (a) {
    case "cockpit":
      return method === "GET" ? json(200, cockpitOf(world)) : notFound();
    case "retention":
      return method === "GET" ? json(200, world.retention) : notFound();

    case "holds": {
      if (method === "GET" && !b) {
        const rows = world.holds
          .filter(
            (hold) =>
              (!query("active") || hold.active === bool(query("active"))) &&
              (!query("reason") || hold.reason === query("reason")) &&
              (!query("target_type") || hold.target_type === query("target_type")) &&
              (!query("user") || String(hold.user) === query("user")),
          )
          .sort((x, y) => Date.parse(y.created) - Date.parse(x.created));
        return paginate(context, rows);
      }
      if (method === "POST" && !b) {
        const user = body.user === null || body.user === undefined || body.user === "" ? null : Number(body.user);
        const targetType = text(body.target_type);
        const reason = text(body.reason);
        const until = text(body.until) || null;
        const fields: Record<string, string[]> = {};
        if (!HOLD_REASONS[reason]) fields.reason = [`"${reason}" is not a valid choice.`];
        if (targetType && !HOLD_TARGET_TYPES.includes(targetType))
          fields.target_type = [`"${targetType}" is not a valid choice.`];
        if (until && until < today) fields.until = ["Today or a later day."];
        if (Object.keys(fields).length) return invalid(fields);
        if (Boolean(user) === Boolean(targetType))
          return invalid({ non_field_errors: ["Hold an account, or one record: one of them."] });
        let label = "";
        let targetId = "";
        if (user) {
          if (!world.users.some((row) => row.id === user)) return invalid({ user: ["No such account."] });
          label = `Account #${user}`;
        } else {
          const given = text(body.target_id);
          const request = targetType === "staff.datarequest" ? byId(world.dataRequests, given) : undefined;
          const order = targetType === "shop.order" ? ORDER_IDS[given] : undefined;
          if (request) [targetId, label] = [String(request.id), `Data request DR-${request.id}`];
          else if (order) [targetId, label] = [String(order), `Order ${given}`];
          else return invalid({ target_id: ["No such record."] });
        }
        const hold: S["LegalHold"] = {
          id: nextId(world),
          user,
          target_type: user ? "" : targetType,
          target_id: targetId,
          target_label: label,
          reason: reason as S["LegalHold"]["reason"],
          note: text(body.note),
          until,
          active: true,
          created: now(),
          created_by: me,
          released_at: null,
          released_by: null,
          release_reason: "",
        };
        world.holds.unshift(hold);
        record(context, "legal_hold.created", {
          permission: "staff.manage_holds",
          ...target("accounts.legalhold", hold.id, `Legal hold ${hold.id}`),
          details: { reason: hold.reason, holds: label, until },
        });
        return json(201, hold);
      }
      const hold = byId(world.holds, b);
      if (!hold) return notFound();
      if (method === "GET" && !c) return json(200, hold);
      if (method === "POST" && c === "release") {
        const reason = text(body.reason);
        if (!reason) return invalid({ reason: ["This field may not be blank."] });
        if (hold.released_at) return invalid({ non_field_errors: ["Released already."] });
        Object.assign(hold, { active: false, released_at: now(), released_by: me, release_reason: reason });
        record(context, "legal_hold.released", {
          permission: "staff.manage_holds",
          ...target("accounts.legalhold", hold.id, `Legal hold ${hold.id}`),
          reason,
        });
        return json(200, hold);
      }
      return notFound();
    }

    case "nominees": {
      const user = byId(world.users, b);
      if (!user) return notFound();
      const kept = world.nominees[String(user.id)];
      const label = target("accounts.user", user.id, `User #${user.id}`);
      if (method === "GET" && !c) {
        if (kept) record(context, "sensitive_read", { ...label, details: { what: "nominee", child: user.under_18 } });
        return json(200, { user: user.id, nominee: kept?.nominee ?? null });
      }
      if (method === "POST" && c === "reveal") {
        const reason = text(body.reason);
        if (reason.length < 5) return invalid({ reason: ["Ensure this field has at least 5 characters."] });
        if (!kept) return json(404, { detail: "No nominee recorded.", code: "not_found" });
        record(context, "sensitive_read", {
          ...label,
          permission: "staff.reveal_contact",
          reason,
          details: { what: "reveal", fields: ["nominee_contact"], child: user.under_18 },
        });
        return json(200, { contact: kept.contact });
      }
      return notFound();
    }

    case "deletions": {
      const deletion = byId(world.deletions, b);
      if (!deletion || method !== "POST" || c !== "parent-confirmation") return notFound();
      const evidence = text(body.evidence_ref);
      if (!evidence) return invalid({ evidence_ref: ["This field may not be blank."] });
      if (deletion.parent_confirmed_at)
        return invalid({ non_field_errors: ["The parent's confirmation is recorded already."] });
      if (!world.users.find((row) => row.id === deletion.user)?.under_18)
        return invalid({ non_field_errors: ["Not a student under 18: no parent's confirmation is needed."] });
      deletion.parent_confirmed_at = now();
      record(context, "account.deletion_parent_confirmed", {
        ...target("accounts.user", deletion.user, `Account #${deletion.user}`),
        details: { deletion_request: deletion.id, through: "staff", evidence },
      });
      return json(200, { deletion: deletion.id, parent_confirmed_at: deletion.parent_confirmed_at });
    }

    case "policies": {
      if (method === "GET" && !b)
        return json(
          200,
          world.policies.map((policy) => policyOf(policy, false)),
        );
      const policy = world.policies.find((row) => row.slug === b);
      if (!policy) return notFound();
      if (method === "GET" && !c) return json(200, policyOf(policy, true));
      if (method === "GET" && c === "versions" && parts[5] === "diff") {
        const diff = policyDiffOf(policy, Number(parts[4]));
        return diff ? json(200, diff) : json(404, { detail: "No such version.", code: "not_found" });
      }
      if (method !== "POST") return notFound();
      const label = target("pages.page", policy.id, policy.slug);
      const current = policyOf(policy, true) as S["PolicyDetail"];
      const scheduled = policy.versions.find((version) => version.effective_from > today);
      if (c === "cancel-scheduled") {
        const reason = text(body.reason);
        if (!reason) return invalid({ reason: ["This field may not be blank."] });
        if (!scheduled) return invalid({ non_field_errors: ["No version waits for its day."] });
        policy.versions = policy.versions.filter((version) => version !== scheduled);
        record(context, "policy.schedule_cancelled", { ...label, reason, details: { version: scheduled.version } });
        return json(200, policyOf(policy, true));
      }
      if (c !== "publish") return notFound();
      const markdown = typeof body.markdown === "string" ? body.markdown : "";
      const summary = text(body.summary);
      const from = text(body.effective_from) || today;
      const title = text(body.title) || current.title;
      const fields: Record<string, string[]> = {};
      if (!markdown.trim()) fields.markdown = ["This field may not be blank."];
      if (!summary) fields.summary = ["This field may not be blank."];
      if (from < today) fields.effective_from = ["Today or a later day: a version is never backdated."];
      if (Object.keys(fields).length) return invalid(fields);
      if (markdown.trim() === current.markdown.trim() && title === current.title)
        return invalid({ markdown: ["This is the text in force: nothing to publish."] });
      const versionLabel = scheduled?.version ?? String(policy.versions.length + 1);
      policy.versions = policy.versions.filter((version) => version !== scheduled);
      policy.versions.push({
        number: policy.versions.length + 1,
        version: versionLabel,
        title,
        summary,
        effective_from: from,
        published_at: now(),
        published_by: me,
        markdown,
      });
      if (from === today) policy.updated = now();
      record(context, from === today ? "policy.published" : "policy.scheduled", {
        ...label,
        details: { version: versionLabel, effective_from: from, replaced: scheduled?.version ?? null },
      });
      return json(200, policyOf(policy, true));
    }

    case "disclosures": {
      const answer = () => json(200, { settings: world.disclosures, history: world.disclosureHistory.slice(0, 100) });
      if (method === "GET" && !b) return answer();
      if (method !== "PUT" || b) return notFound();
      const values = (body.values && typeof body.values === "object" ? body.values : {}) as Record<string, unknown>;
      const reason = text(body.reason);
      const fields: Record<string, string[]> = {};
      if (!reason) fields.reason = ["This field may not be blank."];
      for (const [key, value] of Object.entries(values)) {
        const row = world.disclosures.find((each) => each.key === key);
        const given = typeof value === "string" ? value.trim() : value;
        if (!row) fields[key] = ["Not one of the disclosures."];
        else if (Array.isArray(row.kind) && !row.kind.includes(given))
          fields[key] = [`One of: ${(row.kind as string[]).join(", ")}.`];
        else if (typeof given !== "string" || given.length > row.max_length)
          fields[key] = [`A text of ${row.max_length.toLocaleString("en-IN")} characters at most.`];
        else if (key === "NCH_SINCE" && given && !/^\d{4}-\d{2}-\d{2}$/.test(given))
          fields[key] = ["A date as YYYY-MM-DD, or empty."];
      }
      if (Object.keys(fields).length) return invalid(fields);
      const changes = Object.entries(values)
        .map(([key, value]) => [key, typeof value === "string" ? value.trim() : value] as const)
        .filter(([key, value]) => {
          const row = world.disclosures.find((each) => each.key === key)!;
          return value !== (row.source === "database" ? row.value : null);
        });
      if (!changes.length) return invalid({ non_field_errors: ["Nothing changed."] });
      for (const [key, value] of changes) {
        const row = world.disclosures.find((each) => each.key === key)!;
        const before = row.value;
        Object.assign(row, { value, source: "database", effective_from: now(), changed_by: me, reason });
        world.disclosureHistory.unshift({ key, value, effective_from: now(), changed_by: me, reason, created: now() });
        record(context, "setting.changed", {
          permission: "staff.manage_settings",
          ...target("staff.sitesetting", nextId(world), key),
          reason,
          changes: { [key]: [before, value] },
          details: { setting: key, group: "disclosures" },
        });
      }
      return answer();
    }

    case "dark-pattern-audits": {
      const audits = world.darkPatternAudits;
      if (method === "GET" && !b)
        return paginate(
          context,
          [...audits].sort((x, y) => y.year - x.year),
          50,
        );
      if (method === "POST" && !b) {
        const year = Number(body.year);
        const thisYear = Number(today.slice(0, 4));
        if (!Number.isInteger(year) || year < FIRST_CERTIFICATE_YEAR - 1 || year > thisYear + 1)
          return invalid({ year: ["From 2026 to next year."] });
        if (audits.some((row) => row.year === year))
          return invalid({ year: ["That year's self-audit exists: open it."] });
        const audit: S["DarkPatternAudit"] = {
          id: nextId(world),
          year,
          rows: Object.entries(DARK_PATTERN_LABELS).map(([pattern, label]) => ({
            pattern: pattern as S["AuditRow"]["pattern"],
            label,
            finding: "",
            fix: "",
          })),
          certificate_text: "",
          effective_from: null,
          completed_at: null,
          completed_by: null,
          created: now(),
          created_by: me,
          has_file: false,
        };
        audits.unshift(audit);
        record(context, "dark_pattern_audit.created", {
          ...target("staff.darkpatternaudit", audit.id, `Self-audit ${year}`),
          details: { year },
        });
        return json(201, audit);
      }
      const audit = byId(audits, b);
      if (!audit) return notFound();
      const label = target("staff.darkpatternaudit", audit.id, `Self-audit ${audit.year}`);
      if (method === "GET" && !c) return json(200, audit);
      if (method === "PATCH" && !c) {
        if (audit.completed_at)
          return invalid({ non_field_errors: ["Completed: a self-audit stays as it was signed. Start next year's."] });
        if ("rows" in body) {
          const rows = Array.isArray(body.rows) ? (body.rows as Body[]) : [];
          const patterns = rows.map((row) => text(row.pattern)).sort();
          if (patterns.join() !== Object.keys(DARK_PATTERN_LABELS).sort().join())
            return invalid({ rows: ["The 13 named patterns, each once."] });
          audit.rows = Object.keys(DARK_PATTERN_LABELS).map((pattern) => {
            const row = rows.find((each) => each.pattern === pattern)!;
            return {
              pattern: pattern as S["AuditRow"]["pattern"],
              label: DARK_PATTERN_LABELS[pattern],
              finding: text(row.finding),
              fix: text(row.fix),
            };
          });
        }
        if ("certificate_text" in body) audit.certificate_text = text(body.certificate_text);
        if ("effective_from" in body) audit.effective_from = text(body.effective_from) || null;
        record(context, "dark_pattern_audit.updated", { ...label, details: { fields: Object.keys(body).sort() } });
        return json(200, audit);
      }
      if (method === "POST" && c === "complete") {
        if (audit.completed_at) return invalid({ non_field_errors: ["Completed already."] });
        const missing = (audit.rows ?? []).filter((row) => !row.finding || !row.fix).map((row) => row.label);
        if (missing.length)
          return invalid({ rows: [`A finding and a fix for each pattern first: ${missing.join(", ")}.`] });
        if (!audit.certificate_text?.trim()) return invalid({ certificate_text: ["The certificate's text first."] });
        audit.completed_at = now();
        audit.completed_by = me;
        audit.effective_from = text(body.effective_from) || audit.effective_from || today;
        for (const item of world.inbox)
          if (item.kind === "compliance" && item.target_id === `year:${audit.year}` && !item.done_at)
            Object.assign(item, { done_at: now(), done_by: me });
        record(context, "dark_pattern_audit.completed", {
          ...label,
          details: { year: audit.year, effective_from: audit.effective_from },
        });
        return json(200, audit);
      }
      if (c === "file" && method === "GET") {
        if (!audit.has_file) return json(404, { detail: "No signed copy is kept.", code: "not_found" });
        record(context, "dark_pattern_audit.file_read", label);
        return new Response("%PDF-1.4\n% the mock's signed certificate\n", {
          status: 200,
          headers: {
            "Content-Type": "application/pdf",
            "Content-Disposition": `attachment; filename="certificate-${audit.year}.pdf"`,
            "Cache-Control": "no-store",
          },
        });
      }
      if (c === "file" && method === "POST") {
        const file = body.file;
        if (!(file instanceof File)) return invalid({ file: ["No file was submitted."] });
        if (file.size > 5 * 1024 * 1024) return invalid({ file: ["5 MB at most."] });
        if (!/\.(pdf|png|jpe?g)$/i.test(file.name)) return invalid({ file: ["A PDF, PNG or JPEG file."] });
        audit.has_file = true;
        record(context, "dark_pattern_audit.file_kept", label);
        return json(200, audit);
      }
      return notFound();
    }
  }
  return notFound();
}

function startJob(context: Context, kind: S["Job"]["kind"], params: unknown, rows: string[]): MockJob {
  const job: MockJob = {
    id: nextId(context.world),
    kind,
    state: "running",
    dry_run: false,
    params,
    done: 0,
    total: rows.length,
    errors: [],
    result: {},
    result_url: null,
    change_request_id: null,
    cancel_requested: false,
    started_by: context.who.id,
    created: now(),
    started_at: now(),
    finished_at: null,
    _ticks: 0,
    _rows: rows,
  };
  context.world.jobs.unshift(job);
  record(context, "job.requested", target("staff.job", job.id, `Job #${job.id}`));
  return job;
}

/** Each look at a running job moves it on by a third (Progress saves about once a second). */
function advance(job: MockJob): MockJob {
  if (job.state !== "running") return job;
  job._ticks += 1;
  job.done = Math.min(job.total, Math.ceil((job.total * job._ticks) / 3));
  if (job.done >= job.total) {
    job.state = "done";
    job.result = job._result ?? { rows: job.total };
    job.finished_at = now();
  }
  return job;
}

/** A job as the API answers it: result_url only for its starter, signed for 5 minutes. */
function visibleJob(context: Context, job: MockJob): S["Job"] {
  const { _ticks, _rows, _result, ...visible } = job;
  void _ticks;
  void _rows;
  const exported =
    ["audit_export", "orders_print", "orders_export", "grievance_export", "report_export"].includes(job.kind) ||
    (job.kind === "gstr1_export" && !job.dry_run);
  const file = job.state === "done" && exported && job.started_by === context.who.id;
  void _result;
  const token = `t-${job.id}-${Date.now() + 5 * 60_000}`;
  return { ...visible, result_url: file ? `${context.url.origin}${ROOT}jobs/${job.id}/result/?token=${token}` : null };
}

/** What the orders area (orders.ts) is lent: the request, the person and the mock's ways of answering. */
function ordersKit(context: Context): OrdersKit {
  const { world, who } = context;
  return {
    url: context.url,
    method: context.method,
    parts: context.parts,
    body: context.body,
    request: context.request,
    orders: world.orders,
    me: who.id,
    can: (permission) => who.breakGlass || context.permissions.includes(permission),
    limit: (name) => limitOf(context, name),
    nextId: () => nextId(world),
    json,
    notFound,
    invalid,
    record: (action, extra) => record(context, action, extra as Partial<S["AuditEvent"]>),
    waiting: (row) => waiting(context, row as Parameters<typeof waiting>[1]),
    executed: (row, result) => {
      const created = now();
      const done = {
        id: nextId(world),
        ...(row as Omit<S["ChangeRequest"], "id">),
        payload_sha256: payloadHash((row as Body).payload),
        maker: who.id,
        rule: "Within the maker's limits: no approval needed.",
        status: "executed",
        expires_at: new Date(Date.now() + 24 * 3_600_000).toISOString(),
        approvals: [],
        result,
        executed_by: who.id,
        executed_at: created,
        created,
        modified: created,
      } as S["ChangeRequest"];
      world.changeRequests.unshift(done);
      record(context, `${done.action}.executed`, {
        ...target(done.target_type ?? "", done.target_id ?? "", done.target_label ?? ""),
        change_request_id: done.id,
      });
      return done;
    },
    paginate: (rows, size) => paginate(context, rows, size),
    startJob: (kind, params, rows) => visibleJob(context, startJob(context, kind, params, rows)),
  };
}

/** What the content module's routes (content.ts) need of a request: its context and this file's helpers. */
function toolsOf(context: Context): Tools {
  return {
    method: context.method,
    parts: context.parts,
    body: context.body,
    url: context.url,
    me: context.who.id,
    can: (perm) => context.permissions.includes(perm),
    world: context.world.content,
    jobs: context.world.jobs,
    nextId: () => nextId(context.world),
    json: (status, body) => json(status, body),
    invalid,
    notFound,
    refuse: (perm) => refuse(perm),
    paginate: (rows) => paginate(context, rows),
    record: (action, extra) => record(context, action, extra),
    target,
  };
}
/** The helpers the support part (support-handler.ts) answers with. */
const KIT: Kit = {
  json,
  noContent,
  notFound,
  invalid,
  record,
  paginate,
  waiting,
  nextId,
  limitOf,
  startJob,
  visibleJob,
};

/** The helpers the Home and reports part (reports.ts) answers with. */
const REPORTS_KIT: ReportsKit = { json, invalid, notFound, refuse, record, startJob, visibleJob };

/** The mock's one entry: refuses outside `next dev` with STAFF_API_MOCK=1. */
export async function handleMock(request: Request): Promise<Response> {
  if (process.env.STAFF_API_MOCK !== "1") throw new Error(OFF);
  const url = new URL(request.url);
  const parts = url.pathname
    .replace(/^\/api\/(mock|v1)\/staff\//, "")
    .replace(/^\/api\/v1\/insights\//, "insights/") // the insights' own lists, which the reports draw
    .split("/")
    .filter(Boolean);
  const who = await signedIn(request);
  if (who instanceof Response) return who;
  if (request.method !== "GET" && request.method !== "HEAD" && !csrfOk(request))
    return json(403, { detail: "CSRF Failed: CSRF token missing or incorrect.", code: "permission_denied" });
  const world = (store.worlds[`${who.email}:${who.role}:${who.breakGlass}`] ??= createWorld({
    id: who.id,
    email: who.email,
    name: who.name,
    roles: who.breakGlass ? [] : [who.role],
  }));
  let body: Body = {};
  if ((request.headers.get("Content-Type") ?? "").startsWith("multipart/form-data")) {
    // a file sent with its form (the self-audit's signed certificate, a legal deposit's proof): the fields as sent,
    // a file as the File itself
    const form = await request.formData().catch(() => null);
    if (form) body = Object.fromEntries(form.entries());
  } else if (request.method !== "GET" && request.method !== "DELETE") {
    const parsed = (await request.json().catch(() => null)) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) body = parsed as Body;
  }
  const permissions = who.breakGlass ? EVERYTHING : (ROLE_PERMISSIONS[who.role] ?? []);
  return route({ request, url, parts, method: request.method, world, who, body, permissions });
}
