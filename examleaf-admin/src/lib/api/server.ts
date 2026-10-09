// The server's side of the API boundary (server components), as on the public site
// (examleaf-frontend/src/lib/api/server.ts): Django over the internal network (API_INTERNAL_BASE, http://web:8000 in
// docker-compose.yml), speaking for the signed-in person. Their cookies go with every call, with their address
// (X-Forwarded-For, as Caddy gave it) and browser, and INTERNAL_API_TOKEN (X-Internal-Token), which makes Django believe
// the address. Never cached: every staff answer is the person's own (Cache-Control: no-store from the API too). The
// server holds no credential of its own (no "god token"): it can do only what the person's session can.
import "server-only";

import { cookies, headers } from "next/headers";

import { FORWARDED_HEADERS } from "@/lib/site";

import type { Transport } from "./staff";

export const API_INTERNAL_BASE = (process.env.API_INTERNAL_BASE ?? "http://localhost:8100").replace(/\/$/, "");

// the console's public host and scheme for Django (src/lib/site.ts), shared with src/proxy.ts's health check
export { FORWARDED_HEADERS };

const INTERNAL_API_TOKEN = process.env.INTERNAL_API_TOKEN ?? "";

/** The person's cookies, address and browser, and the secret that makes Django believe the address. */
export async function personHeaders(): Promise<Record<string, string>> {
  const [jar, incoming] = await Promise.all([cookies(), headers()]);
  const forwarded: Record<string, string> = { ...FORWARDED_HEADERS, Cookie: jar.toString() };
  if (INTERNAL_API_TOKEN) forwarded["X-Internal-Token"] = INTERNAL_API_TOKEN;
  for (const name of ["X-Forwarded-For", "User-Agent"]) {
    const value = incoming.get(name);
    if (value) forwarded[name] = value;
  }
  return forwarded;
}

const noStore = (request: Request) => fetch(request, { cache: "no-store" });

/** The staff API as the signed-in person, for server components. With STAFF_API_MOCK=1 (next dev only) the fixtures
 *  answer in this process, through the same handler as the browser's calls (src/app/api/mock/staff/). */
export async function staffTransport(): Promise<Transport> {
  const forwarded = await personHeaders();
  // written out here, not MOCK: the build compiles the condition to false and leaves the fixtures out of the bundle
  if (process.env.STAFF_API_MOCK === "1") {
    return {
      base: "http://mock.invalid",
      headers: forwarded,
      fetch: async (request) => (await import("@/mocks/staff/handler")).handleMock(request),
    };
  }
  return { base: API_INTERNAL_BASE, headers: forwarded, fetch: noStore };
}

/** Whether the browser holds a Django session at all (no cookie: signed out, no call needed). */
export async function hasSessionCookie(): Promise<boolean> {
  return (await cookies()).has("sessionid");
}

/** allauth.headless (browser client) for a server component, as the person: its `data`, or null when it failed. */
export async function allauthGet<T>(path: string): Promise<{ status: number; data: T | null }> {
  try {
    const response = await fetch(`${API_INTERNAL_BASE}/_allauth/browser/v1${path}`, {
      headers: { ...(await personHeaders()), Accept: "application/json" },
      cache: "no-store",
    });
    const body = (await response.json().catch(() => null)) as { data?: T } | null;
    return { status: response.status, data: response.ok ? ((body?.data as T) ?? null) : null };
  } catch {
    return { status: 0, data: null };
  }
}
