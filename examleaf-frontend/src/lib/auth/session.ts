// The signed-in visitor, for server components: allauth.headless's session over the internal network with the
// visitor's cookies, once per request (React cache). Anyone without a session cookie is anonymous without a call.
import "server-only";

import { redirect } from "next/navigation";
import { cache } from "react";

import { API_INTERNAL_BASE, FORWARDED_HEADERS, hasSessionCookie, personalFetch } from "@/lib/api/server";

import type { AuthUser } from "./headless";
import { withNext } from "./next-url";

export const getSessionUser = cache(async (): Promise<AuthUser | null> => {
  if (!(await hasSessionCookie())) return null;
  const { headers } = await personalFetch();
  try {
    const response = await fetch(`${API_INTERNAL_BASE}/_allauth/browser/v1/auth/session`, {
      headers: { ...FORWARDED_HEADERS, ...headers, Accept: "application/json" },
      cache: "no-store",
    });
    if (response.status !== 200) return null;
    const body = (await response.json()) as { data?: { user?: AuthUser } };
    return body.data?.user ?? null;
  } catch {
    return null; // the backend is down: the page renders as for a visitor, its personal parts show their own state
  }
});

/** For pages that need a signed-in student: the login page otherwise, coming back to `path` afterwards. */
export async function requireUser(path: string): Promise<AuthUser> {
  const user = await getSessionUser();
  if (!user) redirect(withNext("/account/login/", path));
  return user;
}
