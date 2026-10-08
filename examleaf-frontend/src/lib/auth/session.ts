// The signed-in visitor, for server components: allauth.headless's session over the internal network with the
// visitor's cookies, once per request (React cache). Anyone without a session cookie is anonymous without a call.
// Three answers, not two: signed in, signed out (401, 403, 410), or not known because Django did not answer (a network
// error, a 5xx, a 429). An outage is never a log-out (security review S5): requireUser() then throws the
// "cannot be reached" error instead of sending the visitor to log in.
import "server-only";

import { redirect } from "next/navigation";
import { cache } from "react";

import { unavailableError } from "@/lib/api/errors";
import { API_INTERNAL_BASE, FORWARDED_HEADERS, hasSessionCookie, personalFetch } from "@/lib/api/server";

import type { AuthUser } from "./headless";
import { withNext } from "./next-url";

const UNKNOWN = "unknown";
const SIGNED_OUT = new Set([401, 403, 410]);

const readSession = cache(async (): Promise<AuthUser | null | typeof UNKNOWN> => {
  if (!(await hasSessionCookie())) return null;
  const { headers } = await personalFetch();
  try {
    const response = await fetch(`${API_INTERNAL_BASE}/_allauth/browser/v1/auth/session`, {
      headers: { ...FORWARDED_HEADERS, ...headers, Accept: "application/json" },
      cache: "no-store",
    });
    if (SIGNED_OUT.has(response.status)) return null;
    if (response.status === 200) {
      const body = (await response.json()) as { data?: { user?: AuthUser } };
      return body.data?.user ?? null;
    }
  } catch {
    // no answer at all: below
  }
  return UNKNOWN;
});

/** The signed-in visitor, or null; also null while Django cannot answer, for pages that render for anyone (the
 *  header, the public pages): their personal parts show their own state. */
export async function getSessionUser(): Promise<AuthUser | null> {
  const user = await readSession();
  return user === UNKNOWN ? null : user;
}

/** For pages that need a signed-in student: the login page when signed out (coming back to `path` afterwards); the
 *  "cannot be reached" error while Django cannot say. */
export async function requireUser(path: string): Promise<AuthUser> {
  const user = await readSession();
  if (user === UNKNOWN) throw unavailableError();
  if (!user) redirect(withNext("/account/login/", path));
  return user;
}
