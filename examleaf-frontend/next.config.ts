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
  async headers() {
    return [
      { source: "/:path*", headers: securityHeaders },
      // the service worker must never be cached by the browser's HTTP cache, or a new release would wait a day
      { source: "/sw.js", headers: [{ key: "Cache-Control", value: "no-cache" }] },
    ];
  },
};

export default nextConfig;
