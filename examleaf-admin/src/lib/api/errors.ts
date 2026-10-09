// One error shape for every answer the console gets, as on the public site (examleaf-frontend/src/lib/api/errors.ts):
// the staff API and API v1 (DRF: {"field": ["…"]}, {"detail": "…", "code": "…"}), allauth.headless
// ({"status": 400, "errors": [{"message", "code", "param"}]}), and no answer at all (status 0). The staff API's codes
// (examleaf-web/staff/README.md, API.md "Staff API") that the console acts on:
//   401 not_authenticated, authentication_failed, session_idle, session_expired
//                              the session ended: sign in again (the sign-in page says why), the draft kept
//   403 permission_denied      the role does not allow it (the manifest is read again)
//   403 reauthentication_required
//                              confirm it's you (allauth's flows), then the call is sent again once (read here as
//                              reauth_required, the console's one name for it)
//   403 mfa_setup_required     staff without two-step sign-in
//   403 impersonating          not while this session is signed in as a customer (payments, passwords, consent …)
//   403 link_expired           a job's file link older than 5 minutes: read the job again for a new one
//   404 not_found              also a record outside the person's scopes: never a 403 that would tell it exists
//   202 approval_required      the console's name for a 202 with a change request: nothing ran, a second person is
//                              asked (the change request is the error's body)
//   409 conflict               the record changed since it was read: reload, the draft kept
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

// The platform's name for "confirm it's you", read as the console's one name for it.
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

/** The digest of the error a page throws when Django cannot answer: error.tsx says "can't be reached" for it. */
export const UNAVAILABLE_DIGEST = "examleaf-admin-unavailable";

export function unavailableError(): Error & { digest: string } {
  return Object.assign(new Error(copy.errors.unavailable), { digest: UNAVAILABLE_DIGEST });
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields: FieldErrors;
  /** The answer's body as it came (allauth's flows, a change request, an erasure's dry run). */
  readonly body: unknown;
  /** Seconds to wait (Retry-After of a 429), when the server said. */
  readonly retryAfter: number | null;
  /** When that wait ends (ms since 1970), counted from when the answer came. */
  readonly retryAt: number | null;
  /** The change request made instead of the action (a 202 with it). */
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

  /** The change request a 202 answered with: its id, status and the permission its approver needs. */
  get approval(): { id: string; status: string; checker: string | null } | null {
    if (!this.changeRequestId) return null;
    const body = (this.body ?? {}) as Record<string, unknown>;
    return {
      id: this.changeRequestId,
      status: typeof body.status === "string" ? body.status : "pending",
      checker: typeof body.checker === "string" ? body.checker : null,
    };
  }
}

/** The change request an answer is ({"id", "payload_sha256", "checker", …}) or names (a job's change_request_id). */
export function changeRequestOf(body: unknown): string | null {
  if (!body || typeof body !== "object") return null;
  const record = body as Record<string, unknown>;
  const id = "payload_sha256" in record ? record.id : record.change_request_id;
  return typeof id === "number" || (typeof id === "string" && id) ? String(id) : null;
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

  // DRF validation: {"field": ["…"], "non_field_errors": ["…"]}; a job's params and an export's filters nest one level
  // ({"params": {"reason": ["…"]}}), read as "params.reason"
  const fields: FieldErrors = {};
  let message = "";
  const read = (key: string, value: unknown) => {
    const list = strings(value);
    if (!list.length) return;
    if (key === "non_field_errors" || key === "__all__") message = list[0];
    else if (key !== "code") fields[key] = list;
  };
  for (const [key, value] of Object.entries(record)) {
    if (value && typeof value === "object" && !Array.isArray(value))
      for (const [inner, nested] of Object.entries(value)) read(`${key}.${inner}`, nested);
    else read(key, value);
  }
  const first = Object.values(fields)[0]?.[0];
  const named = typeof record.code === "string" && record.code ? record.code : code;
  return new ApiError(status, named, message || first || fallback, fields, body, retryAfter);
}
