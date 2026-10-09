// The API v1 client for client components: same origin (Caddy sends /api/ to Django), the session cookie, and the
// CSRF token from the csrftoken cookie on every unsafe method (API.md, "Authentication boundaries"). Any 401 means
// the session ended (or never was, for a signed-in-only call): the visitor goes to log in and comes back here. No
// call waits more than 30 s for an answer (timedFetch), and none is ever sent again by itself.
// Usage: const book = await unwrap(api.GET("/api/v1/books/{slug}/", { params: { path: { slug } }, signal }));
import createClient, { type Middleware } from "openapi-fetch";

import { ApiError, noAnswer, unwrap } from "./errors";
import type { paths } from "./schema";

/** How long the browser waits for Django's answer: a call with none in 30 s fails as status 0, so no button stays busy
 *  on a hung connection. */
export const ANSWER_TIMEOUT_MS = 30_000;

/** The answer timeout with the caller's own signal: AbortSignal.any, or a controller where the browser lacks it
 *  (Safari before 17.4, Chrome before 116: Next's baseline is Safari 16.4 and Chrome 111). */
export function withTimeout(signal?: AbortSignal | null): AbortSignal {
  const timeout = AbortSignal.timeout(ANSWER_TIMEOUT_MS);
  if (!signal) return timeout;
  if (typeof AbortSignal.any === "function") return AbortSignal.any([signal, timeout]);
  const both = new AbortController();
  for (const each of [signal, timeout]) {
    if (each.aborted) both.abort(each.reason);
    each.addEventListener("abort", () => both.abort(each.reason), { once: true });
  }
  return both.signal;
}

export function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  return document.cookie
    .split("; ")
    .find((pair) => pair.startsWith(`${name}=`))
    ?.slice(name.length + 1);
}

/**
 * Before a visitor's first change (a log-in or a code request, a guest cart, a guest's checkout): Django's CSRF
 * cookie, which allauth and the API need as X-CSRFToken with the session cookie; allauth.headless's config answer
 * (200, public) sets it. A page's own first request may not have answered yet (a cold server, a slow network).
 */
export async function ensureCsrfCookie() {
  if (typeof document === "undefined" || readCookie("csrftoken")) return;
  await fetch(`${process.env.NEXT_PUBLIC_API_BASE ?? ""}/_allauth/browser/v1/config`, {
    credentials: "same-origin",
    cache: "no-store",
    signal: withTimeout(),
  }).catch(() => undefined);
}

const SAFE = new Set(["GET", "HEAD", "OPTIONS"]);

/** fetch with the answer timeout; a cancelled call stays an AbortError, and a change that timed out says it may have
 *  gone through (noAnswer), so the visitor checks before pressing again. */
export async function timedFetch(request: Request): Promise<Response> {
  try {
    return await fetch(request, { signal: withTimeout(request.signal) });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw noAnswer(request.method, error);
  }
}

export const csrfMiddleware: Middleware = {
  onRequest({ request }) {
    const token = readCookie("csrftoken");
    if (!SAFE.has(request.method) && token) request.headers.set("X-CSRFToken", token);
    return request;
  },
};

/** The login page with the current page as the destination (a session that ended, API.md "Errors" 401). */
export function loginUrl(
  next = typeof window === "undefined" ? "/" : window.location.pathname + window.location.search,
) {
  return `/account/login/?next=${encodeURIComponent(next)}`;
}

/** Every 401 of every call: off to log in and back (the call still fails with its ApiError for the caller). */
export const sessionMiddleware: Middleware = {
  onResponse({ response }) {
    if (response.status === 401 && typeof window !== "undefined") window.location.assign(loginUrl());
    return response;
  },
};

export const api = createClient<paths>({
  baseUrl: process.env.NEXT_PUBLIC_API_BASE ?? "",
  credentials: "same-origin",
  fetch: timedFetch,
});
api.use(csrfMiddleware, sessionMiddleware);

/** unwrap() for the signed-in visitor's calls; the redirect on a 401 is the client's own (sessionMiddleware). */
export const personal = unwrap;

export { ApiError, unwrap };
