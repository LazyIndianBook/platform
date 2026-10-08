// The API v1 client for server components and route handlers: Django over the internal network (API_INTERNAL_BASE,
// http://web:8000 in docker-compose.yml), with the cache rules of the plan:
//   public catalogue and content: publicFetch("books")  -> cached 60 s, tagged, no cookies (one answer for everyone)
//   anything personal:            await personalFetch() -> the visitor's cookies forwarded, never cached
// Usage: const book = await unwrap(serverApi.GET("/api/v1/books/{slug}/", { params: { path: { slug } }, ...publicFetch("books") }));
import "server-only";

import { cookies, headers } from "next/headers";
import createClient from "openapi-fetch";

import { SITE_URL } from "@/lib/site";

import type { paths } from "./schema";

export const API_INTERNAL_BASE = (process.env.API_INTERNAL_BASE ?? "http://localhost:8100").replace(/\/$/, "");

// Django builds absolute URLs (covers, links) and checks ALLOWED_HOSTS with the public host, as when Caddy forwards
// a request: it trusts X-Forwarded-Host (USE_X_FORWARDED_HOST=1) and, behind a proxy, X-Forwarded-Proto.
const site = new URL(SITE_URL);
export const FORWARDED_HEADERS = {
  "X-Forwarded-Host": site.host,
  "X-Forwarded-Proto": site.protocol.replace(":", ""),
};

export const serverApi = createClient<paths>({ baseUrl: API_INTERNAL_BASE, headers: FORWARDED_HEADERS });

export const REVALIDATE_SECONDS = 60;

/** Public data: Next's data cache for 60 s, invalidated early with revalidateTag(tag). */
export function publicFetch(...tags: string[]) {
  return {
    fetch: (request: Request) => fetch(request, { next: { revalidate: REVALIDATE_SECONDS, tags } }),
  };
}

/** The visitor's own data: their cookies (session, CSRF) and address forwarded, nothing cached. */
export async function personalFetch() {
  const [jar, incoming] = await Promise.all([cookies(), headers()]);
  const forwarded: Record<string, string> = { Cookie: jar.toString() };
  const address = incoming.get("x-forwarded-for");
  if (address) forwarded["X-Forwarded-For"] = address;
  return {
    headers: forwarded,
    fetch: (request: Request) => fetch(request, { cache: "no-store" }),
  };
}

/** Whether the visitor's browser holds a Django session at all (no cookie: anonymous, no call needed). */
export async function hasSessionCookie(): Promise<boolean> {
  return (await cookies()).has("sessionid");
}
