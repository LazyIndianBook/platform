# Resilience: the public site

What keeps `examleaf-frontend` answering when Django is slow, hung or gone, what keeps one process up, and why any
number of them can serve one visitor. Checked on 9 October 2026 against Next.js 16.4.0 and React 19.3: each item
verified in the code, fixed where it failed, then proven on a production build (`next build`, the standalone
`server.js` as the image runs it) under load against a stub Django. The console has its own:
`../examleaf-admin/RESILIENCE.md`.

## The checklist

| #   | Item                                             | Finding                                                                                                                                                                                                                                                                                                                                                       | Fix, or already right                                                                                                                                                                                                                                                                                                                                                                                                                                                     | Proof                                                                                                                                                            |
| --- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Server-side calls to Django time out             | None had a timeout but the proxy's health check (2 s): undici waits five minutes for the headers alone, so a hung Django held the page, its streamed placeholder and the visitor's connection.                                                                                                                                                                | `djangoFetch()` (`src/lib/api/server.ts`) for every call: a timer to the request's deadline, cleared once the whole answer is read. One deadline per request, the proxy's `x-request-start` plus `API_INTERNAL_TIMEOUT_MS` (10 s), shared by the layout, the page and `generateMetadata`. Then `<Unavailable/>`: `error.tsx`'s "This page can't be reached right now" in a 500.                                                                                           | `server.test.ts`, `outage.test.ts`. Django hung: every page's 500 in 10.0 to 11.4 s (run B1); the visitor's own pages the proxy's 503 in 2.0 s.                  |
| 2   | Browser calls time out and let go                | None had a timeout: a hung connection kept a button busy for good. The audit of every call site also found late answers overwriting newer ones (the coupon, the PIN lookup), overlapping progress saves, Turn on (authenticator) sendable twice, Pay stuck when Razorpay's window threw, unhandled rejections on log-out, a throttled reset link called dead. | `timedFetch` and `withTimeout()` (`src/lib/api/client.ts`): 30 s beside the caller's own signal; a change that timed out says it may have gone through, and nothing is sent again by itself. `useAction` and `useAuthAction` drop a second run while one is out. Each call site fixed. A 429 already said its wait: DRF's words ("Expected available in N seconds"), a time on the server pages and the contact form (`retryAt`), the form's own limit on the auth forms. | `client.test.tsx`; the `shop`, `course`, `account` and `auth` tests.                                                                                             |
| 3   | Any instance serves anyone                       | Module state: the proxy's 5-second health cache and the solutions' rendering cache. Nothing written to disk but Next's data cache, and the image optimizer was on, unused.                                                                                                                                                                                    | The health cache cannot wedge: a failed or hung check is asked again 5 s later. `images.unoptimized`: `/_next/image` answers 404, so `.next/cache` holds only the data cache (`unstable_cache`, 60 s, each instance its own, safe to lose). No ISR. The session is its cookies; `sessionStorage` holds drafts only; no `localStorage`. New: the calls in flight per public answer (item 4).                                                                               | `outage.test.ts` ("never wedges"); the build's route table: every page `ƒ`, only the manifest and `robots.txt` static.                                           |
| 4   | One process stays up                             | The load test found two leaks that kept every request (the process dead within a minute), a cold or stale cache sending Django one call per page view, a rendering cache that could reach 500 MB, Node's 5 s keep-alive under the proxies' 90 s and 2 minutes, and no heap limit.                                                                             | The leaks fixed (below); one call per public answer in flight, shared; the rendering cache an LRU of 160,000 characters (about 60 MB); the image sets `KEEP_ALIVE_TIMEOUT=125000` and `NODE_OPTIONS=--max-old-space-size=384`. Already right: Next's handlers log an uncaught exception and an unhandled rejection and keep serving; the image runs as `node`, the chart and compose with a read-only root.                                                               | The runs below. A thrown exception and rejection: logged, the server serving on. A connection idle 95 s: reused.                                                 |
| 5   | Graceful shutdown                                | Already right: Next's standalone server stops listening on SIGTERM, finishes the requests it has and exits 143. `/api/health/` answered 200 to the end.                                                                                                                                                                                                       | `/api/health/` answers 503 (`draining`) from SIGTERM on. Grace needed: the preStop, the 10 s deadline and about a second.                                                                                                                                                                                                                                                                                                                                                 | `route.test.ts`. SIGTERM with a request in flight: new connections refused at once, the request answered at 10.2 s with `Connection: close`, exit 143 at 10.3 s. |
| 6   | Error boundaries                                 | Already right: the root `error.tsx`, `not-found.tsx` and `global-error.tsx` cover the four route groups, whose layouts render inside the root layout; the house's copy; a digest, never a stack. `RouteFocus` and Next's route announcer untouched.                                                                                                           | Nothing to change.                                                                                                                                                                                                                                                                                                                                                                                                                                                        | The 500's HTML: the digest `examleaf-unavailable`, no stack trace.                                                                                               |
| 7   | Security headers, CSP, `x-middleware-subrequest` | Unchanged: `next.config.ts`'s headers, `src/lib/security/csp.ts` and the proxy's 503 policy untouched. Next 16.4.0 never reads `x-middleware-subrequest` (no file in the package names it); Caddy and the chart's Traefik drop it on the admin host only.                                                                                                     | Nothing to change here (an option under "The chart").                                                                                                                                                                                                                                                                                                                                                                                                                     | The header sent as `src/proxy` and as `middleware`, five times over: the CSP set, `/cart/` still the outage's 503.                                               |
| 8   | Load proof                                       | One build; 50 connections for 60 s with Django answering, hung, and hung behind a stale cache.                                                                                                                                                                                                                                                                | —                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | "The load proof", below.                                                                                                                                         |
| 9   | The chart's probes and grace period              | Right as they are; a few changes worth making.                                                                                                                                                                                                                                                                                                                | Listed under "The chart", not edited.                                                                                                                                                                                                                                                                                                                                                                                                                                     | `deploy/kubernetes/examleaf-platform/templates/nextjs.yaml`, `values.yaml`.                                                                                      |

## The two leaks

**The deadline's own timer.** The first deadline was an `AbortSignal.timeout()` per request, kept in React's cache of
the request. Node keeps such a signal's timer in a FinalizationRegistry until the signal is collected; the timer
carries the async context it was made in, the request's, and that context reaches the request's React cache, which
held the signal: neither could be collected. With 50 connections the heap grew by about 90 KB a request and the
process ran out of its 384 MB within a minute; a heap snapshot showed 540 requests alive, each held by a `Timeout`
through its `kResourceStore`. The integration branch's build stayed flat under the same load. `djangoFetch()` uses a
plain `AbortController` and a `setTimeout` it clears itself, and the deadline is a moment, not a signal.

**React's abort Error.** With that fixed, a signed-in visitor's pages (the session check and the cart count ask Django
on every one) still grew until the process died after 4,083 requests. React's server renderer ends every render by
aborting the request's cache signal with an `Error` made inside a `setImmediate` callback. Until an Error's stack is
read, V8 keeps its frames, and a frame holds the Immediate. Node leaves a run Immediate linked to those queued with
it, each holding the async context of the request that queued it, which holds that request's own Error. Under load
every request was chained to the next, and anything made during a request and kept (a keep-alive connection to
Django; Next's own resolved `io()` promise) held them all. `src/instrumentation.ts` wraps
`AbortController.prototype.abort` once at start so that an abort given an Error reads its stack first: V8 turns the
frames into a string and lets them go.

## The load proof

Each run: 50 keep-alive connections for 60 s, in turn to `/`, `/books/physics-2027/` and `/shop/`, from a Node script
with no dependency; the standalone `server.js` with the image's `--max-old-space-size=384` and
`KEEP_ALIVE_TIMEOUT=125000`; a stub Django on the same machine answering the config, the catalogue and the session,
with modes that sleep 15 s. The machine: an 8-core laptop shared with other work (load average up to 25), Node 20.19
(the image runs Node 24). The rates are the laptop's; the shapes are the code's. The heap is V8's `heapUsed` at the
run's first sample, its peak and its last; the RSS is macOS's, which leaves out compressed pages, so the heap is the
figure to trust.

| Run                                             | Requests       | Per s | p50       | p95       | Max       | Answers                                                     | Django: calls, most in flight, most connections | Heap MB: first, peak, last | RSS MB, peak |
| ----------------------------------------------- | -------------- | ----- | --------- | --------- | --------- | ----------------------------------------------------------- | ----------------------------------------------- | -------------------------- | ------------ |
| Before the fixes, Django answering              | 3,371          | 54    | 729 ms    | 2,050 ms  | 5,565 ms  | 3,340 × 200, then 31 resets: out of heap                    | 123, 1, 123                                     | 44, 352, died              | 463          |
| The integration branch, Django answering (26 s) | 1,223          | 48    | 959 ms    | 1,883 ms  | 2,108 ms  | all 200                                                     | —                                               | 26, 102, 85                | 212          |
| A: Django answering                             | 2,518          | 41    | 1,001 ms  | 2,447 ms  | 8,416 ms  | all 200                                                     | 16, 1, 7                                        | 49, 82, 64                 | 196          |
| A, on an earlier build of the fix               | 5,086          | 84    | 551 ms    | 1,074 ms  | 1,745 ms  | all 200                                                     | 129, 1, 130                                     | 26, 89, 78                 | 221          |
| B1: Django hung, the data cache empty           | 300            | 5     | 10,903 ms | 11,363 ms | 11,364 ms | all 500: the unavailable state                              | 24, 4, 5                                        | 39, 62, 54                 | 153          |
| B1 before the shared deadline and calls         | 234            | 3     | 10,315 ms | 20,584 ms | 20,858 ms | all 500, the book page's after 20 s                         | 712, 133, 133                                   | 26, 81, 63                 | 167          |
| B2: Django hung, the data cache stale           | 4,550          | 76    | 492 ms    | 1,524 ms  | 6,439 ms  | all 200, from the stale cache                               | 36, 6, 12                                       | 72, 196, 128               | 311          |
| B2 before the shared calls                      | 3,521          | 58    | 747 ms    | 1,771 ms  | 6,511 ms  | all 200, from the stale cache                               | 14,083, 3,345, 3,504                            | 63, 290, 278               | 473          |
| S: signed in, two calls to Django a page        | 5,852          | 97    | 359 ms    | 1,397 ms  | 3,947 ms  | all 200                                                     | 11,708, 1, 96                                   | 40, 100, 78                | 259          |
| S before the abort wrapper                      | 4,083 answered | —     | —         | —         | —         | 4,083 × 200, then 50 resets and 25,295 refused: out of heap | 8,256, 1, 60                                    | 76, 341, died              | 485          |

A, B1 and B2 ran on the build before the abort wrapper: those pages, answered from the data cache, rarely call
Django, and their heap stayed bounded without it. S ran on the final code. Also measured on the final build: SIGTERM
with a request in flight (item 5); `Keep-Alive: timeout=125`, and a connection idle 95 s reused; `/_next/image` 404;
`/account/` during the outage the proxy's 503 with `Retry-After: 30`, in 2.0 s. The solutions' rendering cache,
measured apart on the 13 committed test papers: 637 texts (220 KB of Markdown) kept 80 MB, 129 KB a text; a whole
paper's solutions take 176 ms to render, 2 ms from the cache.

## Graceful shutdown and the probes

On SIGTERM Next's standalone server stops listening at once (so the kubelet's probes and new connections are refused
and the pod reads not ready), finishes the requests it has and exits 143. A request lasts until its deadline at the
latest (10 s), and its answer carries `Connection: close`. `/api/health/` answers 503 from SIGTERM on, for whatever
still asks on a connection already open. Kubernetes takes a terminating pod out of its Service's endpoints at once;
the chart's preStop sleep lets Traefik follow before SIGTERM comes. So the grace needed is the preStop, plus the 10 s
deadline, plus about a second: the chart gives the preStop plus 20 s. Docker Compose has no preStop and kills a
container 10 s after SIGTERM by default, the deadline itself: `stop_grace_period: 15s` on the frontend service lets
the last request finish.

Keep-alive: a proxy keeps an idle connection to this server in its pool (Traefik 90 s by default, Caddy 2 minutes)
and may send the next request on it at any moment. If this server closes it first (Node's default is 5 s), a request
sent as it closes fails with a 502. So the server's keep-alive must be longer than the proxy's: the image sets
`KEEP_ALIVE_TIMEOUT=125000`. Node closes idle connections when the server closes, so it does not slow the shutdown.

## The operator's knobs

| Knob                      | Where                                   | Default                    | What it does                                                                                       |
| ------------------------- | --------------------------------------- | -------------------------- | -------------------------------------------------------------------------------------------------- |
| `API_INTERNAL_TIMEOUT_MS` | environment                             | 10000                      | How long one request may wait on Django in all. Raise the grace period with it.                    |
| `NODE_OPTIONS`            | environment (the image's)               | `--max-old-space-size=384` | The heap limit: about 75 % of the memory limit (576 for 768Mi, 768 for 1Gi).                       |
| `KEEP_ALIVE_TIMEOUT`      | environment (the image's)               | 125000                     | Longer than the proxy keeps an idle connection (Traefik's `idleConnTimeout`, Caddy's `keepalive`). |
| `ANSWER_TIMEOUT_MS`       | `src/lib/api/client.ts`                 | 30 s                       | How long the browser waits for an answer.                                                          |
| `CACHE_CHARS`             | `src/components/solutions/markdown.tsx` | 160,000                    | The solutions' rendering cache, in characters (about 375 bytes of heap each).                      |
| `REVALIDATE_SECONDS`      | `src/lib/api/server.ts`                 | 60                         | How long one instance keeps a public answer before it asks again.                                  |
| The health cache          | `src/proxy.ts`                          | 5 s, 2 s                   | How often the visitor's own pages ask `/health/web/`, and how long they wait for it.               |

## The chart

`deploy/kubernetes/examleaf-platform` as on `design/answer-script`, for the frontend (the admin has the same
template). Not edited here:

- **Probes.** `/api/health/` for startup, readiness and liveness, the process only, never Django: right, and it now
  answers 503 while draining. Nothing to change.
- **Grace period.** `terminationGracePeriodSeconds` is `preStopSeconds` + 20 (30 s): enough for the preStop and the
  10 s deadline. Keep the 20 at least `API_INTERNAL_TIMEOUT_MS` + 5 s if that changes.
- **Heap.** The image sets `--max-old-space-size=384` for the 512Mi limit. With another limit, set
  `frontend.env.NODE_OPTIONS` to about 75 % of it, e.g. `"--max-old-space-size=576"` for 768Mi. Under load the
  process stayed under 320 MB of RSS with the fixes; before them it reached 485 MB.
- **Keep-alive.** The image's 125 s is longer than Traefik's `serversTransport` `idleConnTimeout` (90 s;
  `traefik-values.yaml` keeps it). If that is raised, set `frontend.env.KEEP_ALIVE_TIMEOUT` above it.
- **The data cache's volume.** `/app/.next/cache` now holds only the data cache, a few MB: its 1Gi emptyDir could be
  `medium: Memory` with a `sizeLimit` of 64Mi, as compose's tmpfs is.
- **A backstop at the edge (optional).** Traefik's `forwardingTimeouts.responseHeaderTimeout` is 0, none; 30 s, above
  the 10 s deadline, would cut a server that never answers (a stuck process, not Django).
- **`X-Middleware-Subrequest` (optional).** `drop-subrequest` runs on the admin host only. Next 16.4 never reads the
  header, so the website is safe without it; the Middleware on the website's host too (and
  `request_header -X-Middleware-Subrequest` in Caddy's main site) would keep it so whatever a later Next does.
- **Replicas.** Any number: the session is cookies only. Each replica keeps its own data cache (60 s) and its own
  calls in flight, so Django sees at most one call per answer per replica.

## Deferred

- **Next's log of failed refreshes.** During an outage with a warm cache, Next logs every request's failed background
  refresh ("revalidating cache with key: …", with its stack): 15,048 lines (17 MB) in the minute of run B2. It is
  inside `unstable_cache`; quieting it means a custom `cacheHandler` or moving the public answers to `'use cache'`, a
  migration rather than a hardening.
- **`revalidateTag` across replicas.** Nothing calls it yet; once a webhook does, it reaches one pod only, until a
  shared cache handler exists. Each pod refreshes on its own within 60 s meanwhile.
- **Version skew in a rolling update.** No `deploymentId`: the consent page's server action, posted from an old page to
  a new build, answers "Failed to find Server Action". A reload mends it.
- **A change that timed out, pressed again.** The words say to check first, but the API takes no idempotency key, so a
  second press can make a second order, cart line, attempt or address.
- **429 wording.** allauth's rate limits come with no `Retry-After`, so the account's security forms say "Wait a
  little"; outside the server pages and the contact form, DRF's wait shows in its own words, in seconds.
- **A failed page without script.** Next 16 draws `error.tsx` after hydration: with script off, a page that failed
  shows no words. The proxy's 503 is self-contained.
- **A body cut off after the headers** of a 200 in allauth's browser client reads as "not signed in": rare (Django
  writes whole answers), and bounded by the 30 s.
- **One visitor's headers on a shared call.** A public answer's call carries the `X-Forwarded-For` and `User-Agent` of
  the visitor who asked first, as `unstable_cache`'s kept answer already did for everyone after.
- **The abort wrapper** (`src/instrumentation.ts`) works around React and Node: remove it once React stops leaving
  that Error or Node unlinks a run Immediate, and run the signed-in load again to see.
