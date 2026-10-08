import type { NextConfig } from "next";

const https = (process.env.NEXT_PUBLIC_SITE_URL ?? "").startsWith("https://");

// The headers Django sets on its own pages (examleaf/settings.py), for every answer of the frontend. The
// Content-Security-Policy is per request (a nonce): src/proxy.ts.
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "same-origin" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(self)" },
  ...(https ? [{ key: "Strict-Transport-Security", value: "max-age=31536000" }] : []),
];

// Django's own page addresses that this site answers elsewhere (old bookmarks and emails; docs/design/parity-nextjs.md):
// a temporary redirect, so that a page coming back later is not hidden by a browser's cached 308.
const DJANGO_PAGES: [string, string][] = [
  ["/account/register/", "/account/signup/"],
  ["/account/login/code/", "/account/login/"],
  ["/account/login/code/confirm/", "/account/login/"],
  ["/account/3rdparty/login/:path*", "/account/login/"],
  ["/account/3rdparty/signup/", "/account/signup/"],
  ["/account/3rdparty/", "/account/security/#google"],
  ["/account/confirm-email/", "/account/verify-email/"],
  ["/account/password/reset/done/", "/account/password/reset/"],
  ["/account/password/reset/key/done/", "/account/login/"],
  ["/account/email/", "/account/security/#change-email"],
  ["/account/password/change/", "/account/security/#change-password"],
  ["/account/password/set/", "/account/security/#change-password"],
  ["/account/phone/:path*", "/account/security/#mobile-number"],
  ["/account/2fa/webauthn/:path*", "/account/security/#passkeys"],
  ["/account/2fa/totp/:path*", "/account/2fa/"],
  ["/account/2fa/recovery-codes/:path*", "/account/2fa/"],
  ["/account/data/", "/account/privacy/#data"],
  ["/account/delete/", "/account/privacy/#delete"],
  ["/account/addresses/:path+", "/account/addresses/"],
  ["/account/record/add/:code/", "/s/:code/#record"],
  ["/account/orders/:number/invoice/", "/api/v1/orders/:number/invoice/"],
  ["/account/orders/:number/credit-notes/:id/", "/api/v1/orders/:number/credit-notes/:id/"],
  ["/orders/t/:token/invoice/", "/api/v1/orders/t/:token/invoice/"],
  ["/orders/t/:token/credit-notes/:id/", "/api/v1/orders/t/:token/credit-notes/:id/"],
  ["/favicon.ico", "/favicon-32.png"], // as Django's examleaf/urls.py: crawlers ask for it by name
];

const nextConfig: NextConfig = {
  output: "standalone",
  trailingSlash: true,
  // allauth.headless paths have no trailing slash (/_allauth/browser/v1/auth/session): src/proxy.ts adds the slash
  // everywhere else and passes Django's prefixes through untouched.
  skipTrailingSlashRedirect: true,
  poweredByHeader: false,
  // a second `next dev` beside another in this directory (Next refuses two in one distDir): NEXT_DIST_DIR=.next/cache/b
  ...(process.env.NEXT_DIST_DIR ? { distDir: process.env.NEXT_DIST_DIR } : {}),
  // a new service-worker cache per build (public/sw.js)
  env: { NEXT_PUBLIC_RELEASE: process.env.NEXT_PUBLIC_RELEASE || String(Date.now()) },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async redirects() {
    return DJANGO_PAGES.map(([source, destination]) => ({ source, destination, permanent: false }));
  },
  async headers() {
    return [
      { source: "/:path*", headers: securityHeaders },
      // the service worker must never be cached by the browser's HTTP cache, or a new release would wait a day
      { source: "/sw.js", headers: [{ key: "Cache-Control", value: "no-cache" }] },
    ];
  },
};

export default nextConfig;
