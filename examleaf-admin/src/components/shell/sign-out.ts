// Signing out (allauth.headless: DELETE auth/session), then a full load of the sign-in page, so no page of the console
// stays in memory. "Everywhere" first ends every other browser and app of the account (allauth.usersessions).
// Drafts in sessionStorage stay: they belong to this tab and come back after signing in again.
import { here, type SignInReason, signInHref } from "@/lib/api/client";
import { auth } from "@/lib/auth/headless";

/** Never fails: a DELETE that gets no answer leaves the session to the backend's idle and absolute limits, and the
 *  sign-in page loads either way. */
export async function signOut(reason: SignInReason = "signed-out", backHere = false) {
  const next = backHere ? here() : null;
  await auth.logout().catch(() => undefined);
  window.location.assign(signInHref(next, reason));
}

/** Rejects with the ApiError, signing out nothing here, when the other sessions could not be ended: signed out here
 *  alone, the person would believe the others were ended too. */
export async function signOutEverywhere() {
  const others = (await auth.sessions()).filter((session) => !session.is_current).map((session) => session.id);
  if (others.length) await auth.endSessions(others);
  await signOut("signed-out");
}
