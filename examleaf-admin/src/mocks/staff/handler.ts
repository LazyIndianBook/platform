// THE STAFF API MOCK, FOR DEVELOPMENT AND TESTS ONLY. It answers the staff API's paths from the fixtures (fixtures.ts),
// for the browser through src/app/api/mock/staff/[...path]/route.ts and for server components in-process
// (src/lib/api/server.ts). It refuses to answer without STAFF_API_MOCK=1, which next.config.ts sets only under
// `next dev`, so a production build can never reach it.
//
// Signing in is real: every request asks the Django backend whose session cookie it carries who is signed in
// (GET /api/v1/me/: 401 signed out, 403 mfa_setup_required for staff without two-step sign-in, the roles otherwise),
// and "confirm it's you" reads allauth's own record of when the session last authenticated. Each staff member gets a
// world of their own (kept on globalThis, so the route handler and the server components share it), changed by what
// they do, and the mock writes audit events as the backend would. Dev-only cookies change what it answers:
// staff_mock_role=SUPPORT (another role's permissions), staff_mock_reauth_after=<epoch seconds> (an authentication
// before then counts as too old, so the next sensitive action asks to confirm it's you).
import { MODULES, P } from "@/lib/modules";

import { createWorld, type Json, payloadHash, type Row, type World } from "./fixtures";

const OFF = "The staff API mock answers only under `next dev` with STAFF_API_MOCK=1 (src/mocks/staff/).";
const API = (process.env.API_INTERNAL_BASE ?? "http://localhost:8100").replace(/\/$/, "");
const REAUTH_SECONDS = 300;
const STAFF_ROLES = new Set([
  "OWNER",
  "ADMIN",
  "FINANCE",
  "SALES",
  "PACKER",
  "SUPPORT",
  "CONTENT_EDITOR",
  "REVIEWER",
  "MARKETING",
  "AUDITOR",
]);
const PRIVILEGED = new Set(["OWNER", "ADMIN"]);
// the plan's idle limits (section 3.5): 15 minutes for OWNER, ADMIN, FINANCE and PACKER, 30 for the others
const SHORT_IDLE_ROLES = new Set(["OWNER", "ADMIN", "FINANCE", "PACKER"]);

const EVERYTHING = [...new Set([...Object.values(P), ...MODULES.flatMap((module) => module.any)])].sort();
const views = EVERYTHING.filter((permission) => /\.view_/.test(permission));
const ROLE_PERMISSIONS: Record<string, string[]> = {
  OWNER: EVERYTHING,
  ADMIN: EVERYTHING,
  AUDITOR: [...views, P.auditExport],
  SUPPORT: [
    P.inboxView,
    P.inboxChange,
    P.approvalsView,
    P.usersView,
    P.usersReveal,
    P.usersUnlock,
    P.usersResendVerification,
    P.usersEndSessions,
    P.usersPasswordReset,
    P.usersResetMfa,
    P.usersImpersonate,
    P.requestsView,
    P.requestsAdd,
    P.requestsChange,
    "shop.view_order",
    "support.view_ticket",
    "accounts.view_teacherprofile",
  ],
  FINANCE: [
    P.inboxView,
    P.inboxChange,
    P.approvalsView,
    P.approvalsDecide,
    P.approvalsExecute,
    P.auditView,
    P.usersView,
    "shop.view_order",
    "erp.view_finance",
    "erp.view_tax",
  ],
  CONTENT_EDITOR: [P.inboxView, P.inboxChange, "content.view_book", "content.view_paper", "learn.view_chapter"],
  SALES: [
    P.inboxView,
    P.inboxChange,
    P.usersView,
    "shop.view_order",
    "shop.view_product",
    "shop.view_coupon",
    "erp.view_crm",
    "partners.view_schoolcode",
  ],
};

type Store = { worlds: Record<string, World> };
const store: Store = ((globalThis as { __examleafStaffMock?: Store }).__examleafStaffMock ??= { worlds: {} });

type Who = { id: number; email: string; name: string; role: string };
type Context = {
  request: Request;
  url: URL;
  parts: string[];
  method: string;
  world: World;
  who: Who;
  body: Record<string, Json>;
};

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store", ...headers },
  });
const noContent = () => new Response(null, { status: 204, headers: { "Cache-Control": "no-store" } });
const notFound = () => json(404, { detail: "Not found." });
const invalid = (fields: Record<string, string[]>) => json(400, fields);

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
  const body = (await response.json().catch(() => null)) as Record<string, Json> | null;
  if (response.status === 401 || response.status === 403) return json(response.status, body ?? { detail: "" });
  if (!response.ok || !body) return json(502, { detail: "The Django backend's answer was not understood." });
  const roles = Array.isArray(body.roles) ? body.roles.map(String) : [];
  const asked = cookie(request, "staff_mock_role");
  const role = asked && ROLE_PERMISSIONS[asked] ? asked : (roles.find((name) => STAFF_ROLES.has(name)) ?? "");
  if (!role) return json(403, { detail: "This account is not a member of staff.", code: "permission_denied" });
  return { id: Number(body.id), email: String(body.email), name: String(body.full_name ?? body.email), role };
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

const REAUTH = {
  detail: "Confirm it's you to do this.",
  code: "reauth_required",
  flows: [{ id: "reauthenticate" }, { id: "mfa_reauthenticate", types: ["totp"] }],
};

/** Django's double-submit CSRF check: the X-CSRFToken header must match the csrftoken cookie. */
function csrfOk(request: Request): boolean {
  const token = cookie(request, "csrftoken");
  return Boolean(token) && request.headers.get("X-CSRFToken") === token;
}

function can(context: Context, permission: string): boolean {
  return (ROLE_PERMISSIONS[context.who.role] ?? []).includes(permission);
}
const refuse = () => json(403, { detail: "Your role does not allow this.", code: "permission_denied" });

function paginate(context: Context, rows: Row[], size = 10): Response {
  const offset = Number(Buffer.from(context.url.searchParams.get("cursor") ?? "", "base64url").toString() || 0) || 0;
  const link = (at: number) => {
    const next = new URL(context.url);
    next.searchParams.set("cursor", Buffer.from(String(at)).toString("base64url"));
    return next.toString();
  };
  return json(200, {
    results: rows.slice(offset, offset + size),
    next: offset + size < rows.length ? link(offset + size) : null,
    previous: offset > 0 ? link(Math.max(0, offset - size)) : null,
  });
}

const now = () => new Date().toISOString();
const me = (context: Context) => ({ id: context.who.id, email: context.who.email, name: context.who.name });
const nextId = (world: World) => ++world.seq;

function record(context: Context, action: string, target: Row | null, extra: Partial<Row> = {}) {
  const id = nextId(context.world);
  context.world.audit.unshift({
    id,
    ts: now(),
    actor: { ...me(context), type: "staff" },
    on_behalf_of: null,
    action,
    target,
    outcome: "success",
    reason: null,
    request_id: `req-${id.toString(16)}`,
    ip: "127.0.0.1",
    changes: {},
    hash: payloadHash({ id, action }),
    ...extra,
  });
}

function changeRequestFor(context: Context, action: string, target: Row, payload: Json, reason: string): Row {
  const row: Row = {
    id: nextId(context.world),
    action,
    target,
    payload,
    payload_sha256: payloadHash(payload),
    amount: null,
    maker: me(context),
    reason,
    state: "pending",
    approvals: [],
    created_at: now(),
    expires_at: new Date(Date.now() + 24 * 3_600_000).toISOString(),
    result: null,
  };
  context.world.changeRequests.unshift(row);
  record(
    context,
    "change_request.create",
    { type: "change_request", id: row.id, label: `Change request ${row.id}` },
    { reason },
  );
  return row;
}

const text = (value: Json | undefined) => (typeof value === "string" ? value.trim() : "");
const matches = (row: Row, query: string) => JSON.stringify(row).toLowerCase().includes(query.toLowerCase());
const byId = (rows: Row[], id: string) => rows.find((row) => String(row.id) === id);

function session(context: Context, { first, last }: { first: number; last: number }): Response {
  const { world, who } = context;
  const permissions = [...(ROLE_PERMISSIONS[who.role] ?? [])].sort();
  return json(200, {
    user: me(context),
    roles: [{ name: who.role, expires_at: null }],
    permissions,
    scopes: { subject: [], board_class: [], order_status: [], warehouse: [], school: [], ticket_queue: [] },
    limits: { refund_inr: 2000, discount_percent: 20, export_rows: 5000, bulk_rows: 100 },
    // the mock's world is test data: the console shows its TEST band
    flags: {
      ...Object.fromEntries(world.flags.map((flag) => [String(flag.key), flag.value === true])),
      test_mode: true,
    },
    reauth_valid_until: last ? new Date((last + REAUTH_SECONDS) * 1000).toISOString() : null,
    idle_timeout_s: SHORT_IDLE_ROLES.has(who.role) ? 900 : 1800,
    absolute_expires_at: first ? new Date((first + 8 * 3600) * 1000).toISOString() : null,
    impersonating:
      world.impersonating && new Date(String(world.impersonating.until)).getTime() > Date.now()
        ? world.impersonating
        : null,
    manifest_version: payloadHash(permissions).slice(0, 12),
  });
}

async function route(context: Context): Promise<Response> {
  const { method, parts, world, url, body } = context;
  const [area, id, verb, extra] = parts;
  const query = (name: string) => url.searchParams.get(name) ?? "";

  if (area === "session" && method === "GET") return session(context, await authenticated(context.request));

  // a sensitive action needs a recent authentication (allauth's reauthenticate flows), as the backend asks
  const sensitive =
    (area === "change-requests" && (verb === "approve" || verb === "execute")) ||
    (area === "users" && ["reveal", "impersonate", "reset-mfa"].includes(verb ?? "")) ||
    (area === "people" && ["roles", "scopes", "offboard"].includes(verb ?? "")) ||
    (area === "api-keys" && method === "POST") ||
    ((area === "settings" || area === "flags") && method === "PUT") ||
    (area === "system" && id === "maintenance") ||
    (area === "audit" && id === "export");
  if (sensitive && !(await recentlyAuthenticated(context.request))) return json(403, REAUTH);

  switch (area) {
    case "inbox": {
      if (!can(context, P.inboxView)) return refuse();
      if (method === "GET" && !id) {
        const state = query("state") || "open";
        const rows = world.inbox.filter((item) => {
          const snoozed = item.snoozed_until && new Date(String(item.snoozed_until)).getTime() > Date.now();
          const itemState = item.done_at ? "done" : snoozed ? "snoozed" : "open";
          const mine = (item.assignee as Row | null)?.id === context.who.id;
          return (
            itemState === state &&
            (!query("kind") || item.kind === query("kind")) &&
            (query("assignee") !== "me" || mine)
          );
        });
        return paginate(context, rows);
      }
      const item = id ? byId(world.inbox, id) : undefined;
      if (!item) return notFound();
      if (!can(context, P.inboxChange)) return refuse();
      if (method === "POST" && verb === "done") {
        item.done_at = now();
        return json(200, item);
      }
      if (method === "POST" && verb === "snooze") {
        const until = text(body.until);
        if (!until || Number.isNaN(Date.parse(until))) return invalid({ until: ["Choose when it comes back."] });
        if (Date.parse(until) <= Date.now()) return invalid({ until: ["Choose a time in the future."] });
        item.snoozed_until = until;
        return json(200, item);
      }
      if (method === "POST" && verb === "assign") {
        const person = world.people.find((row) => String(row.id) === String(body.user_id));
        if (!person) return invalid({ user_id: ["No staff member has this id."] });
        item.assignee = { id: person.id, email: person.email, name: person.name };
        return json(200, item);
      }
      return notFound();
    }

    case "audit": {
      if (!can(context, P.auditView)) return refuse();
      if (method === "POST" && id === "export") {
        if (!can(context, P.auditExport)) return refuse();
        const from = text(body.from);
        const to = text(body.to);
        if (!from || !to)
          return invalid({
            ...(from ? {} : { from: ["Choose the first day."] }),
            ...(to ? {} : { to: ["Choose the last day."] }),
          });
        record(context, "audit.export", null, { reason: `${from} to ${to}` });
        return json(202, {
          job_id: startJob(
            context,
            "audit.export",
            world.audit.map((row) => String(row.id)),
          ),
        });
      }
      if (method !== "GET") return notFound();
      const rows = world.audit.filter((event) => {
        const actor = event.actor as Row;
        const target = event.target as Row | null;
        const ts = Date.parse(String(event.ts));
        return (
          (!query("q") || matches(event, query("q"))) &&
          (!query("actor") || String(actor.email ?? "").includes(query("actor"))) &&
          (!query("action") || String(event.action).startsWith(query("action"))) &&
          (!query("target_type") || target?.type === query("target_type")) &&
          (!query("target_id") || String(target?.id ?? "") === query("target_id")) &&
          (!query("from") || ts >= Date.parse(`${query("from")}T00:00:00+05:30`)) &&
          (!query("to") || ts <= Date.parse(`${query("to")}T23:59:59+05:30`))
        );
      });
      return paginate(context, rows, 15);
    }

    case "change-requests": {
      if (!can(context, P.approvalsView)) return refuse();
      if (method === "GET" && !id) {
        const state = query("state");
        return paginate(
          context,
          world.changeRequests.filter((row) => !state || row.state === state),
        );
      }
      const row = id ? byId(world.changeRequests, id) : undefined;
      if (!row) return notFound();
      if (method === "GET" && !verb) return json(200, row);
      const comment = text(body.comment);
      if (verb === "approve" || verb === "reject") {
        if (!can(context, P.approvalsDecide)) return refuse();
        if ((row.maker as Row).id === context.who.id)
          return json(403, {
            detail: "You asked for this change, so someone else must decide.",
            code: "permission_denied",
          });
        if (row.state !== "pending") return json(409, { detail: "This request was decided already." });
        if (verb === "reject" && !comment) return invalid({ comment: ["Say why it is rejected."] });
        row.state = verb === "approve" ? "approved" : "rejected";
        (row.approvals as Row[]).push({ user: me(context), decision: verb, comment, at: now() });
        record(
          context,
          `change_request.${verb}`,
          { type: "change_request", id: row.id, label: `Change request ${row.id}` },
          { reason: comment || null },
        );
        return json(200, row);
      }
      if (verb === "execute") {
        if (!can(context, P.approvalsExecute)) return refuse();
        if (row.state !== "approved") return json(409, { detail: "Only an approved request can be carried out." });
        row.state = "executed";
        row.result = { status: "done", at: now() };
        record(context, String(row.action), row.target as Row, { reason: `Change request ${row.id}` });
        return json(200, row);
      }
      return notFound();
    }

    case "saved-views": {
      if (method === "GET" && !id) {
        const key = query("list_key");
        // the person's own views (the fixtures' count as theirs) and those shared with their role
        const visible = (view: Row) =>
          !("_owner" in view) || view._owner === context.who.id || view.shared_with_role === context.who.role;
        return json(
          200,
          world.savedViews.filter((view) => (!key || view.list_key === key) && visible(view)),
        );
      }
      if (method === "POST" && !id) {
        const name = text(body.name);
        if (!name) return invalid({ name: ["Name the view."] });
        const view: Row = {
          id: nextId(world),
          list_key: text(body.list_key),
          name,
          filters: (body.filters as Row) ?? {},
          columns: (body.columns as Json[]) ?? [],
          sort: text(body.sort),
          shared_with_role: text(body.shared_with_role) || null,
          _owner: context.who.id,
        };
        world.savedViews.push(view);
        return json(201, view);
      }
      const view = id ? byId(world.savedViews, id) : undefined;
      if (!view) return notFound();
      if (method === "PATCH") {
        for (const key of ["name", "filters", "columns", "sort", "shared_with_role"])
          if (key in body) view[key] = body[key];
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
      const viewing = area === "settings" ? P.settingsView : P.flagsView;
      const changing = area === "settings" ? P.settingsChange : P.flagsChange;
      if (!can(context, viewing)) return refuse();
      const rows = area === "settings" ? world.settings : world.flags;
      if (method === "GET" && !id) return json(200, rows);
      const row = rows.find((entry) => entry.key === decodeURIComponent(id ?? ""));
      if (!row) return notFound();
      if (method !== "PUT") return notFound();
      if (!can(context, changing)) return refuse();
      if (row.source === "env") return json(409, { detail: "This value is set in the server's environment." });
      const reason = text(body.reason);
      if (!reason) return invalid({ reason: ["Give a reason: it is saved in the audit trail."] });
      if (!("value" in body)) return invalid({ value: ["Give the new value."] });
      const effective = text(body.effective_from) || null;
      const before = row.value;
      row.history = [
        { value: body.value, changed_by: me(context), reason, at: now(), effective_from: effective },
        ...(row.history as Row[]),
      ];
      row.value = body.value;
      row.changed_by = me(context);
      row.reason = reason;
      row.effective_from = effective;
      record(
        context,
        `${area}.change`,
        { type: area === "settings" ? "setting" : "flag", id: row.key, label: row.key },
        { reason, changes: { value: [before, body.value] } },
      );
      return json(200, row);
    }

    case "api-keys": {
      if (!can(context, P.apiKeysView)) return refuse();
      if (method === "GET" && !id) return json(200, world.apiKeys);
      if (method === "POST" && !id) {
        if (!can(context, P.apiKeysAdd)) return refuse();
        const name = text(body.name);
        const expires = text(body.expires_at);
        const scopes = Array.isArray(body.scopes) ? body.scopes.map(String).filter(Boolean) : [];
        const fields: Record<string, string[]> = {};
        if (!name) fields.name = ["Name the key."];
        if (!scopes.length) fields.scopes = ["Give at least one scope."];
        if (!expires || Number.isNaN(Date.parse(expires))) fields.expires_at = ["Choose when it ends."];
        else if (Date.parse(expires) > Date.now() + 366 * 86_400_000)
          fields.expires_at = ["At most 12 months from today."];
        if (Object.keys(fields).length) return invalid(fields);
        const key: Row = {
          id: nextId(world),
          name,
          prefix: `el_live_${Math.random().toString(36).slice(2, 6)}`,
          scopes,
          created_at: now(),
          expires_at: expires,
          last_used_at: null,
          last_ip: null,
          sponsor: me(context),
          revoked_at: null,
        };
        world.apiKeys.unshift(key);
        record(context, "api_key.create", { type: "api_key", id: key.id, label: name });
        return json(201, { ...key, secret: `${key.prefix}_${crypto.randomUUID().replace(/-/g, "")}` });
      }
      const key = id ? byId(world.apiKeys, id) : undefined;
      if (!key) return notFound();
      if (method === "POST" && verb === "revoke") {
        if (!can(context, P.apiKeysRevoke)) return refuse();
        key.revoked_at = now();
        record(context, "api_key.revoke", { type: "api_key", id: key.id, label: key.name });
        return noContent();
      }
      return notFound();
    }

    case "people": {
      if (!can(context, P.peopleView)) return refuse();
      if (method === "GET" && !id) {
        const q = query("q");
        return paginate(
          context,
          world.people.filter((row) => !q || matches(row, q)),
        );
      }
      if (method === "POST" && id === "invite") {
        if (!can(context, P.peopleInvite)) return refuse();
        const email = text(body.email);
        const role = text(body.role);
        const fields: Record<string, string[]> = {};
        if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) fields.email = ["Enter a work email address."];
        else if (world.people.some((row) => row.email === email)) fields.email = ["This person is staff already."];
        if (!STAFF_ROLES.has(role)) fields.role = ["Choose a role."];
        if (Object.keys(fields).length) return invalid(fields);
        if (PRIVILEGED.has(role)) {
          const asked = changeRequestFor(
            context,
            "staff.invite",
            { type: "staff", id: email, label: email },
            { email, role },
            `Invite ${email} as ${role}.`,
          );
          return json(202, asked);
        }
        const person: Row = {
          id: nextId(world),
          email,
          name: "",
          roles: [{ name: role, expires_at: null, granted_by: me(context) }],
          scopes: [],
          mfa: false,
          last_login: null,
          sessions: 0,
          status: "invited",
        };
        world.people.push(person);
        record(
          context,
          "staff.invite",
          { type: "staff", id: person.id, label: email },
          { changes: { roles: [[], [role]] } },
        );
        return json(201, person);
      }
      const person = id ? byId(world.people, id) : undefined;
      if (!person) return notFound();
      const label = { type: "staff", id: person.id, label: String(person.name || person.email) };
      if (method === "GET" && !verb) return json(200, person);
      if (verb === "roles") {
        if (!can(context, P.peopleRoles)) return refuse();
        const roles = person.roles as Row[];
        if (method === "POST") {
          const role = text(body.role);
          const reason = text(body.reason);
          const fields: Record<string, string[]> = {};
          if (!STAFF_ROLES.has(role)) fields.role = ["Choose a role."];
          if (!reason) fields.reason = ["Give a reason: it is saved in the audit trail."];
          if (Object.keys(fields).length) return invalid(fields);
          if (person.id === context.who.id)
            return json(403, { detail: "No one grants a role to themselves.", code: "permission_denied" });
          if (PRIVILEGED.has(role))
            return json(202, changeRequestFor(context, "staff.grant_role", label, { user: person.id, role }, reason));
          const before = roles.map((entry) => entry.name);
          person.roles = [
            ...roles.filter((entry) => entry.name !== role),
            { name: role, expires_at: text(body.expires_at) || null, granted_by: me(context) },
          ];
          record(context, "staff.grant_role", label, {
            reason,
            changes: { roles: [before, (person.roles as Row[]).map((entry) => entry.name)] },
          });
          return json(201, person);
        }
        if (method === "DELETE" && extra) {
          const before = roles.map((entry) => entry.name);
          person.roles = roles.filter((entry) => entry.name !== decodeURIComponent(extra));
          record(context, "staff.revoke_role", label, {
            changes: { roles: [before, (person.roles as Row[]).map((entry) => entry.name)] },
          });
          return noContent();
        }
      }
      if (verb === "scopes") {
        if (!can(context, P.peopleScopes)) return refuse();
        const scopes = person.scopes as Row[];
        if (method === "POST") {
          const kind = text(body.kind);
          const value = text(body.value);
          const reason = text(body.reason);
          const fields: Record<string, string[]> = {};
          if (!kind) fields.kind = ["Choose the kind of scope."];
          if (!value) fields.value = ["Give the value."];
          if (!reason) fields.reason = ["Give a reason: it is saved in the audit trail."];
          if (Object.keys(fields).length) return invalid(fields);
          person.scopes = [...scopes, { id: nextId(world), kind, value, expires_at: null }];
          record(context, "staff.add_scope", label, {
            reason,
            changes: {
              scopes: [
                scopes.map((s) => `${s.kind}:${s.value}`),
                (person.scopes as Row[]).map((s) => `${s.kind}:${s.value}`),
              ],
            },
          });
          return json(201, person);
        }
        if (method === "DELETE" && extra) {
          person.scopes = scopes.filter((scope) => String(scope.id) !== extra);
          record(context, "staff.remove_scope", label);
          return noContent();
        }
      }
      if (method === "POST" && verb === "end-sessions") {
        if (!can(context, P.peopleSessions)) return refuse();
        person.sessions = 0;
        record(context, "staff.end_sessions", label);
        return noContent();
      }
      if (method === "POST" && verb === "offboard") {
        if (!can(context, P.peopleOffboard)) return refuse();
        const reason = text(body.reason);
        if (!reason) return invalid({ reason: ["Give a reason: it is saved in the audit trail."] });
        if (person.id === context.who.id)
          return json(403, { detail: "No one offboards themselves here.", code: "permission_denied" });
        person.status = "offboarded";
        person.roles = [];
        person.scopes = [];
        person.sessions = 0;
        record(context, "staff.offboard", label, { reason });
        return noContent();
      }
      return notFound();
    }

    case "access-review": {
      if (!can(context, P.accessReview)) return refuse();
      return json(200, {
        generated_at: now(),
        rows: world.people.map((row) => ({
          person: { id: row.id, email: row.email, name: row.name },
          roles: (row.roles as Row[]).map((role) => role.name),
          scopes: (row.scopes as Row[]).map((scope) => `${scope.kind}: ${scope.value}`),
          last_login: row.last_login,
          unused_permissions: row.id === 9006 ? ["staff.export_auditevent", "shop.view_order"] : [],
          dormant: row.last_login ? Date.now() - Date.parse(String(row.last_login)) > 45 * 86_400_000 : false,
        })),
      });
    }

    case "data-requests": {
      if (!can(context, P.requestsView)) return refuse();
      if (method === "GET" && !id) {
        return paginate(
          context,
          world.dataRequests.filter(
            (row) =>
              (!query("state") || row.state === query("state")) && (!query("type") || row.type === query("type")),
          ),
        );
      }
      if (method === "POST" && !id) {
        if (!can(context, P.requestsAdd)) return refuse();
        const type = text(body.type);
        const received = text(body.received_at);
        const email = text(body.requester_email);
        const phone = text(body.requester_phone);
        const fields: Record<string, string[]> = {};
        if (!type) fields.type = ["Choose the type of request."];
        if (!received || Number.isNaN(Date.parse(received))) fields.received_at = ["When did it arrive?"];
        if (!email && !phone) fields.requester_email = ["Give the requester's email address or mobile number."];
        if (Object.keys(fields).length) return invalid(fields);
        const start = Date.parse(received);
        const row: Row = {
          id: nextId(world),
          type,
          channel: text(body.channel) || "email",
          requester: {
            masked_email: email ? `${email[0]}•••@${email.split("@")[1] ?? ""}` : null,
            masked_phone: phone
              ? `+91 ${phone.replace(/\D/g, "").slice(-10, -8)}•• ••• ${phone.replace(/\D/g, "").slice(-3)}`
              : null,
            verified: false,
          },
          received_at: new Date(start).toISOString(),
          acknowledged_at: null,
          ack_due_at: new Date(start + 48 * 3_600_000).toISOString(),
          due_at: new Date(start + 30 * 86_400_000).toISOString(),
          state: "received",
          notes: text(body.notes),
          actions: [{ at: now(), text: "Logged in the console." }],
          version: 1,
        };
        world.dataRequests.unshift(row);
        record(context, "data_request.create", { type: "data_request", id: row.id, label: `Data request ${row.id}` });
        return json(201, row);
      }
      const row = id ? byId(world.dataRequests, id) : undefined;
      if (!row) return notFound();
      const label = { type: "data_request", id: row.id, label: `Data request ${row.id}` };
      if (method === "GET" && !verb) return json(200, row);
      if (!can(context, P.requestsChange)) return refuse();
      if (method === "PATCH" && !verb) {
        const match = context.request.headers.get("If-Match");
        if (match && match.replace(/"/g, "") !== String(row.version))
          return json(409, { detail: "This request changed since you opened it." });
        if ("notes" in body) row.notes = text(body.notes);
        if ("state" in body) row.state = text(body.state);
        row.version = Number(row.version) + 1;
        record(context, "data_request.change", label);
        return json(200, row);
      }
      if (method === "POST" && verb === "acknowledge") {
        if (row.acknowledged_at) return json(409, { detail: "It was acknowledged already." });
        row.acknowledged_at = now();
        row.state = "acknowledged";
        row.version = Number(row.version) + 1;
        (row.actions as Row[]).push({ at: now(), text: `Acknowledged by ${context.who.name}.` });
        record(context, "data_request.acknowledge", label);
        return noContent();
      }
      if (method === "POST" && verb === "erasure-dry-run") {
        if (row.type !== "erasure") return json(409, { detail: "A dry run is for erasure requests." });
        record(context, "data_request.erasure_dry_run", label);
        return json(200, {
          held: [
            {
              what: "2 orders and their GST invoices",
              why: "Tax records are kept for 8 financial years (Companies Act s.128).",
              until: "2035-03-31",
            },
            {
              what: "Sign-in and processing logs",
              why: "Kept for a year under DPDP Rule 8(3).",
              until: new Date(Date.now() + 300 * 86_400_000).toISOString().slice(0, 10),
            },
          ],
          will_erase: [
            "The account and its profile",
            "1 child's record of marks (12 attempts)",
            "Saved addresses (2)",
            "Notes written by staff",
          ],
        });
      }
      return notFound();
    }

    case "incidents": {
      if (!can(context, P.incidentsView)) return refuse();
      if (method === "GET" && !id)
        return paginate(
          context,
          world.incidents.filter((row) => !query("state") || row.state === query("state")),
        );
      if (method === "POST" && !id) {
        if (!can(context, P.incidentsAdd)) return refuse();
        const detected = text(body.detected_at);
        const type = text(body.type);
        const fields: Record<string, string[]> = {};
        if (!detected || Number.isNaN(Date.parse(detected))) fields.detected_at = ["When was it detected?"];
        else if (Date.parse(detected) > Date.now() + 60_000)
          fields.detected_at = ["A detection time cannot be in the future."];
        if (!type) fields.type = ["Choose the type."];
        if (Object.keys(fields).length) return invalid(fields);
        const start = Date.parse(detected);
        const row: Row = {
          id: nextId(world),
          detected_at: new Date(start).toISOString(),
          type,
          systems: Array.isArray(body.systems) ? body.systems : [],
          data_categories: Array.isArray(body.data_categories) ? body.data_categories : [],
          people_affected: typeof body.people_affected === "number" ? body.people_affected : null,
          children_affected: body.children_affected === true,
          certin_due_at: new Date(start + 6 * 3_600_000).toISOString(),
          board_due_at: new Date(start + 72 * 3_600_000).toISOString(),
          certin_reported_at: null,
          board_reported_at: null,
          notices_sent: 0,
          actions: [],
          state: "open",
          version: 1,
        };
        world.incidents.unshift(row);
        record(context, "incident.create", { type: "incident", id: row.id, label: `Incident ${row.id}` });
        return json(201, row);
      }
      const row = id ? byId(world.incidents, id) : undefined;
      if (!row) return notFound();
      if (method === "GET") return json(200, row);
      if (method === "PATCH") {
        if (!can(context, P.incidentsChange)) return refuse();
        const match = context.request.headers.get("If-Match");
        if (match && match.replace(/"/g, "") !== String(row.version))
          return json(409, { detail: "This incident changed since you opened it." });
        for (const key of ["certin_reported_at", "board_reported_at", "notices_sent", "state"])
          if (key in body) row[key] = body[key];
        if (text(body.action)) (row.actions as Row[]).push({ at: now(), text: text(body.action) });
        row.version = Number(row.version) + 1;
        record(context, "incident.change", { type: "incident", id: row.id, label: `Incident ${row.id}` });
        return json(200, row);
      }
      return notFound();
    }

    case "processors": {
      if (!can(context, P.processorsView)) return refuse();
      if (method === "GET") return json(200, world.processors);
      if (method === "POST") {
        if (!can(context, P.processorsAdd)) return refuse();
        const name = text(body.name);
        if (!name) return invalid({ name: ["Name the processor."] });
        const row: Row = {
          id: nextId(world),
          name,
          purpose: text(body.purpose),
          country: text(body.country),
          data_categories: Array.isArray(body.data_categories) ? body.data_categories : [],
          contract_until: text(body.contract_until) || null,
        };
        world.processors.push(row);
        record(context, "processor.create", { type: "processor", id: row.id, label: name });
        return json(201, row);
      }
      return notFound();
    }

    case "users": {
      if (!can(context, P.usersView)) return refuse();
      if (method === "GET" && !id) {
        const q = query("q");
        return paginate(
          context,
          world.users.filter(
            (row) =>
              (!q ||
                matches(row, q) ||
                (world.contacts[String(row.id)] && matches(world.contacts[String(row.id)] as unknown as Row, q))) &&
              (!query("kind") || row.kind === query("kind")) &&
              (!query("status") || row.status === query("status")),
          ),
          8,
        );
      }
      const user = id ? byId(world.users, id) : undefined;
      if (!user) return notFound();
      const label = { type: "user", id: user.id, label: String(user.name) };
      const flags = user.flags as Row;
      if (method === "GET" && !verb) {
        record(context, (user.flags as Row).child ? "accounts.sensitive_read" : "users.view", label);
        return json(200, user);
      }
      if (method !== "POST" && !(method === "DELETE" && verb === "impersonate")) return notFound();
      switch (verb) {
        case "reveal": {
          if (!can(context, P.usersReveal)) return refuse();
          const field = text(body.field);
          const reason = text(body.reason);
          if (field !== "email" && field !== "phone")
            return invalid({ field: ["Choose the email address or the mobile number."] });
          if (reason.length < 5) return invalid({ reason: ["Give a reason: it is saved in the audit trail."] });
          const recent = world.audit.filter(
            (event) =>
              event.action === "accounts.reveal_contact" &&
              (event.actor as Row).id === context.who.id &&
              Date.now() - Date.parse(String(event.ts)) < 600_000,
          );
          if (recent.length >= 5)
            return json(
              429,
              { detail: "Request was throttled. Expected available in 60 seconds." },
              { "Retry-After": "60" },
            );
          record(context, "accounts.reveal_contact", label, { reason, changes: {} });
          return json(200, { value: world.contacts[String(user.id)]?.[field] || "" });
        }
        case "suspend":
        case "unsuspend":
          if (!can(context, P.usersSuspend)) return refuse();
          user.status = verb === "suspend" ? "suspended" : "active";
          flags.suspended = verb === "suspend";
          record(context, `accounts.${verb}_user`, label, {
            changes: { status: [verb === "suspend" ? "active" : "suspended", user.status] },
          });
          return noContent();
        case "unlock":
          if (!can(context, P.usersUnlock)) return refuse();
          flags.locked = false;
          record(context, "accounts.unlock_user", label);
          return noContent();
        case "resend-verification":
          if (!can(context, P.usersResendVerification)) return refuse();
          record(context, "accounts.resend_verification", label);
          return noContent();
        case "end-sessions":
          if (!can(context, P.usersEndSessions)) return refuse();
          user.sessions = 0;
          record(context, "accounts.end_user_sessions", label);
          return noContent();
        case "password-reset":
          if (!can(context, P.usersPasswordReset)) return refuse();
          record(context, "accounts.initiate_password_reset", label);
          return noContent();
        case "reset-mfa":
          if (!can(context, P.usersResetMfa)) return refuse();
          return json(
            202,
            changeRequestFor(
              context,
              "accounts.reset_user_mfa",
              label,
              { user: user.id },
              `Reset ${user.name}'s two-step sign-in.`,
            ),
          );
        case "impersonate": {
          if (method === "DELETE") {
            world.impersonating = null;
            record(context, "accounts.impersonate_end", label);
            return noContent();
          }
          if (!can(context, P.usersImpersonate)) return refuse();
          const reason = text(body.reason);
          if (reason.length < 5) return invalid({ reason: ["Give a ticket number and why."] });
          if (flags.child)
            return json(
              202,
              changeRequestFor(context, "accounts.impersonate_user", label, { user: user.id, reason }, reason),
            );
          const until = new Date(Date.now() + 15 * 60_000).toISOString();
          world.impersonating = {
            user_id: user.id,
            email: world.contacts[String(user.id)]?.email ?? String(user.masked_email),
            until,
          };
          record(context, "accounts.impersonate_start", label, { reason });
          return json(200, {
            url: `${process.env.NEXT_PUBLIC_WEBSITE_URL ?? "http://localhost:3000"}/account/`,
            until,
          });
        }
      }
      return notFound();
    }

    case "system": {
      if (!can(context, P.systemView)) return refuse();
      if (method === "GET" && !id) return json(200, world.system);
      if (method === "POST" && id === "maintenance") {
        if (!can(context, P.maintenance)) return refuse();
        const reason = text(body.reason);
        if (!reason) return invalid({ reason: ["Give a reason: it is saved in the audit trail."] });
        const maintenance = world.system.maintenance as Row;
        const before = { ...maintenance };
        maintenance.on = body.on === true;
        maintenance.banner = text(body.banner);
        record(context, "system.maintenance", null, {
          reason,
          changes: { on: [before.on, maintenance.on], banner: [before.banner, maintenance.banner] },
        });
        return noContent();
      }
      return notFound();
    }

    case "jobs": {
      if (method === "POST" && !id) {
        const action = text(body.action);
        const ids = Array.isArray(body.ids) ? body.ids.map(String) : [];
        if (!action) return invalid({ action: ["Name the action."] });
        if (ids.length > 100) {
          const asked = changeRequestFor(
            context,
            "staff.bulk",
            { type: "job", id: action, label: action },
            { action, ids },
            `${ids.length} rows at once.`,
          );
          return json(403, {
            detail: "More than 100 rows at once needs a second person's approval.",
            code: "approval_required",
            change_request: { id: asked.id },
          });
        }
        if (action === "users.export") {
          if (!can(context, P.usersExport)) return refuse();
          return json(202, {
            job_id: startJob(
              context,
              action,
              world.users.map((row) => String(row.id)),
            ),
          });
        }
        if (action === "inbox.done" || action === "inbox.assign_me") {
          if (!can(context, P.inboxChange)) return refuse();
          if (!ids.length) return invalid({ ids: ["Select at least one row."] });
          return json(202, { job_id: startJob(context, action, ids) });
        }
        return invalid({ action: ["This action cannot run in bulk."] });
      }
      const running = id ? world.jobs[id] : undefined;
      if (!running) return notFound();
      if (method === "GET" && verb === "file") {
        const rows = running._rows.map((row) => `"${row}"`).join("\n");
        return new Response(`id\n${rows}\n`, {
          headers: {
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": `attachment; filename="${running.action}-${id}.csv"`,
            "Cache-Control": "no-store",
          },
        });
      }
      if (method !== "GET") return notFound();
      return json(200, advance(context, running));
    }
  }
  return notFound();
}

function startJob(context: Context, action: string, ids: string[]): number {
  const id = nextId(context.world);
  const failing: Record<string, string> = {};
  if (action === "inbox.done") {
    for (const itemId of ids) {
      const item = byId(context.world.inbox, itemId);
      if (item?.kind === "incident") failing[itemId] = "Close an incident from its own page, where its clocks are.";
    }
  }
  context.world.jobs[String(id)] = {
    id,
    action,
    state: "running",
    done: 0,
    total: ids.length,
    errors: [],
    result_url: null,
    _ticks: 0,
    _rows: ids,
    _failing: failing,
  };
  return id;
}

/** Each look at a job moves it on by a third, then applies what it does. */
function advance(context: Context, job: World["jobs"][string]) {
  if (job.state === "running") {
    job._ticks += 1;
    job.done = Math.min(job.total as number, Math.ceil(((job.total as number) * job._ticks) / 3));
    if (job.done === job.total) {
      job.state = "done";
      if (job.action === "inbox.done" || job.action === "inbox.assign_me") {
        for (const itemId of job._rows) {
          if (job._failing[itemId]) continue;
          const item = byId(context.world.inbox, itemId);
          if (!item) continue;
          if (job.action === "inbox.done") item.done_at = now();
          else item.assignee = me(context);
        }
      } else {
        job.result_url = `/api/mock/staff/jobs/${job.id}/file/`;
      }
      job.errors = Object.entries(job._failing).map(([rowId, message]) => ({
        id: rowId,
        label: String(byId(context.world.inbox, rowId)?.title ?? rowId),
        message,
      }));
    }
  }
  const { _ticks: _a, _rows: _b, _failing: _c, ...visible } = job;
  void _a;
  void _b;
  void _c;
  return visible;
}

/** The mock's one entry: refuses outside `next dev` with STAFF_API_MOCK=1. */
export async function handleMock(request: Request): Promise<Response> {
  if (process.env.STAFF_API_MOCK !== "1") throw new Error(OFF);
  const url = new URL(request.url);
  const parts = url.pathname
    .replace(/^\/api\/mock\/staff\//, "")
    .split("/")
    .filter(Boolean);
  const who = await signedIn(request);
  if (who instanceof Response) return who;
  if (request.method !== "GET" && request.method !== "HEAD" && !csrfOk(request))
    return json(403, { detail: "CSRF Failed: CSRF token missing or incorrect." });
  const world = (store.worlds[who.email] ??= createWorld({
    id: who.id,
    email: who.email,
    name: who.name,
    roles: [who.role],
  }));
  let body: Record<string, Json> = {};
  if (request.method !== "GET" && request.method !== "DELETE") {
    const parsed = (await request.json().catch(() => null)) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) body = parsed as Record<string, Json>;
  }
  return route({ request, url, parts, method: request.method, world, who, body });
}
