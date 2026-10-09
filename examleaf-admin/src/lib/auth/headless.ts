// allauth.headless for the browser (/_allauth/browser/v1/, same origin, the session cookie and the CSRF token), the
// public site's client (examleaf-frontend/src/lib/auth/headless.ts) narrowed to what staff do here: email and password,
// then the second step (the authenticator app's code, a recovery code, or a passkey or security key; staff cannot sign
// in with a passkey alone, accounts/adapter.py), Google when the server has it, "confirm it's you" before sensitive
// actions, the signed-in devices, and signing out. An answer is 200 (signed in), or 401 with the flows still to do
// (one is_pending), or an ApiError (400 with the fields' errors, 409, 410, 429).
import { ensureCsrfCookie, readCookie, withTimeout } from "@/lib/api/client";
import { noAnswer, toApiError } from "@/lib/api/errors";

import { safeNext } from "./next-url";
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
export type AuthUser = { id?: number; display: string; email?: string; has_usable_password: boolean };

export type AuthResult = {
  status: number;
  authenticated: boolean;
  user: AuthUser | null;
  flows: Flow[];
  pending: Flow | null;
  data: Record<string, unknown>;
  meta?: Record<string, unknown>;
};

/** A browser signed in to the account (allauth.usersessions): times in seconds since 1970. */
export type Session = {
  id: number;
  user_agent: string;
  ip: string | null;
  created_at: number;
  last_seen_at?: number;
  is_current: boolean;
};

/** One request to allauth.headless: 2xx and 401 come back as an AuthResult, anything else is thrown as an ApiError.
 *  A change makes sure of Django's CSRF cookie first. */
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
      signal: withTimeout(), // no answer in 30 s: status 0, the busy button released
    });
  } catch (error) {
    throw noAnswer(method, error);
  }
  const json = (await response.json().catch(() => null)) as {
    data?: Record<string, unknown>;
    meta?: { is_authenticated?: boolean };
  } | null;
  if (!response.ok && response.status !== 401) throw toApiError(response.status, json, response.headers);
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

/** Where to go after an answer: the destination once signed in; null to stay (the second step is on the sign-in page,
 *  and a switched-off account is the caller's to send to /inactive/). */
export function nextRoute(result: AuthResult, next: string | null | undefined): string | null {
  return result.authenticated ? safeNext(next) : null;
}

export const auth = {
  session: () => call("GET", "/auth/session"),
  logout: () => call("DELETE", "/auth/session"),
  login: (input: { email: string; password: string }) => call("POST", "/auth/login", input),
  mfaAuthenticate: (code: string) => call("POST", "/auth/2fa/authenticate", { code }),

  /** The second step with a passkey or security key. */
  async passkeyAuthenticate() {
    const options = await call("GET", "/auth/webauthn/authenticate");
    const credential = await getCredential(options.data.request_options);
    return call("POST", "/auth/webauthn/authenticate", { credential });
  },

  /** "Confirm it's you" (allauth's reauthenticate flows): the password, the app's code, or a passkey. */
  reauthenticate: (password: string) => call("POST", "/auth/reauthenticate", { password }),
  mfaReauthenticate: (code: string) => call("POST", "/auth/2fa/reauthenticate", { code }),
  async passkeyReauthenticate() {
    const options = await call("GET", "/auth/webauthn/reauthenticate");
    const credential = await getCredential(options.data.request_options);
    return call("POST", "/auth/webauthn/reauthenticate", { credential });
  },

  /** The browsers and apps signed in to the account, and ending some of them (allauth.usersessions). */
  sessions: async () => (await call("GET", "/auth/sessions")).data as unknown as Session[],
  endSessions: (ids: number[]) => call("DELETE", "/auth/sessions", { sessions: ids }),
};

/** Google: a normal form POST (not fetch) to the headless redirect, which sends the browser on to Google and back to
 *  callbackPath on this host, where the sign-in page reads the session (allauth.headless "provider_redirect"). */
export async function startProviderLogin(provider: string, callbackPath: string) {
  await ensureCsrfCookie();
  const form = document.createElement("form");
  form.method = "POST";
  form.action = `${AUTH_BASE}/auth/provider/redirect`;
  const fields = {
    provider,
    callback_url: callbackPath,
    process: "login",
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
