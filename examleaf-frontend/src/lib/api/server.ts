// The API v1 client for server components and route handlers: Django over the internal network (API_INTERNAL_BASE,
// http://web:8000 in docker-compose.yml), with the cache rules of the plan:
//   public catalogue and content: publicFetch("books")    -> kept 60 s by URL, tagged, no cookies (one answer for all)
//   anything personal:            await personalFetch()   -> the visitor's cookies forwarded, never cached
//   by an emailed link's secret:  await anonymousFetch()  -> no cookies, never cached
// Every call gives up at the request's deadline (djangoFetch): a hung Django costs a page 10 s at most, never more.
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

/** One deadline per request: the moment the proxy took it (x-request-start, never later than now, so a header sent
 *  from outside can only shorten its own request) plus API_INTERNAL_TIMEOUT_MS (10 s). The layout, the page and
 *  generateMetadata, which Next renders apart (each with a React cache of its own), share it, so a hung Django costs a
 *  page this long at most however many calls it makes, never Node's default (5 minutes for the headers alone).
 *  Outside a request: from now. A moment, not a signal: see djangoFetch. */
async function deadline(): Promise<number> {
  const now = Date.now();
  let start = now;
  try {
    start = Math.min(Number((await headers()).get("x-request-start")) || now, now);
  } catch {
    // no request to read (a build): from now
  }
  return start + (Number(process.env.API_INTERNAL_TIMEOUT_MS) || 10_000);
}

const NO_BODY = new Set([101, 103, 204, 205, 304]);

/** fetch for every server-side call to Django: under a timer set to the request's deadline and cleared once the whole
 *  answer is read (a body that stalls counts too), so a call never waits past the deadline and nothing of it outlives
 *  it. A deadline that passes rejects the call with a TimeoutError, which unwrap() reports as status 0 ("cannot be
 *  reached"). Not AbortSignal.timeout(): Node keeps that signal's timer, and with the timer the whole request (the async
 *  context it captured), until the signal is collected, and a signal the request can reach never is; nor
 *  AbortSignal.any(), whose composite outlives a timeout source. The load test found every request kept in memory that
 *  way (RESILIENCE.md). No server call brings a signal of its own, so none is kept. `by` is the deadline read
 *  beforehand, where headers() cannot be (inside unstable_cache's callback). */
export async function djangoFetch(input: Request | string, init: RequestInit = {}, by?: number): Promise<Response> {
  const late = () => new DOMException("Django did not answer in time.", "TimeoutError");
  const left = (by ?? (await deadline())) - Date.now();
  if (left <= 0) throw late(); // the request's time is spent: nothing is sent
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(late()), left);
  try {
    const response = await fetch(input, { ...init, signal: controller.signal });
    const body = NO_BODY.has(response.status) ? null : await response.arrayBuffer();
    return new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers });
  } finally {
    clearTimeout(timer);
  }
}

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

const noStore = (request: Request) => djangoFetch(request, { cache: "no-store" });

type Answer = { status: number; type: string | null; body: string };
class NotKept {
  constructor(readonly answer: Answer) {}
}

// ponytail: one call per public URL in flight per process, shared by every request that needs it meanwhile. Without
// it a cold or stale data cache sent Django one call per page view and per answer: with Django hung, the load test's
// process held 3,500 connections to it and nearly its whole memory, and Django would have met them all on its return.
// Only the calls in flight, each gone once it settles.
const asking = new Map<string, Promise<Answer>>();

/** A public answer, the same for everyone: kept 60 s in Next's data cache by URL alone (tagged: revalidateTag(tag)
 *  refreshes it early), so the visitor's headers on a miss do not split the cache. Only a 200 is kept; React's cache
 *  shares one call between the layout and the page of a request, `asking` between requests. */
const keptAnswer = cache(async (url: string, redirect: RequestRedirect, tags: string): Promise<Answer> => {
  // both read here: inside unstable_cache's callback Next refuses headers(), and the call would get a deadline of its own
  const [visitor, by] = await Promise.all([visitorHeaders(), deadline()]);
  const ask = (): Promise<Answer> => {
    const key = `${redirect} ${url}`;
    let call = asking.get(key);
    if (!call) {
      // a refresh of a stale answer in the background runs in this request too, and keeps its deadline
      call = djangoFetch(
        url,
        { redirect, headers: { ...FORWARDED_HEADERS, ...visitor, Accept: "application/json" }, cache: "no-store" },
        by,
      )
        .then(async (response) => {
          const answer = {
            status: response.status,
            type: response.headers.get("Content-Type"),
            body: await response.text(),
          };
          if (response.status !== 200) throw new NotKept(answer);
          return answer;
        })
        .finally(() => asking.delete(key));
      asking.set(key, call);
    }
    return call;
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
