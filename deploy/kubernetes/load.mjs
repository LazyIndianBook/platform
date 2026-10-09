// A steady request stream for TESTING.md's chaos runs (hey is not installed on the test machine): CONNECTIONS
// keep-alive connections for SECONDS, the URLs shared out among them. Each sends its next request as soon as the last
// is answered, or with --rate at its share of RATE requests a second in all (a stream that leaves the servers room,
// so that what a failure costs is not lost in a saturated machine). Every host resolves to 127.0.0.1 (the kind node's
// ports) and the self-signed certificates are accepted. Prints the latency percentiles, the answers by status and
// the failures, with the seconds they fell in.
//   node load.mjs [--connections 50] [--seconds 60] [--rate 100] URL...
// A failure is a status of 500 or more, or no answer at all (a reset, a timeout of 10 s).
import http from "node:http";
import https from "node:https";

const args = process.argv.slice(2);
const option = (name, fallback) => {
  const at = args.indexOf(`--${name}`);
  return at === -1 ? fallback : Number(args.splice(at, 2)[1]);
};
const connections = option("connections", 50);
const seconds = option("seconds", 60);
const rate = option("rate", 0); // requests a second in all; 0: as fast as the answers come
const urls = args.map((url) => new URL(url));
if (!urls.length) throw new Error("usage: node load.mjs [--connections 50] [--seconds 60] URL...");

const lookup = (hostname, options, callback) =>
  options.all ? callback(null, [{ address: "127.0.0.1", family: 4 }]) : callback(null, "127.0.0.1", 4);
const agents = {
  "https:": new https.Agent({ keepAlive: true, maxSockets: connections, lookup, rejectUnauthorized: false }),
  "http:": new http.Agent({ keepAlive: true, maxSockets: connections, lookup }),
};

const latencies = [];
const statuses = {};
const failures = {}; // second -> count
const failureKinds = {};
const start = Date.now();
const end = start + seconds * 1000;
let sent = 0;

function once(url) {
  return new Promise((resolve) => {
    const began = performance.now();
    const request = (url.protocol === "https:" ? https : http).get(
      url,
      { agent: agents[url.protocol], timeout: 10_000, headers: { Accept: "application/json, text/html" } },
      (response) => {
        response.resume();
        response.on("end", () => resolve({ status: response.statusCode, ms: performance.now() - began }));
      },
    );
    request.on("timeout", () => request.destroy(new Error("timeout")));
    request.on("error", (error) => resolve({ error: error.code || error.message, ms: performance.now() - began }));
  });
}

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function connection(index) {
  const every = rate ? (connections * 1000) / rate : 0; // ms between this connection's requests
  let due = start + (every * index) / connections; // the connections' turns spread over one interval
  for (let turn = index; Date.now() < end; turn += connections) {
    if (every) {
      if (due > Date.now()) await pause(due - Date.now());
      due += every;
    }
    const result = await once(urls[turn % urls.length]);
    sent += 1;
    latencies.push(result.ms);
    const second = Math.floor((Date.now() - start) / 1000);
    if (result.error || result.status >= 500) {
      const kind = result.error || String(result.status);
      failureKinds[kind] = (failureKinds[kind] || 0) + 1;
      failures[second] = (failures[second] || 0) + 1;
    }
    if (result.status) statuses[result.status] = (statuses[result.status] || 0) + 1;
  }
}

await Promise.all(Array.from({ length: connections }, (_, index) => connection(index)));
latencies.sort((a, b) => a - b);
const at = (share) => latencies[Math.min(latencies.length - 1, Math.floor(share * latencies.length))].toFixed(0);
const failed = Object.values(failureKinds).reduce((sum, count) => sum + count, 0);
console.log(
  JSON.stringify({
    requests: sent,
    perSecond: Math.round(sent / seconds),
    p50ms: Number(at(0.5)),
    p95ms: Number(at(0.95)),
    p99ms: Number(at(0.99)),
    maxMs: Number(latencies.at(-1).toFixed(0)),
    statuses,
    failed,
    failureKinds,
    failuresBySecond: failures,
  }),
);
