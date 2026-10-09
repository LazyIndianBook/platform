# ExamLeaf on Kubernetes

This directory packages the platform for a Kubernetes cluster, as section 3.4 of
`docs/examleaf-admin-control-panel-plan.md` decided: one Helm chart, `examleaf-platform`, with the Django backend and
its Celery processes, the Next.js website, a place for the admin panel, PostgreSQL through the CloudNativePG operator,
two Redis, the Ingress and its certificates. ERPNext is a dependency of the chart with its database, backups and
Ingress prepared, switched off until it is added (section "ERPNext" below). docker-compose
(`examleaf-web/docker-compose.yml`) stays for development and for a one-machine server; this is the same stack,
translated. `TESTING.md` records a full run of the chart on a `kind` cluster (ERPNext rendered and validated, not run);
the chart has not yet run on a real cluster.

| Path | What it holds |
|---|---|
| `examleaf-platform/` | the chart: `values.yaml` (every setting, each explained), `values-kind.yaml` (the laptop profile), `templates/` |
| `Makefile` | the images, the chart's checks and the kind cluster (`make` lists the tasks) |
| `kind-config.yaml`, `kind-extras.yaml` | the kind test cluster, and its stand-ins for Let's Encrypt and Cloudflare R2 |
| `TESTING.md` | what was run on kind, and what it showed |

## What runs where

| docker-compose.yml | Kubernetes (release `examleaf`) |
|---|---|
| `web` (migrate, bootstrap_roles, gunicorn) | Deployment `examleaf-web`: an init container waits for the database and runs `migrate` and `bootstrap_roles`; gunicorn is ready once `/health/web/` answers |
| `worker`, `beat`, `media-worker` | Deployments `examleaf-worker`, `examleaf-beat` (always one pod), `examleaf-media-worker` (its own small environment); each waits until the migrations are applied |
| `frontend` | Deployment `examleaf-frontend` |
| (none yet) | Deployment `examleaf-admin` at `admin.<domain>`, off until the panel's image exists |
| `db` (postgres:17) | CloudNativePG `Cluster` `examleaf-db` (PostgreSQL 17), continuous backup to a bucket |
| `redis`, `redis-cache` | Deployments `examleaf-redis-queue` (with a volume) and `examleaf-redis-cache` |
| `caddy` | four Ingresses for ingress-nginx, certificates from cert-manager |
| `.env` | the ConfigMap `examleaf-config` (from `values.yaml` "config") and the Secrets you make (`examleaf-env` …) |
| volumes `media`, `pgdata`, `redisdata` | PersistentVolumeClaims `examleaf-media`, the Cluster's own, `examleaf-redis-queue` |
| (none) | with `erpnext.enabled`: frappe/helm's ERPNext (`examleaf-erpnext-*`), its MariaDB `examleaf-erp-db` through mariadb-operator, the site backups, `erp.<domain>` |

## Operators first

The chart expects these in the cluster. Each is installed the way its project documents, at the release the Makefile
pins (the kind test used exactly these).

| What | Release | Install | Why |
|---|---|---|---|
| ingress-nginx | controller v1.15.1 (chart 4.15.1) | its Helm chart, or the provider's manifest from `deploy/static/provider/` | the Ingresses' controller |
| cert-manager | v1.21.2 | `kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.21.2/cert-manager.yaml` | the certificates of both hosts; the Barman Cloud plugin needs it too |
| CloudNativePG | 1.30.1 | `kubectl apply --server-side -f https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.30/releases/cnpg-1.30.1.yaml` | PostgreSQL |
| Barman Cloud plugin | v0.15.1 | `kubectl apply -f https://github.com/cloudnative-pg/plugin-barman-cloud/releases/download/v0.15.1/manifest.yaml` (after cert-manager, into `cnpg-system`) | backups and restores of PostgreSQL |
| External Secrets Operator | 2.12.0 | its Helm chart | only with `secrets.mode: externalSecret` |
| metrics-server | 0.9.0 | its manifest or chart | only for the autoscalers (`web.autoscaling`, `frontend.autoscaling`) |
| mariadb-operator | 26.10.1 | its two Helm charts, `mariadb-operator-crds` then `mariadb-operator` (`https://helm.mariadb.com/mariadb-operator`), into `mariadb-operator` | only with ERPNext |

CloudNativePG's own support for Barman Cloud inside the operator is deprecated (removal is announced for 1.31), so the
chart uses the plugin from the start.

**ingress-nginx is retired.** The Kubernetes project stopped maintaining it in March 2026: v1.15.1 is the last
release and no security fix will follow. The chart uses it because the plan chose it, and nothing in the chart is
tied to it but annotations: the Ingresses are plain `networking.k8s.io/v1` resources, the controller-specific
annotations are listed below, and `ingress.className`, `ingress.annotations` and `ingress.healthAnnotations` change
them. Choose the replacement (another Ingress controller, or the Gateway API) before the site goes live.

### The ingress controller

Three controller-wide settings keep Caddy's behaviour. ingress-nginx adds its own
`Strict-Transport-Security: max-age=31536000; includeSubDomains` to every https answer, replacing Django's and Next's
header, which leave out `includeSubDomains` on purpose (DEPLOYMENT.md section 13, `check --deploy`'s W005); it
compresses nothing unless told to, where Caddy compressed every answer; and it waits 60 seconds for a client's
headers, where Caddy waited 10. With the Helm chart:

```sh
helm upgrade --install ingress-nginx ingress-nginx --repo https://kubernetes.github.io/ingress-nginx --version 4.15.1 \
  --namespace ingress-nginx --create-namespace \
  --set-string controller.config.hsts=false \
  --set-string controller.config.use-gzip=true \
  --set-string controller.config.client-header-timeout=10 \
  --set controller.service.externalTrafficPolicy=Local
```

`externalTrafficPolicy=Local` keeps the visitor's address: Django counts failed log-ins, rate limits and the device
list by it (`PROXY_COUNT=1` trusts the one proxy in front, as with Caddy). If a load balancer or Cloudflare's proxy
sits in front of the controller, the address it sees is the balancer's, and every visitor would share one limit: use
the PROXY protocol (`controller.config.use-proxy-protocol`) or the controller's `use-forwarded-headers` with
`proxy-real-ip-cidr` set to the balancer's ranges, then try `/api/v1/` from two addresses.

With ERPNext add `--set-string controller.config.global-allowed-response-headers="Strict-Transport-Security\,X-Content-Type-Options\,Referrer-Policy\,X-Frame-Options"`:
the controller sets those headers on the ERP's host only (`custom-headers`), and refuses any header not listed there.

The Ingresses carry these annotations: `proxy-body-size` (10 MB, 500 MB on the clip and revision admin pages, as the
Caddyfile has them), `proxy-request-buffering: "off"` on those two pages (Caddy streamed a body past its first 10 MB
too), `preserve-trailing-slash` (the https redirect keeps the whole path, as Caddy's did), `auth-type`, `auth-secret`
and `auth-realm` on `/health`, `whitelist-source-range` on the admin host when `admin.allowlist` is set (and on the
ERP's with `erp.allowlist`), `custom-headers` on the ERP's, and `cert-manager.io/cluster-issuer`. ingress-nginx
1.15.1 does not reload for a change of `preserve-trailing-slash` alone (TESTING.md section 6): a new install has it;
on a running controller, restart the controller once.

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
            ingressClassName: nginx
```

The chart's NetworkPolicies let the controller reach cert-manager's challenge pods.

## Images

The chart runs the two images that the repository's Dockerfiles build, unchanged. From this directory:

```sh
make images DOMAIN=examleaf.in RAZORPAY_KEY_ID=rzp_live_… TURNSTILE_SITE_KEY=… PUBLIC_MEDIA_DOMAIN=media.examleaf.in
make push REGISTRY=ghcr.io/lazyindianbook/
```

Both are tagged with the git commit (`TAG`, which can be set). The website's `NEXT_PUBLIC_*` values are compiled into
its build: a change of domain or of one of those keys means `make images` again. A private registry needs a pull
secret, named in `imagePullSecrets`.

## Secrets

No secret ever goes into a values file. The chart reads three Secrets in the release's namespace (four with ERPNext),
and makes none from values:

| Secret (default name) | Keys | Read by |
|---|---|---|
| `examleaf-env` | `SECRET_KEY`, `LEARN_CODE_SECRET` and `INTERNAL_API_TOKEN`, then as the features need them the keys `values.yaml` lists under `secrets.env` (email, SMS, Razorpay, Google, Turnstile, S3, Firebase, Sentry) | web, worker and beat as their environment (every key); the frontend and the admin `INTERNAL_API_TOKEN`; the media worker `SECRET_KEY` and the four S3 keys |
| `examleaf-health-auth` | `auth`: `monitor:{PLAIN}<HEALTH_CHECK_TOKEN>` | ingress-nginx, for `/health` |
| `examleaf-backup` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (the backup bucket's keys, as `scripts/backup.sh` names them) | the Barman Cloud plugin; with ERPNext, mariadb-operator's backups and the site backups; no pod of the site |
| `examleaf-erp` (ERPNext only) | `db-root-password`, `admin-password` | MariaDB, bench (the site's database), the createSite Job |

**Made by hand** (`secrets.mode: existing`, the default). Keep the values in a password manager, put them into files
that never enter the repository, and load them:

```sh
kubectl create namespace examleaf
kubectl -n examleaf create secret generic examleaf-env --from-env-file=examleaf.env   # KEY=value lines, no comments
kubectl -n examleaf create secret generic examleaf-health-auth --from-literal=auth="monitor:{PLAIN}$HEALTH_CHECK_TOKEN"
kubectl -n examleaf create secret generic examleaf-backup \
  --from-literal=AWS_ACCESS_KEY_ID=… --from-literal=AWS_SECRET_ACCESS_KEY=…
shred -u examleaf.env
```

The values are made as DEPLOYMENT.md section 4 makes them (`python3 -c "import secrets; print(secrets.token_urlsafe(50))"`
for `SECRET_KEY` and `LEARN_CODE_SECRET`, `token_urlsafe(32)` for `INTERNAL_API_TOKEN` and `HEALTH_CHECK_TOKEN`).
`LEARN_CODE_SECRET` is set once and never changed (printed book codes depend on it).

**From a secret store** (`secrets.mode: externalSecret`). With the External Secrets Operator and a ClusterSecretStore
for your store (AWS Secrets Manager, Vault, 1Password, Doppler …), the chart renders ExternalSecrets that write the
same Secrets: `secrets.externalSecret.envKey` (default `examleaf/env`) is one JSON object whose properties are the
environment's keys, `backupKey` (`examleaf/backup`) holds the two backup keys, `erpKey` (`examleaf/erp`) ERPNext's
two, and the health Secret's line is made from the `HEALTH_CHECK_TOKEN` property of `envKey`. The ExternalSecrets
were rendered but not run (TESTING.md section 8).

A changed Secret reaches the pods when they start again: `kubectl -n examleaf rollout restart deployment` (the
settings in the ConfigMap restart the pods by themselves on `helm upgrade`). RUNBOOK.md's "Secrets and key rotation"
applies as it stands, with `kubectl create secret … --dry-run=client -o yaml | kubectl apply -f -` in place of editing
`.env`.

## DNS and the two hosts

Two names point at the ingress controller's address (an `A` and an `AAAA` record each): `examleaf.in` (the `domain`
value) and `admin.examleaf.in` (`admin.host`, default `admin.<domain>`) once the admin panel is enabled. cert-manager
asks Let's Encrypt for each host's certificate once the name resolves to the controller and port 80 answers there.

The main host routes as the Caddyfile does: `/api`, `/_allauth`, `/admin`, `/shop/webhooks`, `/anymail`,
`/shop/media`, `/learn/preview`, `/learn/hls`, `/account/google`, `/qr` and `/static` to Django, every other path to
the website; http is redirected to https (308). The admin host sends everything to the admin panel. Its cookies are
its own (Django's and the panel's are host-only), and `admin.allowlist` (comma separated CIDRs) limits who reaches it
at all: others get 403 from the controller before the panel's own sign-in.

## Install

```sh
cd deploy/kubernetes
make deps                                            # the ERPNext chart that Chart.lock pins (switched off)
helm upgrade --install examleaf examleaf-platform --namespace examleaf --create-namespace \
  -f values-production.yaml --set image.tag=<TAG> --set frontend.image.tag=<TAG> --wait --timeout 15m
```

`values-production.yaml` is yours, kept outside the repository or without secrets in it: at least `domain`,
`image.repository` and `frontend.image.repository` (with the registry), the `config` settings that DEPLOYMENT.md
section 4 lists for a first deployment (`EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL`, the seller's details …), `media` and
`postgres.storage` with the cluster's storage classes, and `postgres.backup`. Then:

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
`HEALTH_CHECK_TOKEN`. ingress-nginx can only compare a header with a value through configuration snippets, which are
off by default since CVE-2025-1974 and would put the token into the Ingress, so the chart puts `/health` behind the
controller's basic auth instead: user `monitor`, password `HEALTH_CHECK_TOKEN`, from the Secret
`examleaf-health-auth`. Anyone else gets 401. Make the Secret before the release: without it ingress-nginx denies
the path, so that nobody gets through (its documented behaviour; the kind run always had the Secret). `/health` must
never fall through to the website: the website's server passes Django's paths on to Django (its development proxy),
and the health pages would be open. The uptime monitor uses basic auth instead of the header (UptimeRobot,
Better Stack, Uptime Kuma and Pingdom all can):

```sh
curl -s -u "monitor:$HEALTH_CHECK_TOKEN" -H 'Accept: application/json' https://examleaf.in/health/
```

Inside the cluster nothing changes: the kubelet asks `/health/web/` directly for web's readiness, with the site's host
and `X-Forwarded-Proto: https` as the compose health check does; it needs no token, and putting the token into the
probe would copy the secret into the Deployment.

`/health/`'s Celery check stops at the first worker that answers its ping, and when that is the media worker it
reports "No worker for Celery task queue celery" although the worker runs (DEPLOYMENT.md section 7: look again); on
kind that was four asks of six. An uptime monitor should alert only after two failures in a row.
`cronJobs.healthCheck` (off by default) does not rely on it: on its schedule it runs `manage.py health_check
health_web` against the web Service (database, cache, storage), then asks the workers which queues they consume, and
fails unless the default queue (and, with the media worker on, the media queue) has a worker; `kubectl get jobs` (or
kube-state-metrics) shows a failed run.

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

**What differs from backup.sh.** The plugin has no counterpart to `BACKUP_AGE_RECIPIENT`: its files are encrypted at
rest by R2, not by an age key that the server never holds, so whoever has the bucket's keys can read them. Keep those
keys to the plugin (they are in a Secret of their own, which no pod of the site mounts). For an age-encrypted copy
off the cluster, as backup.sh made, a dump can be streamed to a computer that has `age`:

```sh
kubectl -n examleaf exec examleaf-db-1 -c postgres -- pg_dump --format custom examleaf \
  | age --recipient age1… > examleaf-$(date +%Y%m%d-%H%M%S).dump.age
```

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

The operators and the controller add about 0.3 CPU and 0.6 GiB (ingress-nginx, cert-manager, CloudNativePG and the
plugin; on kind they used 164 MiB together), and the cluster itself (k3s, or a managed control plane elsewhere) about
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
| `erp.host`, `erp.allowlist` | the Ingress `examleaf-erp` for `erp.examleaf.in`: its certificate, bodies up to 50 MB, HSTS, nosniff, Referrer-Policy and X-Frame-Options set by the controller, an optional allowlist |
| NetworkPolicies | ERPNext's pods open to each other within the namespace (its Jobs' pods carry no labels to select them by), its nginx to the controller, its Valkey and MariaDB to the namespace and to mariadb-operator, the web Service to its webhooks |

The `erpnext` values cover the chart's gaps: the custom image, the external MariaDB (the chart's own `mariadb-sts`
would start MariaDB 10.6, past its end of life, and its Bitnami subchart is frozen on `bitnamilegacy`), requests and
limits for every component (the chart sets none), HTTP probes on `/api/method/ping` (the chart's only check ports),
the gunicorn autoscaler kept off (it targets `apps/v2`, which does not exist), and the sites volume ReadWriteOnce for
one node.

### Before switching it on

1. **mariadb-operator** 26.10 ("Operators first") and the controller's `global-allowed-response-headers` ("The ingress
   controller").
2. **The image** `ghcr.io/examleaf/erp:<tag>`, built with frappe_docker v4.0.0 in `examleaf-erp/image`
   (`FRAPPE_BRANCH=v16.50.0`, `apps.json` as a BuildKit secret), and its pull secret `ghcr-pull` in the namespace
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
answers 400; the website's health check had exactly that fault (TESTING.md section 6).

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
section 7: rendered and validated against the API server, not run).

## Differences from docker-compose

- **TLS and the edge.** cert-manager and ingress-nginx in place of Caddy. The controller's own HSTS is off and it
  neither adds nor removes the applications' headers (Django's and Next's are what the browser gets); it redirects
  http to https with 308, as Caddy did. There is no `Server` header, as with Caddy. It does not serve HTTP/3 (Caddy
  answered on 443/udp).
- **The health gate** is basic auth with `HEALTH_CHECK_TOKEN` as the password and answers 401, where Caddy wanted the
  `X-Health-Token` header and answered 404 ("Health checks" above).
- **Request IDs.** ingress-nginx sends its own `X-Request-ID` unless the client sent one, which it passes on; Caddy
  always made a new one. A client's own ID therefore reaches the controller's access log as it was sent, while
  Django, which takes only a UUID, logs one of its own for such a request.
- **Limits** are per Ingress (`proxy-body-size`) and per controller (the header timeout); nginx's body timeout is
  60 seconds between two reads rather than Caddy's five minutes for the whole body.
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
