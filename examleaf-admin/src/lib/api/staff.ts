// The staff API (/api/v1/staff/, examleaf-web's staff app): every call the console makes for staff data, as thin typed
// functions, each with a runtime guard (plain narrowing, no schema library) that turns the answer into the types below
// or fails loudly with code "bad_response", so a renamed field costs this one file. The types are the contract as it
// stands (docs/examleaf-admin-control-panel-plan.md, the panel brief); once the backend publishes its OpenAPI schema,
// `npm run api:snapshot && npm run api:types` generates src/lib/api/schema.d.ts and these types come from there.
//
// One function, two places. In a server component pass the server's transport (`await staffTransport()`, server.ts):
// Django over the internal network with the person's cookies. In the browser leave it out: same origin, the CSRF token,
// and the answers the browser acts on (client.ts): a 401 sends the person to sign in and back, a refusal by role or
// scope reads the manifest again, "confirm it's you" opens the dialog and sends the call once more.
//
// STAFF_API_MOCK=1 (next dev only, next.config.ts) points everything at the fixtures of src/mocks/staff/ instead.
import type { Flow } from "@/lib/auth/headless";
import { copy } from "@/lib/copy";

import { endedBy, ensureCsrfCookie, manifestStale, reauth, readCookie, sessionEnded } from "./client";
import { ApiError, changeRequestOf, toApiError } from "./errors";

/** Compiled in by next.config.ts: "1" only in `next dev` with STAFF_API_MOCK=1, "" in every build. */
export const MOCK = process.env.STAFF_API_MOCK === "1";
export const STAFF_ROOT = MOCK ? "/api/mock/staff/" : "/api/v1/staff/";

export type Transport = {
  /** Where the API is: Django's internal address on the server, "" (same origin) in the browser. */
  base: string;
  headers?: Record<string, string>;
  fetch?: (request: Request) => Promise<Response>;
};

type Query = Record<string, string | number | boolean | null | undefined>;
type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
type CallOptions = { query?: Query; body?: unknown; version?: string | number | null; signal?: AbortSignal };

const UNSAFE = new Set<Method>(["POST", "PUT", "PATCH", "DELETE"]);

/** The path and query under the staff root: empty values are left out. */
export function staffPath(path: string, query: Query = {}): string {
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") search.set(name, String(value));
  }
  const tail = search.toString();
  return `${STAFF_ROOT}${path}${tail ? `?${tail}` : ""}`;
}

async function call<T>(
  transport: Transport | undefined,
  method: Method,
  path: string,
  read: (body: unknown) => T,
  options: CallOptions = {},
  retried = false,
): Promise<T> {
  const browser = !transport && typeof window !== "undefined";
  const base = transport?.base ?? (typeof window === "undefined" ? "" : window.location.origin);
  const headers: Record<string, string> = { Accept: "application/json", ...transport?.headers };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.version !== undefined && options.version !== null) headers["If-Match"] = `"${options.version}"`;
  if (browser && UNSAFE.has(method)) {
    await ensureCsrfCookie();
    const token = readCookie("csrftoken");
    if (token) headers["X-CSRFToken"] = token;
  }
  const request = new Request(`${base}${staffPath(path, options.query)}`, {
    method,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    credentials: "same-origin",
    // the server's transport sends its own cache rule (no-store) to Next's fetch
    ...(transport ? {} : { cache: "no-store" as const }),
    signal: options.signal,
  });

  let response: Response;
  try {
    response = await (transport?.fetch ?? fetch)(request);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "unavailable", copy.errors.unavailable);
  }
  const json: unknown = response.status === 204 ? null : await response.json().catch(() => null);

  // 202 with a change request: the action did not run, a second person is asked; for the console that is the same
  // outcome as a 403 approval_required, so both reach the caller as that error (and its changeRequestId)
  const asked = response.status === 202 ? (changeRequestOf(json) ?? changeRequestIdOf(json)) : null;
  if (asked) {
    throw new ApiError(202, "approval_required", copy.errors.approvalRequired, {}, { change_request: asked });
  }

  if (!response.ok) {
    const error = toApiError(response.status, json, response.headers);
    if (browser) {
      if (error.status === 401) sessionEnded(endedBy(error.code));
      if (error.code === "reauth_required" && !retried && (await reauth.request(flowsOf(json))))
        return call(transport, method, path, read, options, true);
      if (error.code === "permission_denied" || error.code === "scope_denied") manifestStale();
    }
    throw error;
  }

  try {
    return read(json);
  } catch (error) {
    if (!(error instanceof ShapeError)) throw error;
    if (typeof console !== "undefined") console.error(`staff API ${method} ${path}: unexpected ${error.message}`);
    throw new ApiError(response.status, "bad_response", copy.errors.badResponse, {}, json);
  }
}

/** A change request's own body ({"id", "payload_sha256", …}) names itself. */
function changeRequestIdOf(body: unknown): string | null {
  if (!body || typeof body !== "object" || !("payload_sha256" in body)) return null;
  const id = (body as { id?: unknown }).id;
  return typeof id === "number" || (typeof id === "string" && id) ? String(id) : null;
}

/** allauth's reauthentication flows, when the 403 carries them. */
function flowsOf(body: unknown): Flow[] {
  const flows = body && typeof body === "object" ? (body as { flows?: unknown }).flows : null;
  return Array.isArray(flows) ? (flows.filter((flow) => flow && typeof flow === "object") as Flow[]) : [];
}

// ---- Guards: plain narrowing. Each takes the value and where it sits, for the message of a mismatch. ----

class ShapeError extends Error {}

const bad = (what: string): never => {
  throw new ShapeError(what);
};
const obj = (value: unknown, what: string): Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : bad(what);
const text = (value: unknown, what: string): string => (typeof value === "string" ? value : bad(what));
const maybeText = (value: unknown, what: string): string | null => (value == null ? null : text(value, what));
const anId = (value: unknown, what: string): string =>
  typeof value === "number" || (typeof value === "string" && value !== "") ? String(value) : bad(what);
const maybeId = (value: unknown, what: string): string | null => (value == null ? null : anId(value, what));
const num = (value: unknown, what: string): number => {
  const number = typeof value === "string" && value.trim() !== "" ? Number(value) : value;
  return typeof number === "number" && Number.isFinite(number) ? number : bad(what);
};
const maybeNum = (value: unknown, what: string): number | null => (value == null ? null : num(value, what));
const yes = (value: unknown, what: string): boolean => (typeof value === "boolean" ? value : bad(what));
const list = <T>(value: unknown, what: string, item: (value: unknown, what: string) => T): T[] =>
  Array.isArray(value) ? value.map((entry, index) => item(entry, `${what}[${index}]`)) : bad(what);
const texts = (value: unknown, what: string): string[] => list(value, what, (entry) => String(entry));

export type PersonRef = { id: string | null; email: string; name: string | null };
export type TargetRef = { type: string; id: string; label: string; url: string | null };

/** A person as the API names one: {id, email, name}, or an email alone. */
function person(value: unknown, what: string): PersonRef {
  if (typeof value === "string") return { id: null, email: value, name: null };
  const record = obj(value, what);
  return {
    id: maybeId(record.id, `${what}.id`),
    email: typeof record.email === "string" ? record.email : "",
    name: maybeText(record.name, `${what}.name`),
  };
}
const maybePerson = (value: unknown, what: string) => (value == null ? null : person(value, what));

function target(value: unknown, what: string): TargetRef {
  const record = obj(value, what);
  return {
    type: text(record.type, `${what}.type`),
    id: anId(record.id, `${what}.id`),
    label: maybeText(record.label, `${what}.label`) ?? "",
    url: maybeText(record.url, `${what}.url`),
  };
}

export type Page<T> = { results: T[]; next: string | null; previous: string | null };

/** The cursor of a link of the API's cursor pagination (`…?cursor=cD0yMDI2…`), or null. */
export function cursorOf(link: unknown): string | null {
  if (typeof link !== "string" || !link) return null;
  try {
    return new URL(link, "http://link.invalid").searchParams.get("cursor");
  } catch {
    return null;
  }
}

const page =
  <T>(item: (value: unknown, what: string) => T) =>
  (body: unknown): Page<T> => {
    const record = obj(body, "page");
    return {
      results: list(record.results, "results", item),
      next: cursorOf(record.next),
      previous: cursorOf(record.previous),
    };
  };

/** A list that may come paginated ({results}) or as a plain array. */
const all =
  <T>(item: (value: unknown, what: string) => T) =>
  (body: unknown): T[] =>
    Array.isArray(body) ? list(body, "list", item) : list(obj(body, "list").results, "results", item);

const nothing = () => undefined;

// ---- The session manifest (GET session/): what the shell draws from. ----

export type Manifest = {
  user: { id: string; email: string; name: string };
  roles: { name: string; expires_at: string | null }[];
  /** Sorted app.codename strings (user.get_all_permissions()). */
  permissions: string[];
  scopes: Record<string, string[]>;
  limits: { refund_inr: number | null; discount_percent: number | null; export_rows: number; bulk_rows: number };
  flags: Record<string, boolean>;
  reauth_valid_until: string | null;
  idle_timeout_s: number;
  absolute_expires_at: string | null;
  impersonating: { user_id: string; email: string; until: string } | null;
  manifest_version: string;
};

export function readManifest(body: unknown): Manifest {
  const record = obj(body, "session");
  const user = obj(record.user, "user");
  const limits = obj(record.limits ?? {}, "limits");
  const scopes = obj(record.scopes ?? {}, "scopes");
  const flags = obj(record.flags ?? {}, "flags");
  const impersonating = record.impersonating == null ? null : obj(record.impersonating, "impersonating");
  return {
    user: {
      id: anId(user.id, "user.id"),
      email: text(user.email, "user.email"),
      name: maybeText(user.name ?? user.full_name, "user.name") ?? "",
    },
    roles: list(record.roles, "roles", (value, what) => {
      const role = obj(value, what);
      return { name: text(role.name, `${what}.name`), expires_at: maybeText(role.expires_at, `${what}.expires_at`) };
    }),
    permissions: texts(record.permissions, "permissions"),
    scopes: Object.fromEntries(Object.entries(scopes).map(([kind, values]) => [kind, texts(values, `scopes.${kind}`)])),
    limits: {
      refund_inr: maybeNum(limits.refund_inr, "limits.refund_inr"),
      discount_percent: maybeNum(limits.discount_percent, "limits.discount_percent"),
      export_rows: maybeNum(limits.export_rows, "limits.export_rows") ?? 0,
      bulk_rows: maybeNum(limits.bulk_rows, "limits.bulk_rows") ?? 0,
    },
    flags: Object.fromEntries(Object.entries(flags).map(([key, value]) => [key, value === true])),
    reauth_valid_until: maybeText(record.reauth_valid_until, "reauth_valid_until"),
    idle_timeout_s: num(record.idle_timeout_s, "idle_timeout_s"),
    absolute_expires_at: maybeText(record.absolute_expires_at, "absolute_expires_at"),
    impersonating: impersonating && {
      user_id: anId(impersonating.user_id, "impersonating.user_id"),
      email: text(impersonating.email, "impersonating.email"),
      until: text(impersonating.until, "impersonating.until"),
    },
    manifest_version: text(record.manifest_version, "manifest_version"),
  };
}

export const getSession = (transport?: Transport) => call(transport, "GET", "session/", readManifest);

// ---- Inbox ----

export type InboxState = "open" | "snoozed" | "done";
export type InboxItem = {
  id: string;
  kind: string;
  title: string;
  target: TargetRef | null;
  assignee: PersonRef | null;
  due_at: string | null;
  snoozed_until: string | null;
  done_at: string | null;
  created_at: string;
};
export type InboxQuery = { kind?: string; assignee?: string; state?: string; cursor?: string };

function inboxItem(value: unknown, what: string): InboxItem {
  const record = obj(value, what);
  return {
    id: anId(record.id, `${what}.id`),
    kind: text(record.kind, `${what}.kind`),
    title: text(record.title, `${what}.title`),
    target: record.target == null ? null : target(record.target, `${what}.target`),
    assignee: maybePerson(record.assignee, `${what}.assignee`),
    due_at: maybeText(record.due_at, `${what}.due_at`),
    snoozed_until: maybeText(record.snoozed_until, `${what}.snoozed_until`),
    done_at: maybeText(record.done_at, `${what}.done_at`),
    created_at: text(record.created_at, `${what}.created_at`),
  };
}

export const listInbox = (query: InboxQuery = {}, transport?: Transport) =>
  call(transport, "GET", "inbox/", page(inboxItem), { query });
export const inboxDone = (id: string) => call(undefined, "POST", `inbox/${id}/done/`, nothing, { body: {} });
export const inboxSnooze = (id: string, until: string) =>
  call(undefined, "POST", `inbox/${id}/snooze/`, nothing, { body: { until } });
export const inboxAssign = (id: string, userId: string) =>
  call(undefined, "POST", `inbox/${id}/assign/`, nothing, { body: { user_id: userId } });

export type InboxCounts = { total: number; more: boolean; byKind: Record<string, number> };

/** What waits for the person, from the first page of their open inbox (the contract has no count endpoint): `more`
 *  when the list goes on beyond it. */
export async function inboxCounts(transport?: Transport): Promise<InboxCounts> {
  const first = await listInbox({ state: "open", assignee: "me" }, transport);
  const byKind: Record<string, number> = {};
  for (const item of first.results) byKind[item.kind] = (byKind[item.kind] ?? 0) + 1;
  return { total: first.results.length, more: Boolean(first.next), byKind };
}

// ---- Audit ----

export type AuditEvent = {
  id: string;
  ts: string;
  actor: PersonRef & { type: string };
  on_behalf_of: PersonRef | null;
  action: string;
  target: TargetRef | null;
  outcome: string;
  reason: string | null;
  request_id: string | null;
  ip: string | null;
  changes: Record<string, [unknown, unknown]>;
  hash: string | null;
};
export type AuditQuery = {
  q?: string;
  actor?: string;
  action?: string;
  target_type?: string;
  target_id?: string;
  from?: string;
  to?: string;
  cursor?: string;
};

function auditEvent(value: unknown, what: string): AuditEvent {
  const record = obj(value, what);
  const actor = obj(record.actor, `${what}.actor`);
  const changes = obj(record.changes ?? {}, `${what}.changes`);
  return {
    id: anId(record.id, `${what}.id`),
    ts: text(record.ts, `${what}.ts`),
    actor: { ...person(actor, `${what}.actor`), type: maybeText(actor.type, `${what}.actor.type`) ?? "staff" },
    on_behalf_of: maybePerson(record.on_behalf_of, `${what}.on_behalf_of`),
    action: text(record.action, `${what}.action`),
    target: record.target == null ? null : target(record.target, `${what}.target`),
    outcome: maybeText(record.outcome, `${what}.outcome`) ?? "success",
    reason: maybeText(record.reason, `${what}.reason`),
    request_id: maybeText(record.request_id, `${what}.request_id`),
    ip: maybeText(record.ip, `${what}.ip`),
    changes: Object.fromEntries(
      Object.entries(changes).map(([field, pair]) => {
        if (!Array.isArray(pair) || pair.length !== 2) bad(`${what}.changes.${field}`);
        return [field, [(pair as unknown[])[0], (pair as unknown[])[1]] as [unknown, unknown]];
      }),
    ),
    hash: maybeText(record.hash, `${what}.hash`),
  };
}

export const listAudit = (query: AuditQuery = {}, transport?: Transport) =>
  call(transport, "GET", "audit/", page(auditEvent), { query });

const job = (body: unknown) => ({ job_id: anId(obj(body, "job").job_id, "job.job_id") });
export const exportAudit = (input: { from: string; to: string }) =>
  call(undefined, "POST", "audit/export/", job, { body: input });

// ---- Change requests (maker-checker) ----

export type ChangeRequestState = "pending" | "approved" | "rejected" | "expired" | "executed" | "failed";
export type ChangeRequest = {
  id: string;
  action: string;
  target: TargetRef | null;
  payload: unknown;
  payload_sha256: string;
  amount: number | null;
  maker: PersonRef;
  reason: string;
  state: string;
  approvals: { user: PersonRef; decision: string; comment: string; at: string }[];
  expires_at: string | null;
  created_at: string | null;
  result: unknown;
};

function changeRequest(value: unknown, what: string): ChangeRequest {
  const record = obj(value, what);
  return {
    id: anId(record.id, `${what}.id`),
    action: text(record.action, `${what}.action`),
    target: record.target == null ? null : target(record.target, `${what}.target`),
    payload: record.payload ?? null,
    payload_sha256: text(record.payload_sha256, `${what}.payload_sha256`),
    amount: maybeNum(record.amount, `${what}.amount`),
    maker: person(record.maker, `${what}.maker`),
    reason: maybeText(record.reason, `${what}.reason`) ?? "",
    state: text(record.state, `${what}.state`),
    approvals: list(record.approvals ?? [], `${what}.approvals`, (entry, where) => {
      const approval = obj(entry, where);
      return {
        user: person(approval.user, `${where}.user`),
        decision: text(approval.decision, `${where}.decision`),
        comment: maybeText(approval.comment, `${where}.comment`) ?? "",
        at: text(approval.at, `${where}.at`),
      };
    }),
    expires_at: maybeText(record.expires_at, `${what}.expires_at`),
    created_at: maybeText(record.created_at, `${what}.created_at`),
    result: record.result ?? null,
  };
}

export const listChangeRequests = (query: { state?: string; cursor?: string } = {}, transport?: Transport) =>
  call(transport, "GET", "change-requests/", page(changeRequest), { query });
export const getChangeRequest = (id: string, transport?: Transport) =>
  call(transport, "GET", `change-requests/${id}/`, (body) => changeRequest(body, "change request"));
const decided = (body: unknown) => changeRequest(body, "change request");
export const approveChangeRequest = (id: string, comment: string) =>
  call(undefined, "POST", `change-requests/${id}/approve/`, decided, { body: { comment } });
export const rejectChangeRequest = (id: string, comment: string) =>
  call(undefined, "POST", `change-requests/${id}/reject/`, decided, { body: { comment } });
export const executeChangeRequest = (id: string) =>
  call(undefined, "POST", `change-requests/${id}/execute/`, decided, { body: {} });

// ---- Saved views ----

export type SavedView = {
  id: string;
  list_key: string;
  name: string;
  filters: Record<string, string>;
  columns: string[];
  sort: string;
  shared_with_role: string | null;
};
export type SavedViewInput = Omit<SavedView, "id">;

function savedView(value: unknown, what: string): SavedView {
  const record = obj(value, what);
  const filters = obj(record.filters ?? {}, `${what}.filters`);
  return {
    id: anId(record.id, `${what}.id`),
    list_key: text(record.list_key, `${what}.list_key`),
    name: text(record.name, `${what}.name`),
    filters: Object.fromEntries(Object.entries(filters).map(([key, entry]) => [key, String(entry ?? "")])),
    columns: texts(record.columns ?? [], `${what}.columns`),
    sort: maybeText(record.sort, `${what}.sort`) ?? "",
    shared_with_role: maybeText(record.shared_with_role, `${what}.shared_with_role`),
  };
}

export const listSavedViews = async (listKey: string, transport?: Transport) =>
  (await call(transport, "GET", "saved-views/", all(savedView), { query: { list_key: listKey } })).filter(
    (view) => view.list_key === listKey,
  );
export const createSavedView = (input: SavedViewInput) =>
  call(undefined, "POST", "saved-views/", (body) => savedView(body, "saved view"), { body: input });
export const updateSavedView = (id: string, input: Partial<SavedViewInput>) =>
  call(undefined, "PATCH", `saved-views/${id}/`, (body) => savedView(body, "saved view"), { body: input });
export const deleteSavedView = (id: string) => call(undefined, "DELETE", `saved-views/${id}/`, nothing);

// ---- Settings and feature flags (one shape) ----

export type SettingKind = "settings" | "flags";
export type SettingChange = {
  value: unknown;
  changed_by: PersonRef | null;
  reason: string | null;
  at: string | null;
  effective_from: string | null;
};
export type Setting = {
  key: string;
  value: unknown;
  source: string;
  effective_from: string | null;
  changed_by: PersonRef | null;
  reason: string | null;
  history: SettingChange[];
};

function setting(value: unknown, what: string): Setting {
  const record = obj(value, what);
  return {
    key: text(record.key, `${what}.key`),
    value: record.value ?? null,
    source: text(record.source, `${what}.source`),
    effective_from: maybeText(record.effective_from, `${what}.effective_from`),
    changed_by: maybePerson(record.changed_by, `${what}.changed_by`),
    reason: maybeText(record.reason, `${what}.reason`),
    history: list(record.history ?? [], `${what}.history`, (entry, where) => {
      const change = obj(entry, where);
      return {
        value: change.value ?? null,
        changed_by: maybePerson(change.changed_by, `${where}.changed_by`),
        reason: maybeText(change.reason, `${where}.reason`),
        at: maybeText(change.at ?? change.changed_at, `${where}.at`),
        effective_from: maybeText(change.effective_from, `${where}.effective_from`),
      };
    }),
  };
}

export const listSettings = (kind: SettingKind, transport?: Transport) =>
  call(transport, "GET", `${kind}/`, all(setting));
export const changeSetting = (
  kind: SettingKind,
  key: string,
  input: { value: unknown; reason: string; effective_from?: string },
) =>
  call(undefined, "PUT", `${kind}/${encodeURIComponent(key)}/`, (body) => setting(body, kind), {
    body: input,
  });

// ---- API keys ----

export type ApiKey = {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  created_at: string | null;
  expires_at: string | null;
  last_used_at: string | null;
  last_ip: string | null;
  sponsor: PersonRef | null;
  revoked_at: string | null;
};

function apiKey(value: unknown, what: string): ApiKey {
  const record = obj(value, what);
  return {
    id: anId(record.id, `${what}.id`),
    name: text(record.name, `${what}.name`),
    prefix: maybeText(record.prefix, `${what}.prefix`) ?? "",
    scopes: texts(record.scopes ?? [], `${what}.scopes`),
    created_at: maybeText(record.created_at, `${what}.created_at`),
    expires_at: maybeText(record.expires_at, `${what}.expires_at`),
    last_used_at: maybeText(record.last_used_at, `${what}.last_used_at`),
    last_ip: maybeText(record.last_ip, `${what}.last_ip`),
    sponsor: maybePerson(record.sponsor, `${what}.sponsor`),
    revoked_at: maybeText(record.revoked_at, `${what}.revoked_at`),
  };
}

export const listApiKeys = (transport?: Transport) => call(transport, "GET", "api-keys/", all(apiKey));
/** The new key with its secret, which the API answers this once. */
export const createApiKey = (input: { name: string; scopes: string[]; expires_at: string }) =>
  call(
    undefined,
    "POST",
    "api-keys/",
    (body) => ({ key: apiKey(body, "api key"), secret: text(obj(body, "api key").secret, "api key.secret") }),
    { body: input },
  );
export const revokeApiKey = (id: string) => call(undefined, "POST", `api-keys/${id}/revoke/`, nothing, { body: {} });

// ---- People (staff) ----

export type StaffRoleGrant = { name: string; expires_at: string | null; granted_by: PersonRef | null };
export type StaffScope = { id: string; kind: string; value: string; expires_at: string | null };
export type StaffMember = {
  id: string;
  email: string;
  name: string;
  roles: StaffRoleGrant[];
  scopes: StaffScope[];
  mfa: boolean;
  last_login: string | null;
  sessions: number;
  status: string;
};

function staffMember(value: unknown, what: string): StaffMember {
  const record = obj(value, what);
  return {
    id: anId(record.id, `${what}.id`),
    email: text(record.email, `${what}.email`),
    name: maybeText(record.name, `${what}.name`) ?? "",
    roles: list(record.roles ?? [], `${what}.roles`, (entry, where) => {
      const role = obj(entry, where);
      return {
        name: text(role.name, `${where}.name`),
        expires_at: maybeText(role.expires_at, `${where}.expires_at`),
        granted_by: maybePerson(role.granted_by, `${where}.granted_by`),
      };
    }),
    scopes: list(record.scopes ?? [], `${what}.scopes`, (entry, where) => {
      const scope = obj(entry, where);
      return {
        id: anId(scope.id, `${where}.id`),
        kind: text(scope.kind, `${where}.kind`),
        value: String(scope.value ?? ""),
        expires_at: maybeText(scope.expires_at, `${where}.expires_at`),
      };
    }),
    mfa: yes(record.mfa, `${what}.mfa`),
    last_login: maybeText(record.last_login, `${what}.last_login`),
    sessions: maybeNum(record.sessions, `${what}.sessions`) ?? 0,
    status: text(record.status, `${what}.status`),
  };
}

export const listPeople = (query: { q?: string; cursor?: string } = {}, transport?: Transport) =>
  call(transport, "GET", "people/", page(staffMember), { query });
/** One staff member (GET people/{id}/: the list's detail route, not named in the brief). */
export const getPerson = (id: string, transport?: Transport) =>
  call(transport, "GET", `people/${id}/`, (body) => staffMember(body, "person"));
/** An invitation (a privileged role needs an approval: the error approval_required). */
export const invitePerson = (input: { email: string; role: string }) =>
  call(undefined, "POST", "people/invite/", nothing, { body: input });
export const grantRole = (id: string, input: { role: string; expires_at?: string; reason: string }) =>
  call(undefined, "POST", `people/${id}/roles/`, nothing, { body: input });
export const revokeRole = (id: string, role: string) =>
  call(undefined, "DELETE", `people/${id}/roles/${encodeURIComponent(role)}/`, nothing);
export const addScope = (id: string, input: { kind: string; value: string; reason: string }) =>
  call(undefined, "POST", `people/${id}/scopes/`, nothing, { body: input });
export const removeScope = (id: string, scopeId: string) =>
  call(undefined, "DELETE", `people/${id}/scopes/${scopeId}/`, nothing);
export const endPersonSessions = (id: string) =>
  call(undefined, "POST", `people/${id}/end-sessions/`, nothing, { body: {} });
export const offboardPerson = (id: string, reason: string) =>
  call(undefined, "POST", `people/${id}/offboard/`, nothing, { body: { reason } });

export type AccessReviewRow = {
  person: PersonRef;
  roles: string[];
  scopes: string[];
  last_login: string | null;
  unused_permissions: string[];
  dormant: boolean;
};
export type AccessReview = { generated_at: string | null; rows: AccessReviewRow[] };

function accessReview(body: unknown): AccessReview {
  const record = Array.isArray(body) ? { rows: body } : obj(body, "access review");
  return {
    generated_at: maybeText(record.generated_at, "generated_at"),
    rows: list(record.rows ?? record.results, "rows", (entry, where) => {
      const row = obj(entry, where);
      return {
        person: person(row.person ?? row.user, `${where}.person`),
        roles: list(row.roles ?? [], `${where}.roles`, (role) =>
          typeof role === "string" ? role : text(obj(role, `${where}.roles`).name, `${where}.roles.name`),
        ),
        scopes: list(row.scopes ?? [], `${where}.scopes`, (scope) =>
          typeof scope === "string"
            ? scope
            : `${text(obj(scope, `${where}.scopes`).kind, `${where}.scopes.kind`)}: ${String(
                (scope as Record<string, unknown>).value ?? "",
              )}`,
        ),
        last_login: maybeText(row.last_login, `${where}.last_login`),
        unused_permissions: texts(row.unused_permissions ?? [], `${where}.unused_permissions`),
        dormant: row.dormant === true,
      };
    }),
  };
}

export const getAccessReview = (transport?: Transport) => call(transport, "GET", "access-review/", accessReview);

// ---- Data-rights requests (DPDP) ----

export const DATA_REQUEST_TYPES = ["access", "correction", "erasure", "nomination", "grievance", "complaint"];
/** States after which no clock runs. */
export const FINAL_REQUEST_STATES = new Set(["responded", "closed", "rejected"]);

export type DataRequest = {
  id: string;
  type: string;
  channel: string;
  requester: { masked_email: string | null; masked_phone: string | null; verified: boolean };
  received_at: string;
  acknowledged_at: string | null;
  ack_due_at: string | null;
  due_at: string | null;
  state: string;
  notes: string;
  actions: { at: string | null; text: string }[];
  version: string | null;
};

/** What was done on a request or an incident: strings, or entries with a time and words. */
function actionsOf(value: unknown, what: string) {
  return list(value ?? [], what, (entry, where) => {
    if (typeof entry === "string") return { at: null, text: entry };
    const action = obj(entry, where);
    const words = action.text ?? action.action ?? action.what ?? action.label;
    return { at: maybeText(action.at, `${where}.at`), text: text(words, `${where}.text`) };
  });
}

function dataRequest(value: unknown, what: string): DataRequest {
  const record = obj(value, what);
  const requester = obj(record.requester ?? {}, `${what}.requester`);
  return {
    id: anId(record.id, `${what}.id`),
    type: text(record.type, `${what}.type`),
    channel: maybeText(record.channel, `${what}.channel`) ?? "",
    requester: {
      masked_email: maybeText(requester.masked_email, `${what}.requester.masked_email`),
      masked_phone: maybeText(requester.masked_phone, `${what}.requester.masked_phone`),
      verified: requester.verified === true,
    },
    received_at: text(record.received_at, `${what}.received_at`),
    acknowledged_at: maybeText(record.acknowledged_at, `${what}.acknowledged_at`),
    ack_due_at: maybeText(record.ack_due_at, `${what}.ack_due_at`),
    due_at: maybeText(record.due_at, `${what}.due_at`),
    state: text(record.state, `${what}.state`),
    notes: typeof record.notes === "string" ? record.notes : "",
    actions: actionsOf(record.actions, `${what}.actions`),
    version: maybeId(record.version, `${what}.version`),
  };
}

export type DryRun = { held: { what: string; why: string; until: string | null }[]; will_erase: string[] };

function dryRun(body: unknown): DryRun {
  const record = obj(body, "dry run");
  return {
    held: list(record.held ?? [], "held", (entry, where) => {
      const held = obj(entry, where);
      return {
        what: text(held.what, `${where}.what`),
        why: text(held.why, `${where}.why`),
        until: maybeText(held.until, `${where}.until`),
      };
    }),
    will_erase: list(record.will_erase ?? [], "will_erase", (entry, where) =>
      typeof entry === "string" ? entry : text(obj(entry, where).what, `${where}.what`),
    ),
  };
}

export const listDataRequests = (query: { state?: string; type?: string; cursor?: string } = {}, t?: Transport) =>
  call(t, "GET", "data-requests/", page(dataRequest), { query });
/** One request (GET data-requests/{id}/: the detail route of the PATCH, not named in the brief). */
export const getDataRequest = (id: string, transport?: Transport) =>
  call(transport, "GET", `data-requests/${id}/`, (body) => dataRequest(body, "data request"));
export const createDataRequest = (input: {
  type: string;
  channel: string;
  requester_email?: string;
  requester_phone?: string;
  received_at: string;
  notes?: string;
}) => call(undefined, "POST", "data-requests/", (body) => dataRequest(body, "data request"), { body: input });
export const updateDataRequest = (id: string, input: { notes?: string; state?: string }, version?: string | null) =>
  call(undefined, "PATCH", `data-requests/${id}/`, (body) => dataRequest(body, "data request"), {
    body: input,
    version,
  });
export const acknowledgeDataRequest = (id: string) =>
  call(undefined, "POST", `data-requests/${id}/acknowledge/`, nothing, { body: {} });
export const erasureDryRun = (id: string) =>
  call(undefined, "POST", `data-requests/${id}/erasure-dry-run/`, dryRun, { body: {} });

// ---- Incidents (the breach register) ----

export type Incident = {
  id: string;
  detected_at: string;
  type: string;
  systems: string[];
  data_categories: string[];
  people_affected: number | null;
  children_affected: boolean;
  certin_due_at: string | null;
  board_due_at: string | null;
  certin_reported_at: string | null;
  board_reported_at: string | null;
  notices_sent: number;
  actions: { at: string | null; text: string }[];
  state: string;
  version: string | null;
};
export type IncidentInput = {
  detected_at: string;
  type: string;
  systems: string[];
  data_categories: string[];
  people_affected: number | null;
  children_affected: boolean;
};

function incident(value: unknown, what: string): Incident {
  const record = obj(value, what);
  const children = record.children_affected;
  return {
    id: anId(record.id, `${what}.id`),
    detected_at: text(record.detected_at, `${what}.detected_at`),
    type: text(record.type, `${what}.type`),
    systems: texts(record.systems ?? [], `${what}.systems`),
    data_categories: texts(record.data_categories ?? [], `${what}.data_categories`),
    people_affected: maybeNum(record.people_affected, `${what}.people_affected`),
    children_affected: typeof children === "number" ? children > 0 : children === true,
    certin_due_at: maybeText(record.certin_due_at, `${what}.certin_due_at`),
    board_due_at: maybeText(record.board_due_at, `${what}.board_due_at`),
    certin_reported_at: maybeText(record.certin_reported_at, `${what}.certin_reported_at`),
    board_reported_at: maybeText(record.board_reported_at, `${what}.board_reported_at`),
    notices_sent: maybeNum(record.notices_sent, `${what}.notices_sent`) ?? 0,
    actions: actionsOf(record.actions, `${what}.actions`),
    state: text(record.state, `${what}.state`),
    version: maybeId(record.version, `${what}.version`),
  };
}

export const listIncidents = (query: { state?: string; cursor?: string } = {}, transport?: Transport) =>
  call(transport, "GET", "incidents/", page(incident), { query });
/** One incident (GET incidents/{id}/: the detail route of the PATCH, not named in the brief). */
export const getIncident = (id: string, transport?: Transport) =>
  call(transport, "GET", `incidents/${id}/`, (body) => incident(body, "incident"));
export const createIncident = (input: IncidentInput) =>
  call(undefined, "POST", "incidents/", (body) => incident(body, "incident"), { body: input });
export const updateIncident = (
  id: string,
  input: Partial<{
    certin_reported_at: string | null;
    board_reported_at: string | null;
    notices_sent: number;
    state: string;
    action: string;
  }>,
  version?: string | null,
) => call(undefined, "PATCH", `incidents/${id}/`, (body) => incident(body, "incident"), { body: input, version });

// ---- Processors ----

export type Processor = {
  id: string;
  name: string;
  purpose: string;
  country: string;
  data_categories: string[];
  contract_until: string | null;
};
export type ProcessorInput = Omit<Processor, "id">;

function processor(value: unknown, what: string): Processor {
  const record = obj(value, what);
  return {
    id: anId(record.id, `${what}.id`),
    name: text(record.name, `${what}.name`),
    purpose: maybeText(record.purpose, `${what}.purpose`) ?? "",
    country: maybeText(record.country, `${what}.country`) ?? "",
    data_categories: texts(record.data_categories ?? [], `${what}.data_categories`),
    contract_until: maybeText(record.contract_until, `${what}.contract_until`),
  };
}

export const listProcessors = (transport?: Transport) => call(transport, "GET", "processors/", all(processor));
export const createProcessor = (input: ProcessorInput) =>
  call(undefined, "POST", "processors/", (body) => processor(body, "processor"), { body: input });

// ---- Customers ----

export type CustomerFlags = { child: boolean; consent_pending: boolean; locked: boolean; suspended: boolean };
export type Customer = {
  id: string;
  masked_email: string | null;
  masked_phone: string | null;
  name: string;
  kind: string;
  status: string;
  joined: string | null;
  last_seen: string | null;
  flags: CustomerFlags;
};
/** The full record (GET users/{id}/; the server logs the read). Beyond the list's fields only what it sends. */
export type CustomerRecord = Customer & {
  email_verified: boolean | null;
  phone_verified: boolean | null;
  mfa: boolean | null;
  consent: string | null;
  sessions: number | null;
};

function customer(value: unknown, what: string): Customer {
  const record = obj(value, what);
  const flags = obj(record.flags ?? {}, `${what}.flags`);
  return {
    id: anId(record.id, `${what}.id`),
    masked_email: maybeText(record.masked_email, `${what}.masked_email`),
    masked_phone: maybeText(record.masked_phone, `${what}.masked_phone`),
    name: maybeText(record.name, `${what}.name`) ?? "",
    kind: text(record.kind, `${what}.kind`),
    status: text(record.status, `${what}.status`),
    joined: maybeText(record.joined, `${what}.joined`),
    last_seen: maybeText(record.last_seen, `${what}.last_seen`),
    flags: {
      child: flags.child === true,
      consent_pending: flags.consent_pending === true,
      locked: flags.locked === true,
      suspended: flags.suspended === true,
    },
  };
}

const maybeYes = (value: unknown) => (typeof value === "boolean" ? value : null);

function customerRecord(body: unknown): CustomerRecord {
  const record = obj(body, "customer");
  const consent = record.consent;
  return {
    ...customer(record, "customer"),
    email_verified: maybeYes(record.email_verified),
    phone_verified: maybeYes(record.phone_verified),
    mfa: maybeYes(record.mfa),
    consent:
      typeof consent === "string"
        ? consent
        : consent && typeof consent === "object"
          ? (maybeText((consent as Record<string, unknown>).state, "customer.consent.state") ?? null)
          : null,
    sessions: maybeNum(record.sessions, "customer.sessions"),
  };
}

export const listUsers = (query: { q?: string; kind?: string; status?: string; cursor?: string } = {}, t?: Transport) =>
  call(t, "GET", "users/", page(customer), { query });
export const getUser = (id: string, transport?: Transport) => call(transport, "GET", `users/${id}/`, customerRecord);
export const revealUser = (id: string, field: "email" | "phone", reason: string) =>
  call(undefined, "POST", `users/${id}/reveal/`, (body) => text(obj(body, "reveal").value, "reveal.value"), {
    body: { field, reason },
  });

export type CustomerAction =
  "suspend" | "unsuspend" | "unlock" | "resend-verification" | "end-sessions" | "password-reset";
export const userAction = (id: string, action: CustomerAction) =>
  call(undefined, "POST", `users/${id}/${action}/`, nothing, { body: {} });

/** Resetting two-step sign-in answers 202 with the change request it made, which reaches the caller as the error
 *  approval_required (its changeRequestId), as every action that needs a second person does. */
export const resetUserMfa = (id: string) => call(undefined, "POST", `users/${id}/reset-mfa/`, nothing, { body: {} });
export const impersonate = (id: string, reason: string) =>
  call(
    undefined,
    "POST",
    `users/${id}/impersonate/`,
    (body) => {
      const record = obj(body, "impersonation");
      return { url: text(record.url, "impersonation.url"), until: text(record.until, "impersonation.until") };
    },
    { body: { reason } },
  );
/** Ends the "sign in as" window (DELETE users/{id}/impersonate/: not named in the brief). */
export const endImpersonation = (userId: string) => call(undefined, "DELETE", `users/${userId}/impersonate/`, nothing);

// ---- System ----

export type HealthCheck = { name: string; ok: boolean; detail: string | null };
export type SystemStatus = {
  health: HealthCheck[];
  celery: { queues: Record<string, number>; failed: number };
  webhooks: { provider: string; event: string; at: string | null; ok: boolean; status: string | null }[];
  email: { sent: number | null; bounced: number | null; suppressed: number | null };
  sms: Record<string, string | number>;
  backups: { last_run: string | null; size: number | null };
  maintenance: { on: boolean; banner: string };
};

/** A health entry as true/false, "ok"/"…", or {ok, detail} / {status, detail}. */
function healthCheck(name: string, value: unknown): HealthCheck {
  if (typeof value === "boolean") return { name, ok: value, detail: null };
  if (typeof value === "string")
    return { name, ok: /^(ok|working|up|pass(ing)?|healthy)$/i.test(value), detail: value };
  const record = obj(value, `health.${name}`);
  const ok =
    typeof record.ok === "boolean"
      ? record.ok
      : typeof record.status === "string" && /^(ok|working|up|pass(ing)?|healthy)$/i.test(record.status);
  return { name, ok, detail: maybeText(record.detail ?? record.error ?? null, `health.${name}.detail`) };
}

function systemStatus(body: unknown): SystemStatus {
  const record = obj(body, "system");
  const celery = obj(record.celery ?? {}, "celery");
  const queues = obj(celery.queues ?? {}, "celery.queues");
  const webhooks = obj(record.webhooks ?? {}, "webhooks");
  const email = obj(record.email ?? {}, "email");
  const sms = obj(record.sms ?? {}, "sms");
  const backups = obj(record.backups ?? {}, "backups");
  const maintenance = obj(record.maintenance ?? {}, "maintenance");
  return {
    health: Object.entries(obj(record.health ?? {}, "health")).map(([name, value]) => healthCheck(name, value)),
    celery: {
      queues: Object.fromEntries(Object.entries(queues).map(([name, size]) => [name, num(size, `queues.${name}`)])),
      failed: maybeNum(celery.failed, "celery.failed") ?? 0,
    },
    webhooks: list(webhooks.recent ?? [], "webhooks.recent", (entry, where) => {
      const hook = obj(entry, where);
      const status = maybeText(hook.status, `${where}.status`);
      return {
        provider: text(hook.provider ?? hook.source ?? "", `${where}.provider`),
        event: text(hook.event ?? hook.type ?? "", `${where}.event`),
        at: maybeText(hook.at ?? hook.received_at, `${where}.at`),
        ok:
          typeof hook.ok === "boolean"
            ? hook.ok
            : typeof hook.signature_valid === "boolean"
              ? hook.signature_valid && status !== "failed"
              : status === "processed" || status === "ok",
        status,
      };
    }),
    email: {
      sent: maybeNum(email.sent, "email.sent"),
      bounced: maybeNum(email.bounced, "email.bounced"),
      suppressed: maybeNum(email.suppressed, "email.suppressed"),
    },
    sms: Object.fromEntries(
      Object.entries(sms)
        .filter(([, value]) => typeof value === "string" || typeof value === "number")
        .map(([key, value]) => [key, value as string | number]),
    ),
    backups: {
      last_run: maybeText(backups.last_run, "backups.last_run"),
      size: maybeNum(backups.size, "backups.size"),
    },
    maintenance: { on: maintenance.on === true, banner: maybeText(maintenance.banner, "maintenance.banner") ?? "" },
  };
}

export const getSystem = (transport?: Transport) => call(transport, "GET", "system/", systemStatus);
export const setMaintenance = (input: { on: boolean; banner: string; reason: string }) =>
  call(undefined, "POST", "system/maintenance/", nothing, { body: input });

// ---- Background jobs (bulk actions and exports; POST jobs/ and GET jobs/{id}/ are not named in the brief) ----

export type Job = {
  id: string;
  state: string;
  done: number;
  total: number;
  errors: { id: string; label: string; message: string }[];
  result_url: string | null;
};

function jobStatus(body: unknown): Job {
  const record = obj(body, "job");
  return {
    id: anId(record.id, "job.id"),
    state: text(record.state, "job.state"),
    done: maybeNum(record.done, "job.done") ?? 0,
    total: maybeNum(record.total, "job.total") ?? 0,
    errors: list(record.errors ?? [], "job.errors", (entry, where) => {
      const error = obj(entry, where);
      return {
        id: anId(error.id, `${where}.id`),
        label: maybeText(error.label, `${where}.label`) ?? String(error.id),
        message: text(error.message, `${where}.message`),
      };
    }),
    result_url: maybeText(record.result_url, "job.result_url"),
  };
}

/** A bulk action or an export in the background: `action` is "<list>.<verb>" (inbox.done, users.export). */
export const startJob = (input: { action: string; ids?: string[]; filters?: Record<string, string> }) =>
  call(undefined, "POST", "jobs/", job, { body: input });
export const getJob = (id: string, signal?: AbortSignal) =>
  call(undefined, "GET", `jobs/${id}/`, jobStatus, { signal });
export const FINAL_JOB_STATES = new Set(["done", "failed", "cancelled"]);
