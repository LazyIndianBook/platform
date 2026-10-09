// One error shape for every answer the console gets, as on the public site (examleaf-frontend/src/lib/api/errors.ts):
// the staff API and API v1 (DRF: {"field": ["…"]}, {"detail": "…", "code": "…"}), allauth.headless
// ({"status": 400, "errors": [{"message", "code", "param"}]}), and no answer at all (status 0). The staff API adds
// meanings the console acts on:
//   401                        the session ended: sign in again, the typed draft kept (sessionStorage)
//   403 permission_denied      the role does not allow it (the manifest is read again)
//   403 scope_denied           the record is outside the person's scopes (the manifest is read again)
//   403 reauth_required        confirm it's you (allauth's reauthenticate flows), then the call is sent again once
//                              (reauthentication_required, the platform's name for it, reads the same)
//   403 approval_required      a change request was made instead; changeRequestId links to it
//   403 mfa_setup_required     staff without two-step sign-in (StaffMFAMiddleware)
//   409 conflict               the record changed since it was read (If-Match): reload, the draft kept
//   429 throttled              retryAfter: the seconds of Retry-After, when the server sends it
import { copy } from "@/lib/copy";

export type FieldErrors = Record<string, string[]>;

const DEFAULT_MESSAGES: Record<number, string> = {
  0: copy.errors.unavailable,
  400: copy.errors.badRequest,
  401: copy.errors.signedOut,
  403: copy.errors.forbidden,
  404: copy.errors.notFound,
  409: copy.errors.conflict,
  429: copy.errors.throttled,
  500: copy.errors.server,
  502: copy.errors.unavailable,
  503: copy.errors.unavailable,
  504: copy.errors.unavailable,
};

// The platform's own names for the same answers (API.md: the account endpoints already answer
// reauthentication_required), read as the brief's, so either side of the contract works.
const ALIASES: Record<string, string> = { reauthentication_required: "reauth_required" };

const CODES: Record<number, string> = {
  0: "unavailable",
  400: "invalid",
  401: "unauthenticated",
  403: "forbidden",
  404: "not_found",
  409: "conflict",
  410: "gone",
  429: "throttled",
};

/** The ApiError of a call that got no answer (status 0). A change the browser stopped waiting for (client.ts's answer
 *  timeout) may still have reached Django: it says so, and nothing sends it again by itself. */
export function noAnswer(method: string, error: unknown): ApiError {
  const timedOut = error instanceof DOMException && error.name === "TimeoutError";
  return new ApiError(
    0,
    "unavailable",
    timedOut && method !== "GET" ? copy.errors.unconfirmed : copy.errors.unavailable,
  );
}

/** The digest of the error a page throws when Django cannot answer: error.tsx says "can't be reached" for it. */
export const UNAVAILABLE_DIGEST = "examleaf-admin-unavailable";

export function unavailableError(): Error & { digest: string } {
  return Object.assign(new Error(copy.errors.unavailable), { digest: UNAVAILABLE_DIGEST });
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields: FieldErrors;
  /** The answer's body as it came (allauth's flows, a change request). */
  readonly body: unknown;
  /** Seconds to wait (Retry-After of a 429), when the server said. */
  readonly retryAfter: number | null;
  /** When that wait ends (ms since 1970), counted from when the answer came. */
  readonly retryAt: number | null;
  /** The change request made instead of the action (403 approval_required, or a 202). */
  readonly changeRequestId: string | null;

  constructor(
    status: number,
    code: string,
    message: string,
    fields: FieldErrors = {},
    body: unknown = null,
    retryAfter: number | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fields = fields;
    this.body = body;
    this.retryAfter = retryAfter;
    this.retryAt = retryAfter === null ? null : Date.now() + retryAfter * 1000;
    this.changeRequestId = changeRequestOf(body);
  }

  /** The backend could not answer (down, timed out, a proxy error). */
  get unavailable(): boolean {
    return this.status === 0 || this.status >= 500;
  }
}

/** The change request an answer names: {"change_request": {"id": 12}}, {"change_request": 12} or
 *  {"change_request_id": 12}. */
export function changeRequestOf(body: unknown): string | null {
  if (!body || typeof body !== "object") return null;
  const record = body as Record<string, unknown>;
  const named = record.change_request ?? record.change_request_id;
  if (typeof named === "number" || (typeof named === "string" && named)) return String(named);
  if (named && typeof named === "object") {
    const id = (named as Record<string, unknown>).id;
    if (typeof id === "number" || (typeof id === "string" && id)) return String(id);
  }
  return null;
}

const strings = (value: unknown): string[] =>
  (Array.isArray(value) ? value : [value]).filter((item): item is string => typeof item === "string");

/** Retry-After as seconds: a number of seconds, or an HTTP date. */
export function retryAfterSeconds(header: string | null | undefined, now = Date.now()): number | null {
  if (!header) return null;
  const seconds = Number(header);
  if (Number.isFinite(seconds) && seconds >= 0) return Math.ceil(seconds);
  const date = Date.parse(header);
  return Number.isNaN(date) ? null : Math.max(0, Math.ceil((date - now) / 1000));
}

/** The API's answer as an ApiError. */
export function toApiError(status: number, body: unknown, headers?: Headers | null): ApiError {
  const retryAfter = status === 429 ? retryAfterSeconds(headers?.get("Retry-After")) : null;
  const fallback = DEFAULT_MESSAGES[status] ?? DEFAULT_MESSAGES[status >= 500 ? 500 : 0];
  const code = CODES[status] ?? (status >= 500 ? "server" : "error");
  if (!body || typeof body !== "object") return new ApiError(status, code, fallback, {}, body, retryAfter);

  const record = body as Record<string, unknown>;
  if (Array.isArray(record.errors)) {
    // allauth.headless: errors with a param belong to that field, the others are the message
    const fields: FieldErrors = {};
    let message = "";
    let firstCode = code;
    for (const item of record.errors as { message?: string; code?: string; param?: string }[]) {
      if (!item?.message) continue;
      if (item.param) (fields[item.param] ??= []).push(item.message);
      else message ||= item.message;
      if (firstCode === code && item.code) firstCode = item.code;
    }
    const first = Object.values(fields)[0]?.[0];
    return new ApiError(status, firstCode, message || first || fallback, fields, body, retryAfter);
  }

  if (typeof record.detail === "string") {
    const named = typeof record.code === "string" && record.code ? (ALIASES[record.code] ?? record.code) : code;
    return new ApiError(status, named, record.detail, {}, body, retryAfter);
  }

  // DRF validation: {"field": ["…"], "non_field_errors": ["…"]}
  const fields: FieldErrors = {};
  let message = "";
  for (const [key, value] of Object.entries(record)) {
    const list = strings(value);
    if (!list.length) continue;
    if (key === "non_field_errors" || key === "__all__") message = list[0];
    else if (key !== "code") fields[key] = list;
  }
  const first = Object.values(fields)[0]?.[0];
  const named = typeof record.code === "string" && record.code ? record.code : code;
  return new ApiError(status, named, message || first || fallback, fields, body, retryAfter);
}
