// What the whole console shares about where it lives: its own address, the public website's, ERPNext's, and the
// paths Django answers. NEXT_PUBLIC_* values are compiled into the build (none of them is a secret).

/** The console's own address (no trailing slash): https://admin.examleaf.in, the host Django sees. */
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3020").replace(/\/$/, "");

/** The public website (https://examleaf.in): where staff set up two-step sign-in and passkeys. */
export const WEBSITE_URL = (process.env.NEXT_PUBLIC_WEBSITE_URL ?? "http://localhost:3000").replace(/\/$/, "");

/** ERPNext's desk (https://erp.examleaf.in): the business modules link there. Empty: those links are not drawn. */
export const ERP_URL = (process.env.NEXT_PUBLIC_ERP_URL ?? "").replace(/\/$/, "");

/** Paths Django answers, exactly the public site's list (examleaf-frontend/src/lib/site.ts): the Caddyfile sends them
 *  to web:8000 on the admin host too, and src/proxy.ts proxies them in development. /api/, /_allauth/, /static/ and
 *  /admin/ are all the console needs. */
export const DJANGO_PREFIXES = [
  "/api/v1/",
  "/api/schema/",
  "/api/docs/",
  "/api/redoc/",
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
