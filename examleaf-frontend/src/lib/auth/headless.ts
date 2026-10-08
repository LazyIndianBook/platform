// allauth.headless for the browser (/_allauth/browser/v1/, same origin, the session cookie and the CSRF token):
// every sign-in flow the website has (API.md, "Frontend integration guide", Flows 1 to 6).
// An answer is 200 (signed in), or 401 with the flows still to do (one is_pending), or an ApiError (400 with the
// fields' errors, 409, 410, 429). nextRoute() turns an answer into the page that comes next.
import { ensureCsrfCookie, readCookie } from "@/lib/api/client";
import { toApiError } from "@/lib/api/errors";

import { safeNext, withNext } from "./next-url";
import { getCredential } from "./webauthn";

export const AUTH_BASE = `${process.env.NEXT_PUBLIC_API_BASE ?? ""}/_allauth/browser/v1`;

export type FlowId =
  | "login"
  | "login_by_code"
  | "mfa_authenticate"
  | "mfa_reauthenticate"
  | "provider_redirect"
  | "provider_signup"
  | "reauthenticate"
  | "signup"
  | "verify_email"
  | "verify_phone"
  | "mfa_login_webauthn";

export type Flow = { id: FlowId; is_pending?: boolean; types?: string[]; provider?: { id: string; name: string } };
export type AuthUser = { id?: number; display: string; email?: string; phone?: string; has_usable_password: boolean };

export type AuthResult = {
  status: number; // 200 (202 for a new mobile number's code), or 401
  authenticated: boolean;
  user: AuthUser | null;
  flows: Flow[];
  pending: Flow | null;
  data: Record<string, unknown>;
  meta?: Record<string, unknown>;
};

/** One request to allauth.headless: 2xx and 401 come back as an AuthResult, anything else is thrown as an ApiError.
 *  A change makes sure of Django's CSRF cookie first: on a slow first load the page's own session check, which sets
 *  it, may still be on its way (a 403 otherwise). */
export async function call(method: string, path: string, body?: unknown, headers: Record<string, string> = {}) {
  if (method !== "GET") await ensureCsrfCookie();
  const token = readCookie("csrftoken");
  let response: Response;
  try {
    response = await fetch(`${AUTH_BASE}${path}`, {
      method,
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        ...(token && method !== "GET" ? { "X-CSRFToken": token } : {}),
        ...headers,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw toApiError(0, null);
  }
  const json = (await response.json().catch(() => null)) as {
    data?: Record<string, unknown>;
    meta?: { is_authenticated?: boolean };
  } | null;
  if (!response.ok && response.status !== 401) throw toApiError(response.status, json);
  const data = json?.data ?? {};
  const flows = (data.flows as Flow[] | undefined) ?? [];
  return {
    status: response.status,
    authenticated: Boolean(json?.meta?.is_authenticated),
    user: (data.user as AuthUser | undefined) ?? null,
    flows,
    pending: flows.find((flow) => flow.is_pending) ?? null,
    data,
    meta: json?.meta ?? {},
  } satisfies AuthResult;
}

/** Where to go after an answer: the destination once signed in, else the page of the pending step. */
export function nextRoute(result: AuthResult, next: string | null | undefined): string | null {
  if (result.authenticated) return safeNext(next);
  switch (result.pending?.id) {
    case "verify_email":
      return withNext("/account/verify-email/", next);
    case "mfa_authenticate":
      return withNext("/account/2fa/authenticate/", next);
    case "provider_signup":
      return withNext("/account/signup/", next);
    case "reauthenticate":
    case "mfa_reauthenticate":
      return withNext("/account/reauthenticate/", next);
    default:
      return null; // the caller stays (login_by_code: the code step is on the log-in page itself)
  }
}

export const auth = {
  session: () => call("GET", "/auth/session"),
  logout: () => call("DELETE", "/auth/session"),

  login: (input: { email: string; password: string } | { phone: string; password: string }) =>
    call("POST", "/auth/login", input),

  /** A code by email or by SMS to a confirmed number; Turnstile's token when the config gives a site key. */
  requestCode: (input: ({ email: string } | { phone: string }) & { turnstile?: string }) =>
    call("POST", "/auth/code/request", input),
  confirmCode: (code: string) => call("POST", "/auth/code/confirm", { code }),

  signup: (input: SignupInput) => call("POST", "/auth/signup", input),
  /** After Google: the student details only (no password). */
  providerSignup: (input: Omit<SignupInput, "password" | "email"> & { email?: string }) =>
    call("POST", "/auth/provider/signup", input),
  verifyEmail: (code: string) => call("POST", "/auth/email/verify", { key: code }),
  resendEmailCode: () => call("POST", "/auth/email/verify/resend"),

  requestPasswordReset: (email: string) => call("POST", "/auth/password/request", { email }),
  checkResetKey: (key: string) => call("GET", "/auth/password/reset", undefined, { "X-Password-Reset-Key": key }),
  resetPassword: (key: string, password: string) => call("POST", "/auth/password/reset", { key, password }),

  reauthenticate: (password: string) => call("POST", "/auth/reauthenticate", { password }),
  mfaAuthenticate: (code: string) => call("POST", "/auth/2fa/authenticate", { code }),

  /** Log in with a passkey: the challenge, the browser's prompt, the signed answer. */
  async passkeyLogin() {
    const options = await call("GET", "/auth/webauthn/login");
    const credential = await getCredential(options.data.request_options);
    return call("POST", "/auth/webauthn/login", { credential });
  },
  /** The second step with a passkey or security key (staff). */
  async passkeyAuthenticate() {
    const options = await call("GET", "/auth/webauthn/authenticate");
    const credential = await getCredential(options.data.request_options);
    return call("POST", "/auth/webauthn/authenticate", { credential });
  },
};

export type SignupInput = {
  email: string;
  password: string;
  full_name: string;
  class_level: number;
  board: number;
  district?: string;
  date_of_birth: string;
  parent_name?: string;
  parent_contact?: string;
  consent: boolean;
  turnstile?: string;
};

/** Google: a normal form POST (not fetch) to the headless redirect, which sends the browser on to Google and back
 *  to callbackPath, where the log-in page reads the session (allauth.headless "provider_redirect"). Flow
 *  "connect" adds Google to the signed-in account instead (Log-in and security). */
export async function startProviderLogin(provider: string, callbackPath: string, flow: "login" | "connect" = "login") {
  await ensureCsrfCookie();
  const form = document.createElement("form");
  form.method = "POST";
  form.action = `${AUTH_BASE}/auth/provider/redirect`;
  const fields = {
    provider,
    callback_url: callbackPath,
    process: flow,
    csrfmiddlewaretoken: readCookie("csrftoken") ?? "",
  };
  for (const [name, value] of Object.entries(fields)) {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = name;
    input.value = value;
    form.appendChild(input);
  }
  document.body.appendChild(form);
  form.submit();
}
