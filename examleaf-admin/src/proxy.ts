// Next's request proxy (Next 16's name for middleware.ts), on every request but static files and prefetches, as the
// public site's (examleaf-frontend/src/proxy.ts):
// 1. Django's prefixes (src/lib/site.ts) are passed to API_INTERNAL_BASE. Caddy does this in production, so these
//    requests only arrive here in development and CI.
// 2. Every other path gets its trailing slash (trailingSlash: true; allauth's paths have none).
// 3. Every page gets a fresh nonce and its Content-Security-Policy (src/lib/security/csp.ts), and the path it was
//    asked for (x-pathname: a page's "sign in, then back here").
// 4. Every page is the person's own: private, no-store (nothing keeps it, not even the browser's back button).
// 5. While Django's health check fails, pages answer 503 with a Retry-After and a self-contained page: an outage is
//    never a sign-out, nor a 200.
// It is never the access check: every page asks the staff API for the session itself (src/lib/auth/session.ts).
import { type NextRequest, NextResponse } from "next/server";

import { copy } from "@/lib/copy";
import { buildCsp } from "@/lib/security/csp";
import { DJANGO_PREFIXES, FORWARDED_HEADERS, SITE_URL } from "@/lib/site";
import { statusPage } from "@/lib/status-page";

const API_INTERNAL_BASE = (process.env.API_INTERNAL_BASE ?? "http://localhost:8100").replace(/\/$/, "");
const FILE = /\/[^/]+\.[a-z0-9]+$/i;

// Django's /health/web/ (database, cache, file storage), asked at most every 5 s; requests meanwhile share one check
let health = { up: true, at: 0 };
let checking: Promise<boolean> | null = null;
function djangoAnswers(): boolean | Promise<boolean> {
  if (Date.now() - health.at < 5000) return health.up;
  checking ??= fetch(`${API_INTERNAL_BASE}/health/web/`, {
    // the console's host and https, as every server-side call names them: with DEBUG=0 Django refuses web:8000 (400)
    headers: { ...FORWARDED_HEADERS, Accept: "application/json" },
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
  title: copy.errors.unavailableTitle,
  heading: copy.errors.unavailableTitle,
  text: copy.errors.unavailableText,
});

export async function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (DJANGO_PREFIXES.some((prefix) => pathname.startsWith(prefix) || `${pathname}/` === prefix)) {
    return NextResponse.rewrite(new URL(`${pathname}${search}`, API_INTERNAL_BASE));
  }

  if (!pathname.endsWith("/") && !FILE.test(pathname)) {
    return NextResponse.redirect(new URL(`${pathname}/${search}`, SITE_URL), 308);
  }

  const page = !FILE.test(pathname) && !pathname.startsWith("/api/");
  if (page && !(await djangoAnswers())) {
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
  const csp = buildCsp({ nonce, dev: process.env.NODE_ENV === "development", https: SITE_URL.startsWith("https://") });
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("x-pathname", `${pathname}${search}`);
  requestHeaders.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  if (page) response.headers.set("Cache-Control", "private, no-cache, no-store, max-age=0, must-revalidate");
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
