# The chart on kind: what was run and what it showed

Two runs on 9 October 2026 on a MacBook (Apple silicon) whose Docker is a Colima VM of 4 CPUs, 6 GiB of memory and a
60 GiB disk (Docker 29.2.1, kind 0.32.0, Helm 4.2.2, kubectl 1.32.2), each on a one-node cluster from
`kind-config.yaml` (`kindest/node:v1.35.5`, ports 80 and 443 of the Mac forwarded to it), each deleted afterwards.
Everything was run from `deploy/kubernetes/`; Secrets were made with random values by `make kind-secrets` and are not
shown. kubectl 1.32 talks to a 1.35 server, three minor versions apart (it warns); every command below worked.

- **Run 2, on Traefik** (04:48–05:25 UTC), sections 1 to 6: the chart as it is now (e5a4f46), images built at
  3529b96 (the platform with the Celery health fix).
- **Run 1, on ingress-nginx** (03:00–04:15 UTC), section 7: the chart's first version, which the second replaced
  where the controller is concerned; what it showed about everything else still stands.

## 1. Images and the cluster

```sh
make images TAG=3529b96 DOMAIN=examleaf.localhost     # 04:48 → 04:53
make kind-up                                           # 04:55:37 → 04:58:26
make kind-secrets
make kind-load TAG=3529b96                             # 35 s
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

## 6. ERPNext and the other options, checked without running them

ERPNext wants 6 to 8 GiB and the laptop had about 3 GB to spare, so it stayed off. With mariadb-operator 26.10.1's CRDs
applied (CRDs only), `helm install erpcheck … --dry-run=server --set erpnext.enabled=true --set
erpnext.image.tag=16.50.0-test --set 'erp.allowlist={10.0.0.0/8}' …` was accepted by the API server: frappe/helm's
Deployments with `ghcr.io/lazyindianbook/examleaf-erp:16.50.0-test`, the MariaDB, its PhysicalBackup, the
site-backup CronJob, the `erp-headers` and `erp-allowlist` Middlewares and the ERP's Ingress. Without
`erpnext.image.tag`, and with `registry` changed but not `erpnext.image.repository`, the chart refused to render, as
it should. The default values with every optional part on (the autoscalers, the admin with an allowlist, beat off,
the smoke test, backups to an R2 endpoint with `encryption: aws:kms`) were accepted the same way, and the ObjectStore
CRD lists `AES256` and `aws:kms` for `encryption`. `helm lint` and `helm template` pass with the default values and
with values-kind.yaml (`make lint`).

## 7. Run 1, on ingress-nginx

The same suite on the chart's first version (ingress-nginx controller v1.15.1, images at 6bcc174, then 3685d9c). Its
routing results are replaced by section 2; the rest did not depend on the controller and still stands:

- **A point-in-time restore**: a row written after the base backup came back in a new Cluster made from the bucket
  (`helm upgrade --set postgres.name=examleaf-db-restore --set postgres.recovery.enabled=true --set
  postgres.recovery.serverName=examleaf-db`, 82 seconds); every pod moved to the new `DATABASE_URL`; the new cluster
  archived under its own name; the old one stayed until deleted.
- **Eviction**: a server-side dry-run drain of beat was refused (`Cannot evict pod as it would violate the pod's
  disruption budget`), the worker's allowed.
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

## 8. Not tested, and why

- **Let's Encrypt and real DNS**: kind has neither; the certificates came from the self-signed issuer through the same
  cert-manager annotation.
- **Cloudflare R2 itself**, and `postgres.backup.encryption` against a real AWS bucket: RustFS stood in.
- **k3s's own Traefik and its HelmChartConfig**, ServiceLB and `externalTrafficPolicy: Local`: kind ran Traefik from
  its chart with hostPorts; the visitor's real address on a real node is untested.
- **ExternalSecret mode and the autoscalers scaling**: no External Secrets Operator or metrics-server on kind.
- **ERPNext running** (section 6), mariadb-operator's backups, the site-backup CronJob.
- **More than one node**: ReadWriteMany media, a database failover, a real drain.
- **Email, SMS, Razorpay, Google sign-in, Turnstile, Sentry, the media buckets**: no accounts on a laptop.
- **A clip through the admin**, `import_papers`, and the admin panel itself (its image does not exist; the website's
  stood in, which answers on the admin host only where Django's paths do not).

## 9. Cleaning up

```sh
make kind-down                    # kind delete cluster --name examleaf-test; docker image prune -f
docker rmi ghcr.io/lazyindianbook/examleaf-web:3529b96 ghcr.io/lazyindianbook/examleaf-frontend:3529b96 <kindest/node image>
colima ssh -- sudo fstrim -av     # the VM's freed blocks back to the Mac (8.9 GiB)
```

The build cache was left this time: another agent's ERPNext image build shares it. Images that other work had
pulled or built (`frappe/erpnext`, `examleaf/erp-dev`, `mariadb`, `valkey`) were left alone.
