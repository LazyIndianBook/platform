// Signing out (allauth.headless: DELETE auth/session), then a full load of the sign-in page, so no page of the console
// stays in memory. "Everywhere" first ends every other browser and app of the account (allauth.usersessions).
// Drafts in sessionStorage stay: they belong to this tab and come back after signing in again.
import { here, type SignInReason, signInHref } from "@/lib/api/client";
import { auth } from "@/lib/auth/headless";

export async function signOut(reason: SignInReason = "signed-out", backHere = false) {
  const next = backHere ? here() : null;
  try {
    await auth.logout();
  } finally {
    window.location.assign(signInHref(next, reason));
  }
}

export async function signOutEverywhere() {
  try {
    const others = (await auth.sessions()).filter((session) => !session.is_current).map((session) => session.id);
    if (others.length) await auth.endSessions(others);
  } finally {
    await signOut("signed-out");
  }
}
