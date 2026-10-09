// The staff API mock's door for the browser (src/mocks/staff/handler.ts), development and tests only. Every build
// compiles STAFF_API_MOCK to "" (next.config.ts), so there this route throws before it reaches any fixture, and the
// fixtures stay out of the bundle (the import sits behind the same check).
export const dynamic = "force-dynamic";

const OFF = "The staff API mock answers only under `next dev` with STAFF_API_MOCK=1.";

async function answer(request: Request): Promise<Response> {
  if (process.env.STAFF_API_MOCK === "1") return (await import("@/mocks/staff/handler")).handleMock(request);
  throw new Error(OFF);
}

export const GET = answer;
export const POST = answer;
export const PUT = answer;
export const PATCH = answer;
export const DELETE = answer;
