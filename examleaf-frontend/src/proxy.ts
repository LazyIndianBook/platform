// Next's request proxy (Next 16's name for middleware.ts), on every request but static files and prefetches:
// 1. Django's prefixes (src/lib/site.ts) are passed to API_INTERNAL_BASE. Caddy does this in production, so these
//    requests only arrive here in development and CI, where there is no Caddy.
// 2. Every other path gets its trailing slash (trailingSlash: true; skipTrailingSlashRedirect leaves it to us because
//    allauth's paths have none).
// 3. Every page gets a fresh nonce and its Content-Security-Policy (src/lib/security/csp.ts).
// 4. A page that is not the visitor's own (isPersonalPage) may be kept by the browser: private, no-cache. Files and
//    the route handlers (/offline/, /api/health/) keep their own Cache-Control.
// 5. The visitor's own pages need Django for everything, the session first: while Django's health check fails they
//    answer 503 with a Retry-After and a self-contained page (security review S5), never the log-in page (an outage
//    is not a log-out) nor a 200. Public pages render on, from Next's data cache where it has their answers.
import { type NextRequest, NextResponse } from "next/server";

import { buildCsp } from "@/lib/security/csp";
import { DJANGO_PREFIXES, isPersonalPage, SITE_URL } from "@/lib/site";
import { statusPage } from "@/lib/status-page";

const API_INTERNAL_BASE = (process.env.API_INTERNAL_BASE ?? "http://localhost:8100").replace(/\/$/, "");
const FILE = /\/[^/]+\.[a-z0-9]+$/i;

// Django's /health/web/ (database, cache, file storage), asked at most every 5 s; the requests that arrive while it is
// being asked share the one check
let health = { up: true, at: 0 };
let checking: Promise<boolean> | null = null;
function djangoAnswers(): boolean | Promise<boolean> {
  if (Date.now() - health.at < 5000) return health.up;
  checking ??= fetch(`${API_INTERNAL_BASE}/health/web/`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal: AbortSignal.timeout(2000),
  })
    .then(
      (response) => response.ok,
      () => false,
    )
    .then((up) => {
      health = { up, at: Date.now() };
      checking = null;
      return up;
    });
  return checking;
}

const UNREACHABLE = statusPage({
  title: "Cannot be reached",
  heading: "ExamLeaf cannot be reached just now",
  text: "This page needs our server, which is not answering. Please try again in a minute.",
});

export async function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (DJANGO_PREFIXES.some((prefix) => pathname.startsWith(prefix) || `${pathname}/` === prefix)) {
    return NextResponse.rewrite(new URL(`${pathname}${search}`, API_INTERNAL_BASE));
  }

  if (!pathname.endsWith("/") && !FILE.test(pathname)) {
    // on the public origin: behind Caddy, request.url names this server (http://localhost:3000), not the site; and
    // a plain URL, as NextURL would format the path back without its slash
    return NextResponse.redirect(new URL(`${pathname}/${search}`, SITE_URL), 308);
  }

  const page = !FILE.test(pathname) && !/^\/(offline|api)\//.test(pathname);
  const personal = page && isPersonalPage(pathname, request.cookies.has("sessionid"));
  if (personal && !(await djangoAnswers())) {
    return new NextResponse(UNREACHABLE, {
      status: 503,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
        "Retry-After": "30",
        "Content-Security-Policy":
          "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
      },
    });
  }

  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = buildCsp({
    nonce,
    pathname,
    dev: process.env.NODE_ENV === "development",
    https: SITE_URL.startsWith("https://"),
    mediaHost: process.env.NEXT_PUBLIC_MEDIA_HOST,
    turnstile: Boolean(process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY),
  });
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("x-pathname", pathname); // for not-found.tsx, which gets no params
  requestHeaders.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  if (page && !personal) response.headers.set("Cache-Control", "private, no-cache");
  return response;
}

export const config = {
  matcher: [
    {
      source: "/((?!_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
