// /api/health/: the container's health check (Dockerfile HEALTHCHECK) and the chart's probes. It checks this process
// only, never Django: a backend outage must not restart the frontend (pages show their unavailable state instead).
// From SIGTERM on it answers 503: Next's server then stops taking connections and finishes the requests it has
// (RESILIENCE.md, "Graceful shutdown"), and whatever still asks on a connection already open hears it is going.
export const dynamic = "force-dynamic";

let draining = false;
process.once("SIGTERM", () => {
  draining = true;
});

export function GET() {
  return Response.json(
    { status: draining ? "draining" : "ok" },
    { status: draining ? 503 : 200, headers: { "Cache-Control": "no-store" } },
  );
}
