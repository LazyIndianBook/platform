// Next calls register() once as the server starts, before it takes any request.
//
// React's server renderer ends every render by aborting the request's cache signal with an Error raised inside a
// setImmediate callback. Until that Error's stack is read, V8 keeps its frames, and a frame holds the Immediate; Node
// leaves a run Immediate linked to those queued with it, each holding the async context of the request that queued
// it, which holds that request's own Error. Under load this chained every request to the next, and anything
// long-lived made during one request (a keep-alive connection, a module's cached promise) kept them all: the server
// ran out of memory within a minute (RESILIENCE.md, "The second leak"). Reading the stack of an abort's Error turns
// its frames into a string and lets them go.
export function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  const abort = AbortController.prototype.abort;
  AbortController.prototype.abort = function (this: AbortController, reason?: unknown) {
    if (reason instanceof Error) void reason.stack;
    return abort.call(this, reason);
  };
}
