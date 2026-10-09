// The signed-in staff member, for server components: the staff API's session manifest (GET session/) with the
// person's cookies, once per request (React cache), so the layout and the page share one call. Every page calls
// requireStaff() itself: a layout is not rendered again on a client-side navigation, so it cannot be the only check
// (and the proxy never is: it only adds headers). The manifest only draws the console; the API checks every call.
//   no session cookie, or 401          -> sign in, then back to `path`
//   403 mfa_setup_required             -> /set-up-two-step/ (staff without an authenticator app or a passkey)
//   403 (any other: not staff)         -> /no-access/
//   no answer, 5xx, 429                -> the "can't be reached" error (an outage is never a sign-out)
import "server-only";

import { redirect } from "next/navigation";
import { cache } from "react";

import { endedBy, signInHref } from "@/lib/api/client";
import { ApiError, unavailableError } from "@/lib/api/errors";
import { hasSessionCookie, staffTransport } from "@/lib/api/server";
import { getSession, type Manifest } from "@/lib/api/staff";

const readSession = cache(async (): Promise<Manifest | ApiError> => {
  if (!(await hasSessionCookie())) return new ApiError(401, "unauthenticated", "");
  try {
    return await getSession(await staffTransport());
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
});

export async function requireStaff(path: string): Promise<Manifest> {
  const session = await readSession();
  if (!(session instanceof ApiError)) return session;
  // signed out: plain sign-in; a session the backend ended (session_idle, session_expired): says why
  if (session.status === 401)
    redirect(signInHref(path, session.code.startsWith("session_") ? endedBy(session.code) : undefined));
  if (session.code === "mfa_setup_required") redirect("/set-up-two-step/");
  if (session.status === 403) redirect("/no-access/");
  if (session.code === "bad_response") throw session;
  throw unavailableError();
}
