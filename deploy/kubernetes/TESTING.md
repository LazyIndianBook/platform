# The chart on kind: what was run and what it showed

![Status](../../docs/assets/badges/status-archive.svg) ![Component](../../docs/assets/badges/component-kubernetes.svg) ![Audience](../../docs/assets/badges/audience-operators.svg)

Three runs on 9 October 2026 on a MacBook (Apple silicon) whose Docker is a Colima VM of 4 CPUs, 6 GiB of memory and
a 60 GiB disk (Docker 29.2.1, kind 0.32.0, Helm 4.2.2, kubectl 1.32.2), each on a one-node cluster from
`kind-config.yaml` (`kindest/node:v1.35.5`, ports 80 and 443 of the Mac forwarded to it), each deleted afterwards.
Everything was run from `deploy/kubernetes/`; Secrets were made with random values by `make kind-secrets` and are not
shown. kubectl 1.32 talks to a 1.35 server, three minor versions apart (it warns); every command below worked.
Operators read it for what the chart was shown to do, and for what is still untried.

> [!NOTE]
> **At a glance**
>
> - A record of what was run, not a procedure: three runs on 9 October 2026, each on a one-node `kind` cluster that was
>   deleted afterwards: run 2 on Traefik (sections 1 to 6), run 3, the HA profile under failure and load (section 7), and
>   run 1 on ingress-nginx (section 8), whose routing results the second replaced.
> - Run 3 killed a web pod, a frontend pod, the PostgreSQL primary, the queue's Redis and a worker under a steady stream
>   of requests and rolled a new image; what it found changed the chart.
> - Not tested: Let's Encrypt and real DNS, Cloudflare R2, k3s's own Traefik, more than one node and ERPNext running
>   (section 9).
> - Phase B changed what the chart carries and no kind run has seen it: section 10 lists, in order, what the next run
>   should check.

## Contents

- [The runs](#the-runs)
- [What the runs proved](#what-the-runs-proved)
- [1. Images and the cluster](#1-images-and-the-cluster)
- [2. Routing, as the Caddyfile has it](#2-routing-as-the-caddyfile-has-it)
- [3. The health gate](#3-the-health-gate)
- [4. Body limits](#4-body-limits)
- [5. Changes on a running release](#5-changes-on-a-running-release)
- [6. Checked without a cluster: ERPNext, the other options, the admin panel's image](#6-checked-without-a-cluster-erpnext-the-other-options-the-admin-panels-image)
- [7. Run 3: the HA profile under failure and load](#7-run-3-the-ha-profile-under-failure-and-load)
- [8. Run 1, on ingress-nginx](#8-run-1-on-ingress-nginx)
- [9. Not tested, and why](#9-not-tested-and-why)
- [10. Phase B: what the next run should check (not run)](#10-phase-b-what-the-next-run-should-check-not-run)
- [11. Cleaning up](#11-cleaning-up)
- [Related documents](#related-documents)

## The runs

| Run | UTC | Sections | What it did |
|---|---|---|---|
| **Run 1, on ingress-nginx** | 03:00–04:15 | 8 | the chart's first version, which the second replaced where the controller is concerned; what it showed about everything else still stands |
| **Run 2, on Traefik** | 04:48–05:25 | 1 to 6 | routing, health, limits and upgrades on the chart of then (e5a4f46), images built at 3529b96 (the platform with the Celery health fix) |
| **The admin panel's own image** | 05:41–05:47 | 6 | it reached the integration branch after run 2 (in 6ec1af5), where the website's image had stood in for it; built and run on its own as the chart runs it |
| **Run 3, the HA profile under failure and load** | 06:41–08:48 | 7 | values-ha.yaml on the one node, a web pod, a frontend pod, the PostgreSQL primary, the queue's Redis and a worker killed under a steady stream of requests, and a new image rolled; what it found changed the chart (readiness, PgBouncer, the deadlines, the checksum) |

## What the runs proved

| What was run | What it showed | Section |
|---|---|---|
| **The install** (run 2) | `helm upgrade --install` of the kind profile took 3 minutes 38 seconds, most of it pulling PostgreSQL's and the plugin's images again: the frontend and the admin stand-in ready at once, the database healthy, web's init container through the migrations to gunicorn, worker, beat and the media worker out of their wait, the first base backup completed | 1 |
| **Routing**, as the Caddyfile has it | each request of the table answered as listed (the website, Django, WhiteNoise, the admin host); the http redirect keeps the whole path and query, 301 for a GET and 308 for a POST | 2 |
| **The health gate** | 401 without credentials or with a wrong password, 200 with the token (`Database`, `Cache`, `Storage` and `WorkerPing` all `OK`); with its Secret deleted `/health` answered the website's 404, because `health-hide` rewrites it | 3 |
| **Body limits** | an 11 MB POST to Django's form and API paths got 413 from Traefik (`body-limit`); the clip and revision admin pages are streamed and Django refused them; the website's paths have no limit at the edge | 4 |
| **A running release** | the admin allowlist answered 403 outside its range and 200 inside; an upgrade with a changed setting took 29 seconds, every Deployment rolled and beat never had more than one pod; `check --deploy` gave W005 and W021 only; the Cluster reported `ContinuousArchiving=True` | 5 |
| **Memory** | the release's working sets came to 851 MiB and the node's to 1.8 GiB in all (Traefik 30 MiB where ingress-nginx used 64) | 5 |
| **ERPNext and the admin panel's image**, without a cluster | the chart with `erpnext.enabled` was accepted by the API server in a server-side dry run, and refused to render without an image tag, as it should (ERPNext did not run); the admin's image ran as `uid=1000(node)` in 56 MiB and its `/api/health/` answered 200 | 6 |
| **Run 3: the install** | two web pods started together, one applied 179 migrations in about two minutes and the other found "No migrations to apply" once the lock freed; `/health/` answered through the pooler; the alerts' 15 rules passed `promtool check rules` | 7.1 |
| **Run 3: the load** | paced at 100 requests a second the baseline was 5,959 requests, p50 83 ms, p95 1,387 ms, none failed; unpaced it found three faults before anything was broken (429s, 503s from web's readiness probe, requests stuck by gunicorn's recycling) | 7.2, 7.3 |
| **A web pod and a frontend pod deleted** | not one request failed on either, because Traefik keeps a terminating pod "fenced" and sends it nothing new; 15 timeouts fell on the web pod that stayed | 7.3 |
| **The primary killed** | the standby took writes at 35 seconds (the first time 80 seconds more, while PostgreSQL asked the archive for timeline history), no pod of the site restarted and nothing was lost; the uncached path answered 945 times 503 until the chart set PgBouncer's `query_wait_timeout` to 10 (not measured again) | 7.3 |
| **The queue's Redis restarted** with 200 tasks waiting | back in 2 seconds when deleted and 3 when killed, each with 200; all 200 succeeded within 27 seconds of the workers' return | 7.3 |
| **A worker killed in the middle of a task** | recorded as FAILURE and not retried, the clip left "processing"; with `CELERY_TASK_ACKS_LATE`, `CELERY_TASK_REJECT_ON_WORKER_LOST` and a `visibility_timeout` of 7200 seconds on a test-only settings module it was delivered again, retried once and succeeded | 7.3 |
| **A new web image rolled under load** | no pod answered 5xx, the old web pods served until new ones were ready and beat never doubled; every Deployment rolled because of a checksum fault (fixed), the node's CPU went to 400% and Helm's 10 minutes ran out; not repeated after the fixes | 7.3 |
| **A point-in-time restore** (run 1) | a row written after the base backup came back in a new Cluster made from the bucket in 82 seconds, every pod moved to the new `DATABASE_URL` and the old one stayed until deleted; a drain of beat was refused by its disruption budget and the worker's allowed; an uninstall kept the Cluster, `examleaf-media` and `examleaf-redis-queue` | 8 |

## 1. Images and the cluster

```sh
make images TAG=3529b96 DOMAIN=examleaf.localhost     # 04:48 → 04:53
```

```sh
make kind-up                                           # 04:55:37 → 04:58:26
```

```sh
make kind-secrets
```

```sh
make kind-load TAG=3529b96                             # 35 s
```

```sh
make kind-install TAG=3529b96                          # helm upgrade --install … -f values-kind.yaml --wait: 04:59:51 → 05:03:29
```

Both Dockerfiles built unchanged, now named under the registry: `ghcr.io/lazyindianbook/examleaf-web:3529b96`
(1.51 GB) and `ghcr.io/lazyindianbook/examleaf-frontend:3529b96` (333 MB), the frontend for
`https://examleaf.localhost`. `kind-up` installed Traefik 3.7.14 from its Helm chart 41.7.0 into `kube-system` (as k3s
runs its own) with `traefik-values.yaml` (its arguments showed `respondingTimeouts.readTimeout=300s` and
`accesslog.format=json`), the node's ports 80 and 443 as hostPorts, and the IngressClass `traefik`; then
cert-manager v1.21.2, CloudNativePG 1.30.1, the Barman Cloud plugin v0.15.1 and `kind-extras.yaml` (a self-signed
ClusterIssuer, RustFS 1.0.1 standing in for R2). No ingress-nginx anywhere.

The install took 3 minutes 38 seconds, most of it pulling PostgreSQL's and the plugin's images again: the frontend and
the admin stand-in ready at once, the database healthy, web's init container from `waiting for the database` through
the migrations to gunicorn, worker, beat and the media worker out of their wait, the first base backup completed.
For the first seconds Traefik logged `middleware "examleaf-examleaf-strip-server@kubernetescrd" does not exist` for
each router (Helm creates the Ingresses before the Middleware resources); nothing after.

## 2. Routing, as the Caddyfile has it

`curl -sk --resolve examleaf.localhost:443:127.0.0.1 …` (the certificates are the self-signed issuer's):

| Request | Answer |
|---|---|
| `https://examleaf.localhost/`, `/shop/`, `/cart/`, `/account/login/` | 200 from the website (the account pages included: run 1's fault is fixed) |
| `/account/` | 307 to `/account/login/?next=%2Faccount%2F` |
| `/api/v1/config/`, `/_allauth/browser/v1/config` | 200 from Django |
| `/api` | 308 to `/api/` (the website adds the slash; Caddy sent it there too) |
| `/apiary/`, `/healthz/`, `/no-such-page/` | 404 from the website (the paths keep the Caddyfile's trailing slashes) |
| `/static/admin/css/base.css` | 200 from WhiteNoise |
| `/admin/` | 302 to `/admin/login/?next=/admin/` |
| `/qr/NOPE.png` | 404 from Django |
| `/health`, `/health/`, `/health/web/` without credentials, or with a wrong password | 401, `www-authenticate: Basic realm="ExamLeaf health"` |
| `/health/` with `-u monitor:<HEALTH_CHECK_TOKEN>` | 200, `Database`, `Cache`, `Storage`, `WorkerPing` all `OK` |
| `https://admin.examleaf.localhost/offline/`, `/` | 200 from the admin stand-in (the website's image) |
| `https://admin.examleaf.localhost/api/v1/config/`, `/_allauth/browser/v1/config`, `/static/…`, `/admin/` | Django's answers on the admin host; no `DisallowedHost` in Django's log (the host is in `ALLOWED_HOSTS`) |
| `https://admin.examleaf.localhost/api/v1/staff/` | 404 from Django (the panel's API is not built yet) |
| `https://admin.examleaf.localhost/health`, `/health/` | 404 from the admin stand-in (`health-hide`) |

**http.** GET `http://examleaf.localhost/` → 301 `https://examleaf.localhost/`; `/shop/` → `…/shop/`;
`/api/v1/config/?x=1&y=2` → `…/api/v1/config/?x=1&y=2`; the admin host the same; a POST → 308. The whole path and
query are kept.

**Headers.** Django's answer: `strict-transport-security: max-age=31536000`, `x-frame-options: DENY`,
`x-content-type-options: nosniff`, `referrer-policy`, `cross-origin-opener-policy`, `permissions-policy` (Django's,
untouched) and no `Server` header, though gunicorn sends `Server: gunicorn` (asked inside the pod): `strip-server`
removed it. The website's answer: Next's headers and its own gzip. `/api/schema/` (208 kB) came back
`content-encoding: zstd` (`compress`); the 407-byte `/api/v1/config/` uncompressed (Traefik compresses from 1 KiB).
Django's answers carry its own `x-request-id`; Traefik's access log (JSON) has `ClientHost: 172.18.0.1` (the kind
network's gateway: on a laptop every request comes from it), the router and the service, and no request ID.

## 3. The health gate

`/health/` six times, 21 seconds apart (past its 20-second cache): `WorkerPing … OK` and 200 every time (run 1 saw
"No worker for Celery task queue celery" in four of six before 3529b96).

**Without its Secret.** `kubectl -n examleaf delete secret examleaf-health-auth`: Traefik logged
`Error while reading basic auth middleware error="secret 'examleaf/examleaf-health-auth' not found"` and
`middleware "examleaf-examleaf-health-auth@kubernetescrd" does not exist` for the health routers, and dropped them.
`/health/`, `/health/web/` and `/health` then answered **404, the website's page**: they fell through to the website's
router, whose `health-hide` rewrote them. Without that rewrite they would have been open: asked inside the frontend
pod with the site's host, as Traefik forwards a request, the website's server passed `/health/` to Django and
answered 200 with the health JSON. With the Secret back, 401 again and 200 with the token.

## 4. Body limits

| Body | Answer |
|---|---|
| 9 MB POST to `/api/v1/contact/` | Django's own 503 ("The contact form is not set up yet") |
| 11 MB POST to `/api/v1/contact/`, to `/_allauth/browser/v1/auth/login`, and to `admin.examleaf.localhost/api/v1/contact/` | 413 from Traefik (`body-limit`), Django never asked |
| 11 MB POST to `/admin/learn/clip/add/` and `/admin/learn/revision/add/` | 403 "Log in first" from Django: streamed, refused before it was read |
| 11 MB POST to `/shop/` (the website) | 200: no limit at the edge on the website's paths |

Bodies of 0.1 to 9 MB, three each, to the same not-set-up contact form: 503 seventeen times of eighteen and once a
502 from Traefik (1 MB), as the first 9 MB request had been. Django answers that form without reading the body, and
gunicorn closes a connection whose body it has not read, which can cut Traefik off while it still sends; a request
whose body Django reads is not affected. Any proxy in front of gunicorn meets the same race.

## 5. Changes on a running release

**The admin allowlist.** `--set 'admin.allowlist={203.0.113.0/24}'` made the Middleware
`ipAllowList: {sourceRange: [203.0.113.0/24]}`: every path of the admin host, Django's included, answered 403 (9
bytes) while the main host answered 200. With `{172.18.0.0/16}` (the Mac's address as Traefik sees it) the admin
host answered 200; without the value the Middleware went and the host answered 200.

**Upgrade** with a changed setting (`--set config.LOG_LEVEL=INFO`, so the ConfigMap's checksum rolls every pod),
which also took the allowlist away: 29 seconds. Every Deployment rolled; a watch every second counted beat's pods,
and there was never more than one.

**Inside the cluster.** `manage.py check --deploy` with a production email backend: W005 and W021 only.
`createsuperuser --noinput` through `kubectl exec`: `admin@examleaf.localhost` a superuser. The smoke-test CronJob,
now `manage.py health_check health` against the web Service, completed on its schedule and by hand
(`WorkerPing … OK`). The NetworkPolicies, probed with throwaway pods: one of the release with another component
reached nothing; one labelled as the worker reached the two Redis and PostgreSQL but not web or the frontend; the
controller's namespace and labels changed (kube-system, `app.kubernetes.io/name: traefik`) and the site answered
through it throughout. The bucket held the base backup `cnpg/examleaf-db/base/20261009T050305/` and seven WAL files;
the Cluster reported `ContinuousArchiving=True`.

**Memory** (working sets): web 164 MiB, worker 168, beat 149, media worker 169, frontend 55, admin 47, PostgreSQL 72
and its sidecar 20, each Redis 3 to 4, Traefik 30 (ingress-nginx used 64); the release 851 MiB, the node 1.8 GiB in
all (2.4 GiB with the page cache).

## 6. Checked without a cluster: ERPNext, the other options, the admin panel's image

ERPNext wants 6 to 8 GiB and the laptop had about 3 GB to spare, so it stayed off. With mariadb-operator 26.10.1's
CRDs applied (CRDs only),
`helm install erpcheck … --dry-run=server --set erpnext.enabled=true --set erpnext.image.tag=16.50.0-test --set 'erp.allowlist={10.0.0.0/8}' …`
was accepted by the API server: frappe/helm's Deployments with `ghcr.io/lazyindianbook/examleaf-erp:16.50.0-test`, the
MariaDB, its PhysicalBackup, the site-backup CronJob, the `erp-headers` and `erp-allowlist` Middlewares and the ERP's
Ingress. Without `erpnext.image.tag`, and with `registry` changed but not `erpnext.image.repository`, the chart
refused to render, as it should. The default values with every optional part on (the autoscalers, the admin with an
allowlist, beat off, the smoke test, backups to an R2 endpoint with `encryption: aws:kms`) were accepted the same way,
and the ObjectStore CRD lists `AES256` and `aws:kms` for `encryption`. `helm lint` and `helm template` pass with the
default values and with values-kind.yaml (`make lint`).

**The admin panel's image.** `make images TAG=6ec1af5 DOMAIN=examleaf.localhost`'s new third build (the
`examleaf-admin` Dockerfile unchanged, for `https://admin.examleaf.localhost`) took 84 seconds: 325 MB. Run as the
chart runs the admin's pod, with no cluster (the laptop's disk and memory were needed by another agent's ERPNext
stack):
`docker run --read-only --tmpfs /tmp --tmpfs /app/.next/cache:mode=1777 --user 1000 --cap-drop ALL --security-opt no-new-privileges`,
`API_INTERNAL_BASE` pointing at nothing. It ran as `uid=1000(node) gid=1000(node)`, 56 MiB; `/api/health/` answered
200 (the probes' path: the process only), `/` and `/sign-in/` 503 with `Retry-After: 30` and the panel's own headers
(CSP, HSTS, `X-Robots-Tag: noindex, nofollow`) while Django was unreachable, and `/health/` 500: the panel passes
Django's paths on, `/health/` among them, so `health-hide` is needed on the admin host as on the website's. The new
Middleware `drop-subrequest` (Headers, `customRequestHeaders` with an empty value, the shape `strip-server` has for
responses) was rendered and linted, not applied.

## 7. Run 3: the HA profile under failure and load

06:41–08:48 UTC, the chart of this commit, images built at 9e0ee99 (91 seconds: cached layers). One node, not three:
the laptop's disk (Docker had to be pruned to free it) and the coordinator's instruction; so this run shows what a
failure costs the site, not where pods land on three nodes (section 9). The profile was values-ha.yaml squeezed onto
the node by `values-kind-ha.yaml` (two of web, the frontend, the worker; one media worker; no admin and no
autoscalers; the media in RustFS's buckets; the anonymous throttles lifted for the load):

```sh
make kind-up && docker update --memory 4000m --memory-swap 4000m examleaf-test-control-plane   # 06:44 → 06:54
```

```sh
make kind-secrets kind-monitoring-crds
```

```sh
kind load docker-image ghcr.io/lazyindianbook/examleaf-web:9e0ee99 ghcr.io/lazyindianbook/examleaf-frontend:9e0ee99 --name examleaf-test
```

```sh
make kind-buckets TAG=9e0ee99
```

```sh
make kind-install TAG=9e0ee99 VALUES="-f examleaf-platform/values-kind.yaml -f examleaf-platform/values-ha.yaml -f examleaf-platform/values-kind-ha.yaml"
```

The node's memory was capped so that the VM's other tenants (another agent's ERPNext stack, at first) kept theirs,
later raised to 5 GB. All of it shared the Mac's 4 CPUs with other agents' work, one of them a load test of its own on
the Mac: the latencies below are a saturated laptop's, and what matters is what changed when something broke.

### 7.1 Install

PostgreSQL's image took eleven minutes to pull, and Helm 4's `--wait` gave up at 07:07:52: the Deployments waiting in
their init containers had passed Kubernetes' default progress deadline of 10 minutes, which kstatus reads as failed.
The chart now gives the four that wait for the migrations `progressDeadlineSeconds: 1800`; the next upgrade was
deployed at once. Then:

- **The migrations' lock**: both web pods started together. One applied the 179 migrations from 07:06:40 to 07:08:41;
  the other waited on the advisory lock and at 07:08:57 found "No migrations to apply".
- **Through the pooler**: web's `DATABASE_URL` was `postgres://examleaf:***@examleaf-db-pooler:5432/examleaf?disable_server_side_cursors=True`
  (django-environ makes it `DISABLE_SERVER_SIDE_CURSORS: True`); `/health/` answered Database, Cache, Storage (the
  RustFS bucket) and WorkerPing OK; a query from web reached the primary (`pg_is_in_recovery() = false`).
- **The alerts' metrics**, read from their ports: `cnpg_pg_replication_in_recovery`, `…_streaming_replicas` (1),
  `…_lag`, `cnpg_pg_stat_archiver_failed_count`, `barman_cloud_cloudnative_pg_io_last_available_backup_timestamp`
  (the plugin's, on the instance's port 9187), `redis_up` and `redis_key_size{key="celery"}` (redis_exporter
  v1.93.0), `certmanager_certificate_expiration_timestamp_seconds` and `…_ready_status` with `namespace="examleaf"`.
  The 15 rules passed `promtool check rules` (Prometheus v3.13.4); the PodMonitors and the PrometheusRule were
  accepted with the Prometheus Operator's v0.94.1 CRDs.

### 7.2 The load, and what it found before anything was broken

`load.mjs`: 50 keep-alive connections through Traefik, half to `/api/v1/boards/` (Django) and half to `/offline/`
(the website). Unpaced first, as fast as the answers came (101 to 266 a second), which showed three things:

1. **429s**: DRF counts an anonymous client against the user rate as well, by its address (600 a minute), and every
   connection came from the Mac's one address; `values-kind-ha.yaml` lifts both rates.
2. **503s from Traefik for every Django path**: web's readiness probe was `/health/web/`, whose storage check (a
   write to the bucket) timed out on the saturated node, so both pods left the rotation at once. A shared dependency
   in the readiness probe turns its slowness into a full outage; web's readiness is now a static file through
   WhiteNoise and Django's middleware (the pod's own gunicorn and Django), with `/health/web/` left to the monitors.
3. **Requests stuck for 10 seconds every half minute**: gunicorn's `--max-requests 1000 --max-requests-jitter 100`
   (examleaf-web's Dockerfile) restarted both processes of a pod within a second of each other, they had started
   together and served the same load, and each new process took 14 to 20 seconds to load Django on this CPU; the pod
   answered nothing meanwhile. With one process a pod (as on kind before) every recycling is such a gap.
   `GUNICORN_CMD_ARGS` cannot change it (the image's command line wins: `gunicorn --print-config` showed it).
   The scenarios below ran with the recycling off (a test-only patch of web's `args`, `--max-requests 0`), to see
   each failure on its own; the backend's options are in README.md "Graceful shutdown".

Paced at 100 requests a second (`--rate 100`, which leaves the node room), the baseline: **5,959 requests, 99 a
second, p50 83 ms, p95 1,387 ms, p99 2,913 ms, none failed.**

### 7.3 The scenarios

Each scenario ran `node load.mjs --connections 50 --rate 100 --seconds <n> <URLs>` in the background, did its damage at
second 20 (`kubectl -n examleaf delete pod …`, the primary's with `--grace-period=0 --force`), and Traefik's access log
(`kubectl -n kube-system logs -f deploy/traefik`, JSON) told which pod each failure came from.

| Scenario | When | Requests | p50 / p95 (ms) | Failed |
|---|---|---|---|---|
| Baseline | 07:58:42, 60 s | 5,959 | 83 / 1,387 | 0 |
| A web pod and a frontend pod deleted | 07:59:52, 60 s | 3,704 | 143 / 2,895 | 15 timeouts, none on the deleted pods |
| The primary killed, a cached Django path | 08:01:35, 90 s | 4,734 | 175 / 4,970 | 122 timeouts |
| The primary killed, an uncached path (`/api/v1/products/`) | 08:05:49, 150 s | 2,595 | 1,095 / 10,077 | 945 × 503, 331 timeouts, 3 × 500 |
| A new web image rolled | 08:35:15, 120 s | 1,831 | 323 / 20,166 | 264 timeouts, no 5xx |

**A web pod and a frontend pod deleted** (08:00:12 and 08:00:17). Not one request failed on either: their
last ones were answered, and nothing new went to them. Traefik 3.7 keeps a terminating pod in the service as
"fenced" (`Serving` and `Terminating` in the EndpointSlice) and sends it no new request: without load the
EndpointSlice showed the deleted frontend pod terminating 0.34 seconds after the delete, and gone 13.5 seconds later
(the 10-second pause, then Next's own drain). The 15 timeouts fell 25 seconds later, on the web pod that stayed, while
its replacement migrated and loaded Django on the same 4 CPUs.

**The primary killed** (`kubectl delete pod --grace-period=0 --force`), twice. The second time: the operator saw the
primary gone after 6 seconds, the standby got its promotion request at 23 seconds (the operator waits until the
standby's WAL receiver has stopped) and accepted writes at **35 seconds**. The first time promotion took 80 seconds
more: before choosing a new timeline PostgreSQL asks the archive for the timelines' history files, each through
`barman-cloud-wal-restore`, which took about 10 seconds a call on the saturated node. No pod of the site restarted;
PgBouncer reconnected to the new primary behind its clients' connections, and nothing had to be done. Nothing was lost:
the standby had replayed everything (its last transaction was the primary's last). The cached path (the catalogue is
kept 15 minutes in Redis) failed only by timeouts on the starved node; the uncached one showed the real cost:
PgBouncer holds a query for up to 120 seconds (`query_wait_timeout`'s default) while there is no primary, every
gunicorn thread ended up waiting, the readiness probes queued behind them, and 30 seconds later Traefik had no web pod
left: 945 answers of 503 between 08:06:51 and 08:07:09, after the primary was back. The chart now sets
`query_wait_timeout: 10` and `server_login_retry: 1` (PgBouncer reconnects within a second, not 15), so that a query
gives up before the probes do. Not measured again: the cluster was degrading (below), and the run had to end.

**The queue's Redis restarted with 200 tasks waiting**: the workers scaled to 0, 200 tasks queued
(`ops.tasks.reset_failed_logins`, harmless), `LLEN celery` 200. Deleted: back in 2 seconds with 200. Killed with no
grace: back in 3 seconds with 200. The workers back: all 200 succeeded within 27 seconds, 100 on each. During a
graceful delete the replacement starts before the old pod has stopped; both mount the same ReadWriteOnce volume on the
one node for a moment, which `ReadWriteOncePod` would forbid on a CSI storage class.

**A worker killed in the middle of a task**: a 120-second 480p test video, made by ffmpeg in the media worker, became a
clip and was queued as the admin queues one (`learn.tasks.queue_processing`). Eight seconds into ffmpeg the pool child
running `process_clip` (ffmpeg's parent, found in `/proc`) got SIGKILL, as the kernel's OOM killer kills a process.
Celery logged `WorkerLostError … signal 9 (SIGKILL)` and recorded the task as FAILURE, **not retried**: the app
acknowledges a task when a worker takes it (no `CELERY_TASK_ACKS_LATE`). The clip stayed "processing" with no error;
`manage.py reprocess_clips 1` queued it again. The what-if, with a test-only settings module on the media worker
(`CELERY_TASK_ACKS_LATE`, `CELERY_TASK_REJECT_ON_WORKER_LOST`, a `visibility_timeout` of 7200 seconds): the child killed
at 08:29:18, the same task delivered again at 08:30:36, **retried once**, and it succeeded at 08:34:28 (the clip ready,
120 seconds of HLS). A real out-of-memory kill came by accident: ffmpeg run by hand in a web pod went past the pod's
limit, and the kernel killed every process of the container (cgroup v2's `memory.oom.group`, which Kubernetes sets: the
gunicorn master, both its workers and ffmpeg); the container restarted (`OOMKilled`) while the other web pod served. So
an OOM in a worker kills its main process too, and with acks_late its task comes back only after the visibility timeout,
which must outlast the longest task (`process_clip`: an hour).

**A new web image rolled under load** (the same image tagged again inside the node,
`helm upgrade --set image.tag=9e0ee99-roll`): every Deployment rolled, not only those on web's image, because the
pods' config checksum covered the ConfigMap's labels, which carry web's tag, and the pooler's labels carried it too
(both fixed: the checksum is now of the ConfigMap's data, and the pooler's pods carry the chart's version). The node's
CPU went to 400%, both PostgreSQL instances failed their liveness probes and restarted twice, the operator and its
plugin restarted with them, and Helm's 10 minutes ran out with the rollout still finishing. The rollout's own rules
held: no pod answered 5xx, the old web pods served until new ones were ready, beat never doubled. Not repeated after
the fixes.

**Beat** in that rollout: its new pod waited 3 minutes 42 seconds in `wait-for-migrations` (web was migrating under
the lock, on the starved node), then took 81 seconds to start. Run 2's whole upgrade, beat's restart in it, took
29 seconds.

### 7.4 What it used

At 07:38 (crictl): web 433 and 450 MiB (two gunicorn processes each), the workers and the media worker 180 each,
beat 158, the frontend 50 each, PostgreSQL 57 and 65 with its Barman Cloud sidecar 28, RustFS 138, the API server 526;
3.1 GiB for every container of the node.

## 8. Run 1, on ingress-nginx

The same suite on the chart's first version (ingress-nginx controller v1.15.1, images at 6bcc174, then 3685d9c). Its
routing results are replaced by section 2; the rest did not depend on the controller and still stands:

- **A point-in-time restore**: a row written after the base backup came back in a new Cluster made from the bucket
  (`helm upgrade --set postgres.name=examleaf-db-restore --set postgres.recovery.enabled=true --set postgres.recovery.serverName=examleaf-db`,
  82 seconds); every pod moved to the new `DATABASE_URL`; the new cluster archived under its own name; the old one
  stayed until deleted.
- **Eviction**: a server-side dry-run drain of beat was refused
  (`Cannot evict pod as it would violate the pod's disruption budget`), the worker's allowed.
- **The shop's clean-up CronJob**, rendered with `beat.enabled=false`, completed when run.
- **Uninstall** kept the Cluster, `examleaf-media` and `examleaf-redis-queue`.
- **Read-only root filesystems**: WeasyPrint drew a PDF with the rupee sign, Assamese and Hindi; FFmpeg made an HLS
  stream; Redis kept compose's settings (AOF and noeviction for the queue, allkeys-lru with no saving for the cache).

What run 1 found, and what changed because of it:

1. **The website's account pages answered 503**: `src/proxy.ts` asked Django's `/health/web/` with no forwarded
   headers, and with `DEBUG=0` Django refused its internal host (400). Fixed in the frontend (2a41671), with a test.
2. **The https redirect dropped a trailing slash** (ingress-nginx): run 2's redirect keeps it.
3. **gunicorn 26 logged a control-socket error** at every start on the read-only root: `--no-control-socket`.
4. **fontconfig had no writable cache** for the PDFs: `XDG_CACHE_HOME=/tmp/.cache`.
5. **Celery warned that it might run as root** (`runAsGroup: 1000` is not examleaf's group): each image's own group.
6. **The first wait for the migrations took two minutes**: each attempt is cut at 30 seconds.
7. **`/health/`'s Celery check flapped** in four of six asks: fixed in the backend (3529b96); the smoke test asks
   `/health/` again.

## 9. Not tested, and why

- **Let's Encrypt and real DNS**: kind has neither; the certificates came from the self-signed issuer through the same
  cert-manager annotation.
- **Cloudflare R2 itself**, and `postgres.backup.encryption` against a real AWS bucket: RustFS stood in.
- **k3s's own Traefik and its HelmChartConfig**, ServiceLB and `externalTrafficPolicy: Local`: kind ran Traefik from
  its chart with hostPorts; the visitor's real address on a real node is untested.
- **ExternalSecret mode and the autoscalers scaling**: no External Secrets Operator or metrics-server on kind.
- **ERPNext running** (section 6), mariadb-operator's backups and replica, the site-backup CronJob, the site's
  set-up Job (rendered, its shell and Python syntax-checked, not run).
- **More than one node** (run 3 ran values-ha.yaml on one): where the spread puts each component's pods on three
  nodes, a node lost (the database's failover across nodes, the endpoints of a NotReady node), a drain with the primary
  on the node, ReadWriteMany media. The placement rules were rendered and linted; their selectors are the pods' own
  labels.
- **The HA profile's autoscalers scaling, the admin in it, synchronous replication, PgBouncer's new timeouts under a
  failover**, and the rollout under load after the checksum fix (section 7).
- **Prometheus and Alertmanager**: the rules were checked with promtool and their metrics read from the exporters,
  not evaluated; kube-state-metrics' (restarts, deployments, disruption budgets) were not on kind.
- **Email, SMS, Razorpay, Google sign-in, Turnstile, Sentry, the media buckets**: no accounts on a laptop.
- **A clip through the admin**, `import_papers`, and the admin panel on kind: run 2 had the website's image standing
  in on the admin host (the panel's arrived later, section 6), so a sign-in through the panel is untried, and its
  staff API (`/api/v1/staff/`) is not built yet.

## 10. Phase B: what the next run should check (not run)

Phase B (the Admin Control Panel's modules, integrated on the branch phase-b) changed what the chart carries, and **no kind
run has seen it**: the laptop's disk is at 99 % and its memory is taken by other agents' work (the reason ERPNext stayed
off in section 6), so kind was not started. What was checked without a cluster: `make lint` (three `helm lint`s and
four `helm template`s, clean), the ConfigMap rendered with sample values for the new settings (an apostrophe and comma
lists survive, and `settings.py` parses them back), and `docker compose config` with the `admin` profile. The next run,
on images built from the Phase B head, should check these, in this order:

1. [ ] **An upgrade, not only an install.** Install the release of the commit before Phase B, then `helm upgrade` to this
    one: web's init container applies some forty migrations to a database that has data. Then once with
    `INTEGRATION_KEYS` taken out of `examleaf-env`: the init container must stop at `support.E001`, the rollout stall and
    `--rollback-on-failure` put the old release back (README.md "Secrets"). `make kind-secrets` makes the key.
2. [ ] **Routing of the new paths.** All are under `/api/` and `/admin/`, which Traefik already sends to web, so what to
    see is the answers: `POST /api/hooks/support-mail/` and `/api/hooks/sms-events/` without their token (403 from
    Django, not the website's 404; with a 5 MB body for the first, passing; with an 11 MB one, 413 from Traefik),
    `/api/v1/reports/`, `/api/v1/errata/`, `/api/v1/me/tickets/` (Django's 200 or 401), `/api/v1/staff/session/` on the
    admin host (200 signed in) and on the main host (404: `ADMIN_HOSTS`). The uploads (a return photograph, the
    dark-pattern certificate, a legal-deposit proof: 5 MiB at most; the catalogue import: 2 MiB) must pass the
    `body-limit` Middleware's 10 MB.
3. [ ] **Beat.** The 59 entries are in django-celery-beat (27 new), one beat pod, and a few run when called by hand:
    `shop.tasks.watch_tax_thresholds`, `support.tasks.watch_clocks`, `learn.tasks.publish_due`,
    `learn.tasks.purge_code_files` and `staff.tasks.check_backups`. None of them has a queue of its own: the worker's
    command needs no `--queues`.
4. [ ] **The backups bucket from the pods.** With RustFS as the backups bucket, `config.BACKUP_BUCKET` and
    `BACKUP_ENDPOINT_URL` set and a token of its own in `examleaf-env` (README.md "Backups and restore"): the System page
    lists the newest object under `cnpg/` once the base backup has run; `accounts.tasks.copy_erasure_ledger` writes
    `erasures/<id>.json` after an erasure; `staff.tasks.export_audit_log` writes `audit/…/<day>.jsonl`. Without them the
    page must say that no bucket is set, and nothing may be reported stale.
5. [ ] **The private storage and the jobs in the worker.** With the buckets of `values-kind-ha.yaml`: a staff job of each
    kind that makes a file (`orders_print`, WeasyPrint's packing slips, on the read-only root and the `/tmp` emptyDir;
    `gstr1_export`; `report_export`; `code_batch`) leaves its file under `staff/jobs/<id>/`, the signed link downloads
    it, and the book codes' file is gone an hour after its 24 hours (`learn.tasks.purge_code_files`; backdate the job
    to see it). Watch the worker's working set (768Mi) during the packing slips of 250 orders.
6. [ ] **The panel's Content → Imports** is expected to answer "No production/ folder in …" (no books in the worker pod,
    README.md "Install"). It is the one Phase B page the chart does not serve yet.
7. [ ] **The System page's own fetches.** Its hardening check and the daily scripts inventory request the site's public
    pages (`/checkout/`, the console's `/sign-in/` and `robots.txt`) from the pod. On kind `examleaf.localhost` is the
    pod itself, so expect errors there; on a real cluster confirm that the pods can reach the public address (the
    ingress from inside).
8. [ ] **CI's dependency report**: `kubectl cp` and `load_dependency_report` as README.md "Upgrades and migrations" has
    them, then System → Dependencies lists the advisories and no inbox item `dependencies_stale` stays open.
9. [ ] **A bad setting stops the rollout, not the site.** `--set-string config.SHOP_SERIES_PREFIXES=tax_invoice=T` (one
    capital) must keep the new web pod in its init container and, with `--rollback-on-failure`, bring the old release
    back; the same for `config.INSIGHTS_MIN_CELL=3` (`insights.E001`).

## 11. Cleaning up

```sh
make kind-down                    # kind delete cluster --name examleaf-test; docker image prune -f
```

```sh
docker rmi ghcr.io/lazyindianbook/examleaf-web:3529b96 ghcr.io/lazyindianbook/examleaf-frontend:3529b96 <kindest/node image>
```

```sh
docker rmi ghcr.io/lazyindianbook/examleaf-admin:6ec1af5      # after section 6's check
```

```sh
docker rmi ghcr.io/lazyindianbook/examleaf-web:9e0ee99 ghcr.io/lazyindianbook/examleaf-frontend:9e0ee99 prom/prometheus:v3.13.4  # run 3
```

```sh
colima ssh -- sudo fstrim -av     # the VM's freed blocks back to the Mac (8.9 GiB)
```

The build cache was left this time: another agent's ERPNext image build shares it. Images that other work had
pulled or built (`frappe/erpnext`, `examleaf/erp-dev`, `mariadb`, `valkey`) were left alone.

## Related documents

- [The chart's README](README.md): installing, upgrading, backing up and operating the chart this record tests.
- [Deployment](../../examleaf-web/DEPLOYMENT.md): the one-machine stack the chart translates, and the Phase B checklist (section 26).
- [Runbook](../../examleaf-web/RUNBOOK.md): restoring the database from a backup, which section 8 ran on kind.
- [Resilience](../../examleaf-web/RESILIENCE.md): the timeouts, the task acknowledgement and the recycling that run 3 led to.
- [Phase B integration](../../docs/phase-b-integration/README.md): the branch whose changes section 10 asks the next run to check.
