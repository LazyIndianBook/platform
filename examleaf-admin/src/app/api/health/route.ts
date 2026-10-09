// /api/health/: the container's health check (Dockerfile HEALTHCHECK). It checks this process only, never Django: a
// backend outage must not restart the console (pages say they cannot reach it instead).
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ status: "ok" }, { headers: { "Cache-Control": "no-store" } });
}
