// What the whole frontend shares about the site: its address, the subjects' token names and Django's paths.

/** The public address (no trailing slash): canonical URLs, Open Graph, the sitemap. Set at build time. */
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000").replace(/\/$/, "");
export const SITE_NAME = "ExamLeaf";

/** Sent with every server-side call to Django, which builds absolute URLs (covers, links) and checks ALLOWED_HOSTS
 *  with the public host, as when Caddy forwards a request: it trusts X-Forwarded-Host (USE_X_FORWARDED_HOST=1) and,
 *  behind a proxy, X-Forwarded-Proto. Without them it sees the internal host (web:8000), refuses it (400) and, with
 *  DEBUG=0, would redirect plain http to https first. */
const site = new URL(SITE_URL);
export const FORWARDED_HEADERS = {
  "X-Forwarded-Host": site.host,
  "X-Forwarded-Proto": site.protocol.replace(":", ""),
};

/** Paths Django answers (Caddyfile sends them to web:8000; src/proxy.ts proxies them in development and CI). */
export const DJANGO_PREFIXES = [
  "/api/v1/",
  "/api/schema/",
  "/api/docs/",
  "/api/redoc/",
  "/api/hooks/", // the couriers' webhook (examleaf-web/shipping/webhooks.py)
  "/_allauth/",
  "/admin/",
  "/shop/webhooks/",
  "/anymail/",
  "/health/",
  "/shop/media/",
  "/learn/preview/",
  "/learn/hls/",
  "/account/google/",
  "/qr/",
  "/static/",
];

/**
 * A page that is the visitor's own: never stored anywhere (Next answers it `private, no-cache, no-store`). /s/ and
 * /revision/ are once a session exists (solutions, the course). Every other page may be kept by the browser alone
 * (`private, no-cache`, src/proxy.ts: back and forward stay instant), never by a shared cache: each carries the header's
 * signed-in state and cart count, and its own CSP nonce.
 */
export function isPersonalPage(pathname: string, hasSession: boolean): boolean {
  return /^\/(account|cart|checkout|orders|c)\//.test(pathname) || (hasSession && /^\/(s|revision)\//.test(pathname));
}

export type SubjectKey = "physics" | "chemistry" | "maths" | "biology";

/** Subject codes of the API (PHY, CHE, MAT, BIO) to the token names of tokens.css (--physics, --physics-pill …). */
export const SUBJECTS: Record<string, { key: SubjectKey; name: string }> = {
  PHY: { key: "physics", name: "Physics" },
  CHE: { key: "chemistry", name: "Chemistry" },
  MAT: { key: "maths", name: "Mathematics" },
  BIO: { key: "biology", name: "Biology" },
};

export const TIERS = { E: "Easy", M: "Medium", H: "Hard" } as const;
export type TierCode = keyof typeof TIERS;

/** "PHY-E01" → "E-01", as the books print it. */
export function shortCode(code: string): string {
  const match = /([EMH])(\d+)$/.exec(code);
  return match ? `${match[1]}-${match[2].padStart(2, "0")}` : code;
}

export function subjectOf(code: string | null | undefined) {
  return (code && SUBJECTS[code]) || null;
}
