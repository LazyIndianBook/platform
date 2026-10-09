// One error shape for every answer the frontend gets: API v1 (DRF: {"field": ["…"]}, {"detail": "…"}) and
// allauth.headless ({"status": 400, "errors": [{"message", "code", "param"}]}), and for no answer at all.

export type FieldErrors = Record<string, string[]>;

const DEFAULT_MESSAGES: Record<number, string> = {
  0: "ExamLeaf cannot be reached just now. Check your connection, then try again.",
  401: "Please log in again.",
  403: "You cannot do that with this account.",
  404: "We could not find that.",
  429: "Too many tries. Wait a little, then try again.",
  500: "Something went wrong on our side. Please try again.",
  502: "ExamLeaf cannot be reached just now. Please try again in a minute.",
  503: "ExamLeaf cannot be reached just now. Please try again in a minute.",
  504: "ExamLeaf cannot be reached just now. Please try again in a minute.",
};

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

const CONSENT_PENDING = /parent or guardian has not confirmed/i;

/** The digest of the error a page throws when Django cannot answer (unavailableError): error.tsx shows "cannot be
 *  reached" for it, and the answer is a server error (500), never a 200 page (security review S5). Next keeps a
 *  digest that is already set. */
export const UNAVAILABLE_DIGEST = "examleaf-unavailable";

export function unavailableError(): Error & { digest: string } {
  return Object.assign(new Error("ExamLeaf cannot be reached just now."), { digest: UNAVAILABLE_DIGEST });
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields: FieldErrors;
  /** allauth.headless answers 401 with the flows still to do; kept so that the auth layer can route on them. */
  readonly body: unknown;

  constructor(status: number, code: string, message: string, fields: FieldErrors = {}, body: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fields = fields;
    this.body = body;
  }

  /** The backend could not answer (down, timed out, a proxy error): pages show their unavailable state. */
  get unavailable(): boolean {
    return this.status === 0 || this.status >= 500;
  }
}

const strings = (value: unknown): string[] =>
  (Array.isArray(value) ? value : [value]).filter((item): item is string => typeof item === "string");

/** The API's answer as an ApiError; a refusal because a parent's consent is awaited gets the code consent_pending (the
 *  API's words are its only mark: a 403 detail for orders and the course, a 400 for marks; API.md "Errors"). */
export function toApiError(status: number, body: unknown): ApiError {
  const error = parse(status, body);
  if (!CONSENT_PENDING.test(error.message)) return error;
  return new ApiError(error.status, "consent_pending", error.message, error.fields, error.body);
}

function parse(status: number, body: unknown): ApiError {
  const fallback = DEFAULT_MESSAGES[status] ?? DEFAULT_MESSAGES[status >= 500 ? 500 : 0];
  const code = CODES[status] ?? (status >= 500 ? "server" : "error");
  if (!body || typeof body !== "object") return new ApiError(status, code, fallback, {}, body);

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
    return new ApiError(status, firstCode, message || first || fallback, fields, body);
  }

  if (typeof record.detail === "string") {
    return new ApiError(status, typeof record.code === "string" ? record.code : code, record.detail, {}, body);
  }

  // DRF validation: {"field": ["…"], "non_field_errors": ["…"]}
  const fields: FieldErrors = {};
  let message = "";
  for (const [key, value] of Object.entries(record)) {
    const list = strings(value);
    if (!list.length) continue;
    if (key === "non_field_errors" || key === "__all__") message = list[0];
    else fields[key] = list;
  }
  const first = Object.values(fields)[0]?.[0];
  return new ApiError(status, code, message || first || fallback, fields, body);
}

/** A change the browser stopped waiting for (client.ts's answer timeout) may still have reached Django: the visitor
 *  checks before sending it again, and nothing sends it again by itself. */
export const UNCONFIRMED_MESSAGE =
  "ExamLeaf didn't answer in time, so this may have gone through. Check before you try again.";

/** The ApiError of a call that got no answer (status 0): a change that timed out says it may have gone through. */
export function noAnswer(method: string, error: unknown): ApiError {
  const timedOut = error instanceof DOMException && error.name === "TimeoutError";
  return new ApiError(0, "unavailable", timedOut && method !== "GET" ? UNCONFIRMED_MESSAGE : DEFAULT_MESSAGES[0]);
}

type Result<T> = { data?: T; error?: unknown; response: Response };

/** The data of an openapi-fetch call, or an ApiError (also when the backend cannot be reached). */
export async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  let result: Result<T>;
  try {
    result = await call;
  } catch (error) {
    if (error instanceof ApiError) throw error; // already worded (client.ts's timedFetch)
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "unavailable", DEFAULT_MESSAGES[0]);
  }
  if (result.error !== undefined || !result.response.ok) throw toApiError(result.response.status, result.error);
  return result.data as T;
}
