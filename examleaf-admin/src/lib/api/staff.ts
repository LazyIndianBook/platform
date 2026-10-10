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

/** The accounts of the list (every tab but the guest buyers', which listGuests asks for: another shape of row). */
export const listUsers = (filters: Filters<"/api/v1/staff/users/">, transport?: Transport, signal?: AbortSignal) =>
  send(transport, (o) => api.GET("/api/v1/staff/users/", { ...o, params: { query: query(filters) } }), signal).then(
    (page) => paged(page) as Page<Customer>,
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

// ---- Tax ----

export type HsnCode = Schemas["HsnCode"];
export type HsnCodeDetail = Schemas["HsnCodeDetail"];
export type HsnRate = Schemas["HsnRate"];
export type TaxProblem = Schemas["TaxProblem"];
export type TaxDocument = Schemas["TaxDocument"];
export type TaxDocumentDetail = Schemas["TaxDocumentDetail"];
export type SeriesRegister = Schemas["SeriesRegister"];
export type ThresholdCard = Schemas["ThresholdCard"];
export type ThresholdRow = Schemas["ThresholdRow"];
export type TaxCalendar = Schemas["TaxCalendar"];
export type Taxability = Schemas["TaxabilityEnum"];

/** The HSN and SAC master by code, with today's rate and a change to come. */
export const listHsnCodes = (filters: Filters<"/api/v1/staff/tax/hsn/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/tax/hsn/", { ...o, params: { query: query(filters) } })).then(paged);
/** One code with its rates (oldest first, each with `until`) and its products. */
export const getHsnCode = (code: string, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/tax/hsn/{code}/", { ...o, params: { path: { code } } }));
/** A code new to the master, with its first rate. */
export const addHsnCode = (body: Schemas["NewHsnCodeRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/tax/hsn/", { ...o, body }));
/** A new dated rate of a code: after its latest start (the history is never rewritten). */
export const addHsnRate = (code: string, body: Schemas["NewHsnRateRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/tax/hsn/{code}/rates/", { ...o, params: { path: { code } }, body }));
/** The products whose GST disagrees with the master today, with why (the catalogue's red chip). */
export const listTaxProblems = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/tax/problems/", o));

/** Invoices (by default) or credit notes, newest first. */
export const listTaxDocuments = (filters: Filters<"/api/v1/staff/tax/documents/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/tax/documents/", { ...o, params: { query: query(filters) } })).then(
    paged,
  );
/** A document by its key (its number with dashes for its slashes): its lines, charges and Rule 46 checks. */
export const getTaxDocument = (number: string, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/tax/documents/{number}/", { ...o, params: { path: { number } } }));
/** Cancel a document with a reason (re-authenticated): it keeps its number. */
export const cancelTaxDocument = (number: string, reason: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/tax/documents/{number}/cancel/", { ...o, params: { path: { number } }, body: { reason } }),
  );
/** A document's PDF on this origin (a look at the buyer's details: the server records it). */
export const taxDocumentPdfHref = (number: string) => `/api/v1/staff/tax/documents/${encodeURIComponent(number)}/pdf/`;

/** Table 13: each series of a year (or a month of it). */
export const getSeriesRegister = (filters: Filters<"/api/v1/staff/tax/series/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/tax/series/", { ...o, params: { query: query(filters) } }));
/** The threshold card: the latest night's lines. */
export const getTaxThresholds = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/tax/thresholds/", o));
/** What is due in a month ("2026-10"; this month without one). */
export const getTaxCalendar = (month: string, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/tax/calendar/", { ...o, params: { query: query({ month }) } }));
/** The GSTR-1 export as a job (202 with the job; above the export limit it waits for an approver first). */
export const startGstr1 = (body: Schemas["Gstr1Request"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/tax/gstr1/", { ...o, body })) as Promise<Job>;
// ---- Legal and privacy ----

export type Cockpit = Schemas["Cockpit"];
export type CockpitClock = Schemas["Clock"];
export type RetentionRule = Schemas["RetentionRule"];
export type LegalHold = Schemas["LegalHold"];
export type HoldReason = Schemas["LegalHoldReasonEnum"];
export type HoldTarget = Schemas["TargetTypeEnum"];
export type Policy = Schemas["Policy"];
export type PolicyDetail = Schemas["PolicyDetail"];
export type PolicyVersion = Schemas["PolicyVersion"];
export type PolicyDiff = Schemas["PolicyDiff"];
export type PolicySlug = paths["/api/v1/staff/privacy/policies/{slug}/"]["get"]["parameters"]["path"]["slug"];
export type Disclosures = Schemas["Disclosures"];
export type DisclosureSetting = Schemas["DisclosureSetting"];
export type DarkPatternAudit = Schemas["DarkPatternAudit"];
export type DarkPatternRow = Schemas["AuditRowRequest"];
export type AccountNominee = Schemas["AccountNominee"];

/** Every clock the rules start, the consents by the notice's version, the self-audit, the legal calendar. */
export const getCockpit = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/privacy/cockpit/", o));
export const getRetention = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/privacy/retention/", o));

export const listHolds = (filters: Filters<"/api/v1/staff/privacy/holds/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/privacy/holds/", { ...o, params: { query: query(filters) } })).then(
    paged,
  );
export const getHold = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/privacy/holds/{id}/", { ...o, params: { path: { id } } }));
/** On an account (`user`) or one record (`target_type` with its number or id). */
export const createHold = (body: Schemas["HoldCreateRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/privacy/holds/", { ...o, body }));
export const releaseHold = (id: number, reason: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/privacy/holds/{id}/release/", { ...o, params: { path: { id } }, body: { reason } }),
  );

/** A customer's nominee, its contact masked (the read is recorded). */
export const getNominee = (user: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/privacy/nominees/{user}/", { ...o, params: { path: { user } } }));
/** The nominee's contact, with a reason (logged, re-authenticated, throttled). */
export const revealNominee = async (user: number, reason: string) =>
  (
    await send(undefined, (o) =>
      api.POST("/api/v1/staff/privacy/nominees/{user}/reveal/", { ...o, params: { path: { user } }, body: { reason } }),
    )
  ).contact;
/** A child's deletion confirmed by the parent by phone or letter: where the evidence is, never the document. */
export const confirmDeletionByParent = (id: number, evidence_ref: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/privacy/deletions/{id}/parent-confirmation/", {
      ...o,
      params: { path: { id } },
      body: { evidence_ref },
    }),
  );

export const listPolicies = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/privacy/policies/", o));
export const getPolicy = (slug: PolicySlug, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/privacy/policies/{slug}/", { ...o, params: { path: { slug } } }));
/** A version against the one before it. */
export const policyDiff = (slug: PolicySlug, number: number, transport?: Transport) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/privacy/policies/{slug}/versions/{number}/diff/", {
      ...o,
      params: { path: { slug, number: String(number) } },
    }),
  );
/** A new version, in force today or from a later day. */
export const publishPolicy = (slug: PolicySlug, body: Schemas["PublishRequest"]) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/privacy/policies/{slug}/publish/", { ...o, params: { path: { slug } }, body }),
  );
export const cancelScheduledPolicy = (slug: PolicySlug, reason: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/privacy/policies/{slug}/cancel-scheduled/", {
      ...o,
      params: { path: { slug } },
      body: { reason },
    }),
  );

export const getDisclosures = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/privacy/disclosures/", o));
/** The changed ones together, with one reason. */
export const saveDisclosures = (values: Record<string, string>, reason: string) =>
  send(undefined, (o) => api.PUT("/api/v1/staff/privacy/disclosures/", { ...o, body: { values, reason } }));

export const listDarkPatternAudits = (transport?: Transport) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/privacy/dark-pattern-audits/", { ...o, params: { query: { page_size: 50 } } }),
  ).then(paged);
export const createDarkPatternAudit = (year: number) =>
  send(undefined, (o) => api.POST("/api/v1/staff/privacy/dark-pattern-audits/", { ...o, body: { year } }));
export const updateDarkPatternAudit = (id: number, body: Schemas["PatchedDarkPatternAuditRequest"]) =>
  send(undefined, (o) =>
    api.PATCH("/api/v1/staff/privacy/dark-pattern-audits/{id}/", { ...o, params: { path: { id } }, body }),
  );
/** Completed once, then as it was signed: its certificate shown on the website from `effective_from`. */
export const completeDarkPatternAudit = (id: number, effective_from: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/privacy/dark-pattern-audits/{id}/complete/", {
      ...o,
      params: { path: { id } },
      body: effective_from ? { effective_from } : {},
    }),
  );
/** The signed certificate (PDF, PNG or JPEG), kept in the private storage. */
export const uploadCertificate = (id: number, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return send(undefined, (o) =>
    api.POST("/api/v1/staff/privacy/dark-pattern-audits/{id}/file/", {
      ...o,
      params: { path: { id } },
      body: form as never,
    }),
  );
};
/** Where the browser downloads the signed certificate (same origin; the read is recorded). */
export const certificateHref = (id: number) => `/api/v1/staff/privacy/dark-pattern-audits/${id}/file/`;
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
// ---- Orders ----

export type OrderRow = Schemas["OrderRow"];
export type OrderDetail = Schemas["OrderDetail"];
export type OrderLine = Schemas["OrderLine"];
export type OrderAction = Schemas["OrderAction"];
export type OrderRefundOptions = Schemas["OrderRefundOptions"];
export type OrderTimelineEntry = Schemas["OrderTimelineEntry"];
export type PackingRow = Schemas["PackingRow"];
export type ReturnRow = Schemas["ReturnRow"];
export type ReturnDetail = Schemas["ReturnDetail"];
export type QuoteRow = Schemas["QuoteRow"];
export type QuoteDetail = Schemas["QuoteDetail"];
export type ProductPick = Schemas["ProductPick"];
export type StaffOrderAsk = Schemas["StaffOrderRequest"];
export type StaffOrderPreview = Schemas["StaffOrderPreview"];
export type StaffOrderPreviewAsk = Schemas["StaffOrderPreviewAskRequest"];
export type RefundAsk = Schemas["OrderRefundAskRequest"];
export type RefundAsked = Schemas["OrderRefundAsked"];
export type ReturnAsk = Schemas["ReturnAskRequest"];
export type ShippingAddress = Schemas["ShippingAddressRequest"];
export type OrderFilters = Filters<"/api/v1/staff/orders/">;
export type OrdersJobKind = Extract<Job["kind"], `orders_${string}`>;

const orderPath = (number: string) => ({ params: { path: { number } } });

export const listOrders = (filters: OrderFilters, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/orders/", { ...o, params: { query: query(filters) } })).then(paged);
/** The record (a child's order: the server records the read as a look at a child's data). */
export const getOrder = (number: string, transport?: Transport, signal?: AbortSignal) =>
  send(transport, (o) => api.GET("/api/v1/staff/orders/{number}/", { ...o, ...orderPath(number) }), signal);
/** The packing queue, oldest first. */
export const listPacking = (filters: Filters<"/api/v1/staff/orders/packing/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/orders/packing/", { ...o, params: { query: query(filters) } })).then(
    paged,
  );

export type OrderMove = "pack" | "deliver" | "release" | "invoice/regenerate" | "invoice/resend";
/** A move without a body: the state machine refuses what cannot happen now (400, its words). */
export const moveOrder = (number: string, move: OrderMove) => {
  const path = orderPath(number);
  switch (move) {
    case "pack":
      return send(undefined, (o) => api.POST("/api/v1/staff/orders/{number}/pack/", { ...o, ...path }));
    case "deliver":
      return send(undefined, (o) => api.POST("/api/v1/staff/orders/{number}/deliver/", { ...o, ...path }));
    case "release":
      return send(undefined, (o) => api.POST("/api/v1/staff/orders/{number}/release/", { ...o, ...path }));
    case "invoice/regenerate":
      return send(undefined, (o) => api.POST("/api/v1/staff/orders/{number}/invoice/regenerate/", { ...o, ...path }));
    case "invoice/resend":
      return send(undefined, (o) => api.POST("/api/v1/staff/orders/{number}/invoice/resend/", { ...o, ...path }));
  }
};
export const shipOrder = (number: string, body: Schemas["OrderShipRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/orders/{number}/ship/", { ...o, ...orderPath(number), body }));
export const holdOrder = (number: string, reason: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/orders/{number}/hold/", { ...o, ...orderPath(number), body: { reason } }),
  );
export const tagOrder = (number: string, body: Schemas["OrderTagsRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/orders/{number}/tags/", { ...o, ...orderPath(number), body }));
export const notifyOrder = (number: string, kind: Schemas["OrderNotifyKindEnum"]) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/orders/{number}/notify/", { ...o, ...orderPath(number), body: { kind } }),
  );
/** A staff order's Razorpay link: sent (the same link again), or cancelled (the next one is new). */
export const paymentLink = (number: string, action: Schemas["OrderPaymentLinkActionEnum"]) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/orders/{number}/payment-link/", { ...o, ...orderPath(number), body: { action } }),
  );
/** Before dispatch: cancelled at once; paid online: through the refund's approval (202: approval_required). */
export const cancelOrder = (number: string, body: Schemas["OrderCancelRequest"]) => {
  const headers = once();
  return send(undefined, (o) =>
    api.POST("/api/v1/staff/orders/{number}/cancel/", {
      ...o,
      headers: { ...o.headers, ...headers },
      ...orderPath(number),
      body,
    }),
  );
};
/** 201 it ran (within your limit); 202 (approval_required) FINANCE approves it. */
export const recordOfflinePayment = (number: string, body: Schemas["OrderOfflinePaymentRequest"]) => {
  const headers = once();
  return send(undefined, (o) =>
    api.POST("/api/v1/staff/orders/{number}/offline-payment/", {
      ...o,
      headers: { ...o.headers, ...headers },
      ...orderPath(number),
      body,
    }),
  );
};
/** A refund by line: 201 it ran (within your limit), 202 (approval_required) it waits for FINANCE. The same
 *  Idempotency-Key answers the first request again (a retry after "confirm it's you"). */
export const askRefund = (number: string, body: RefundAsk) => {
  const headers = once();
  return send(undefined, (o) =>
    api.POST("/api/v1/staff/orders/{number}/refunds/", {
      ...o,
      headers: { ...o.headers, ...headers },
      ...orderPath(number),
      body,
    }),
  );
};
export const askReturn = (number: string, body: ReturnAsk) =>
  send(undefined, (o) => api.POST("/api/v1/staff/orders/{number}/returns/", { ...o, ...orderPath(number), body }));

/** A PDF of the order for staff, on this origin (the session's cookie): the packing slip, the 4×6 label, the invoice
 *  and a credit note. */
export function orderPdfHref(number: string, what: "packing-slip" | "label" | "invoice" | { note: number }): string {
  const base = `/api/v1/staff/orders/${encodeURIComponent(number)}/`;
  if (typeof what === "object") return `${base}credit-notes/${what.note}/`;
  return what === "invoice" ? `${base}invoice/` : `${base}documents/${what}/`;
}
/** The pick list of these orders as a PDF (each book once, with its copies and orders). */
export const pickList = (orders: string[]) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/orders/pick-list/", { ...o, body: { orders }, parseAs: "blob" }),
  ) as Promise<Blob>;
/** A bulk action on orders, or the export, as a background job (202): above your limit it waits for an approver. */
export const startOrdersJob = (kind: OrdersJobKind, params: Record<string, unknown>) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/jobs/", { ...o, body: { kind, params, dry_run: false } }),
  ) as Promise<Job>;

// staff orders
export const searchProducts = (q: string, signal?: AbortSignal) =>
  send(undefined, (o) => api.GET("/api/v1/staff/orders/products/", { ...o, params: { query: { q } } }), signal);
/** What the order would cost and whether it would wait for a second person: nothing is stored. */
export const previewStaffOrder = (body: StaffOrderPreviewAsk, signal?: AbortSignal) =>
  send(undefined, (o) => api.POST("/api/v1/staff/orders/preview/", { ...o, body }), signal);
/** 201: made at once (its change request's `result.order`); 202 (approval_required): nothing exists until approved. */
export const createStaffOrder = (body: StaffOrderAsk) => {
  const headers = once();
  return send(undefined, (o) =>
    api.POST("/api/v1/staff/orders/", { ...o, headers: { ...o.headers, ...headers }, body }),
  );
};

// bank refunds (FINANCE)
export const markRefundPaid = (id: number, utr: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/orders/refunds/{id}/mark-paid/", { ...o, params: { path: { id } }, body: { utr } }),
  );
/** The customer's account or UPI ID for the transfer, with a reason (logged as a look at personal data). */
export const showRefundPayee = (id: number, reason: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/orders/refunds/{id}/payee/", { ...o, params: { path: { id } }, body: { reason } }),
  );

// returns
export const listReturns = (filters: Filters<"/api/v1/staff/orders/returns/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/orders/returns/", { ...o, params: { query: query(filters) } })).then(
    paged,
  );
export const getReturn = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/orders/returns/{id}/", { ...o, params: { path: { id } } }));
export type ReturnMove =
  | { move: "approve" }
  | { move: "receive" }
  | { move: "decline"; note: string }
  | { move: "label"; courier: string; awb: string }
  | { move: "inspect"; outcome: Schemas["ReturnInspectOutcomeEnum"] };
export const moveReturn = (id: number, step: ReturnMove) => {
  const path = { params: { path: { id } } };
  switch (step.move) {
    case "approve":
      return send(undefined, (o) => api.POST("/api/v1/staff/orders/returns/{id}/approve/", { ...o, ...path }));
    case "receive":
      return send(undefined, (o) => api.POST("/api/v1/staff/orders/returns/{id}/receive/", { ...o, ...path }));
    case "decline":
      return send(undefined, (o) =>
        api.POST("/api/v1/staff/orders/returns/{id}/decline/", { ...o, ...path, body: { note: step.note } }),
      );
    case "label":
      return send(undefined, (o) =>
        api.POST("/api/v1/staff/orders/returns/{id}/label/", {
          ...o,
          ...path,
          body: { courier: step.courier, awb: step.awb },
        }),
      );
    case "inspect":
      return send(undefined, (o) =>
        api.POST("/api/v1/staff/orders/returns/{id}/inspect/", { ...o, ...path, body: { outcome: step.outcome } }),
      );
  }
};
/** A photograph of what came back (multipart: the browser sets its boundary). */
export const addReturnPhoto = (id: number, photo: File) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/orders/returns/{id}/photos/", {
      ...o,
      params: { path: { id } },
      body: { photo: photo as unknown as string },
      bodySerializer: (body) => {
        const form = new FormData();
        form.append("photo", body.photo as unknown as File);
        return form;
      },
    }),
  );
export const returnPhotoHref = (id: number, index: number) => `/api/v1/staff/orders/returns/${id}/photos/${index}/`;

// quotes
export const listQuotes = (filters: Filters<"/api/v1/staff/orders/quotes/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/orders/quotes/", { ...o, params: { query: query(filters) } })).then(
    paged,
  );
export const getQuote = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/orders/quotes/{id}/", { ...o, params: { path: { id } } }));
/** A staff order from the quote, once: 201 made, 202 (approval_required) beyond your discount limit. */
export const convertQuote = (id: number, body: Schemas["QuoteConvertRequest"]) => {
  const headers = once();
  return send(undefined, (o) =>
    api.POST("/api/v1/staff/orders/quotes/{id}/convert/", {
      ...o,
      headers: { ...o.headers, ...headers },
      params: { path: { id } },
      body,
    }),
  );
};
export const quotationHref = (id: number) => `/api/v1/staff/orders/quotes/${id}/quotation/`;
// ---- Content ----
// examleaf-web's content/staff_api.py (API.md "Content (staff)"): books and papers change at once; a question's or a
// solution's text goes to its draft, which a second person reviews and publishes; reported mistakes are triaged;
// imports from the books repository are staff jobs (kind content_import); legal deposits are recorded per library.

export type ContentSummary = Schemas["ContentSummary"];
export type ContentBook = Schemas["ContentBook"];
export type ContentBookDetail = Schemas["ContentBookDetail"];
export type ContentPaper = Schemas["ContentPaper"];
export type ContentPaperDetail = Schemas["ContentPaperDetail"];
export type ContentQuestion = Schemas["ContentQuestionDetail"];
export type ContentSolution = Schemas["ContentSolutionDetail"];
export type ContentReview = Schemas["ContentReview"];
export type ContentReviewDetail = Schemas["ContentReviewDetail"];
export type ContentReport = Schemas["ContentReport"];
export type ContentReportDetail = Schemas["ContentReportDetail"];
export type ContentErratum = Schemas["ContentErratum"];
export type ContentVersion = Schemas["ContentVersion"];
export type ContentChange = Schemas["ContentChange"];
export type LegalDeposit = Schemas["LegalDeposit"];
export type MissingDeposit = Schemas["MissingDeposit"];
export type PaperQr = Schemas["PaperQr"];
/** The records that keep a draft and a history of their own. */
export type Drafted = "questions" | "solutions";
export type Versioned = "books" | "papers" | Drafted;
export type ReportStep = "confirm" | "reject" | "fix-online" | "fix-in-printing" | "reopen";
export type ReviewDecision = "approve" | "needs-changes" | "publish";
/** A draft as the API keeps it, {field: value}: the schema types it as any JSON. */
export type Draft = Record<string, unknown>;
export const draftOf = (record: { draft: unknown }): Draft =>
  record.draft && typeof record.draft === "object" && !Array.isArray(record.draft) ? (record.draft as Draft) : {};

export const getContentSummary = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/content/summary/", o));

export const listBooks = (filters: Filters<"/api/v1/staff/content/books/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/content/books/", { ...o, params: { query: query(filters) } })).then(
    paged,
  );
export const getBook = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/content/books/{id}/", { ...o, params: { path: { id } } }));
export const createBook = (body: Schemas["ContentBookRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/content/books/", { ...o, body }));
export const updateBook = (id: number, body: Schemas["PatchedContentBookRequest"]) =>
  send(undefined, (o) => api.PATCH("/api/v1/staff/content/books/{id}/", { ...o, params: { path: { id } }, body }));

export const listPapers = (filters: Filters<"/api/v1/staff/content/papers/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/content/papers/", { ...o, params: { query: query(filters) } })).then(
    paged,
  );
export const getPaper = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/content/papers/{id}/", { ...o, params: { path: { id } } }));
/** On the site or off it, the book's open sample or not (staff.publish_paper; the sample moves from the book's other
 *  paper). */
export const publishPaper = (id: number, body: Schemas["PaperPublishRequest"]) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/content/papers/{id}/publish/", { ...o, params: { path: { id } }, body }),
  );
export const updatePaper = (id: number, body: Schemas["PatchedContentPaperDetailRequest"]) =>
  send(undefined, (o) => api.PATCH("/api/v1/staff/content/papers/{id}/", { ...o, params: { path: { id } }, body }));
/** The paper's QR code and the address it prints, with a print run's label if given (the site's report form reads
 *  it); refused (site_url_not_public) on a plain-http or local site. */
export const getPaperQr = (id: number, printing = "", transport?: Transport) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/content/papers/{id}/qr/", { ...o, params: { path: { id }, query: query({ printing }) } }),
  );

export const getQuestion = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/content/questions/{id}/", { ...o, params: { path: { id } } }));
/** The text, table, options and marks go to the draft; the tags change at once. */
export const updateQuestion = (id: number, body: Schemas["PatchedQuestionUpdateRequest"]) =>
  send(undefined, (o) => api.PATCH("/api/v1/staff/content/questions/{id}/", { ...o, params: { path: { id } }, body }));
export const getSolution = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/content/solutions/{id}/", { ...o, params: { path: { id } } }));
/** Into the draft (the live text stays until a reviewer publishes it). */
export const updateSolution = (id: number, body_md: string) =>
  send(undefined, (o) =>
    api.PATCH("/api/v1/staff/content/solutions/{id}/", { ...o, params: { path: { id } }, body: { body_md } }),
  );

/** The draft to a second person (201: the review); `discard` drops it; `rollback` undoes the last publish. */
export function draftAction(kind: Drafted, id: number, verb: "submit" | "discard" | "rollback") {
  const path = { params: { path: { id } } };
  if (kind === "questions") {
    if (verb === "submit")
      return send(undefined, (o) =>
        api.POST("/api/v1/staff/content/questions/{id}/submit/", { ...o, ...path, body: {} }),
      );
    if (verb === "discard")
      return send(undefined, (o) => api.POST("/api/v1/staff/content/questions/{id}/discard/", { ...o, ...path }));
    return send(undefined, (o) => api.POST("/api/v1/staff/content/questions/{id}/rollback/", { ...o, ...path }));
  }
  if (verb === "submit")
    return send(undefined, (o) =>
      api.POST("/api/v1/staff/content/solutions/{id}/submit/", { ...o, ...path, body: {} }),
    );
  if (verb === "discard")
    return send(undefined, (o) => api.POST("/api/v1/staff/content/solutions/{id}/discard/", { ...o, ...path }));
  return send(undefined, (o) => api.POST("/api/v1/staff/content/solutions/{id}/rollback/", { ...o, ...path }));
}

/** A record's versions, newest first, each with what it changed. */
export function listHistory(kind: Versioned, id: number, cursor = "", transport?: Transport) {
  const options = { params: { path: { id }, query: query({ cursor }) } };
  const ask = {
    books: () => send(transport, (o) => api.GET("/api/v1/staff/content/books/{id}/history/", { ...o, ...options })),
    papers: () => send(transport, (o) => api.GET("/api/v1/staff/content/papers/{id}/history/", { ...o, ...options })),
    questions: () =>
      send(transport, (o) => api.GET("/api/v1/staff/content/questions/{id}/history/", { ...o, ...options })),
    solutions: () =>
      send(transport, (o) => api.GET("/api/v1/staff/content/solutions/{id}/history/", { ...o, ...options })),
  }[kind];
  return ask().then(paged);
}

/** A version back: a book's or a paper's fields at once, a question's or a solution's text into its draft. */
export function restoreVersion(kind: Versioned, id: number, history_id: number) {
  const path = { params: { path: { id, history_id } } };
  const ask = {
    books: () =>
      send(undefined, (o) =>
        api.POST("/api/v1/staff/content/books/{id}/history/{history_id}/restore/", { ...o, ...path }),
      ),
    papers: () =>
      send(undefined, (o) =>
        api.POST("/api/v1/staff/content/papers/{id}/history/{history_id}/restore/", { ...o, ...path }),
      ),
    questions: () =>
      send(undefined, (o) =>
        api.POST("/api/v1/staff/content/questions/{id}/history/{history_id}/restore/", { ...o, ...path }),
      ),
    solutions: () =>
      send(undefined, (o) =>
        api.POST("/api/v1/staff/content/solutions/{id}/history/{history_id}/restore/", { ...o, ...path }),
      ),
  }[kind];
  return ask();
}

export const listReviews = (filters: Filters<"/api/v1/staff/content/reviews/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/content/reviews/", { ...o, params: { query: query(filters) } })).then(
    paged,
  );
export const getReview = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/content/reviews/{id}/", { ...o, params: { path: { id } } }));
/** A reviewer's decision; never on their own edit (403 own_edit). Needs changes takes a comment. */
export function decideReview(id: number, verb: ReviewDecision, comment: string, field = "") {
  const path = { params: { path: { id } } };
  if (verb === "needs-changes")
    return send(undefined, (o) =>
      api.POST("/api/v1/staff/content/reviews/{id}/needs-changes/", { ...o, ...path, body: { comment, field } }),
    );
  if (verb === "approve")
    return send(undefined, (o) =>
      api.POST("/api/v1/staff/content/reviews/{id}/approve/", { ...o, ...path, body: { comment } }),
    );
  return send(undefined, (o) =>
    api.POST("/api/v1/staff/content/reviews/{id}/publish/", { ...o, ...path, body: { comment } }),
  );
}

export const listReports = (filters: Filters<"/api/v1/staff/content/reports/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/content/reports/", { ...o, params: { query: query(filters) } })).then(
    paged,
  );
export const getReport = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/content/reports/{id}/", { ...o, params: { path: { id } } }));
export const updateReport = (id: number, body: Schemas["PatchedContentReportUpdateRequest"]) =>
  send(undefined, (o) => api.PATCH("/api/v1/staff/content/reports/{id}/", { ...o, params: { path: { id } }, body }));
/** One step of the triage: a rejection says why (staff_note), a fix in printing names it (fixed_in). */
export function reportStep(id: number, verb: ReportStep, body: Schemas["ContentTransitionRequest"] = {}) {
  const options = { params: { path: { id } }, body };
  const ask = {
    confirm: () =>
      send(undefined, (o) => api.POST("/api/v1/staff/content/reports/{id}/confirm/", { ...o, ...options })),
    reject: () => send(undefined, (o) => api.POST("/api/v1/staff/content/reports/{id}/reject/", { ...o, ...options })),
    "fix-online": () =>
      send(undefined, (o) => api.POST("/api/v1/staff/content/reports/{id}/fix-online/", { ...o, ...options })),
    "fix-in-printing": () =>
      send(undefined, (o) => api.POST("/api/v1/staff/content/reports/{id}/fix-in-printing/", { ...o, ...options })),
    reopen: () => send(undefined, (o) => api.POST("/api/v1/staff/content/reports/{id}/reopen/", { ...o, ...options })),
  }[verb];
  return ask();
}
/** The reporter emailed that the fix is published (once; their address goes then). */
export const tellReporter = (id: number) =>
  send(undefined, (o) => api.POST("/api/v1/staff/content/reports/{id}/tell/", { ...o, params: { path: { id } } }));

export const listErrata = (filters: Filters<"/api/v1/staff/content/errata/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/content/errata/", { ...o, params: { query: query(filters) } })).then(
    paged,
  );

export const listImports = (cursor: string, transport?: Transport) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/content/imports/", { ...o, params: { query: query({ cursor, page_size: 20 }) } }),
  ).then(paged);
export type ImportParams = { subject: string; commit: string; fixtures?: boolean; dry_run_job?: number };
/** A dry run, or the apply of one (naming it): a staff job (202), followed with JobProgress. */
export const startImport = (params: ImportParams, dry_run: boolean) =>
  send(undefined, (o) => api.POST("/api/v1/staff/jobs/", { ...o, body: { kind: "content_import", params, dry_run } }));

export const listDeposits = (filters: Filters<"/api/v1/staff/content/legal-deposits/">, transport?: Transport) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/content/legal-deposits/", { ...o, params: { query: query(filters) } }),
  ).then(paged);
export const listMissingDeposits = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/content/legal-deposits/missing/", o));
/** A deposit recorded: the form's fields and, if chosen, the proof's scan (multipart). */
export const recordDeposit = (form: FormData) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/content/legal-deposits/", {
      ...o,
      body: form as unknown as Schemas["LegalDepositRequest"],
      bodySerializer: (body) => body as unknown as FormData,
    }),
  );
/** The proof's scan, opened on this origin (the file, or the private bucket's own link). */
export const depositProofHref = (id: number) => `/api/v1/staff/content/legal-deposits/${id}/proof/`;
// ---- Support ----

export type Ticket = Schemas["Ticket"];
export type TicketRecord = Schemas["TicketRecord"];
export type TicketMessage = Schemas["Message"];
export type TicketClock = Schemas["TicketClock"];
export type TicketSidebar = Schemas["Sidebar"];
export type SidebarOrder = Schemas["SidebarOrder"];
export type SavedReply = Schemas["SavedReply"];
export type SavedReplyText = Schemas["SavedReplyText"];
export type Agent = Schemas["Agent"];
export type SupportSummary = Schemas["SupportSummary"];
export type TicketStatus = Schemas["TicketStatusEnum"];
export type TicketCategory = Schemas["TicketCategoryEnum"];
export type TicketLanguage = Schemas["LanguageEnum"];
export type TicketFilters = Filters<"/api/v1/staff/support/tickets/">;
/** A ticket's path parameter: its number (SR-2026-000123) or, from the inbox and the audit log, its id. */
const ticketPath = (number: string) => ({ params: { path: { number } } });

/** The queue, the next legal clock first (spam only by its status; on a live site a test order's only with `test`). */
export const listTickets = (filters: TicketFilters, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/support/tickets/", { ...o, params: { query: query(filters) } })).then(
    paged,
  );
/** A ticket by its number (or id): its conversation, clocks, sidebar and saved replies. The server records the read
 *  (a child's as such) and marks the reader's mentions on it done. */
export const getTicket = (number: string, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/support/tickets/{number}/", { ...o, ...ticketPath(number) }));
/** A call, a WhatsApp message, an NCH complaint (its docket) or an email, logged: the new ticket. */
export const logTicket = (body: Schemas["TicketCreateRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/support/tickets/", { ...o, body }));
export const changeTicket = (number: string, body: Schemas["PatchedTicketChangeRequest"]) =>
  send(undefined, (o) => api.PATCH("/api/v1/staff/support/tickets/{number}/", { ...o, ...ticketPath(number), body }));
/** A reply (emailed, or a call or WhatsApp message recorded) or an internal note with its mentions. */
export const addTicketMessage = (number: string, body: Schemas["MessageCreateRequest"]) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/support/tickets/{number}/messages/", { ...o, ...ticketPath(number), body }),
  );
export const assignTicket = (number: string, assignee: number | null) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/support/tickets/{number}/assign/", { ...o, ...ticketPath(number), body: { assignee } }),
  );
export const claimTicket = (number: string) =>
  send(undefined, (o) => api.POST("/api/v1/staff/support/tickets/{number}/claim/", { ...o, ...ticketPath(number) }));
/** Moves it on (its `transitions`); resolving or closing asks for its `closing_fields`, refused field by field. */
export const setTicketStatus = (number: string, body: Schemas["StatusRequest"]) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/support/tickets/{number}/status/", { ...o, ...ticketPath(number), body }),
  );
export const reopenTicket = (number: string) =>
  send(undefined, (o) => api.POST("/api/v1/staff/support/tickets/{number}/reopen/", { ...o, ...ticketPath(number) }));
/** The acknowledgement sent again; with `note`, recorded as given another way (on the call). */
export const acknowledgeTicket = (number: string, note = "") =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/support/tickets/{number}/acknowledge/", { ...o, ...ticketPath(number), body: { note } }),
  );
/** The requester's email address or mobile number, with a reason (logged, re-authenticated, throttled). */
export async function revealRequester(number: string, field: "email" | "phone", reason: string): Promise<string> {
  const shown = await send(undefined, (o) =>
    api.POST("/api/v1/staff/support/tickets/{number}/reveal/", {
      ...o,
      ...ticketPath(number),
      body: { show: [field], reason },
    }),
  );
  return shown[field] ?? "";
}
/** A file of the conversation, opened through the API (a link signed for 5 minutes, or the file). */
export const ticketAttachmentHref = (number: string, attachment: number) =>
  `/api/v1/staff/support/tickets/${encodeURIComponent(number)}/attachments/${attachment}/`;

/** A refund through the shop's (201 done; 202 approval_required above your limit): by `amount`, or by `lines`. */
export const refundFromTicket = (number: string, body: Schemas["RefundRequest"]) => {
  const headers = once();
  return send(undefined, (o) =>
    api.POST("/api/v1/staff/support/tickets/{number}/refund/", {
      ...o,
      headers: { ...o.headers, ...headers },
      ...ticketPath(number),
      body,
    }),
  );
};
/** Cancels an order: paid online, through its refund (as refundFromTicket); otherwise at once ({order, status}). */
export const cancelFromTicket = (number: string, body: Schemas["TicketCancelRequest"]) => {
  const headers = once();
  return send(undefined, (o) =>
    api.POST("/api/v1/staff/support/tickets/{number}/cancel/", {
      ...o,
      headers: { ...o.headers, ...headers },
      ...ticketPath(number),
      body,
    }),
  );
};
export const resendInvoice = (number: string, order: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/support/tickets/{number}/resend-invoice/", {
      ...o,
      ...ticketPath(number),
      body: { order },
    }),
  );
export const resendConfirmation = (number: string, order: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/support/tickets/{number}/resend-confirmation/", {
      ...o,
      ...ticketPath(number),
      body: { order },
    }),
  );
export const extendAccess = (number: string, body: Schemas["ExtendRequest"]) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/support/tickets/{number}/extend-access/", { ...o, ...ticketPath(number), body }),
  );
/** A book code looked up by its digest (never kept): one line to answer with. */
export const lookUpBookCode = (number: string, code: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/support/tickets/{number}/book-code/", { ...o, ...ticketPath(number), body: { code } }),
  );
/** A data request from a grievance or privacy ticket (the rights queue's own clocks, from when the ticket came). */
export const startDataRequest = (number: string, body: Schemas["DataRequestStartRequest"]) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/support/tickets/{number}/data-request/", { ...o, ...ticketPath(number), body }),
  );

/** Who a ticket may be given to or a note may name (`handles`: may be given tickets). */
export const listAgents = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/support/agents/", o));
/** The module's numbers over `days` to today; the backlog and what is overdue now. */
export const getSupportSummary = (days: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/support/summary/", { ...o, params: { query: { days } } }));

export const listSavedReplies = (filters: Filters<"/api/v1/staff/support/saved-replies/">, transport?: Transport) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/support/saved-replies/", { ...o, params: { query: query(filters) } }),
  ).then(paged);
export const createSavedReply = (body: Schemas["SavedReplyRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/support/saved-replies/", { ...o, body }));
export const updateSavedReply = (id: number, body: Schemas["PatchedSavedReplyRequest"]) =>
  send(undefined, (o) =>
    api.PATCH("/api/v1/staff/support/saved-replies/{id}/", { ...o, params: { path: { id } }, body }),
  );
/** Into the bin for 30 days (restoreSavedReply takes it out). */
export const deleteSavedReply = (id: number) =>
  send(undefined, (o) => api.DELETE("/api/v1/staff/support/saved-replies/{id}/", { ...o, params: { path: { id } } }));
export const restoreSavedReply = (id: number) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/support/saved-replies/{id}/restore/", { ...o, params: { path: { id } } }),
  );

/** The grievance register as a background job (a dated CSV): the days received, both optional; above your export
 *  limit the job waits for an approver (its change_request_id). */
export const exportGrievances = (params: { from?: string; until?: string }) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/jobs/", { ...o, body: { kind: "grievance_export", params, dry_run: false } }),
  );

// ---- Finance ----

export type FinanceToday = Schemas["FinanceToday"];
export type FinanceTodayRow = Schemas["FinanceTodayRow"];
export type FinancePayment = Schemas["FinancePayment"];
export type FinancePaymentDetail = Schemas["FinancePaymentDetail"];
export type FinanceReconciled = Schemas["FinanceReconciled"];
export type FinanceRequestRow = Schemas["FinanceRequestRow"];
export type FinanceLink = Schemas["FinanceLink"];
export type FinanceLinkAnswer = Schemas["FinanceLinkAnswer"];
export type FinanceSettlement = Schemas["FinanceSettlement"];
export type FinanceSettlementDetail = Schemas["FinanceSettlementDetail"];
export type FinanceSettlementLine = Schemas["FinanceSettlementLine"];
export type FinanceDocumentErp = Schemas["FinanceDocumentErp"];
export type FinanceLinkAsk = Schemas["FinanceLinkAskRequest"];
export type FinanceMatch = Schemas["FinanceMatchRequest"];

/** What FINANCE has to do today: a row a duty, each for whoever may see its records; test mode left out. */
export const getFinanceToday = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/finance/today/", o));

/** Payments, newest first (`stuck=true`: those waiting on Razorpay too long). */
export const listFinancePayments = (filters: Filters<"/api/v1/staff/finance/payments/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/finance/payments/", { ...o, params: { query: query(filters) } })).then(
    paged,
  );
/** A payment with its refunds, the webhooks seen and its timeline (a child's order's: a logged read). */
export const getFinancePayment = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/finance/payments/{id}/", { ...o, params: { path: { id } } }));
/** Ask Razorpay again what became of the payment's order: answered with what changed (503: not reachable). */
export const reconcileFinancePayment = (id: number) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/finance/payments/{id}/reconcile/", { ...o, params: { path: { id } } }),
  );

/** Offline payments: `state=waiting` the change requests waiting for FINANCE, else those recorded. */
export const listOfflinePayments = (
  filters: Filters<"/api/v1/staff/finance/offline-payments/">,
  transport?: Transport,
) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/finance/offline-payments/", { ...o, params: { query: query(filters) } }),
  ).then(paged);
/** Refunds by state and method; `state=waiting`: the change requests waiting for FINANCE. */
export const listFinanceRefunds = (filters: Filters<"/api/v1/staff/finance/refunds/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/finance/refunds/", { ...o, params: { query: query(filters) } })).then(
    paged,
  );

/** Payment links: the staff orders' (`kind=order`, the default) or the B2B invoices' (`kind=invoice`). */
export const listPaymentLinks = (filters: Filters<"/api/v1/staff/finance/payment-links/">, transport?: Transport) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/finance/payment-links/", { ...o, params: { query: query(filters) } }),
  ).then(paged);
/** An order's link sent (made once, then the same again) or cancelled; a B2B invoice's made (201) or cancelled. */
export const askPaymentLink = (body: FinanceLinkAsk) =>
  send(undefined, (o) => api.POST("/api/v1/staff/finance/payment-links/", { ...o, body }));
/** A B2B invoice's link asked of Razorpay again (its webhook lost). */
export const reconcileInvoiceLink = (id: number) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/finance/payment-links/invoices/{id}/reconcile/", { ...o, params: { path: { id } } }),
  );
/** A B2B invoice's payment posted in ERPNext by hand: the Payment Entry's name recorded (its inbox item done). */
export const markInvoiceLinkPosted = (id: number, erpName: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/finance/payment-links/invoices/{id}/posted/", {
      ...o,
      params: { path: { id } },
      body: { erp_name: erpName },
    }),
  );

/** Razorpay's settlements, newest day first. */
export const listSettlements = (filters: Filters<"/api/v1/staff/finance/settlements/">, transport?: Transport) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/finance/settlements/", { ...o, params: { query: query(filters) } }),
  ).then(paged);
/** A settlement with its counts and its ERPNext entry. */
export const getSettlement = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/finance/settlements/{id}/", { ...o, params: { path: { id } } }));
/** A settlement's lines in Razorpay's order (`matched=false`: those not ours yet). */
export const listSettlementLines = (
  id: number,
  filters: Filters<"/api/v1/staff/finance/settlements/{settlement}/lines/">,
  transport?: Transport,
) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/finance/settlements/{settlement}/lines/", {
      ...o,
      params: { path: { settlement: String(id) }, query: query(filters) },
    }),
  ).then(paged);
/** A line matched by hand: to a payment, a refund, or an adjustment accepted as it is; with a note (audited). */
export const matchSettlementLine = (id: number, body: FinanceMatch) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/finance/settlements/{id}/match/", { ...o, params: { path: { id } }, body }),
  );
/** A day of Razorpay's settlements fetched as a background job (202 with the job). */
export const fetchSettlements = (body: Schemas["FinanceFetchRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/finance/settlements/fetch/", { ...o, body })) as Promise<Job>;

/** An invoice's or credit note's ERPNext mirror (its number, dashes for its slashes). */
export const getDocumentErp = (number: string, transport?: Transport) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/finance/documents/{number}/erp/", { ...o, params: { path: { number } } }),
  );
// ---- Home and reports ----

export type Home = Schemas["Home"];
export type HomeCard = Schemas["HomeCard"];
export type HomePeriod = "today" | "week" | "month";

/** Home's cards for the person asking: the totals over the period (the last 7 days when left out), the queues as they
 *  stand now, each card with its definition and the list or report it counts. */
export const getHome = (period: HomePeriod | "", transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/home/", { ...o, params: { query: query({ period }) } }));

export type ReportIndex = Schemas["ReportIndex"];
export type ReportIndexItem = Schemas["ReportIndexItem"];
export type ReportColumn = Schemas["ReportColumn"];
export type SalesReport = Schemas["ReportSales"];
export type PlaceReport = Schemas["ReportPlace"];
export type CodesReport = Schemas["ReportCodes"];
export type HealthReport = Schemas["ReportHealth"];
export type CodReport = Schemas["ReportCod"];
export type SettlementsReport = Schemas["ReportSettlements"];
export type PrintRun = Schemas["ReportPrintRun"];
export type PrintRunInputs = Schemas["ReportPrintRunRequestRequest"];

export const getReportIndex = (transport?: Transport) => send(transport, (o) => api.GET("/api/v1/staff/reports/", o));
export const getSalesReport = (filters: Filters<"/api/v1/staff/reports/sales/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/reports/sales/", { ...o, params: { query: query(filters) } }));
export const getPlaceReport = (filters: Filters<"/api/v1/staff/reports/sales-by-place/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/reports/sales-by-place/", { ...o, params: { query: query(filters) } }));
export const getCodesReport = (filters: Filters<"/api/v1/staff/reports/codes/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/reports/codes/", { ...o, params: { query: query(filters) } }));
export const getHealthReport = (filters: Filters<"/api/v1/staff/reports/course-health/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/reports/course-health/", { ...o, params: { query: query(filters) } }));
export const getCodReport = (filters: Filters<"/api/v1/staff/reports/cod/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/reports/cod/", { ...o, params: { query: query(filters) } }));
export const getSettlementsReport = (filters: Filters<"/api/v1/staff/reports/settlements/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/reports/settlements/", { ...o, params: { query: query(filters) } }));

/** The newsvendor sum again with the inputs typed: the critical ratio, and the size at that percentile of the newest
 *  forecast, less the copies in stock and on order. Nothing is stored. */
export const recomputePrintRun = (body: PrintRunInputs) =>
  send(undefined, (o) => api.POST("/api/v1/staff/reports/print-run/", { ...o, body }));

/** A report as a file: a background job (a CSV with the filters it was read with and the person's number at the end);
 *  above your export limit it waits for an approver (the job's change_request_id). `report` is a key of the index. */
export const exportReport = (report: string, filters: Record<string, string>) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/jobs/", {
      ...o,
      body: { kind: "report_export", params: { report, filters }, dry_run: false },
    }),
  );

// The insights' own lists (/api/v1/insights/, numbered pages), which the reports draw and do not rebuild.
export type Forecast = Schemas["Forecast"];
export type PrintRunAdvice = Schemas["PrintRunAdvice"];
export type CohortStat = Schemas["CohortStat"];
/** What an insights list says besides its rows and its page: how the rows were made (API.md "Insights (staff)"; the
 *  schema does not type these four). */
export type InsightsAbout = {
  method: string;
  data_as_of: string | null;
  backtest: Schemas["ReportBacktest"] | null;
  /** false while a prediction has not beaten the seasonal naive in the backtest: the panel labels it untested */
  shown: boolean;
};
export type InsightsPage<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
} & InsightsAbout;
const insights = <T>(page: { count: number; next?: string | null; previous?: string | null; results: T[] }) =>
  page as unknown as InsightsPage<T>;

type InsightsFilters = { page?: number; page_size?: number; product?: string; district?: string };

export const listForecasts = (filters: InsightsFilters, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/insights/forecasts/", { ...o, params: { query: query(filters) } })).then(
    insights,
  );
export const listPrintRuns = (filters: InsightsFilters, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/insights/print-runs/", { ...o, params: { query: query(filters) } })).then(
    insights,
  );
export const listCohorts = (filters: InsightsFilters, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/insights/cohorts/", { ...o, params: { query: query(filters) } })).then(
    insights,
  );
// ---- Catalogue ----

export type CatalogueProductRow = Schemas["CatalogueProductRow"];
export type CatalogueProduct = Schemas["CatalogueProduct"];
export type CatalogueProductChange = Schemas["PatchedCatalogueProductWriteRequest"];
export type CatalogueNewProduct = Schemas["CatalogueProductWriteRequest"];
export type CataloguePriorPrice = Schemas["CataloguePriorPrice"];
export type CatalogueVersion = Schemas["CatalogueVersion"];
export type CatalogueStockRow = Schemas["CatalogueStockRow"];
export type CatalogueAlertRow = Schemas["CatalogueAlertRow"];
export type CatalogueCoupon = Schemas["CatalogueCoupon"];
export type CatalogueCouponInput = Schemas["CatalogueCouponWriteRequest"];
export type CatalogueCode = Schemas["CatalogueCode"];
export type CatalogueOffer = Schemas["CatalogueOffer"];
export type CatalogueOfferInput = Schemas["CatalogueOfferWriteRequest"];
export type CatalogueShippingRate = Schemas["CatalogueShippingRate"];
export type CatalogueRateInput = Schemas["CatalogueShippingRateWriteRequest"];
export type CatalogueCategory = Schemas["CatalogueCategory"];
export type CatalogueCollection = Schemas["CatalogueCollection"];
export type CatalogueSummary = Schemas["CatalogueSummary"];
export type CatalogueOptions = Schemas["CatalogueOptions"];
export type CatalogueJobKind = "coupon_codes" | "product_import" | "product_export";
/** A price change answered 202: the rest saved, the price waiting for its approver. */
export type CataloguePriceWaiting = Schemas["CatalogueProductPriceWaiting"];

const CATALOGUE = "/api/v1/staff/catalogue/";

/** The products with their chips (the GST against the master, the courier's data, the stock). */
export const listCatalogueProducts = (filters: Filters<"/api/v1/staff/catalogue/products/">, transport?: Transport) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/catalogue/products/", { ...o, params: { query: query(filters) } }),
  ).then(paged);
/** A product by section, with the approvals waiting about it. */
export const getCatalogueProduct = (slug: string, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/catalogue/products/{slug}/", { ...o, params: { path: { slug } } }));
/** A new product, made at its MRP; a lower price follows through its approval (`price_change`). */
export const createCatalogueProduct = (body: CatalogueNewProduct) => {
  const headers = once();
  return send(undefined, (o) =>
    api.POST("/api/v1/staff/catalogue/products/", { ...o, headers: { ...o.headers, ...headers }, body }),
  );
};
/** A change: the page's fields at once; a price within your limit too, beyond it the answer is the waiting change
 *  request (`price_change`) with the rest saved. */
export const updateCatalogueProduct = (slug: string, body: CatalogueProductChange) => {
  const headers = once();
  return send(undefined, (o) =>
    api.PATCH("/api/v1/staff/catalogue/products/{slug}/", {
      ...o,
      headers: { ...o.headers, ...headers },
      params: { path: { slug } },
      body,
    }),
  ) as Promise<CatalogueProduct | CataloguePriceWaiting>;
};
/** What a selling price would show if set now (the lowest of the 30 days before it): nothing changes. */
export const getPriorPrice = (slug: string, price: string, signal?: AbortSignal) =>
  send(
    undefined,
    (o) =>
      api.GET("/api/v1/staff/catalogue/products/{slug}/prior-price/", {
        ...o,
        params: { path: { slug }, query: { price } },
      }),
    signal,
  );
export const productHistory = (slug: string, cursor: string, transport?: Transport) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/catalogue/products/{slug}/history/", {
      ...o,
      params: { path: { slug }, query: query({ cursor }) },
    }),
  ).then(paged);
/** A picture (multipart: the browser sets its boundary): the form's `image`, `alt`, `position`, `as_cover`. */
export const addProductPicture = (slug: string, form: FormData) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/catalogue/products/{slug}/pictures/", {
      ...o,
      params: { path: { slug } },
      body: form as unknown as Schemas["CataloguePictureUploadRequest"],
      bodySerializer: (body) => body as unknown as FormData,
    }),
  );
export const changeProductPicture = (
  slug: string,
  picture: number,
  body: Schemas["PatchedCataloguePictureChangeRequest"],
) =>
  send(undefined, (o) =>
    api.PATCH("/api/v1/staff/catalogue/products/{slug}/pictures/{picture}/", {
      ...o,
      params: { path: { slug, picture } },
      body,
    }),
  );
export const removeProductPicture = (slug: string, picture: number) =>
  send(undefined, (o) =>
    api.DELETE("/api/v1/staff/catalogue/products/{slug}/pictures/{picture}/", {
      ...o,
      params: { path: { slug, picture } },
    }),
  );
/** A bundle's books and copies of each, all at once. */
export const setBundleLines = (slug: string, lines: Schemas["CatalogueBundleLineRequest"][]) =>
  send(undefined, (o) =>
    api.PUT("/api/v1/staff/catalogue/products/{slug}/bundle/", { ...o, params: { path: { slug } }, body: { lines } }),
  );
/** A book's copies set by hand with the reason; `expected`, the count read: refused when orders changed it since. */
export const setProductStock = (slug: string, body: Schemas["CatalogueStockSetRequest"]) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/catalogue/products/{slug}/stock/", { ...o, params: { path: { slug } }, body }),
  );
/** Its ISBN's EAN-13 barcode (SVG, sized for print), on this origin. */
export const barcodeHref = (slug: string) => `${CATALOGUE}products/${encodeURIComponent(slug)}/barcode.svg/`;

/** The books' copies, the fewest first, with what orders hold. */
export const listCatalogueStock = (filters: Filters<"/api/v1/staff/catalogue/stock/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/catalogue/stock/", { ...o, params: { query: query(filters) } })).then(
    paged,
  );
/** Back-in-stock requests by product (never who asked). */
export const listStockAlerts = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/catalogue/stock-alerts/", o)).then(paged);

export const listCoupons = (filters: Filters<"/api/v1/staff/catalogue/coupons/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/catalogue/coupons/", { ...o, params: { query: query(filters) } })).then(
    paged,
  );
export const getCoupon = (code: string, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/catalogue/coupons/{code}/", { ...o, params: { path: { code } } }));
/** A new coupon through coupon.create: its change request, executed within your limit; beyond it the error
 *  approval_required (a 202: it waits for FINANCE). */
export const createCoupon = (body: CatalogueCouponInput) => {
  const headers = once();
  return send(undefined, (o) =>
    api.POST("/api/v1/staff/catalogue/coupons/", { ...o, headers: { ...o.headers, ...headers }, body }),
  );
};
/** The fields that change, through coupon.change (a deeper discount beyond your limit: approval_required). */
export const updateCoupon = (code: string, body: Schemas["PatchedCatalogueCouponWriteRequest"]) => {
  const headers = once();
  return send(undefined, (o) =>
    api.PATCH("/api/v1/staff/catalogue/coupons/{code}/", {
      ...o,
      headers: { ...o.headers, ...headers },
      params: { path: { code } },
      body,
    }),
  );
};
export const listCouponCodes = (
  code: string,
  filters: { used?: string; job?: string; cursor?: string },
  transport?: Transport,
) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/catalogue/coupons/{code}/codes/", {
      ...o,
      params: { path: { code }, query: query(filters) },
    }),
  ).then(paged);
export const couponHistory = (code: string, transport?: Transport) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/catalogue/coupons/{code}/history/", { ...o, params: { path: { code } } }),
  ).then(paged);

export const listOffers = (filters: Filters<"/api/v1/staff/catalogue/offers/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/catalogue/offers/", { ...o, params: { query: query(filters) } })).then(
    paged,
  );
export const getOffer = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/catalogue/offers/{id}/", { ...o, params: { path: { id } } }));
/** A new offer through offer.create (beyond your limit: approval_required). */
export const createOffer = (body: CatalogueOfferInput) => {
  const headers = once();
  return send(undefined, (o) =>
    api.POST("/api/v1/staff/catalogue/offers/", { ...o, headers: { ...o.headers, ...headers }, body }),
  );
};
export const updateOffer = (id: number, body: Schemas["PatchedCatalogueOfferWriteRequest"]) => {
  const headers = once();
  return send(undefined, (o) =>
    api.PATCH("/api/v1/staff/catalogue/offers/{id}/", {
      ...o,
      headers: { ...o.headers, ...headers },
      params: { path: { id } },
      body,
    }),
  );
};
export const offerHistory = (id: number, transport?: Transport) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/catalogue/offers/{id}/history/", { ...o, params: { path: { id } } }),
  ).then(paged);

export const listShippingRates = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/catalogue/shipping-rates/", o)).then(paged);
export const getShippingRate = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/catalogue/shipping-rates/{id}/", { ...o, params: { path: { id } } }));
export const createShippingRate = (body: CatalogueRateInput) =>
  send(undefined, (o) => api.POST("/api/v1/staff/catalogue/shipping-rates/", { ...o, body }));
export const updateShippingRate = (id: number, body: Schemas["PatchedCatalogueShippingRateWriteRequest"]) =>
  send(undefined, (o) =>
    api.PATCH("/api/v1/staff/catalogue/shipping-rates/{id}/", { ...o, params: { path: { id } }, body }),
  );
export const rateHistory = (id: number, transport?: Transport) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/catalogue/shipping-rates/{id}/history/", { ...o, params: { path: { id } } }),
  ).then(paged);

/** The shelves in tree order (each followed by those under it). */
export const listCategories = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/catalogue/categories/", o));
export const createCategory = (body: Schemas["CatalogueCategoryWriteRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/catalogue/categories/", { ...o, body }));
export const updateCategory = (slug: string, body: Schemas["PatchedCatalogueCategoryWriteRequest"]) =>
  send(undefined, (o) =>
    api.PATCH("/api/v1/staff/catalogue/categories/{slug}/", { ...o, params: { path: { slug } }, body }),
  );
/** It moves with what is under it: under `target` (first or last), beside it, or to the top (no target). */
export const moveCategory = (slug: string, body: Schemas["CatalogueCategoryMoveRequest"]) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/catalogue/categories/{slug}/move/", { ...o, params: { path: { slug } }, body }),
  );

export const listCollections = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/catalogue/collections/", o)).then(paged);
export const createCollection = (body: Schemas["CatalogueCollectionWriteRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/catalogue/collections/", { ...o, body }));
export const updateCollection = (slug: string, body: Schemas["PatchedCatalogueCollectionWriteRequest"]) =>
  send(undefined, (o) =>
    api.PATCH("/api/v1/staff/catalogue/collections/{slug}/", { ...o, params: { path: { slug } }, body }),
  );

/** The module's home: what waits. */
export const getCatalogueSummary = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/catalogue/summary/", o));
/** The forms' choices in one answer. */
export const getCatalogueOptions = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/catalogue/options/", o));

/** A product CSV uploaded and its dry run started (202 with the job). */
export const uploadProductImport = (file: File) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/catalogue/import/", {
      ...o,
      body: { file: file as unknown as string },
      bodySerializer: (body) => {
        const form = new FormData();
        form.append("file", body.file as unknown as File);
        return form;
      },
    }),
  ) as Promise<Job>;
/** The catalogue's jobs (202 with the job): a school's codes, an import's apply (naming its dry run), the export of the
 *  list's filters. Above your limit the job waits for an approver first. */
export const startCatalogueJob = (kind: CatalogueJobKind, params: Record<string, unknown>) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/jobs/", { ...o, body: { kind, params, dry_run: false } }),
  ) as Promise<Job>;
// ---- Course ----
// examleaf-web's learn/staff_api.py (API.md "Course (staff)"): a subject's outline (chapters, revisions, clips, cards,
// quiz items) with its moves, a revision's review and publish, the 30-day bin, the quiz bank, entitlements, the print
// runs' book codes and the lookup, the codes report, one learner's page (logged). Bulk work is a staff job: the bank's
// metadata (`item_metadata`) and entitlements (`entitlement.grant`, `.extend`, `.revoke`), a dry run first.

export type CourseSubject = Schemas["CourseSubject"];
export type CourseOutline = Schemas["CourseOutline"];
export type CourseOutlineChapter = Schemas["CourseOutlineChapter"];
export type CourseOutlineClip = Schemas["CourseOutlineClip"];
export type CourseRevision = Schemas["CourseRevision"];
export type CourseClip = Schemas["CourseClip"];
export type CourseCard = Schemas["CourseCard"];
export type CourseItem = Schemas["CourseItem"];
export type CourseItemRow = Schemas["CourseItemRow"];
export type CourseItemStats = Schemas["CourseItemStats"];
export type CourseVersion = Schemas["CourseVersion"];
export type CourseBinRow = Schemas["CourseBinRow"];
export type CourseEntitlement = Schemas["CourseEntitlement"];
export type CourseEntitlementDetail = Schemas["CourseEntitlementDetail"];
export type CourseBatch = Schemas["CourseBatch"];
export type CourseBatchDetail = Schemas["CourseBatchDetail"];
export type CourseCodeLookup = Schemas["CourseCodeLookup"];
export type CourseReport = Schemas["CourseReport"];
export type CourseLearner = Schemas["CourseLearner"];
/** The bin's and the moves' kinds of row, as the paths name them. */
export type CourseRowKind = Schemas["CourseRowKindEnum"];
export type CourseMove = Schemas["CourseMoveEnum"];
export type CourseTransition = Schemas["CourseTransitionEnum"];
/** The bulk actions of the course (the approvals' actions a bulk job names). */
export type CourseBulkAction = "item_metadata" | "entitlement.grant" | "entitlement.extend" | "entitlement.revoke";

const rowPath = (id: number) => ({ params: { path: { id } } });

export const listCourseSubjects = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/course/subjects/", o));
export const getCourseOutline = (subject: number, transport?: Transport) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/course/subjects/{subject}/outline/", { ...o, params: { path: { subject } } }),
  );
export const changeChapter = (id: number, body: Schemas["PatchedCourseChapterRequest"]) =>
  send(undefined, (o) => api.PATCH("/api/v1/staff/course/chapters/{id}/", { ...o, ...rowPath(id), body }));

export const getRevision = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/course/revisions/{id}/", { ...o, ...rowPath(id) }));
export const changeRevision = (id: number, body: Schemas["PatchedCourseRevisionRequest"]) =>
  send(undefined, (o) => api.PATCH("/api/v1/staff/course/revisions/{id}/", { ...o, ...rowPath(id), body }));
/** One move of a revision's review (its `transitions` say which the reader may make now). */
export function moveRevision(id: number, move: CourseTransition, input: { comment?: string; publishAt?: string }) {
  switch (move) {
    case "submit":
      return send(undefined, (o) => api.POST("/api/v1/staff/course/revisions/{id}/submit/", { ...o, ...rowPath(id) }));
    case "approve":
      return send(undefined, (o) =>
        api.POST("/api/v1/staff/course/revisions/{id}/approve/", {
          ...o,
          ...rowPath(id),
          body: { comment: input.comment ?? "" },
        }),
      );
    case "needs_changes":
      return send(undefined, (o) =>
        api.POST("/api/v1/staff/course/revisions/{id}/needs-changes/", {
          ...o,
          ...rowPath(id),
          body: { comment: input.comment ?? "" },
        }),
      );
    case "publish":
      return send(undefined, (o) =>
        api.POST("/api/v1/staff/course/revisions/{id}/publish/", {
          ...o,
          ...rowPath(id),
          body: { publish_at: input.publishAt || null },
        }),
      );
    case "unpublish":
      return send(undefined, (o) =>
        api.POST("/api/v1/staff/course/revisions/{id}/unpublish/", { ...o, ...rowPath(id) }),
      );
  }
}

export const getClip = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/course/clips/{id}/", { ...o, ...rowPath(id) }));
export const changeClip = (id: number, body: Schemas["PatchedCourseClipRequest"]) =>
  send(undefined, (o) => api.PATCH("/api/v1/staff/course/clips/{id}/", { ...o, ...rowPath(id), body }));
/** Its video processed again: a failed clip, or one stuck in processing. */
export const retryClip = (id: number) =>
  send(undefined, (o) => api.POST("/api/v1/staff/course/clips/{id}/retry/", { ...o, ...rowPath(id) }));
export const getCard = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/course/cards/{id}/", { ...o, ...rowPath(id) }));
export const changeCard = (id: number, body: Schemas["PatchedCourseCardRequest"]) =>
  send(undefined, (o) => api.PATCH("/api/v1/staff/course/cards/{id}/", { ...o, ...rowPath(id), body }));

/** A clip, card or quiz item moved first, last, or before or after a sibling (the API numbers them again). */
export function moveRow(kind: CourseRowKind, id: number, to: CourseMove, target?: number | null) {
  const body = { to, target: target ?? null };
  if (kind === "clips")
    return send(undefined, (o) => api.POST("/api/v1/staff/course/clips/{id}/move/", { ...o, ...rowPath(id), body }));
  if (kind === "cards")
    return send(undefined, (o) => api.POST("/api/v1/staff/course/cards/{id}/move/", { ...o, ...rowPath(id), body }));
  return send(undefined, (o) => api.POST("/api/v1/staff/course/items/{id}/move/", { ...o, ...rowPath(id), body }));
}
/** Into the bin for 30 days (a clip keeps its files): the bin's row, with `bin_until`. */
export function deleteRow(kind: CourseRowKind, id: number) {
  if (kind === "clips")
    return send(undefined, (o) => api.DELETE("/api/v1/staff/course/clips/{id}/", { ...o, ...rowPath(id) }));
  if (kind === "cards")
    return send(undefined, (o) => api.DELETE("/api/v1/staff/course/cards/{id}/", { ...o, ...rowPath(id) }));
  return send(undefined, (o) => api.DELETE("/api/v1/staff/course/items/{id}/", { ...o, ...rowPath(id) }));
}
/** Out of the bin, back at its place (within 30 days). */
export async function restoreRow(kind: CourseRowKind, id: number): Promise<void> {
  if (kind === "clips")
    await send(undefined, (o) => api.POST("/api/v1/staff/course/clips/{id}/restore/", { ...o, ...rowPath(id) }));
  else if (kind === "cards")
    await send(undefined, (o) => api.POST("/api/v1/staff/course/cards/{id}/restore/", { ...o, ...rowPath(id) }));
  else await send(undefined, (o) => api.POST("/api/v1/staff/course/items/{id}/restore/", { ...o, ...rowPath(id) }));
}
export const listBin = (filters: Filters<"/api/v1/staff/course/bin/">, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/course/bin/", { ...o, params: { query: query(filters) } })).then(paged);

export type CourseItemFilters = Filters<"/api/v1/staff/course/items/">;
export const listItems = (filters: CourseItemFilters, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/course/items/", { ...o, params: { query: query(filters) } })).then(
    paged,
  );
export const getItem = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/course/items/{id}/", { ...o, ...rowPath(id) }));
export const changeItem = (id: number, body: Schemas["PatchedCourseItemRequest"]) =>
  send(undefined, (o) => api.PATCH("/api/v1/staff/course/items/{id}/", { ...o, ...rowPath(id), body }));
/** "Needs checking": a report in the content triage, once while one is open (`created` false: open already). */
export const flagItem = (id: number, note: string) =>
  send(undefined, (o) => api.POST("/api/v1/staff/course/items/{id}/flag/", { ...o, ...rowPath(id), body: { note } }));
export const itemHistory = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/course/items/{id}/history/", { ...o, ...rowPath(id) }));

export type CourseEntitlementFilters = Filters<"/api/v1/staff/course/entitlements/">;
/** Who may watch what; `q` is an account's email address, exactly (the server records the search by its hash). */
export const listEntitlements = (filters: CourseEntitlementFilters, transport?: Transport) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/course/entitlements/", { ...o, params: { query: query(filters) } }),
  ).then(paged);
export const getEntitlement = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/course/entitlements/{id}/", { ...o, ...rowPath(id) }));
export const grantEntitlement = (body: Schemas["CourseGrantRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/course/entitlements/", { ...o, body }));
export const extendEntitlement = (id: number, days: number, reason: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/course/entitlements/{id}/extend/", { ...o, ...rowPath(id), body: { days, reason } }),
  );
export const revokeEntitlement = (id: number, reason: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/course/entitlements/{id}/revoke/", { ...o, ...rowPath(id), body: { reason } }),
  );
/** A bulk action of the course as a staff job (202): each row through its own rules; `dryRun` checks and changes
 *  nothing. Above the starter's bulk_rows it waits for an approver (its change_request_id). */
export const startCourseBulk = (
  action: CourseBulkAction,
  targets: (number | string)[],
  payload: Record<string, unknown>,
  reason: string,
  dryRun: boolean,
) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/jobs/", {
      ...o,
      body: { kind: "bulk_action", params: { action, targets, payload, reason }, dry_run: dryRun },
    }),
  ) as Promise<Job>;

export const listBatches = (filters: Filters<"/api/v1/staff/course/codes/batches/">, transport?: Transport) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/course/codes/batches/", { ...o, params: { query: query(filters) } }),
  ).then(paged);
/** A batch by its `key` (its label, or ~ and its id). */
export const getBatch = (key: string, transport?: Transport) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/course/codes/batches/{label}/", { ...o, params: { path: { label: key } } }),
  );
/** A print run's codes, made by a job (202: the batch and the job; the printer's file is the maker's for 24 hours). */
export const makeBatch = (body: Schemas["CourseBatchCreateRequest"]) =>
  send(undefined, (o) => api.POST("/api/v1/staff/course/codes/batches/", { ...o, body }));
/** A print run whose job failed before its codes were made, made again: a new job (POST jobs/, kind code_batch). */
export const remakeBatch = (batch: number) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/jobs/", { ...o, body: { kind: "code_batch", params: { batch }, dry_run: false } }),
  ) as Promise<Job>;
export const markDispatched = (key: string, at: string | null) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/course/codes/batches/{label}/dispatched/", {
      ...o,
      params: { path: { label: key } },
      body: { at },
    }),
  );
/** Every unused code of the batch voided, with why (critical: the owners are told). */
export const voidBatch = (key: string, reason: string) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/course/codes/batches/{label}/void/", {
      ...o,
      params: { path: { label: key } },
      body: { reason },
    }),
  );
export const voidCode = (code: string, reason: string) =>
  send(undefined, (o) => api.POST("/api/v1/staff/course/codes/void/", { ...o, body: { code, reason } }));
/** A typed or scanned code, answered in one line (hashed on the server, never kept; audited and throttled). */
export const lookUpCode = (code: string) =>
  send(undefined, (o) => api.POST("/api/v1/staff/course/codes/lookup/", { ...o, body: { code } }));
/** The Course module's codes report by print run (the reports module's getCodesReport adds the districts). */
export const getCourseCodesReport = (transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/course/codes/report/", o));

/** One learner's course for support: reading it is logged (a sensitive read; a child's a summary without times). */
export const getLearner = (user: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/course/learners/{user}/", { ...o, params: { path: { user } } }));
export const signOutDevice = (user: number, device: number) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/course/learners/{user}/devices/{device}/sign-out/", {
      ...o,
      params: { path: { user, device } },
    }),
  );
// ---- Customers (the tabs, the timeline, the commerce summary, consent, bulk actions) ----

/** The list's tabs: `kind` of GET users/. Guest buyers are not accounts: another shape of row. */
export type CustomerKind = "students" | "parents" | "guests";
export type CustomerGuest = Schemas["CustomerGuest"];
export type CustomerParentLink = Schemas["CustomerParentLink"];
export type CustomerLinked = Schemas["CustomerLinked"];
export type CustomerTimeline = Schemas["CustomerTimeline"];
export type TimelineRow = Schemas["CustomerTimelineRow"];
export type CustomerCommerce = Schemas["CustomerCommerce"];
export type ConsentPending = Schemas["CustomerConsentPending"];
export type ConsentRecord = Schemas["CustomerConsentRecord"];
export type ConsentMethod = Schemas["ConsentVerifyMethodEnum"];

/** The guest buyers: people who bought without an account, one row for each email address on their orders. */
export const listGuests = (
  filters: Pick<Filters<"/api/v1/staff/users/">, "q" | "cursor">,
  transport?: Transport,
  signal?: AbortSignal,
) =>
  send(
    transport,
    (o) => api.GET("/api/v1/staff/users/", { ...o, params: { query: query({ ...filters, kind: "guests" }) } }),
    signal,
  ).then((page) => paged(page) as Page<CustomerGuest>);

/** One person's merged timeline, newest first, at most 200 rows (`before`: the older ones, the last answer's
 *  `next_before`); opening it is a read the server records, a child's as such. `kind`: only these kinds. */
export const getTimeline = (id: number, filters: { before?: string; kind?: string }, transport?: Transport) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/users/{id}/timeline/", { ...o, params: { path: { id }, query: query(filters) } }),
  );
/** What they bought: a child's counts only. */
export const getCommerce = (id: number, transport?: Transport) =>
  send(transport, (o) => api.GET("/api/v1/staff/users/{id}/commerce/", { ...o, params: { path: { id } } }));
/** The students under 18 waiting for a parent, the first registered first. */
export const listConsentPending = (filters: { cursor?: string }, transport?: Transport) =>
  send(transport, (o) =>
    api.GET("/api/v1/staff/users/consent-pending/", { ...o, params: { query: query(filters) } }),
  ).then(paged);
/** A parent's consent recorded by hand: a method, where the evidence is, and why (high risk: confirm it's you). */
export const verifyConsent = (id: number, body: { method: ConsentMethod; evidence_ref: string; reason: string }) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/users/{id}/consent/verify/", { ...o, params: { path: { id } }, body }),
  );

/** The account actions a bulk job runs, named as the API names them (user.suspend …). */
export type CustomersBulkAction = "user.suspend" | "user.unsuspend" | "user.end_sessions" | "user.resend_consent";
/** A bulk action on accounts as a background job (202): `dryRun` checks every row and changes nothing. Above your
 *  row limit, or with a child's account among the targets, the job waits for an approver (`change_request_id`). */
export const startCustomersJob = (action: CustomersBulkAction, ids: number[], reason: string, dryRun: boolean) =>
  send(undefined, (o) =>
    api.POST("/api/v1/staff/jobs/", {
      ...o,
      body: {
        kind: "bulk_action",
        dry_run: dryRun,
        params: { action, targets: ids.map(String), payload: {}, reason },
      },
    }),
  ) as Promise<Job>;

/** What a finished bulk job says of itself (its `result`, free JSON in the schema): the counts by outcome, the
 *  children among the targets, and for a dry run whether the real one would wait for an approver. */
export type BulkResult = {
  outcomes: Record<string, number>;
  minors: number;
  approval: string | null;
};
export function bulkResult(job: Pick<Job, "result">): BulkResult {
  const result = (job.result && typeof job.result === "object" ? job.result : {}) as Record<string, unknown>;
  const outcomes = result.outcomes && typeof result.outcomes === "object" ? result.outcomes : {};
  return {
    outcomes: Object.fromEntries(Object.entries(outcomes).map(([name, count]) => [name, Number(count) || 0])),
    minors: Number(result.minors) || 0,
    approval: typeof result.approval === "string" ? result.approval : null,
  };
}
