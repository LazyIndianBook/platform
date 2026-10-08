// The API v1 client for client components: same origin (Caddy sends /api/ to Django), the session cookie, and the
// CSRF token from the csrftoken cookie on every unsafe method (API.md, "Authentication boundaries"). Any 401 means
// the session ended (or never was, for a signed-in-only call): the visitor goes to log in and comes back here.
// Usage: const book = await unwrap(api.GET("/api/v1/books/{slug}/", { params: { path: { slug } }, signal }));
import createClient, { type Middleware } from "openapi-fetch";

import { ApiError, unwrap } from "./errors";
import type { paths } from "./schema";

export function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  return document.cookie
    .split("; ")
    .find((pair) => pair.startsWith(`${name}=`))
    ?.slice(name.length + 1);
}

const SAFE = new Set(["GET", "HEAD", "OPTIONS"]);

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
});
api.use(csrfMiddleware, sessionMiddleware);

/** unwrap() for the signed-in visitor's calls; the redirect on a 401 is the client's own (sessionMiddleware). */
export const personal = unwrap;

export { ApiError, unwrap };
