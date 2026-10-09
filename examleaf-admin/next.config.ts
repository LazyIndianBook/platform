import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

const https = (process.env.NEXT_PUBLIC_SITE_URL ?? "").startsWith("https://");

// The headers Django sets on its own pages, for every answer of the console, tightened for a staff tool: no referrer
// leaves it, it is never framed, never indexed. The Content-Security-Policy is per request (a nonce): src/proxy.ts.
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  { key: "Cross-Origin-Resource-Policy", value: "same-origin" },
  { key: "X-Robots-Tag", value: "noindex, nofollow" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
  ...(https ? [{ key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" }] : []),
];

export default function config(phase: string): NextConfig {
  return {
    output: "standalone",
    trailingSlash: true,
    // allauth.headless paths have no trailing slash: src/proxy.ts adds the slash everywhere else
    skipTrailingSlashRedirect: true,
    poweredByHeader: false,
    // STAFF_API_MOCK=1 points the staff API at the fixtures of src/mocks/staff/ (src/lib/api/staff.ts), and only under
    // `next dev`: every build compiles it to "", so a production bundle can never answer from fixtures.
    env: {
      STAFF_API_MOCK: phase === PHASE_DEVELOPMENT_SERVER && process.env.STAFF_API_MOCK === "1" ? "1" : "",
    },
    turbopack: {
      rules: {
        "*.css": {
          loaders: ["@tailwindcss/turbopack"],
          as: "*.css",
        },
      },
    },
    async headers() {
      return [{ source: "/:path*", headers: securityHeaders }];
    },
  };
}
