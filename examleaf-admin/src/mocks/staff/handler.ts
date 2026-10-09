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

import { COLLEAGUES, createWorld, type MockJob, type MockSchemas, payloadHash, type World } from "./fixtures";

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
  "shop.view_order",
  ...["staff.reveal_contact", "staff.unlock_user", "staff.resend_verification", "staff.end_user_sessions"],
  ...["staff.initiate_password_reset", "staff.reset_user_mfa", "staff.impersonate_user"],
  ...["staff.view_datarequest", "staff.handle_data_request", "staff.view_processorrecord"],
  ...["staff.refund_order", "staff.add_changerequest"],
];
const FINANCE = [
  ...PANEL,
  "accounts.view_user",
  "shop.view_order",
  ...["staff.refund_order", "staff.approve_refund", "staff.record_offline_payment", "staff.approve_payment"],
  ...["staff.approve_discount", "staff.add_changerequest"],
];
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
    ...["content.view_book", "content.view_paper", "learn.view_chapter"],
    ...["staff.view_parcels", "staff.book_parcel", "staff.view_insights", "erp.view_sync"],
  ]),
].sort();
const ROLE_PERMISSIONS: Record<string, string[]> = {
  OWNER: EVERYTHING,
  ADMIN: EVERYTHING.filter((perm) => !OWNER_ONLY.includes(perm) && !MONEY_APPROVALS.includes(perm)),
  FINANCE,
  SUPPORT,
  AUDITOR: [...EVERYTHING.filter((perm) => perm.split(".")[1].startsWith("view_")), "staff.export_auditlog"],
  CONTENT_EDITOR: [...PANEL, "content.view_book", "content.view_paper", "learn.view_chapter", "shop.view_product"],
  PACKER: ["staff.view_inbox", "staff.view_savedview", "shop.view_order", "staff.view_parcels"],
};
// accounts/roles.py ROLE_LIMITS (null: none)
const LIMITS: Record<string, Record<string, number | null>> = {
  OWNER: { refund_inr: null, offline_inr: null, discount_percent: null, export_rows: null, bulk_rows: null },
  ADMIN: { refund_inr: 10000, offline_inr: 50000, discount_percent: 50, export_rows: 10000, bulk_rows: 1000 },
  FINANCE: { refund_inr: 10000, offline_inr: 50000, discount_percent: 50, export_rows: 10000, bulk_rows: 500 },
  SUPPORT: { refund_inr: 1000, offline_inr: 0, discount_percent: 0, export_rows: 100, bulk_rows: 50 },
  AUDITOR: { refund_inr: 0, offline_inr: 0, discount_percent: 0, export_rows: 5000, bulk_rows: 0 },
};
// staff/catalogue.py: the high and critical permissions, which need a recent authentication
const RISKY = new Set([
  ...["staff.refund_order", "staff.approve_refund", "staff.approve_payment", "staff.approve_discount"],
  ...["staff.reveal_contact", "staff.suspend_user", "staff.reset_user_mfa", "staff.impersonate_user"],
  ...["staff.export_personal_data", "staff.approve_erasure", "staff.manage_incident", "staff.assign_role"],
  ...["staff.approve_role_change", "staff.manage_api_keys", "staff.export_auditlog", "staff.approve_export"],
  ...["staff.manage_settings", "staff.manage_flags", "staff.toggle_maintenance"],
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
    role_scopes: who.role === "PACKER" ? { PACKER: { order_status: ["paid", "packed", "shipped"] } } : {},
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
    case "jobs":
      return "staff.view_job";
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

    case "jobs": {
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
      if (flag)
        Object.assign(flag, { value: change.value, effective_from: change.effective_from, changed_by: me, reason });
      else
        world.flags.push({
          key: a,
          value: change.value,
          effective_from: change.effective_from,
          changed_by: me,
          reason,
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
        return json(200, erasureReportOf(row));
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
        const report = erasureReportOf(row);
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
  }
  return notFound();
}

/** The dry run of an erasure (privacy.erasure_report): an order on its way stops it. */
function erasureReportOf(row: S["DataRequest"]): S["ErasureReport"] {
  const blocks = row.user === 7101 ? ["Order EL-2026-000123 is on its way: erase once it is delivered."] : [];
  return {
    erase: [
      { what: "The account and its profile", count: 1 },
      { what: "Saved addresses", count: 2 },
      { what: "Attempts and marks", count: 12 },
    ],
    keep: [
      {
        what: "Invoices and credit notes",
        why: "Tax records: 8 financial years (Companies Act s.128).",
        until: "2035-03-31",
      },
      {
        what: "Sign-in and processing logs",
        why: "A year (DPDP Rules 8(3)).",
        until: new Date(Date.now() + 300 * 86_400_000).toISOString().slice(0, 10),
      },
    ],
    blocks,
    can_erase: blocks.length === 0 && row.identity_verified !== false,
    notes: row.identity_verified ? [] : ["The requester's identity is not checked yet."],
  };
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
    job.result = { rows: job.total };
    job.finished_at = now();
  }
  return job;
}

/** A job as the API answers it: result_url only for its starter, signed for 5 minutes. */
function visibleJob(context: Context, job: MockJob): S["Job"] {
  const { _ticks, _rows, ...visible } = job;
  void _ticks;
  void _rows;
  const file = job.state === "done" && job.kind === "audit_export" && job.started_by === context.who.id;
  const token = `t-${job.id}-${Date.now() + 5 * 60_000}`;
  return { ...visible, result_url: file ? `${context.url.origin}${ROOT}jobs/${job.id}/result/?token=${token}` : null };
}

/** The mock's one entry: refuses outside `next dev` with STAFF_API_MOCK=1. */
export async function handleMock(request: Request): Promise<Response> {
  if (process.env.STAFF_API_MOCK !== "1") throw new Error(OFF);
  const url = new URL(request.url);
  const parts = url.pathname
    .replace(/^\/api\/(mock|v1)\/staff\//, "")
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
  if (request.method !== "GET" && request.method !== "DELETE") {
    const parsed = (await request.json().catch(() => null)) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) body = parsed as Body;
  }
  const permissions = who.breakGlass ? EVERYTHING : (ROLE_PERMISSIONS[who.role] ?? []);
  return route({ request, url, parts, method: request.method, world, who, body, permissions });
}
