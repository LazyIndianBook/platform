// Next's request proxy (Next 16's name for middleware.ts), on every request but static files and prefetches:
// 1. Django's prefixes (src/lib/site.ts) are passed to API_INTERNAL_BASE. Caddy does this in production, so these
//    requests only arrive here in development and CI, where there is no Caddy.
// 2. Every other path gets its trailing slash (trailingSlash: true; skipTrailingSlashRedirect leaves it to us because
//    allauth's paths have none).
// 3. Every page gets a fresh nonce and its Content-Security-Policy (src/lib/security/csp.ts).
import { type NextRequest, NextResponse } from "next/server";

import { buildCsp } from "@/lib/security/csp";
import { DJANGO_PREFIXES, SITE_URL } from "@/lib/site";

const API_INTERNAL_BASE = (process.env.API_INTERNAL_BASE ?? "http://localhost:8100").replace(/\/$/, "");
const FILE = /\/[^/]+\.[a-z0-9]+$/i;

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (DJANGO_PREFIXES.some((prefix) => pathname.startsWith(prefix) || `${pathname}/` === prefix)) {
    return NextResponse.rewrite(new URL(`${pathname}${search}`, API_INTERNAL_BASE));
  }

  if (!pathname.endsWith("/") && !FILE.test(pathname)) {
    // on the public origin: behind Caddy, request.url names this server (http://localhost:3000), not the site; and
    // a plain URL, as NextURL would format the path back without its slash
    return NextResponse.redirect(new URL(`${pathname}/${search}`, SITE_URL), 308);
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
