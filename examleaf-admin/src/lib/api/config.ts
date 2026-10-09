// GET /api/v1/config/: what the server has switched on, read rather than hard-coded (API.md, "Frontend integration
// guide"). The console needs only the sign-in methods: Google, and passkeys for the second step.
import "server-only";

import { API_INTERNAL_BASE, djangoFetch, FORWARDED_HEADERS } from "./server";

export type SiteConfig = { auth: { google: boolean; passkeys: boolean } };

/** The config, or null when the backend cannot be reached (the sign-in page then says so). */
export async function getConfig(): Promise<SiteConfig | null> {
  try {
    const response = await djangoFetch(`${API_INTERNAL_BASE}/api/v1/config/`, {
      headers: { ...FORWARDED_HEADERS, Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) return null;
    const body = (await response.json()) as { auth?: { google?: unknown; passkeys?: unknown } } | null;
    return { auth: { google: body?.auth?.google === true, passkeys: body?.auth?.passkeys === true } };
  } catch {
    return null;
  }
}
