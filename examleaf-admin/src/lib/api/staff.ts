// The staff API (/api/v1/staff/, examleaf-web's staff app): every call the console makes for staff data, typed from
// the backend's own OpenAPI schema (openapi.json, `npm run api:types` → schema.d.ts) through openapi-fetch. A path, a
// query parameter, a body or a field the backend renames is a type error here and in every page that reads it: the
// types are the contract, never written by hand (but the manifest's `policies_due`, which the schema types as a map).
// No call waits without a limit: the browser's 30 s (client.ts), the server's request deadline (server.ts).
//
// One function, two places. In a server component pass the server's transport (`await staffTransport()`, server.ts):
// Django over the internal network with the person's cookies. In the browser leave it out: same origin, the CSRF token,
// and the answers the browser acts on (client.ts): a 401 sends the person to sign in and back, a refusal by permission
// reads the manifest again, "confirm it's you" opens the dialog and sends the call once more. An action that waits for
// a second person answers 202 with its change request: that reaches the caller as the error `approval_required`
// (the change request in its body), since nothing ran.
//
// STAFF_API_MOCK=1 (next dev only, next.config.ts) answers every path from the fixtures of src/mocks/staff/ instead:
// src/proxy.ts sends the browser's calls there, server.ts the server's.
import createClient from "openapi-fetch";

import type { Flow } from "@/lib/auth/headless";
import { copy } from "@/lib/copy";

import { endedBy, ensureCsrfCookie, manifestStale, reauth, readCookie, sessionEnded, withTimeout } from "./client";
import { ApiError, noAnswer, toApiError } from "./errors";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

/** A note on a record (plan 7.1): personal data too, so it goes into the person's access export. */
export type Note = Schemas["Note"];
/** A policy the person has not acknowledged in its current version (the manifest's `policies_due`, which the schema
 *  types as a map: STAFF_POLICIES' key and the version in force). */
export type PolicyDue = { policy: string; version: string };
/** A break-glass session (research 1.6): its reason, asked before anything else, and the end of its box. */
export type BreakGlass = Schemas["StaffBreakGlass"];

const api = createClient<paths>({ credentials: "same-origin" });

// ---- The transport and the answers ----

export type Transport = {
  /** Where the API is: Django's internal address on the server, "" (same origin) in the browser. */
  base: string;
  headers?: Record<string, string>;
  fetch?: (request: Request) => Promise<Response>;
};

type Init = {
  baseUrl: string;
  headers: Record<string, string>;
  fetch: (request: Request) => Promise<Response>;
  signal?: AbortSignal;
};

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/** The browser's way: same origin, never cached, Django's CSRF token on every change. */
async function browserFetch(request: Request): Promise<Response> {
  if (UNSAFE.has(request.method)) {
    await ensureCsrfCookie();
    const token = readCookie("csrftoken");
    if (token) request.headers.set("X-CSRFToken", token);
  }
  return fetch(request, { cache: "no-store" });
}

/** The answer read whole, under the call's own limit (the browser's 30 s, client.ts; the server's request deadline,
 *  server.ts): a call, or a body the limit cut off, that ends without an answer is status 0 (noAnswer: a change the
 *  browser stopped waiting for may have gone through), and the page's own cancel stays an AbortError. */
const answered =
  (send: (request: Request) => Promise<Response>) =>
  async (request: Request): Promise<Response> => {
    try {
      const response = await send(request);
      const body = response.status === 204 ? null : await response.arrayBuffer();
      return new Response(body, {
        status: response.status,
        statusText: response.statusText,
        headers: response.headers,
      });
    } catch (error) {
      throw error instanceof DOMException && error.name === "AbortError" ? error : noAnswer(request.method, error);
    }
  };

function init(transport: Transport | undefined, signal?: AbortSignal): Init {
  const headers = { Accept: "application/json", ...transport?.headers };
  if (transport) return { baseUrl: transport.base, headers, fetch: answered(transport.fetch ?? fetch), signal };
  return {
    baseUrl: typeof window === "undefined" ? "" : window.location.origin,
    headers,
    fetch: answered(browserFetch),
    // the browser gives up after 30 s; the server's transport keeps its request's deadline itself
    signal: withTimeout(signal),
  };
}

type Answer = { data?: unknown; error?: unknown; response: Response };
/** What a call answers: its 2xx body, or nothing (204). */
type Data<A extends Answer> = [Exclude<A["data"], undefined>] extends [never] ? void : Exclude<A["data"], undefined>;

const isChangeRequest = (body: unknown): body is Schemas["ChangeRequest"] =>
  Boolean(body && typeof body === "object" && "payload_sha256" in body && "checker" in body);

/** allauth's reauthentication flows, when the 403 carries them. */
function flowsOf(body: unknown): Flow[] {
  const flows = body && typeof body === "object" ? (body as { flows?: unknown }).flows : null;
  return Array.isArray(flows) ? (flows.filter((flow) => flow && typeof flow === "object") as Flow[]) : [];
}

async function send<A extends Answer>(
  transport: Transport | undefined,
  ask: (init: Init) => Promise<A>,
  signal?: AbortSignal,
  retried = false,
): Promise<Data<A>> {
  const browser = !transport && typeof window !== "undefined";
  let answer: A;
  try {
    answer = await ask(init(transport, signal));
  } catch (error) {
    if (error instanceof ApiError || (error instanceof DOMException && error.name === "AbortError")) throw error;
    throw new ApiError(0, "unavailable", copy.errors.unavailable);
  }
  const { response } = answer;
  // 202 with a change request: nothing ran, a second person is asked
  if (response.status === 202 && isChangeRequest(answer.data)) {
    throw new ApiError(202, "approval_required", copy.errors.approvalRequired, {}, answer.data);
  }
  if (!response.ok) {
    const body = answer.error && typeof answer.error === "object" ? answer.error : null;
    const error = toApiError(response.status, body, response.headers);
    if (browser) {
      if (error.status === 401) sessionEnded(endedBy(error.code));
      if (error.code === "reauth_required" && !retried && (await reauth.request(flowsOf(body))))
        return send(transport, ask, signal, true);
      // a refusal by permission or scope, a break-glass session that owes its reason, a passkey to add first: the
      // manifest, read again, says which
      if (["permission_denied", "scope_denied", "break_glass_reason_required", "passkey_required"].includes(error.code))
        manifestStale();
    }
    throw error;
  }
  return answer.data as Data<A>;
}

// ---- Lists: the API's cursor pages, with each page's link turned into its cursor ----

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

const paged = <T>(page: { results: T[]; next?: string | null; previous?: string | null }): Page<T> => ({
  results: page.results,
  next: cursorOf(page.next),
  previous: cursorOf(page.previous),
});

/** A list's filters as the address gives them: the schema's names (a renamed one is a type error), any value (the API
 *  checks it: 400 for one it does not take). Empty values are left out. */
type Filters<P extends keyof paths> = paths[P] extends { get: { parameters: { query?: infer Q } } }
  ? { [K in keyof NonNullable<Q>]?: string | number | boolean | null }
  : never;

function query(filters: Record<string, string | number | boolean | null | undefined>): never {
  const kept = Object.entries(filters).filter(([, value]) => value !== undefined && value !== null && value !== "");
  return Object.fromEntries(kept) as never;
}

/** A unique Idempotency-Key: the same key answers the first request again (a retry after "confirm it's you"). */
const once = () => ({ "Idempotency-Key": crypto.randomUUID() });

// ---- The session manifest (GET session/): what the shell draws from ----

export type Manifest = Omit<Schemas["StaffManifest"], "policies_due"> & {
  /** The policies to acknowledge, once each version. */
  policies_due: PolicyDue[];
};
export type Limits = { refund_inr: number | null; export_rows: number | null; bulk_rows: number | null };

export const getSession = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/session/", o)) as Promise<Manifest>;
/** A break-glass session's reason, before anything else (the backend's research 1.6 box). */
export const giveSessionReason = (reason: string) =>
  send(undefined, (o) => api.POST("/api/v1/staff/session/reason/", { ...o, body: { reason } }));
export const acknowledgePolicy = (policy: PolicyDue) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/policies/ack/", { ...o, body: { policy: policy.policy, version: policy.version } }),
  );

/** The manifest's limits, which the schema types as a map: null is no limit. */
export function limitsOf(manifest: Pick<Manifest, "limits">): Limits {
  const value = (name: string) => (name in manifest.limits ? (manifest.limits[name] ?? null) : 0);
  return { refund_inr: value("refund_inr"), export_rows: value("export_rows"), bulk_rows: value("bulk_rows") };
}

/** A role of the manifest (the schema types them as maps). */
export type ManifestRole = { name: string; expires_at: string | null };
export const rolesOf = (manifest: Pick<Manifest, "roles">): ManifestRole[] =>
  manifest.roles.map((role) => ({
    name: String(role.name ?? ""),
    expires_at: typeof role.expires_at === "string" ? role.expires_at : null,
  }));

// ---- Inbox ----

export type InboxItem = Schemas["InboxItem"];
export type InboxCount = Schemas["InboxCount"];

export const listInbox = (filters: Filters<"/api/v1/staff/inbox/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/inbox/", { ...o, params: { query: query(filters) } })).then(paged);
export const inboxCount = (transport?: Transport) => send(transport, (o) => api.GET("/api/v1/staff/inbox/count/", o));
export const inboxDone = (id: number) =>
  send(undefined, (o) => api.POST("/api/v1/staff/inbox/{id}/done/", { ...o, params: { path: { id } } }));
export const inboxSnooze = (id: number, until: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/inbox/{id}/snooze/", { ...o, params: { path: { id } }, body: { until } }),
  );
export const inboxAssign = (id: number, assignee: number | null) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/inbox/{id}/assign/", { ...o, params: { path: { id } }, body: { assignee } }),
  );

// ---- Audit ----

export type AuditEvent = Schemas["AuditEvent"];
export type AuditFilters = Filters<"/api/v1/staff/audit/">;

export const listAudit = (filters: AuditFilters, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/audit/", { ...o, params: { query: query(filters) } })).then(paged);

export type AuditExport = { file: Blob; name: string } | { job: Job };

/** The list's filters as a file: JSON lines at once (up to 5,000 rows within your export limit), else a job. */
export async function exportAudit(filters: Record<string, string>): Promise<AuditExport> {
  let disposition = "";
  let status = 0;
  const answer = await send(undefined, async (o) => {
    const sent = await api.POST("/api/v1/staff/audit/export/", { ...o, body: { filters }, parseAs: "blob" });
    status = sent.response.status;
    disposition = sent.response.headers.get("Content-Disposition") ?? "";
    return status === 202 && sent.data ? { ...sent, data: JSON.parse(await sent.data.text()) as Job } : sent;
  });
  if (status === 202) return { job: answer as Job };
  return { file: answer as Blob, name: /filename="([^"]+)"/.exec(disposition)?.[1] ?? "audit.jsonl" };
}

// ---- Change requests (maker-checker) ----

export type ChangeRequest = Schemas["ChangeRequest"];
export type AskRequest = Schemas["AskRequest"];

export const listChangeRequests = (filters: Filters<"/api/v1/staff/change-requests/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/change-requests/", { ...o, params: { query: query(filters) } })).then(
    paged,
  );
export const getChangeRequest = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/change-requests/{id}/", { ...o, params: { path: { id } } }));
/** 201: it ran at once (within your limits); 202 (approval_required): it waits for a second person. */
export const askChange = (body: AskRequest) => {
  const headers = once();
  return send(undefined, (o) =>
    api.POST("/api/v1/staff/change-requests/", { ...o, headers: { ...o.headers, ...headers }, body }),
  );
};
/** The approval binds to the payload the approver read: its SHA-256 goes back. */
export const approveChangeRequest = (request: Pick<ChangeRequest, "id" | "payload_sha256">, comment: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/change-requests/{id}/approve/", {
      ...o,
      params: { path: { id: request.id } },
      body: { payload_sha256: request.payload_sha256, comment, override: false },
    }),
  );
export const rejectChangeRequest = (id: number, comment: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/change-requests/{id}/reject/", { ...o, params: { path: { id } }, body: { comment } }),
  );
export const executeChangeRequest = (id: number) =>
  send(undefined, (o) => api.POST("/api/v1/staff/change-requests/{id}/execute/", { ...o, params: { path: { id } } }));

// ---- Background jobs ----

export type Job = Schemas["Job"];
export const FINAL_JOB_STATES = new Set<Job["state"]>(["done", "failed", "cancelled"]);

export const listJobs = (filters: Filters<"/api/v1/staff/jobs/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/jobs/", { ...o, params: { query: query(filters) } })).then(paged);
export const getJob = (id: number, signal?: AbortSignal) =>
  send(undefined, (o) => api.GET("/api/v1/staff/jobs/{id}/", { ...o, params: { path: { id } } }), signal);
export const cancelJob = (id: number) =>
  send(undefined, (o) => api.POST("/api/v1/staff/jobs/{id}/cancel/", { ...o, params: { path: { id } } }));

/** A job's file: the job read again for a fresh `result_url` (its token lasts 5 minutes), opened on this origin. */
export async function jobFileHref(id: number): Promise<string | null> {
  const job = await getJob(id);
  if (!job.result_url) return null;
  const url = new URL(job.result_url, "http://link.invalid");
  return `${url.pathname}${url.search}`;
}

// ---- Saved views ----

export type SavedView = Omit<Schemas["SavedView"], "filters" | "columns" | "sort"> & {
  filters: Record<string, string>;
  columns: string[];
  sort: string;
};
export type SavedViewInput = Pick<SavedView, "list_key" | "name" | "filters" | "columns" | "sort"> & { role: string };

/** The schema types a view's filters, columns and sort as any JSON: the console keeps text. */
function view(row: Schemas["SavedView"]): SavedView {
  const filters = row.filters && typeof row.filters === "object" ? (row.filters as Record<string, unknown>) : {};
  return {
    ...row,
    filters: Object.fromEntries(Object.entries(filters).map(([key, value]) => [key, String(value ?? "")])),
    columns: Array.isArray(row.columns) ? row.columns.map(String) : [],
    sort: typeof row.sort === "string" ? row.sort : "",
  };
}

export const listSavedViews = async (listKey: string, transport?: Transport) =>
  (
    await send(transport, (o) =>
      api.GET("/api/v1/staff/saved-views/", { ...o, params: { query: { list_key: listKey, page_size: 50 } } }),
    )
  ).results.map(view);
export const createSavedView = async (body: SavedViewInput) =>
  view(await send(undefined, (o) => api.POST("/api/v1/staff/saved-views/", { ...o, body })));
export const updateSavedView = async (id: number, body: Partial<SavedViewInput>) =>
  view(
    await send(undefined, (o) =>
      api.PATCH("/api/v1/staff/saved-views/{id}/", { ...o, params: { path: { id } }, body }),
    ),
  );
export const deleteSavedView = (id: number) =>
  send(undefined, (o) => api.DELETE("/api/v1/staff/saved-views/{id}/", { ...o, params: { path: { id } } }));

// ---- Site settings and feature flags ----

export type Setting = Schemas["Setting"];
export type Flag = Schemas["Flag"];
export type SwitchRow = Schemas["SwitchRow"];
export type SwitchChange = Schemas["SwitchChangeRequest"];

export const listSettings = (transport?: Transport) => send(transport, (o) => api.GET("/api/v1/staff/settings/", o));
export const listFlags = (transport?: Transport) => send(transport, (o) => api.GET("/api/v1/staff/flags/", o));
/** One switch's history, newest first. */
export const switchHistory = (kind: "settings" | "flags", key: string) =>
  kind === "settings"
    ? send(undefined, (o) => api.GET("/api/v1/staff/settings/{key}/", { ...o, params: { path: { key } } }))
    : send(undefined, (o) => api.GET("/api/v1/staff/flags/{key}/", { ...o, params: { path: { key } } }));
/** A new value from now or from `effective_from`, with a reason (null: back to the environment's; a flag: off). */
export const changeSetting = (key: string, body: SwitchChange) =>
  send(undefined, (o) => api.PUT("/api/v1/staff/settings/{key}/", { ...o, params: { path: { key } }, body }));
export const changeFlag = (key: string, body: SwitchChange) =>
  send(undefined, (o) => api.PUT("/api/v1/staff/flags/{key}/", { ...o, params: { path: { key } }, body }));

// ---- API keys ----

export type ApiKey = Schemas["ApiKey"];

export const listApiKeys = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/api-keys/", { ...o, params: { query: { page_size: 200 } } })).then(
    paged,
  );
/** The new key: its `key` (the whole secret) is in this answer only. */
export const createApiKey = (body: Schemas["ApiKeyRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/api-keys/", { ...o, body }));
export const revokeApiKey = (id: number) =>
  send(undefined, (o) => api.POST("/api/v1/staff/api-keys/{id}/revoke/", { ...o, params: { path: { id } } }));

// ---- People (staff) ----

export type Person = Schemas["Person"];
export type StaffInvite = Schemas["StaffInvite"];
export type AccessRow = Schemas["AccessRow"];
export type Role = Schemas["RoleEnum"];
export type ScopeKind = Schemas["ScopeKindEnum"];

export const listPeople = (filters: Filters<"/api/v1/staff/people/">, transport?: Transport, signal?: AbortSignal) =>
  send(transport, (o) => api.GET("/api/v1/staff/people/", { ...o, params: { query: query(filters) } }), signal).then(
    paged,
  );
export const getPerson = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/people/{id}/", { ...o, params: { path: { id } } }));
export const listInvites = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/people/invites/", o)).then(paged);
/** 201 the invitation; a privileged role: 202, another person approves first (approval_required). */
export const invitePerson = (body: Schemas["InviteRequest"]) => {
  const headers = once();
  return send(undefined, (o) =>
    api.POST("/api/v1/staff/people/invite/", { ...o, headers: { ...o.headers, ...headers }, body }),
  );
};
export const revokeInvite = (invite: number) =>
  send(undefined, (o) => api.DELETE("/api/v1/staff/people/invites/{invite}/", { ...o, params: { path: { invite } } }));
/** A privileged role, or one for yourself: 202, another person approves (approval_required); separation of duties:
 *  400. */
export const grantRole = (id: number, body: Schemas["GrantRequest"]) => {
  const headers = once();
  return send(undefined, (o) =>
    api.POST("/api/v1/staff/people/{id}/roles/", {
      ...o,
      headers: { ...o.headers, ...headers },
      params: { path: { id } },
      body,
    }),
  );
};
export const revokeRole = (id: number, role: Role, reason: string) =>
  send(undefined, (o) =>
    api.DELETE("/api/v1/staff/people/{id}/roles/{role}/", {
      ...o,
      params: { path: { id, role } },
      querySerializer: () => new URLSearchParams({ reason }).toString(),
    }),
  );
export const addScope = (id: number, body: Schemas["ScopeAddRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/people/{id}/scopes/", { ...o, params: { path: { id } }, body }));
export const removeScope = (id: number, scope: number) =>
  send(undefined, (o) =>
    api.DELETE("/api/v1/staff/people/{id}/scopes/{scope}/", { ...o, params: { path: { id, scope } } }),
  );
export const endPersonSessions = (id: number) =>
  send(undefined, (o) => api.POST("/api/v1/staff/people/{id}/end-sessions/", { ...o, params: { path: { id } } }));
export const resetPersonMfa = (id: number, reason: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/people/{id}/reset-mfa/", { ...o, params: { path: { id } }, body: { reason } }),
  );
export const offboardPerson = (id: number, reason: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/people/{id}/offboard/", { ...o, params: { path: { id } }, body: { reason } }),
  );
export const getAccessReview = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/access-review/", o));

// ---- Customers ----

export type Customer = Schemas["Customer"];
export type CustomerDetail = Schemas["CustomerDetail"];
export type Revealable = Schemas["ShowEnum"];

export const listUsers = (filters: Filters<"/api/v1/staff/users/">, transport?: Transport, signal?: AbortSignal) =>
  send(transport, (o) => api.GET("/api/v1/staff/users/", { ...o, params: { query: query(filters) } }), signal).then(
    paged,
  );
/** The full record; the server records the read (a child's as such). */
export const getUser = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/users/{id}/", { ...o, params: { path: { id } } }));
/** A detail shown, with a reason (logged, re-authenticated, 30 an hour): `{show: [fields]}` → `{field: value}`, the
 *  first of `fields` that has one (the masked mobile number is the login number, else the contact number). */
export async function revealUser(id: number, fields: Revealable[], reason: string): Promise<string> {
  const shown = await send(undefined, (o) =>
    api.POST("/api/v1/staff/users/{id}/reveal/", { ...o, params: { path: { id } }, body: { show: fields, reason } }),
  );
  return fields.map((field) => shown[field]).find(Boolean) ?? "";
}

export type CustomerAction = "unlock" | "resend-verification" | "end-sessions" | "password-reset";
export const userAction = (id: number, action: CustomerAction) => {
  const path = { params: { path: { id } } };
  switch (action) {
    case "unlock":
      return send(undefined, (o) => api.POST("/api/v1/staff/users/{id}/unlock/", { ...o, ...path }));
    case "resend-verification":
      return send(undefined, (o) => api.POST("/api/v1/staff/users/{id}/resend-verification/", { ...o, ...path }));
    case "end-sessions":
      return send(undefined, (o) => api.POST("/api/v1/staff/users/{id}/end-sessions/", { ...o, ...path }));
    case "password-reset":
      return send(undefined, (o) => api.POST("/api/v1/staff/users/{id}/password-reset/", { ...o, ...path }));
  }
};
export const suspendUser = (id: number, suspend: boolean, reason: string) =>
  suspend
    ? send(undefined, (o) =>
        api.POST("/api/v1/staff/users/{id}/suspend/", { ...o, params: { path: { id } }, body: { reason } }),
      )
    : send(undefined, (o) =>
        api.POST("/api/v1/staff/users/{id}/unsuspend/", { ...o, params: { path: { id } }, body: { reason } }),
      );
/** Always 202: another person approves it (approval_required). */
export const resetUserMfa = (id: number, reason: string) => {
  const headers = once();
  return send(undefined, (o) =>
    api.POST("/api/v1/staff/users/{id}/reset-mfa/", {
      ...o,
      headers: { ...o.headers, ...headers },
      params: { path: { id } },
      body: { reason },
    }),
  );
};

export type Impersonation = { token: string; until: string; url: string };
const IMPERSONATION_KEY = "examleaf-admin:impersonation";

/** The token of this tab's impersonation of a customer, which ending it needs (kept in sessionStorage: this tab only,
 *  gone with it; the token lasts 15 minutes anyway). */
export function impersonationToken(userId: number): string | null {
  try {
    const kept = JSON.parse(window.sessionStorage.getItem(IMPERSONATION_KEY) ?? "null") as {
      user: number;
      token: string;
    } | null;
    return kept?.user === userId ? kept.token : null;
  } catch {
    return null;
  }
}

function keepImpersonation(userId: number, token: string | null) {
  try {
    if (token) window.sessionStorage.setItem(IMPERSONATION_KEY, JSON.stringify({ user: userId, token }));
    else window.sessionStorage.removeItem(IMPERSONATION_KEY);
  } catch {
    // storage off: End is offered on the website's own banner instead
  }
}

/** A 15-minute token for the website's account area (never staff or a child), with a reason and a ticket: the link
 *  that opens it there (`website`/account/impersonate/?token=…). */
export async function impersonate(id: number, body: Schemas["ImpersonateRequest"], website: string) {
  const answer = await send(undefined, (o) =>
    api.POST("/api/v1/staff/users/{id}/impersonate/", { ...o, params: { path: { id } }, body }),
  );
  keepImpersonation(id, answer.token);
  const url = `${website}/account/impersonate/?token=${encodeURIComponent(answer.token)}`;
  return { token: answer.token, until: answer.expires_at, url } satisfies Impersonation;
}
export async function endImpersonation(userId: number, token: string) {
  await send(undefined, (o) =>
    api.POST("/api/v1/staff/users/{id}/impersonate/end/", { ...o, params: { path: { id: userId } }, body: { token } }),
  );
  keepImpersonation(userId, null);
}

// ---- Notes (not in the schema yet: Pending) ----

export const listNotes = (target: { type: string; id: string }, transport?: Transport) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/notes/", { ...o, params: { query: { target_type: target.type, target_id: target.id } } }),
  );
export const addNote = (target: { type: string; id: string }, body: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/notes/", { ...o, body: { target_type: target.type, target_id: target.id, body } }),
  );

// ---- Data protection ----

export type DataRequest = Schemas["DataRequest"];
export type DataRequestRow = Schemas["DataRequestList"];
export type ErasureReport = Schemas["ErasureReport"];
export type Incident = Schemas["Incident"];
export type Processor = Schemas["Processor"];

export const listDataRequests = (filters: Filters<"/api/v1/staff/data-requests/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/data-requests/", { ...o, params: { query: query(filters) } })).then(
    paged,
  );
export const getDataRequest = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/data-requests/{id}/", { ...o, params: { path: { id } } }));
export const createDataRequest = (body: Schemas["DataRequestRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/data-requests/", { ...o, body }));
export const updateDataRequest = (id: number, body: Schemas["PatchedDataRequestRequest"]) =>
  send(undefined, (o) => api.PATCH("/api/v1/staff/data-requests/{id}/", { ...o, params: { path: { id } }, body }));
export const acknowledgeDataRequest = (id: number) =>
  send(undefined, (o) => api.POST("/api/v1/staff/data-requests/{id}/acknowledge/", { ...o, params: { path: { id } } }));
export const verifyIdentity = (id: number, note: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/data-requests/{id}/verify-identity/", {
      ...o,
      params: { path: { id } },
      body: { note },
    }),
  );
export const closeDataRequest = (id: number, body: Schemas["CloseRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/data-requests/{id}/close/", { ...o, params: { path: { id } }, body }));
/** The answer's text with the contact block, to send as it is or adapted. */
export const dataRequestResponse = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/data-requests/{id}/response/", { ...o, params: { path: { id } } }));
/** The erasure's dry run: what goes, what stays and why, what stops it. */
export const erasureReport = (id: number) =>
  send(undefined, (o) =>
    api.GET("/api/v1/staff/data-requests/{id}/erasure-report/", { ...o, params: { path: { id } } }),
  );
/** 202 (approval_required): the erasure waits for staff.approve_erasure; 400 with the dry run while something stops
 *  it (its blocks, in the error's body). */
export const eraseForRequest = (id: number, reason: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/data-requests/{id}/erase/", { ...o, params: { path: { id } }, body: { reason } }),
  );
/** An access request's data, emailed to the account's own address (202, its words). */
export const exportForRequest = (id: number) =>
  send(undefined, (o) => api.POST("/api/v1/staff/data-requests/{id}/export/", { ...o, params: { path: { id } } }));

export const listIncidents = (filters: Filters<"/api/v1/staff/incidents/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/incidents/", { ...o, params: { query: query(filters) } })).then(paged);
export const getIncident = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/incidents/{id}/", { ...o, params: { path: { id } } }));
export const createIncident = (body: Schemas["IncidentRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/incidents/", { ...o, body }));
export const updateIncident = (id: number, body: Schemas["PatchedIncidentRequest"]) =>
  send(undefined, (o) => api.PATCH("/api/v1/staff/incidents/{id}/", { ...o, params: { path: { id } }, body }));
export const closeIncident = (id: number) =>
  send(undefined, (o) => api.POST("/api/v1/staff/incidents/{id}/close/", { ...o, params: { path: { id } } }));

export const listProcessors = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/processors/", { ...o, params: { query: { page_size: 200 } } })).then(
    paged,
  );
export const createProcessor = (body: Schemas["ProcessorRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/processors/", { ...o, body }));

// ---- System ----

/** GET system/ as staff/api.py's SystemView builds it (the schema types each part as any JSON). */
export type SystemStatus = {
  health: { check: string; ok: boolean; error: string }[];
  celery: {
    queues: Record<string, number> | { error: string } | null;
    failed_7_days: number;
    failed: { task_id: string; task_name: string | null; date_done: string }[];
  };
  webhooks: { last_day: Record<string, number>; refused_7_days: number };
  email: { suppressed: number; suppressed_7_days: Record<string, number> };
  sms: { last_day: Record<string, number> };
  backups: { configured: boolean; error?: string; latest?: string | null; size?: number; at?: string };
  maintenance: { on: boolean; banner: string };
  audit: { last_verification: { action: string; ts: string; details: unknown } | null; heads: unknown };
  /** One line per subsystem, with the time it came to its state (staff/system_api.py). */
  status: Schemas["SystemStatus"][];
};

export const getSystem = async (transport?: Transport) =>
  (await send(transport, (o) => api.GET("/api/v1/staff/system/", o))) as SystemStatus;
/** Ask Razorpay what became of an online order's payment (a lost webhook). */
export const reconcileOrder = (order: string) =>
  send(undefined, (o) => api.POST("/api/v1/staff/system/reconcile/", { ...o, body: { order } }));

// ---- Staff, settings and integrations, system ----
// The role catalogue, a person's Access tab and a role change's preview, offboarding's checklist, ERPNext's role
// mirror, one's own sessions; settings' and flags' history; the connections page (cards, tests, credentials, mode,
// circuit, webhooks, events, calls, dead letters); the message templates; the system's pages. Their words:
// copy.management; their pages: people/, settings/, system/.

export type RoleCatalogueRow = Schemas["RoleCatalogue"];
export type Capability = Schemas["Capability"];
export type CapabilityArea = Schemas["CapabilityArea"];
export type Access = Schemas["Access"];
export type RolePreview = Schemas["RolePreview"];
export type Offboarding = Schemas["Offboarding"];
export type OffboardingStep = Schemas["OffboardingStep"];
export type ErpMirror = Schemas["ErpMirror"];
export type OwnSession = Schemas["OwnSession"];

export const listRoleCatalogue = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/people/roles/", o));
export const getAccess = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/people/{id}/access/", { ...o, params: { path: { id } } }));
/** What granting (or revoking) a role would change: nothing changes. */
export const previewRole = (id: number, body: Schemas["RolePreviewRequestRequest"], signal?: AbortSignal) =>
  send(
    undefined,
    (o) => api.POST("/api/v1/staff/people/{id}/roles/preview/", { ...o, params: { path: { id } }, body }),
    signal,
  );
/** Their latest offboarding's checklist (404: never offboarded). */
export const getOffboarding = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/people/{id}/offboarding/", { ...o, params: { path: { id } } }));
export const tickOffboarding = (id: number, body: Schemas["OffboardingTickRequest"]) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/people/{id}/offboarding/tick/", { ...o, params: { path: { id } }, body }),
  );
export const getErpMirror = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/people/{id}/erp/", { ...o, params: { path: { id } } }));
export const listOwnSessions = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/people/me/sessions/", o));
export const endOwnSession = (session: number) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/people/me/sessions/{session}/end/", { ...o, params: { path: { session } } }),
  );
export const endOtherSessions = () =>
  send(undefined, (o) => api.POST("/api/v1/staff/people/me/sessions/end-others/", o));

/** A setting's or a flag's history, newest first (who, when, why, from when). */
export const historyOf = (kind: "settings" | "flags", key: string) =>
  kind === "settings"
    ? send(undefined, (o) => api.GET("/api/v1/staff/settings/{key}/history/", { ...o, params: { path: { key } } }))
    : send(undefined, (o) => api.GET("/api/v1/staff/flags/{key}/history/", { ...o, params: { path: { key } } }));

export type ConnectionCard = Schemas["ConnectionCard"];
export type ConnectionProvider = ConnectionCard["provider"];
export type ConnectionAccount = Schemas["AccountRow"];
export type TestResult = Schemas["TestResult"];
export type WebhookInfo = Schemas["WebhookInfo"];
export type InboundEvent = Schemas["InboundEvent"];
export type IntegrationCall = Schemas["Call"];
export type DeadLetter = Schemas["Failure"];

const provider = (key: ConnectionProvider) => ({ params: { path: { provider: key } } });

export const listConnections = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/connections/", o));
export const getConnection = (key: ConnectionProvider, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/connections/{provider}/", { ...o, ...provider(key) }));
/** One harmless read with the keys in force: ok false is a test that ran and failed (its words). */
export const testConnection = (key: ConnectionProvider) =>
  send(undefined, (o) => api.POST("/api/v1/staff/connections/{provider}/test/", { ...o, ...provider(key) }));
/** New credentials, kept only if their own test passes in the same call (400 with the provider's words otherwise). */
export const replaceCredentials = (key: ConnectionProvider, body: Schemas["CredentialsRequest"]) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/connections/{provider}/credentials/", { ...o, ...provider(key), body }),
  );
export const switchMode = (key: ConnectionProvider, body: Schemas["ModeRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/connections/{provider}/mode/", { ...o, ...provider(key), body }));
export const setCircuit = (key: ConnectionProvider, body: Schemas["CircuitActionRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/connections/{provider}/circuit/", { ...o, ...provider(key), body }));
export const getWebhooks = (key: ConnectionProvider, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/connections/{provider}/webhooks/", { ...o, ...provider(key) }));
/** A new webhook token: in this answer only. */
export const rotateWebhook = (key: ConnectionProvider, reason: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/connections/{provider}/webhooks/rotate/", { ...o, ...provider(key), body: { reason } }),
  );
export const listInboundEvents = (
  key: ConnectionProvider,
  filters: Filters<"/api/v1/staff/connections/{provider}/events/">,
  transport?: Transport,
) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/connections/{provider}/events/", {
      ...o,
      params: { path: { provider: key }, query: query(filters) },
    }),
  ).then(paged);
export const replayInboundEvent = (key: ConnectionProvider, id: number) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/connections/{provider}/events/{id}/replay/", {
      ...o,
      params: { path: { provider: key, id } },
    }),
  );
export const replayFailedEvents = (key: ConnectionProvider, since: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/connections/{provider}/events/replay-failed/", {
      ...o,
      ...provider(key),
      body: { since },
    }),
  );
export const listCalls = (
  key: ConnectionProvider,
  filters: Filters<"/api/v1/staff/connections/{provider}/calls/">,
  transport?: Transport,
) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/connections/{provider}/calls/", {
      ...o,
      params: { path: { provider: key }, query: query(filters) },
    }),
  ).then(paged);
export const listDeadLetters = (
  key: ConnectionProvider,
  filters: Filters<"/api/v1/staff/connections/{provider}/failures/">,
  transport?: Transport,
) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/connections/{provider}/failures/", {
      ...o,
      params: { path: { provider: key }, query: query(filters) },
    }),
  ).then(paged);
export const replayDeadLetter = (key: ConnectionProvider, id: number) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/connections/{provider}/failures/{id}/replay/", {
      ...o,
      params: { path: { provider: key, id } },
    }),
  );
export const discardDeadLetter = (key: ConnectionProvider, id: number, reason: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/connections/{provider}/failures/{id}/discard/", {
      ...o,
      params: { path: { provider: key, id } },
      body: { reason },
    }),
  );

export type MessageTemplate = Schemas["Template"];

export const listTemplates = (filters: Filters<"/api/v1/staff/templates/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/templates/", { ...o, params: { query: query(filters) } }));
export const createTemplate = (body: Schemas["TemplateRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/templates/", { ...o, body }));
export const updateTemplate = (id: number, body: Schemas["PatchedTemplateRequest"]) =>
  send(undefined, (o) => api.PATCH("/api/v1/staff/templates/{id}/", { ...o, params: { path: { id } }, body }));
/** A test to your own confirmed number or address only. */
export const testTemplate = (id: number, variables: Record<string, string>) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/templates/{id}/test/", { ...o, params: { path: { id } }, body: { variables } }),
  );

export type SystemLine = Schemas["SystemStatus"];
export type SyncMonitor = Schemas["Sync"];
export type ErpLinkRow = Schemas["ErpLink"];
export type Backups = Schemas["Backups"];
export type RestoreDrill = Schemas["RestoreDrill"];
export type LogsAndTime = Schemas["Logs"];
export type Dependencies = Schemas["Dependencies"];
export type HardeningRow = Schemas["HardeningRow"];
export type ScriptChecks = Schemas["Scripts"];

export const getSync = (transport?: Transport) => send(transport, (o) => api.GET("/api/v1/staff/system/sync/", o));
export const findErpLinks = (q: string, signal?: AbortSignal) =>
  send(undefined, (o) => api.GET("/api/v1/staff/system/sync/links/", { ...o, params: { query: { q } } }), signal);
export const getBackups = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/system/backups/", o));
export const recordDrill = (body: Schemas["RestoreDrillRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/system/backups/drills/", { ...o, body }));
export const getLogs = (transport?: Transport) => send(transport, (o) => api.GET("/api/v1/staff/system/logs/", o));
export const getDependencies = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/system/dependencies/", o));
export const getHardening = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/system/hardening/", o));
export const getScripts = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/system/scripts/", o));
