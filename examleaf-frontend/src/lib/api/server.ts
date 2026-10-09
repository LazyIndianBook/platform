// The API v1 client for server components and route handlers: Django over the internal network (API_INTERNAL_BASE,
// http://web:8000 in docker-compose.yml), with the cache rules of the plan:
//   public catalogue and content: publicFetch("books")    -> kept 60 s by URL, tagged, no cookies (one answer for all)
//   anything personal:            await personalFetch()   -> the visitor's cookies forwarded, never cached
//   by an emailed link's secret:  await anonymousFetch()  -> no cookies, never cached
// Every call speaks for the visitor: their address (X-Forwarded-For, as Caddy gave it) and browser go with it, and
// INTERNAL_API_TOKEN (X-Internal-Token) makes Django believe the address, so its limits count each visitor and never
// this server as one anonymous client (security review S4; examleaf-web's FrontendClientMiddleware).
// Usage: const book = await unwrap(serverApi.GET("/api/v1/books/{slug}/", { params: { path: { slug } }, ...publicFetch("books") }));
import "server-only";

import { unstable_cache } from "next/cache";
import { cookies, headers } from "next/headers";
import createClient from "openapi-fetch";
import { cache } from "react";

import { FORWARDED_HEADERS } from "@/lib/site";

import type { paths } from "./schema";

export const API_INTERNAL_BASE = (process.env.API_INTERNAL_BASE ?? "http://localhost:8100").replace(/\/$/, "");

// the public host and scheme for Django (src/lib/site.ts), shared with src/proxy.ts's health check
export { FORWARDED_HEADERS };

export const serverApi = createClient<paths>({ baseUrl: API_INTERNAL_BASE, headers: FORWARDED_HEADERS });

export const REVALIDATE_SECONDS = 60;

const INTERNAL_API_TOKEN = process.env.INTERNAL_API_TOKEN ?? "";

/** The visitor's address and browser, and the secret that makes Django believe them. */
async function visitorHeaders(): Promise<Record<string, string>> {
  const incoming = await headers();
  const visitor: Record<string, string> = INTERNAL_API_TOKEN ? { "X-Internal-Token": INTERNAL_API_TOKEN } : {};
  for (const name of ["X-Forwarded-For", "User-Agent"]) {
    const value = incoming.get(name);
    if (value) visitor[name] = value;
  }
  return visitor;
}

const noStore = (request: Request) => fetch(request, { cache: "no-store" });

type Answer = { status: number; type: string | null; body: string };
class NotKept {
  constructor(readonly answer: Answer) {}
}

/** A public answer, the same for everyone: kept 60 s in Next's data cache by URL alone (tagged: revalidateTag(tag)
 *  refreshes it early), so the visitor's headers on a miss do not split the cache. Only a 200 is kept; React's cache
 *  shares one call between the layout and the page of a request. */
const keptAnswer = cache(async (url: string, redirect: RequestRedirect, tags: string): Promise<Answer> => {
  const visitor = await visitorHeaders();
  const ask = async (): Promise<Answer> => {
    const response = await fetch(url, {
      redirect,
      headers: { ...FORWARDED_HEADERS, ...visitor, Accept: "application/json" },
      cache: "no-store",
    });
    const answer = { status: response.status, type: response.headers.get("Content-Type"), body: await response.text() };
    if (response.status !== 200) throw new NotKept(answer);
    return answer;
  };
  try {
    return await unstable_cache(ask, [url, redirect], { revalidate: REVALIDATE_SECONDS, tags: tags.split(" ") })();
  } catch (error) {
    if (error instanceof NotKept) return error.answer;
    throw error;
  }
});

/** Public data (GET): kept 60 s by URL for everyone, tagged; see keptAnswer. */
export function publicFetch(...tags: string[]) {
  return {
    fetch: async (request: Request) => {
      const answer = await keptAnswer(request.url, request.redirect, tags.join(" "));
      return new Response(answer.body, {
        status: answer.status,
        headers: answer.type ? { "Content-Type": answer.type } : undefined,
      });
    },
  };
}

/** The visitor's own data: their cookies (session, CSRF) with their address and browser, nothing cached. Each call
 *  with the session cookie records the device's browser and address (allauth.usersessions: Log-in and security). */
export async function personalFetch() {
  const [jar, visitor] = await Promise.all([cookies(), visitorHeaders()]);
  return { headers: { ...visitor, Cookie: jar.toString() }, fetch: noStore };
}

/** As the visitor but without their cookies (an order by its emailed link: the link is the key), nothing cached. */
export async function anonymousFetch() {
  return { headers: await visitorHeaders(), fetch: noStore };
}

/** Whether the visitor's browser holds a Django session at all (no cookie: anonymous, no call needed). */
export async function hasSessionCookie(): Promise<boolean> {
  return (await cookies()).has("sessionid");
}
