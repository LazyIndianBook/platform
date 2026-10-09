# ExamLeaf on Kubernetes

This directory packages the platform for a Kubernetes cluster, as section 3.4 of
`docs/examleaf-admin-control-panel-plan.md` decided: one Helm chart, `examleaf-platform`, with the Django backend and
its Celery processes, the Next.js website and admin panel, PostgreSQL through the CloudNativePG operator,
two Redis, the Ingress and its certificates. ERPNext is a dependency of the chart with its database, backups and
Ingress prepared, switched off until it is added (section "ERPNext" below). docker-compose
(`examleaf-web/docker-compose.yml`) stays for development and for a one-machine server; this is the same stack,
translated. `TESTING.md` records the chart's runs on a `kind` cluster, the latest on Traefik (ERPNext rendered and
validated, not run); the chart has not yet run on a real cluster.

| Path | What it holds |
|---|---|
| `examleaf-platform/` | the chart: `values.yaml` (every setting, each explained), `values-kind.yaml` (the laptop profile), `templates/` |
| `Makefile` | the images, the chart's checks and the kind cluster (`make` lists the tasks) |
| `traefik-values.yaml` | Traefik's own settings that go with the chart (section "The ingress controller") |
| `kind-config.yaml`, `kind-extras.yaml` | the kind test cluster, and its stand-ins for Let's Encrypt and Cloudflare R2 |
| `TESTING.md` | what was run on kind, and what it showed |

## What runs where

| docker-compose.yml | Kubernetes (release `examleaf`) |
|---|---|
| `web` (migrate, bootstrap_roles, gunicorn) | Deployment `examleaf-web`: an init container waits for the database and runs `migrate` and `bootstrap_roles`; gunicorn is ready once `/health/web/` answers |
| `worker`, `beat`, `media-worker` | Deployments `examleaf-worker`, `examleaf-beat` (always one pod), `examleaf-media-worker` (its own small environment); each waits until the migrations are applied |
| `frontend` | Deployment `examleaf-frontend` |
| `admin` (profile `admin`) | Deployment `examleaf-admin` at `admin.<domain>` (Django's paths there go to web), with `admin.enabled` |
| `db` (postgres:17) | CloudNativePG `Cluster` `examleaf-db` (PostgreSQL 17), continuous backup to a bucket |
| `redis`, `redis-cache` | Deployments `examleaf-redis-queue` (with a volume) and `examleaf-redis-cache` |
| `caddy` | Ingresses and Middlewares for Traefik (k3s's bundled controller), certificates from cert-manager |
| `.env` | the ConfigMap `examleaf-config` (from `values.yaml` "config") and the Secrets you make (`examleaf-env` …) |
| volumes `media`, `pgdata`, `redisdata` | PersistentVolumeClaims `examleaf-media`, the Cluster's own, `examleaf-redis-queue` |
| (none) | with `erpnext.enabled`: frappe/helm's ERPNext (`examleaf-erpnext-*`), its MariaDB `examleaf-erp-db` through mariadb-operator, the site backups, `erp.<domain>` |

## Operators first

The chart expects these in the cluster. Each is installed the way its project documents, at the release the Makefile
pins (the kind test used exactly these).

| What | Release | Install | Why |
|---|---|---|---|
| Traefik | v3.7 (k3s v1.35.9 bundles v3.7.13; chart 41.7.0 is v3.7.14) | bundled with k3s in `kube-system`; elsewhere its Helm chart (`https://traefik.github.io/charts`), with `traefik-values.yaml` | the Ingresses' controller and the Middleware resources the chart uses |
| cert-manager | v1.21.2 | `kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.21.2/cert-manager.yaml` | the certificates of both hosts; the Barman Cloud plugin needs it too |
| CloudNativePG | 1.30.1 | `kubectl apply --server-side -f https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.30/releases/cnpg-1.30.1.yaml` | PostgreSQL |
| Barman Cloud plugin | v0.15.1 | `kubectl apply -f https://github.com/cloudnative-pg/plugin-barman-cloud/releases/download/v0.15.1/manifest.yaml` (after cert-manager, into `cnpg-system`) | backups and restores of PostgreSQL |
| External Secrets Operator | 2.12.0 | its Helm chart | only with `secrets.mode: externalSecret` |
| metrics-server | 0.9.0 | its manifest or chart | only for the autoscalers (`web.autoscaling`, `frontend.autoscaling`) |
| mariadb-operator | 26.10.1 | its two Helm charts, `mariadb-operator-crds` then `mariadb-operator` (`https://helm.mariadb.com/mariadb-operator`), into `mariadb-operator` | only with ERPNext |

CloudNativePG's own support for Barman Cloud inside the operator is deprecated (removal is announced for 1.31), so the
chart uses the plugin from the start.

The chart's routing was first written for ingress-nginx, which the Kubernetes project retired in March 2026 (no
release or security fix after v1.15.1); it now targets Traefik, which k3s bundles, which is maintained, and which
serves the Gateway API as well when the chart moves to it.

### The ingress controller

The chart's Ingresses (`ingressClassName: traefik`) carry Traefik's annotations `router.entrypoints` (`websecure`, or
`web` for the http redirect) and `router.middlewares`, which name the chart's Middleware resources
(`templates/middlewares.yaml`): `redirect-https`, `body-limit` (Buffering), `compress`, `strip-server` (Headers),
`health-auth` (BasicAuth), `health-hide` (ReplacePathRegex), `drop-subrequest` (Headers) and `admin-allowlist`
(IPAllowList), plus `erp-headers` and `erp-allowlist` with ERPNext. Traefik adds no headers of its own (no HSTS, no
`Server`), so Django's and Next's are what the browser gets.

Two of Traefik's own settings go with them (`traefik-values.yaml`): a read timeout of 5 minutes for a whole request
(Traefik's default of 60 seconds would cut off a photo from a slow phone, which Caddy gave 5 minutes), and the access
log as JSON on stdout. Traefik has no separate timeout for the headers: they share the 5 minutes (Caddy gave them 10
seconds). On k3s they go into a HelmChartConfig for the bundled Traefik, with the visitor's address kept:

```yaml
apiVersion: helm.cattle.io/v1
kind: HelmChartConfig
metadata:
  name: traefik
  namespace: kube-system
spec:
  valuesContent: |-
    ports:
      websecure:
        transport:
          respondingTimeouts:
            readTimeout: 300s
    accessLog:
      enabled: true
      format: json
    service:
      spec:
        externalTrafficPolicy: Local
```

Saved as `/var/lib/rancher/k3s/server/manifests/traefik-config.yaml` on the server, k3s applies it and redeploys
Traefik. Anywhere else, Traefik's chart: `helm upgrade --install traefik traefik --repo
https://traefik.github.io/charts --version 41.7.0 --namespace kube-system -f traefik-values.yaml --set
service.spec.externalTrafficPolicy=Local` (`ingress.controllerNamespace` follows the namespace you choose).

`externalTrafficPolicy: Local` keeps the visitor's address: Django counts failed log-ins, rate limits and the device
list by it (`PROXY_COUNT=1` trusts the one proxy in front, as with Caddy). Traefik drops a client's own
`X-Forwarded-*` headers and sends the address it saw, so this holds while nothing else stands in front. On k3s,
ServiceLB keeps the address with `Local` unless the node has `node-external-ip` set (k3s's documentation). If a load
balancer or Cloudflare's proxy stands in front, Traefik sees the balancer's address and every visitor would share one
limit: give the balancer the PROXY protocol and Traefik `ports.websecure.proxyProtocol.trustedIPs`, then try
`/api/v1/` from two addresses. Trusting the balancer's `X-Forwarded-For` instead (`forwardedHeaders.trustedIPs`) does
not fit as the site is written: the chain grows by one, and the website's server-side calls, which forward the last
address (`FrontendClientMiddleware`), would speak for the balancer.

The http redirect is the chart's (`<release>-http`, a RedirectScheme on the `web` entrypoint for every host): it
keeps the whole path and query, as Caddy's did, answers 301 to a GET and 308 to anything else (Caddy: 308), and
leaves cert-manager's HTTP-01 challenges alone, as their longer rule wins. Traefik's own entrypoint redirect
(`ports.web.http.redirections`) would do the same with `allowACMEByPass: true`; the chart does not need it.

### A ClusterIssuer

`ingress.clusterIssuer` names a cert-manager ClusterIssuer (`letsencrypt` by default). One for Let's Encrypt with the
HTTP-01 challenge, which needs port 80 of both hosts to reach the controller:

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: <the address Let's Encrypt writes to before a certificate expires>
    privateKeySecretRef:
      name: letsencrypt-account
    solvers:
      - http01:
          ingress:
            ingressClassName: traefik
```

The chart's NetworkPolicies let the controller reach cert-manager's challenge pods.

## Images

Every image of the platform lives under one registry, the chart's `registry` value (default
`ghcr.io/lazyindianbook`, the owner's GitHub organisation): `examleaf-web`, `examleaf-frontend` and the admin panel's
`examleaf-admin`, which the repository's Dockerfiles build unchanged, and ERPNext's `examleaf-erp` (section
"ERPNext"). From this directory:

```sh
docker login ghcr.io          # a token with write:packages
make images DOMAIN=examleaf.in RAZORPAY_KEY_ID=rzp_live_… TURNSTILE_SITE_KEY=… PUBLIC_MEDIA_DOMAIN=media.examleaf.in
make push
```

The three are tagged with the git commit (`TAG`; `REGISTRY` changes the registry, as the chart's value does). The two
Next.js builds have their `NEXT_PUBLIC_*` values compiled in: the website its domain and keys, the panel its own host
(`ADMIN_HOST`, default `admin.<DOMAIN>`, the chart's `admin.host`), the website's address and ERPNext's desk for its
links (`ERP_URL`, empty until ERPNext runs). A change of one of them means `make images` again. The packages of a
private repository are private, so the cluster pulls with a Secret, `ghcr-pull` (`imagePullSecrets`, and
`erpnext.imagePullSecrets` for ERPNext's pods), made from a token with `read:packages`:

```sh
kubectl -n examleaf create secret docker-registry ghcr-pull --docker-server=ghcr.io \
  --docker-username=<GitHub user> --docker-password=<token with read:packages>
```

## Secrets

No secret ever goes into a values file. The chart reads three Secrets in the release's namespace (four with ERPNext),
and makes none from values:

| Secret (default name) | Keys | Read by |
|---|---|---|
| `examleaf-env` | `SECRET_KEY`, `LEARN_CODE_SECRET`, `INTERNAL_API_TOKEN` and `INTEGRATION_KEYS`, then as the features need them the keys `values.yaml` lists under `secrets.env` (insights, email, SMS, Razorpay, Google, Turnstile, S3, Firebase, Sentry) | web, worker and beat as their environment (every key); the frontend and the admin `INTERNAL_API_TOKEN`; the media worker `SECRET_KEY` and the four S3 keys |
| `examleaf-health-auth` | type `kubernetes.io/basic-auth`: `username` monitor, `password` HEALTH_CHECK_TOKEN | Traefik's BasicAuth, for `/health` |
| `examleaf-backup` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (the backup bucket's keys, as `scripts/backup.sh` names them) | the Barman Cloud plugin; with ERPNext, mariadb-operator's backups and the site backups; no pod of the site |
| `examleaf-erp` (ERPNext only) | `db-root-password`, `admin-password` | MariaDB, bench (the site's database), the createSite Job |

**Made by hand** (`secrets.mode: existing`, the default). Keep the values in a password manager, put them into files
that never enter the repository, and load them:

```sh
kubectl create namespace examleaf
kubectl -n examleaf create secret generic examleaf-env --from-env-file=examleaf.env   # KEY=value lines, no comments
kubectl -n examleaf create secret generic examleaf-health-auth --type=kubernetes.io/basic-auth \
  --from-literal=username=monitor --from-literal=password="$HEALTH_CHECK_TOKEN"
kubectl -n examleaf create secret generic examleaf-backup \
  --from-literal=AWS_ACCESS_KEY_ID=… --from-literal=AWS_SECRET_ACCESS_KEY=…
shred -u examleaf.env
```

The values are made as DEPLOYMENT.md section 4 makes them (`python3 -c "import secrets; print(secrets.token_urlsafe(50))"`
for `SECRET_KEY` and `LEARN_CODE_SECRET`, `token_urlsafe(32)` for `INTERNAL_API_TOKEN` and `HEALTH_CHECK_TOKEN`).
`LEARN_CODE_SECRET` is set once and never changed (printed book codes depend on it). `INTEGRATION_KEYS`, Fernet keys
newest first, must be there before anyone adds an integration account (Shiprocket's): the accounts' credentials are
encrypted with them, and once one exists `migrate` stops without them (`integrations.E001`), so web's init container
never finishes; a database restored elsewhere needs the same keys. One key:
`python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

**From a secret store** (`secrets.mode: externalSecret`). With the External Secrets Operator and a ClusterSecretStore
for your store (AWS Secrets Manager, Vault, 1Password, Doppler …), the chart renders ExternalSecrets that write the
same Secrets: `secrets.externalSecret.envKey` (default `examleaf/env`) is one JSON object whose properties are the
environment's keys, `backupKey` (`examleaf/backup`) holds the two backup keys, `erpKey` (`examleaf/erp`) ERPNext's
two, and the health Secret's password is the `HEALTH_CHECK_TOKEN` property of `envKey`. The ExternalSecrets were
rendered but not run (TESTING.md section 8).

A changed Secret reaches the pods when they start again: `kubectl -n examleaf rollout restart deployment` (the
settings in the ConfigMap restart the pods by themselves on `helm upgrade`). RUNBOOK.md's "Secrets and key rotation"
applies as it stands, with `kubectl create secret … --dry-run=client -o yaml | kubectl apply -f -` in place of editing
`.env`.

## DNS and the two hosts

Two names point at the ingress controller's address (an `A` and an `AAAA` record each): `examleaf.in` (the `domain`
value) and `admin.examleaf.in` (`admin.host`, default `admin.<domain>`) once the admin panel is enabled. cert-manager
asks Let's Encrypt for each host's certificate once the name resolves to the controller and port 80 answers there.

Both hosts route as the Caddyfile does: `/api/`, `/_allauth/`, `/admin/`, `/shop/webhooks/`, `/anymail/`,
`/shop/media/`, `/learn/preview/`, `/learn/hls/`, `/account/google/`, `/qr/` and `/static/` to Django, every other
path to the website on the main host and to the panel on the admin host; http is redirected to https. The paths keep
the Caddyfile's trailing slashes (`/api/*` there): Traefik matches a Prefix path character by character, so `/api`
alone would also have caught `/apiary/`. The admin host needs Django's paths because the panel signs in and calls
`/api/v1/staff/` on its own host: with the admin on, the chart adds the host to `ALLOWED_HOSTS` and its origin to
`CSRF_TRUSTED_ORIGINS` (both from the environment, as Django reads them). Its cookies are its own (Django's and the
panel's are host-only, so a session there is not the website's). `admin.allowlist` (a list of CIDRs) limits who reaches
the admin host at all, Django's paths there included: others get 403 from Traefik before the panel's own sign-in.
`/health` is not served on the admin host; the panel's server never sees it (`health-hide`), so it answers 404. As
the Caddyfile's admin site does, Traefik drops the request header `X-Middleware-Subrequest` before the panel
(`drop-subrequest`: Next.js's internal header, never a visitor's, CVE-2025-29927). Staff who sign in with Google there
need `https://admin.<domain>/account/google/login/callback/` among the OAuth client's redirect URIs
(`examleaf-admin/README.md` "Deploy").

## Install

```sh
cd deploy/kubernetes
make deps                                            # the ERPNext chart that Chart.lock pins (switched off)
helm upgrade --install examleaf examleaf-platform --namespace examleaf --create-namespace \
  -f values-production.yaml --set image.tag=<TAG> --set frontend.image.tag=<TAG> --set admin.image.tag=<TAG> \
  --wait --timeout 15m
```

`values-production.yaml` is yours, kept outside the repository or without secrets in it: at least `domain` (and
`registry` if the images live elsewhere than `ghcr.io/lazyindianbook`), the `config` settings that DEPLOYMENT.md
section 4 lists for a first deployment (`EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL`, the seller's details …), `media` and
`postgres.storage` with the cluster's storage classes, and `postgres.backup`. The pull Secret `ghcr-pull` ("Images")
and the Secrets ("Secrets") come first. Then:

```sh
kubectl -n examleaf get pods,cluster                             # all Running; the Cluster "Cluster in healthy state"
kubectl -n examleaf logs deploy/examleaf-web -c migrate          # the migrations and bootstrap_roles
kubectl -n examleaf exec -it deploy/examleaf-web -- python manage.py createsuperuser
kubectl -n examleaf exec deploy/examleaf-web -- python manage.py check --deploy   # W005 and W021 only, with EMAIL_BACKEND set
kubectl -n examleaf exec deploy/examleaf-web -- python manage.py sendtestemail you@example.com
```

**The papers.** `import_papers` reads a checkout of the books repository (DEPLOYMENT.md section 4), which is not in
the image. Copy the folders it reads into the web pod and import from there:

```sh
tar czf papers.tgz -C /path/to/books production/{physics,chemistry,mathematics,biology}/{papers_md,format.json,orders,pyq}
POD=$(kubectl -n examleaf get pod -l app.kubernetes.io/component=web -o name | head -n 1)
kubectl -n examleaf cp papers.tgz ${POD#pod/}:/tmp/papers.tgz -c web
kubectl -n examleaf exec $POD -c web -- sh -c "mkdir -p /tmp/books && tar xzf /tmp/papers.tgz -C /tmp/books && python manage.py import_papers --all --root /tmp/books"
```

`/tmp` is the pod's own and goes with it; importing again is safe at any time (DEPLOYMENT.md section 11).

## Health checks

The Caddyfile answers `/health` and `/health/*` with 404 unless the header `X-Health-Token` carries
`HEALTH_CHECK_TOKEN`. Traefik's middlewares cannot compare a header with a secret value, so the chart puts `/health`
behind Traefik's BasicAuth instead: user `monitor`, password `HEALTH_CHECK_TOKEN`, from the Secret
`examleaf-health-auth`. Anyone else gets 401. **The uptime monitor changes**: it sends basic auth instead of the
header (UptimeRobot, Better Stack, Uptime Kuma and Pingdom all can), with the same token:

```sh
curl -s -u "monitor:$HEALTH_CHECK_TOKEN" -H 'Accept: application/json' https://examleaf.in/health/
```

A second monitor, as DEPLOYMENT.md asks, watches `/health/integrations/` with the same credentials: a provider down
for half an hour, or dead letters and failed webhooks waiting for staff; `/health/` stays the site's own.

`/health` must never reach the website: its server passes Django's paths on to Django (its development proxy), and the
health pages would be open. Traefik drops a router whose middleware cannot be built, and without its Secret the
BasicAuth cannot, so `/health` would fall through to the website's router; that router rewrites any `/health` path
before the website sees it (`health-hide`), and the answer is the website's 404, as Caddy's was while the token was
unset. TESTING.md section 3 tries it.

Inside the cluster nothing changes: the kubelet asks `/health/web/` directly for web's readiness, with the site's host
and `X-Forwarded-Proto: https` as the compose health check does; it needs no token, and putting the token into the
probe would copy the secret into the Deployment. `/health/` waits two seconds for every Celery worker and fails unless
the default and the media queue each have one (`examleaf.health.WorkerPing`), so the media worker is part of a
healthy site: `CELERY_HEALTH_QUEUES` in settings.py lists both, and with `mediaWorker.enabled: false` `/health/`
answers 500 until that list changes.
`cronJobs.healthCheck` (off by default) runs `manage.py health_check health` against the web Service on a schedule;
`kubectl get jobs` (or kube-state-metrics) shows a failed run.

## Upgrades and migrations

```sh
make images push TAG=<new>            # or the CI's images
helm upgrade examleaf examleaf-platform -n examleaf -f values-production.yaml \
  --set image.tag=<new> --set frontend.image.tag=<new> --wait --timeout 15m
```

The new web pod runs `migrate` and `bootstrap_roles` in its init container while the old pod still serves; once it is
ready the old one goes (`maxUnavailable: 0`, one new pod at a time, so only one pod migrates). Worker, beat and the
media worker each wait in their init container until the migrations are applied, then replace their old pods; beat's
old pod is gone before the new one starts. As with compose, the old code runs against the new schema for the
minute of the rollout: a migration that drops or renames something the old code reads goes out in two releases.
`helm rollback` brings the old images back but not the old schema; restore from a backup if a migration must be
undone. A release can bring settings: compare `values.yaml` with yours and DEPLOYMENT.md section 13.

## Backups and restore

**What is backed up.** With `postgres.backup.enabled`, CloudNativePG's Barman Cloud plugin archives every WAL file to
the bucket as PostgreSQL writes it, and the ScheduledBackup takes a base backup every day at 02:15 UTC and once at
the start. Any moment of the last `keepDays` (30, `BACKUP_KEEP_DAYS`) can be restored. The variables are
`scripts/backup.sh`'s: `bucket` is `BACKUP_BUCKET`, `endpointURL` is `BACKUP_ENDPOINT_URL`
(`https://<ACCOUNT_ID>.r2.cloudflarestorage.com` for R2), the keys are `AWS_ACCESS_KEY_ID` and
`AWS_SECRET_ACCESS_KEY` in the Secret `examleaf-backup`. The files go under `cnpg/<cluster name>/` in the bucket, apart
from backup.sh's `database/`.

```sh
kubectl -n examleaf get backups,scheduledbackups
kubectl -n examleaf get cluster examleaf-db -o jsonpath='{.status.conditions[?(@.type=="ContinuousArchiving")].status}'   # True
```

Give the bucket a lifecycle rule for `cnpg/` a few days longer than the window (35 days): barman deletes what falls
out of the window itself, and the rule only catches what it leaves behind. The newest base backup older than the
window is kept as the window's start, so the oldest data in the bucket is up to 31 days old (the Privacy Policy says
30 days of backups).

**What differs from backup.sh: encryption.** The plugin has no counterpart to `BACKUP_AGE_RECIPIENT`, so whoever
holds the bucket's keys can read the backups; keep those keys to the plugin (they are in a Secret of their own, which
no pod of the site mounts). What the bucket itself offers:

- **Cloudflare R2** encrypts every object at rest with its own keys, always, and refuses the server-side encryption
  header (`x-amz-server-side-encryption`), so `postgres.backup.encryption` stays empty there. R2 also takes keys of
  your own per request (SSE-C), which barman-cloud 3.20 can send, but the plugin's ObjectStore has no field for it
  yet.
- **AWS S3** (e.g. a bucket in Mumbai, should the private data move there) takes `postgres.backup.encryption:
  AES256` (S3's own keys) or `aws:kms` (a KMS key the IAM policy controls), set on the base backups and the WAL.

Neither keeps the backups from someone with the bucket's keys, as age did. For a copy that only an offline key opens,
the documented way stays a dump streamed to a computer that has `age` (no extra image in the cluster):

```sh
kubectl -n examleaf exec examleaf-db-1 -c postgres -- pg_dump --format custom examleaf \
  | age --recipient age1… > examleaf-$(date +%Y%m%d-%H%M%S).dump.age
```

Keep it off the server, as DEPLOYMENT.md section 9 keeps backup.sh's (a weekly copy, say, besides the continuous
backups).

**The media volume** is not in these backups. With the buckets of DEPLOYMENT.md section 17 the invoices and the
pictures are in R2 and the volume holds almost nothing; without them it holds the invoices (tax records: eight years),
so copy it out as DEPLOYMENT.md section 9 does:
`kubectl -n examleaf exec deploy/examleaf-web -c web -- tar czf - -C /app/media . > media-$(date +%F).tgz`.

**Restore** to a point in time makes a new Cluster from the bucket (CloudNativePG never restores over a running
one). Note the account deletions completed since that point first (RUNBOOK.md "Restore the database from a
backup", step 2), then:

```sh
helm upgrade examleaf examleaf-platform -n examleaf -f values-production.yaml --reuse-values \
  --set postgres.name=examleaf-db-2 \
  --set postgres.recovery.enabled=true \
  --set postgres.recovery.serverName=examleaf-db \
  --set-string postgres.recovery.targetTime="2026-10-09 02:00:00+05:30"   # leave it out for the latest moment
```

The new cluster recovers from the base backup and the WAL, then archives under its own name in the same bucket; every
pod of the site restarts with the new cluster's `DATABASE_URL`. The old Cluster stays (Helm keeps it) until you delete
it: `kubectl -n examleaf delete cluster examleaf-db`. Keep `postgres.name` and the recovery values in your values
file afterwards (they only act when a Cluster is created). Then RUNBOOK.md's steps 4 and 5: erase the noted accounts
again and check `/health/`. TESTING.md shows such a restore.

**From docker-compose** (the first move, or a dump of RUNBOOK.md's kind):

```sh
docker compose exec -T db pg_dump --username examleaf --format custom examleaf > examleaf.dump   # on the old server
kubectl -n examleaf scale deployment examleaf-web examleaf-worker examleaf-beat examleaf-media-worker --replicas 0
kubectl -n examleaf exec -i examleaf-db-1 -c postgres -- pg_restore --clean --if-exists --no-owner --role examleaf \
  --dbname examleaf < examleaf.dump
kubectl -n examleaf scale deployment examleaf-web examleaf-worker examleaf-beat examleaf-media-worker --replicas 1
```

and the media volume across (`tar` out of the compose volume, then into the web pod with `kubectl exec -i … tar xzf -
-C /app/media`), before DNS moves.

## Storage

| Claim | Access | Size (default) | Notes |
|---|---|---|---|
| `examleaf-media` | `media.accessMode`: ReadWriteMany | 10Gi | web, worker, beat and the media worker mount it. ReadWriteOnce works while those pods run on one node: single-node clusters, and provisioners without ReadWriteMany (k3s's local-path, kind) need it; with more nodes pin the pods to one (`nodeSelector`) or use RWX storage (NFS, CephFS, Longhorn) or the buckets |
| the Cluster's | ReadWriteOnce | 10Gi | made by CloudNativePG, one per instance |
| `examleaf-redis-queue` | ReadWriteOnce | 1Gi | the queue's AOF |

`helm uninstall` leaves the media claim, the queue's claim and the Cluster in place (`helm.sh/resource-policy: keep`):
they hold invoices, queued emails and the database. Delete them by hand when they are truly not wanted.

## Node maintenance

Two disruption budgets refuse eviction on purpose: beat's (two beats would send every periodic task twice) and, with
one instance, CloudNativePG's for the primary. Before draining a node:

```sh
kubectl -n examleaf scale deployment examleaf-beat --replicas 0
kubectl -n examleaf patch cluster examleaf-db --type merge -p '{"spec":{"nodeMaintenanceWindow":{"inProgress":true,"reusePVC":true}}}'
kubectl drain <node> --ignore-daemonsets --delete-emptydir-data
# … the maintenance; then
kubectl uncordon <node>
kubectl -n examleaf patch cluster examleaf-db --type merge -p '{"spec":{"nodeMaintenanceWindow":{"inProgress":false}}}'
kubectl -n examleaf scale deployment examleaf-beat --replicas 1
```

On a single node the site is down while the node is; with three nodes and `postgres.instances: 3` the database fails
over and the drain needs none of this but the beat step.

## Sizing for a single node

The requests and limits in `values.yaml`, for one node to start:

| Pod | Requests | Limits |
|---|---|---|
| web (3 gunicorn processes of 8 threads) | 250m, 640Mi | 1 CPU, 1Gi |
| worker (2 processes) | 100m, 384Mi | 1 CPU, 768Mi |
| beat | 20m, 192Mi | 500m, 384Mi |
| media worker (FFmpeg) | 100m, 256Mi | 2 CPU, 1Gi |
| frontend | 100m, 256Mi | 1 CPU, 512Mi |
| PostgreSQL, with the backup sidecar | 300m, 640Mi | 3 CPU, 1.5Gi |
| the two Redis | 100m, 128Mi | 1 CPU, 832Mi |
| **the site** | **about 1 CPU, 2.5Gi** | |

The operators and the controller add about 0.3 CPU and 0.6 GiB (Traefik, cert-manager, CloudNativePG and the
plugin; TESTING.md has what they used on kind), and the cluster itself (k3s, or a managed control plane elsewhere) about
0.5 CPU and 1 GiB. A node of 4 vCPU and 8 GB carries the platform with room for traffic and the admin panel (100m,
256Mi more). ERPNext asks for about 2.2 CPU and 5.8 GiB more and runs at 6–8 GiB (section "ERPNext"): with it, a node
of 8 vCPU and 16 GB. TESTING.md has the memory measured on kind; `values-kind.yaml` shows the smallest settings that
work.

## ERPNext

ERPNext v16 is the business's system of record beside the platform (plan sections 3.1 to 3.4); the facts behind its
values are in `docs/research/2026-10-09-admin-control-panel/research-erpnext.md`. `Chart.yaml` lists frappe/helm's
`erpnext` chart 8.0.84 (app v16.50.0) with `condition: erpnext.enabled`, which `make deps` fetches. While it is off
nothing of it is rendered. With it on, the release gets frappe/helm's Deployments (nginx, gunicorn, worker-default,
worker-short, worker-long, the scheduler, socketio) and its two Valkey, and from this chart:

| Part (values.yaml) | What |
|---|---|
| `erp.database` | a standalone `MariaDB` of mariadb-operator, `examleaf-erp-db`, kept by `helm uninstall`: MariaDB 11.8 (v16 needs it, and no supported release runs on PostgreSQL), `utf8mb4` and `utf8mb4_unicode_ci` with `skip-character-set-client-handshake`, a 2 GiB buffer pool in a 4 GiB pod, `innodb-flush-log-at-trx-commit = 1`, the binlog kept 14 days |
| `erp.database.backup` | a `PhysicalBackup` (mariadb-backup) every day at 02:30 to the platform's bucket under `erpnext/mariadb`, kept 30 days |
| `erp.siteBackup` | a CronJob every 6 hours: `bench --site all backup --with-files` onto the sites volume, then rclone copies the backups folder (the database dump, the public and private files, `site_config_backup.json`) to the bucket under `erpnext/sites` |
| `erp.host`, `erp.allowlist` | the Ingress `examleaf-erp` for `erp.examleaf.in`: its certificate, HSTS, nosniff, Referrer-Policy and X-Frame-Options set by Traefik (`erp-headers`), an optional allowlist (`erp-allowlist`); no Buffering, so that socketio's WebSockets pass and ERPNext's nginx keeps its own 50 MB limit |
| NetworkPolicies | ERPNext's pods open to each other within the namespace (its Jobs' pods carry no labels to select them by), its nginx to the controller, its Valkey and MariaDB to the namespace and to mariadb-operator, the web Service to its webhooks |

The `erpnext` values cover the chart's gaps: the custom image, the external MariaDB (the chart's own `mariadb-sts`
would start MariaDB 10.6, past its end of life, and its Bitnami subchart is frozen on `bitnamilegacy`), requests and
limits for every component (the chart sets none), HTTP probes on `/api/method/ping` (the chart's only check ports),
the gunicorn autoscaler kept off (it targets `apps/v2`, which does not exist), and the sites volume ReadWriteOnce for
one node.

### Before switching it on

1. **mariadb-operator** 26.10 ("Operators first").
2. **The image** `<registry>/examleaf-erp:<tag>` (`ghcr.io/lazyindianbook/examleaf-erp`), built and tagged with
   frappe_docker v4.0.0 in `examleaf-erp/image` (`FRAPPE_BRANCH=v16.50.0`, `apps.json` as a BuildKit secret). Its tag
   comes from there: `erpnext.image.tag` has no default and the chart refuses to render ERPNext without it.
   frappe/helm's chart reads only `erpnext.image.repository`, so that value spells the registry out, and the chart
   refuses one that is not `<registry>/examleaf-erp`. The pull Secret `ghcr-pull` serves it too
   (`erpnext.imagePullSecrets`). Never `frappe/erpnext:latest`, which is the `develop` branch.
3. **The Secret** `examleaf-erp`, with `db-root-password` (MariaDB's root, which bench uses to make the site's
   database) and `admin-password` (the site's Administrator), or `secrets.externalSecret.erpKey`:
   `kubectl -n examleaf create secret generic examleaf-erp --from-literal=db-root-password=… --from-literal=admin-password=…`.
   The backup bucket's keys are `examleaf-backup`'s.
4. **Storage**: `erpnext.persistence.worker.storageClass` named (the chart refuses an empty one; `local-path` on
   k3s), ReadWriteOnce on one node, ReadWriteMany (NFS, CephFS, Longhorn RWX) once ERPNext's pods spread over nodes;
   `erp.database.storage` for MariaDB.
5. **Names**: DNS for `erp.examleaf.in`. Another host means `erp.host` and the values that repeat it (the `*erpSite`
   anchor in values.yaml: the Jobs' site name and the probes' Host). `erpnext.nginx.environment.upstreamRealIPAddress`
   is the cluster's pod network (k3s's 10.42.0.0/16 by default), so that ERPNext's nginx takes the visitor's address
   from the controller. The release is called `examleaf`: `erpnext.dbHost` (`examleaf-erp-db`) and
   `erpnext.dbExistingSecret` follow its name, and the chart refuses a `dbHost` that is not its MariaDB.

Then `helm upgrade … --set erpnext.enabled=true --set erpnext.image.tag=<tag>`.

### The site, its Jobs and its upgrades

frappe/helm's Jobs are not part of the release: each is rendered with `helm template -s` and applied (each name
carries a timestamp). With the release's own values file in `$VALUES`:

```sh
erp_job() {  # frappe/helm's charts/erpnext/templates/job-$1.yaml, with jobs.$2.enabled
  helm template examleaf examleaf-platform -n examleaf -f "$VALUES" --set erpnext.enabled=true \
    --set "erpnext.jobs.$2.enabled=true" -s "charts/erpnext/templates/job-$1.yaml" | kubectl -n examleaf apply -f -
}
erp_job create-site createSite   # once: erp.examleaf.in with erpnext, india_compliance, hrms, offsite_backups, examleaf_erp
```

Once the site exists, keep its `site_config.json` as a secret: it holds the Fernet `encryption_key` that decrypts
every password field (API secrets, email passwords), and a site restored without it cannot read its own secrets.

```sh
kubectl -n examleaf exec deploy/examleaf-erpnext-gunicorn -- cat sites/erp.examleaf.in/site_config.json \
  | kubectl -n examleaf create secret generic examleaf-erp-site-config --from-file=site_config.json=/dev/stdin
```

A copy goes into the password manager too, again whenever System Settings' "Encrypt Backup" adds its
`backup_encryption_key`. Every upgrade (Frappe tags a release every week: patch weekly, a major after a staging run):

```sh
kubectl -n examleaf create job --from=cronjob/examleaf-erp-site-backup erp-backup-$(date +%s)   # 1. a backup; wait for it
helm upgrade examleaf examleaf-platform -n examleaf -f "$VALUES" --set erpnext.image.tag=<new>     # 2. the new image
erp_job migrate-site migrate                                                                        # 3. bench migrate, in maintenance mode
erp_job clear-cache clearCache                                                                      # 4. the cache
```

A new app means a new image (apps are baked in, a pod cannot fetch one), then
`kubectl -n examleaf exec deploy/examleaf-erpnext-gunicorn -- bench --site erp.examleaf.in install-app <app>`, then
steps 3 and 4.

### ERPNext's backups and restore

Two copies, both in the platform's backup bucket: mariadb-operator's daily physical backup (`erpnext/mariadb`,
30 days) and the site backups every 6 hours (`erpnext/sites`; rclone only adds, so give that prefix a 30-day lifecycle
rule). The `offsite_backups` app, installed with the site, can push the same to the bucket from ERPNext's own settings
instead of the CronJob. A site is restored in a pod that mounts the sites volume:
`bench --site erp.examleaf.in restore <…-database.sql.gz> --with-public-files <…> --with-private-files <…>
--db-root-username root --db-root-password <…>`, then its `site_config.json` from the Secret; the database alone, from
a `MariaDB` with `bootstrapFrom` the PhysicalBackup (mariadb-operator's documentation). Try one every quarter in a
scratch namespace.

### ERPNext's security

ERPNext is for staff only: sign-in through Google Workspace SSO with 2FA by role, email-link log-in off (it is on by
default), sessions of 8 to 12 hours instead of the default 170 (System Settings), no portal or website pages for the
public. `erp.allowlist`, or a VPN in front, limits who reaches the host at all. The platform calls ERPNext's API inside
the cluster (`http://examleaf-erpnext.examleaf.svc:8080`, with the site's name as the Host), and ERPNext's webhooks
reach Django the same way (`http://examleaf-web.examleaf.svc:8000/…`). Django checks ALLOWED_HOSTS, so every webhook
carries the headers `X-Forwarded-Host: examleaf.in` and `X-Forwarded-Proto: https` (Webhook → Headers), or Django
answers 400; the website's health check had exactly that fault (TESTING.md section 7).

### ERPNext's sizing

An estimate for 5 to 15 staff and a few hundred synced orders a day (research-erpnext.md section 3.6):

| Component | Requests | Limits |
|---|---|---|
| gunicorn (3 workers of 4 threads) | 500m, 1Gi | 2 CPU, 2Gi |
| worker-default, worker-short | 100m, 256Mi each | 1 CPU, 512Mi each |
| worker-long (GSTR-1, reports, imports) | 200m, 512Mi | 2 CPU, 1.5Gi |
| scheduler, socketio, nginx | 50m each; 192Mi, 128Mi, 64Mi | 500m each; 384Mi, 256Mi, 256Mi |
| valkey-cache, valkey-queue | 50m each; 256Mi, 128Mi | 320Mi, 256Mi |
| MariaDB | 1 CPU, 3Gi | 4Gi |
| **ERPNext** | **about 2.2 CPU, 5.8 GiB** | about 9.9 GiB |

About 6 to 8 GiB in steady state; with the platform, a node of 8 vCPU and 16 GB. On kind it stays off (TESTING.md
section 6: rendered and validated against the API server, not run).

## Differences from docker-compose

- **TLS and the edge.** cert-manager and Traefik in place of Caddy. Traefik adds no security headers of its own, so
  Django's and Next's are what the browser gets, and `strip-server` removes gunicorn's `Server` header as Caddy did.
  The http redirect keeps the whole path; it answers a GET with 301 where Caddy answered 308. HTTP/3 is off (Caddy
  answered on 443/udp; Traefik's chart has `ports.websecure.http3.enabled`).
- **The health gate** is basic auth with `HEALTH_CHECK_TOKEN` as the password and answers 401, where Caddy wanted the
  `X-Health-Token` header and answered 404 ("Health checks" above). It is on the main host only; Caddy's admin site
  served `/health` with the token too.
- **Request IDs.** Traefik makes none: django-guid makes one per request (and takes a client's own only when it is a
  UUID), so the access log and Django's log share no ID, where Caddy put its own ID into both.
- **Body limits.** 10 MB on Django's form and API paths, read whole before gunicorn sees them, as Caddy did. The
  website's pages and Django's file paths stream instead, because Traefik's Buffering also holds back every response
  until it is complete: the website's streamed pages would lose their streaming, and pictures, invoices and the
  course's video would go through Traefik's disk. The clip and revision admin pages stream to Django with no limit at
  the edge (Caddy's was 500 MB): buffering 500 MB there would let anyone park that much on the controller's disk
  before Django could refuse it, while streamed, Django refuses a body over 1 MB from anyone but signed-in staff
  before reading it (`learn.uploads.LargeBodyGuard`), and the clip form checks `LEARN_MAX_UPLOAD_MB` for staff.
- **Timeouts.** A request has 5 minutes, its headers included (`traefik-values.yaml`); Caddy gave the headers 10
  seconds and the body 5 minutes.
- **Migrations** run in web's init container, as compose's web command runs them, and the Celery processes wait for
  them (compose waited for web to be healthy). The readiness probe replaces the start-up `health_check` command.
- **Beat** cannot overlap: Recreate on rollout and a disruption budget against eviction.
- **Backups** are continuous (WAL and daily base backups, to any moment of 30 days) instead of a nightly `pg_dump`,
  and not age-encrypted ("Backups and restore").
- **Hardening.** Every container runs as its image's unprivileged user by number, without capabilities or a service
  account token, with a read-only root filesystem and an emptyDir at `/tmp` (compose made only the frontend
  read-only). NetworkPolicies deny ingress by default; the media worker's restricted environment is the same.
- **Secrets** are Secrets (by hand or from a store) instead of `.env`; a change needs a rollout restart.
- **The papers** are copied into a pod to import them; compose mounted the books checkout (`BOOK_SOURCE`).
- **Logs** are `kubectl logs` (the kubelet rotates them at 10 MiB, five files, as compose's json-file settings did);
  the access log is the controller's.
