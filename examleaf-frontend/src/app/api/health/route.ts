// /api/health/: the container's health check (Dockerfile HEALTHCHECK). It checks this process only, never Django:
// a backend outage must not restart the frontend (pages show their unavailable state instead).
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ status: "ok" }, { headers: { "Cache-Control": "no-store" } });
}
