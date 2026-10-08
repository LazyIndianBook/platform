// The API v1 client for client components: same origin (Caddy sends /api/ to Django), the session cookie, and the
// CSRF token from the csrftoken cookie on every unsafe method (API.md, "Authentication boundaries").
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

export const api = createClient<paths>({
  baseUrl: process.env.NEXT_PUBLIC_API_BASE ?? "",
  credentials: "same-origin",
});
api.use(csrfMiddleware);

/** The login page with the current page as the destination (a session that ended, API.md "Errors" 401). */
export function loginUrl(
  next = typeof window === "undefined" ? "/" : window.location.pathname + window.location.search,
) {
  return `/account/login/?next=${encodeURIComponent(next)}`;
}

/** unwrap() for personal calls: a 401 means the session ended, so the visitor goes to log in and comes back. */
export async function personal<T>(call: Parameters<typeof unwrap<T>>[0]): Promise<T> {
  try {
    return await unwrap(call);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401 && typeof window !== "undefined") {
      window.location.assign(loginUrl());
    }
    throw error;
  }
}

export { ApiError, unwrap };
