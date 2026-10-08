// GET /api/v1/config/: what the server has switched on (log-in methods, Turnstile, the shop, consent mode). Read it,
// never hard-code a feature flag (API.md, "Frontend integration guide").
import "server-only";

import { unwrap } from "./errors";
import type { components } from "./schema";
import { publicFetch, serverApi } from "./server";

export type SiteConfig = components["schemas"]["Config"];

/** The config, or null when the backend cannot be reached (pages then show their unavailable state). */
export async function getConfig(): Promise<SiteConfig | null> {
  try {
    return await unwrap(serverApi.GET("/api/v1/config/", publicFetch("config")));
  } catch {
    return null;
  }
}
