# The chart on kind: what was run and what it showed

One run on 9 October 2026, 03:00–04:15 UTC, on a MacBook (Apple silicon) whose Docker is a Colima VM of 4 CPUs,
6 GiB of memory and a 60 GiB disk (Docker 29.2.1, kind 0.32.0, Helm 4.2.2, kubectl 1.32.2). The first install ran
images built at 6bcc174 (the integration branch then) with the chart's first commit; what it found (section 6) was
fixed, and every later step ran images rebuilt at 3685d9c (the platform at 62cf68e, the frontend fix, the chart's
fixes). Everything was run from `deploy/kubernetes/`. Secrets were made with random values by `make kind-secrets` and
are not shown. The cluster, the images and the build cache were deleted at the end.

kubectl 1.32 talks to a 1.35 server here, three minor versions apart (it warns); every command below worked.

## 1. Images

```sh
make images TAG=6bcc174 DOMAIN=examleaf.localhost    # the first install
make images TAG=3685d9c DOMAIN=examleaf.localhost    # after the fixes (the web image from cache but its last two steps)
```

Both Dockerfiles built unchanged: `examleaf-web:3685d9c` (1.51 GB; 373 MB as kind stores it) and
`examleaf-frontend:3685d9c` (333 MB; 86 MB), the frontend built for `https://examleaf.localhost`. From a cold cache the
web image took about 3 minutes (apt 80 s, pip 80 s, collectstatic 13 s) and the frontend about 3 minutes (npm ci 30 s,
the Next build the rest).

## 2. The cluster and the operators

```sh
make kind-up                           # 03:18:56 → 03:21:46
```

One node, `kindest/node:v1.35.5`, ports 80 and 443 of the Mac forwarded to it. Installed from their release manifests:
ingress-nginx controller v1.15.1 (with `hsts=false`, `use-gzip=true`, `client-header-timeout=10` patched into its
ConfigMap), cert-manager v1.21.2, CloudNativePG 1.30.1, the Barman Cloud plugin v0.15.1, then `kind-extras.yaml`
(a self-signed ClusterIssuer, and RustFS 1.0.1 in the namespace `s3` standing in for R2).

```sh
make kind-secrets                      # examleaf-env, examleaf-health-auth, examleaf-backup (and rustfs-root)
make kind-load TAG=6bcc174             # 34 s
make kind-install TAG=6bcc174          # helm upgrade --install … -f values-kind.yaml --wait: 03:24:30 → 03:27:09
```

The start, as the pods showed it: the frontend and the admin stand-in ready within 7 seconds; CloudNativePG's initdb
Job, then the instance (its Barman Cloud sidecar image pulled in 27 s) healthy at 03:26:05; web's init container
printing `waiting for the database` until then, then running every migration and `bootstrap_roles`
(`STUDENT: 0 permissions … ADMIN: 351 permissions`); gunicorn ready on `/health/web/` at 03:26:25; worker, beat and
the media worker out of their wait at 03:27:07–11. The ScheduledBackup's immediate base backup ran from 03:26:14 to
03:27:17 and completed.

```
cluster.postgresql.cnpg.io/examleaf-db   1   1   Cluster in healthy state   examleaf-db-1
backup.postgresql.cnpg.io/examleaf-db-daily-20261009032442   examleaf-db   plugin   completed
Initialized=True ConsistentSystemID=True Ready=True ContinuousArchiving=True LastBackupSucceeded=True
poddisruptionbudget.policy/examleaf-beat         N/A   0   0
poddisruptionbudget.policy/examleaf-db-primary   1     N/A 0
```

## 3. Through the ingress, from the Mac

`curl -sk --resolve examleaf.localhost:443:127.0.0.1 …` (the certificate is the self-signed issuer's):

| Request | Answer |
|---|---|
| `https://examleaf.localhost/` | 200, 71.7 kB (the website's home page, with Django's data) |
| `/shop/` | 200 |
| `/cart/` | 200 after the fix (a visitor's own page, as the log-in page is) |
| `/account/login/` | **503 "ExamLeaf cannot be reached just now"** on the first images, 200 after the fix (section 6) |
| `/account/` | 307 to `/account/login/?next=%2Faccount%2F` |
| `/api/v1/config/` | 200 from Django (JSON, gzip) |
| `/static/admin/css/base.css` | 200 from WhiteNoise |
| `/admin/` | 302 to `/admin/login/?next=/admin/` |
| `/health/`, `/health/web/`, `/health` without credentials, or with a wrong password | 401 `Basic realm="ExamLeaf health"` |
| `/health/` with `-u monitor:<HEALTH_CHECK_TOKEN>` | 200, `{"Database…": "OK", "Cache…": "OK", "Storage…": "OK", "Ping…": "OK"}` |
| `/healthz/`, `/no-such-page/` | 404 from the website |
| `http://examleaf.localhost/api/v1/config/` | 308 to `https://examleaf.localhost/api/v1/config` (slash lost), after the fix `…/config/` |
| `https://admin.examleaf.localhost/api/health/` | 200 (the website's image standing in for the admin panel) |
| `https://admin.examleaf.localhost/health/` | 401 |
| POST 9 MB to `/api/v1/contact/` | reaches Django (503: the contact form is not set up) |
| POST 11 MB to `/api/v1/contact/` | 413 from nginx |
| POST 11 MB to `/admin/learn/clip/add/` and `/admin/learn/revision/add/` | reaches Django (403, signed out) |

**Headers.** The website's answer carries Next's own headers (`strict-transport-security: max-age=31536000`,
`x-frame-options: DENY`, `x-content-type-options: nosniff`, `referrer-policy: same-origin`,
`cross-origin-opener-policy: same-origin`, `permissions-policy`, its CSP) and Django's answer Django's, with
`content-encoding: gzip` from the controller and no `Server` header at all, also on the controller's own 401 and 308.
With the controller's default `hsts: "true"` switched back on for a moment, Django's header became
`max-age=31536000; includeSubDomains`; with `hsts: "false"` it is Django's `max-age=31536000` again.

**Request IDs.** The controller's access log and Django's `X-Request-ID` answer carry the same 32-character ID
(`ec18de1aeb1133fe1e7f07eda38728d5`); a client's own `X-Request-ID: not-a-uuid` reached the access log as it was
and Django replaced it with its own.

**Client address.** The controller saw every request from 172.18.0.1, the kind network's gateway (Docker's port
forwarding), so Django counted all of them as one address: on a laptop that is expected; README.md "The ingress
controller" says what a real node needs.

## 4. Inside the cluster

```sh
kubectl -n examleaf exec deploy/examleaf-web -c web -- python manage.py migrate --noinput   # No migrations to apply.
kubectl -n examleaf exec deploy/examleaf-web -c web -- env DJANGO_SUPERUSER_EMAIL=admin@examleaf.localhost \
  DJANGO_SUPERUSER_FULL_NAME="Kind Test" DJANGO_SUPERUSER_PASSWORD=<random> python manage.py createsuperuser --noinput
kubectl -n examleaf exec deploy/examleaf-web -c web -- python manage.py check --deploy
```

`check --deploy` stopped at `mail.E001` (the console email backend, which values-kind.yaml leaves) and warned W005
and W021; with `EMAIL_BACKEND=anymail.backends.amazon_ses.EmailBackend` it gave W005 and W021 only and exited 0, as
DEPLOYMENT.md section 7 expects.

- **Celery.** `celery@examleaf-worker-… ready`, `media@examleaf-media-worker-… ready` (queue `media`), beat
  `scheduler -> django_celery_beat.schedulers.DatabaseScheduler`, `DatabaseScheduler: Schedule changed`.
  `celery inspect active_queues` listed the queues `celery` and `media`.
- **Read-only root filesystems.** In web, WeasyPrint drew a PDF with the rupee sign, Assamese and Hindi (7,069
  bytes in `/tmp`); in the media worker, FFmpeg made a two-second HLS stream in `/tmp`.
- **Redis.** The queue: `appendonly yes`, `maxmemory-policy noeviction`, its AOF files on the volume. The cache:
  `maxmemory 67108864` (values-kind.yaml's 64 MB), `allkeys-lru`, `save ""`.
- **NetworkPolicies** (kindnet enforces them), probed with a throwaway pod opening TCP connections:

  | From | web 8000 | frontend 3000 | redis-queue | redis-cache | PostgreSQL |
  |---|---|---|---|---|---|
  | a pod of the release with another component | blocked | blocked | blocked | blocked | blocked |
  | a pod labelled as the worker | blocked | blocked | open | open | open |
  | a pod in the namespace `default` | blocked | blocked | blocked | blocked | blocked |

- **The bucket** (listed with boto3 and the backup Secret's keys): `cnpg/examleaf-db/base/20261009T032614/` (the base
  backup) and the WAL under `cnpg/examleaf-db/wals/`.
- **Memory** (working sets, crictl): web 200 MiB (one gunicorn process), worker 169, beat 148, media worker 211,
  frontend 60, admin 50, PostgreSQL 119 and its sidecar 27, each Redis 4; the release about 1.0 GiB, everything in
  the node 1.8 GiB (kube-system 600 MiB, cert-manager, CloudNativePG, the plugin and the controller 164 MiB, RustFS
  64 MiB).

## 5. Changes on a running release

**Upgrade** to the fixed images and chart (`make kind-install TAG=3685d9c` again): about 30 seconds. Every Deployment
rolled one new pod at a time; beat's old pod was terminating, with no new one, until it was gone, and there was never
more than one beat pod. The Celery processes' waits passed at once (no new migration).

**The admin allowlist.** `--set admin.allowlist=203.0.113.0/24`: `admin.examleaf.localhost` answered 403 while the
main host answered 200; with `172.18.0.0/16` the admin host answered 200; with the allowlist removed, 200.

**Restore into a new cluster.** The superuser had been made at 03:30:41, after the base backup of 03:27:17, so it
could only come back through the WAL.

```sh
helm upgrade examleaf examleaf-platform -n examleaf -f examleaf-platform/values-kind.yaml --set image.tag=3685d9c \
  --set frontend.image.tag=3685d9c --set admin.image.tag=3685d9c \
  --set postgres.name=examleaf-db-restore --set postgres.recovery.enabled=true --set postgres.recovery.serverName=examleaf-db \
  --wait --timeout 15m                                                     # 03:55:03 → 03:56:25
```

The new Cluster recovered from the bucket (`examleaf-db-restore-1`, timeline 2, out of recovery), with
`admin@examleaf.localhost | 2026-10-09 03:30:41` and 174 migrations in it; every pod of the site restarted with
`DATABASE_URL` on `examleaf-db-restore-rw`, `/health/` answered OK, the new cluster took its own base backup and
archived under `cnpg/examleaf-db-restore/` beside the old one's files. The old Cluster stayed until
`kubectl delete cluster examleaf-db`.

**Eviction.** `kubectl drain … --pod-selector=app.kubernetes.io/component=beat --dry-run=server` was refused
(`Cannot evict pod as it would violate the pod's disruption budget`); the same for the worker was allowed.

**The shop's clean-up CronJob** (rendered with `beat.enabled=false`, applied, run once with
`kubectl create job --from=cronjob/examleaf-shop-clean-up`): completed.

**Uninstall.** `helm uninstall examleaf` removed the Deployments, Services and Ingresses and kept the Cluster
(still healthy), `examleaf-media` and `examleaf-redis-queue`.

## 6. What the run found, and what changed

1. **The website's account pages answered 503.** `src/proxy.ts` asks Django's `/health/web/` before a visitor's own
   page, with no forwarded headers; with `DEBUG=0` Django refused the internal host (`Invalid HTTP_HOST header:
   'examleaf-web:8000'`, 400) and the frontend took Django for down. The same happens under docker-compose
   (`web:8000`); development, CI and Playwright run with `DEBUG=1`, which allows local hosts. The health check now
   sends the forwarded headers every other server-side call sends (commit "Frontend: the proxy's health check names
   the site …"; Vitest 180 of 180, ESLint, Prettier and tsc clean, the new assertion fails against the old proxy).
2. **ingress-nginx's https redirect dropped a trailing slash**: `preserve-trailing-slash: "true"` on every Ingress.
   A change of that annotation alone does not reload ingress-nginx 1.15.1 (its comparison of the rewrite settings
   leaves the field out): on this already-running controller it took effect after `kubectl -n ingress-nginx rollout
   restart deployment ingress-nginx-controller`. A new install has it from the start.
3. **gunicorn 26 logged `Control server error: [Errno 30] Read-only file system: '/home/examleaf'`** at every
   start (its new control socket under `$HOME`; under compose the same call fails for want of the home directory):
   `--no-control-socket` in `GUNICORN_CMD_ARGS`.
4. **fontconfig had no writable cache** for the PDFs: `XDG_CACHE_HOME=/tmp/.cache`.
5. **Celery warned that it might run as root**: `runAsGroup: 1000` is not a group of examleaf-web's image (examleaf
   is 999). The pods now take each image's primary group (`uid=1000(examleaf) gid=999(examleaf) groups=999,1000`).
6. **The first wait for the migrations took two minutes** in worker and beat: a connection the starting database
   never answered held it for TCP's retries. Each attempt is now cut at 30 seconds.
7. **The smoke test failed three scheduled runs of three** with `No worker for Celery task queue celery` while both
   workers ran, and `/health/` said the same in four asks of six: the ping stops at the first answer (`limit=1` in
   `examleaf/urls.py`), and when that is the media worker's the default queue looks unserved (DEPLOYMENT.md section 7
   knows it). The CronJob now checks `/health/web/` and the workers' queues itself; its manual runs passed
   (`queues with a worker: ['celery', 'media']`).

## 7. ERPNext, checked without running it

The laptop had about 3 GB of memory to spare while other work ran, and ERPNext wants 6–8 GiB, so it stayed off. Its
part of the chart was rendered (`helm template … --set erpnext.enabled=true`: frappe/helm's seven Deployments, two
Valkey, the configure Job; this chart's MariaDB, PhysicalBackup, site-backup CronJob, header ConfigMap, Ingress and
NetworkPolicies; the probes on `/api/method/ping` with the site's Host and no `tcpSocket`) and sent to the API server
as a dry run after installing mariadb-operator 26.10.1's CRDs only:

```sh
kubectl apply --server-side -f https://github.com/mariadb-operator/mariadb-operator/releases/download/mariadb-operator-crds-26.10.1/crds.yaml
helm install erpcheck examleaf-platform -n examleaf --dry-run=server -f examleaf-platform/values-kind.yaml … \
  --set erpnext.enabled=true --set erpnext.image.tag=16.50.0-test --set erpnext.dbHost=erpcheck-erp-db …
```

It was accepted, ingress-nginx's admission webhook included. The default values with every optional part on
(autoscalers, the admin with an allowlist, beat off, the smoke test, backups to an R2 endpoint) were accepted the
same way. `helm template -s charts/erpnext/templates/job-migrate-site.yaml` and `-s …/job-create-site.yaml` rendered
the Jobs README.md applies (`bench new-site … --install-app=erpnext --install-app=india_compliance --install-app=hrms
--install-app=offsite_backups --install-app=examleaf_erp`, the passwords from `examleaf-erp`).

## 8. Not tested, and why

- **Let's Encrypt and real DNS**: kind has neither; the certificates came from the self-signed issuer through the same
  cert-manager annotations.
- **Cloudflare R2 itself**: RustFS stood in (the plugin's configuration differs only in the endpoint and keys); the
  checksum variables that R2 needs were set but could not be proven necessary or sufficient here.
- **ExternalSecret mode and the autoscalers' scaling**: no External Secrets Operator or metrics-server on kind; both
  were rendered, and the autoscalers passed the server dry run (the ExternalSecrets were only rendered).
- **ERPNext running** (section 7), mariadb-operator's backups, and the site-backup CronJob.
- **More than one node**: ReadWriteMany media, a database failover with `instances: 3`, a real drain with the
  maintenance window.
- **The visitor's address on a real node** (externalTrafficPolicy, the PROXY protocol, Cloudflare in front).
- **Email, SMS, Razorpay, Google sign-in, Turnstile, Sentry, the buckets for media**: no accounts on a laptop.
- **A clip through the admin** (the media worker was shown to run FFmpeg on a read-only root, not to process an
  upload), and `import_papers` (no checkout of the books here).
- **The admin panel**: its image does not exist yet; the website's image stood in.

## 9. Cleaning up

```sh
make kind-down                     # kind delete cluster --name examleaf-test; docker image prune -f
docker rmi examleaf-web:3685d9c examleaf-frontend:3685d9c examleaf-frontend-deps:test <kindest/node image>
docker builder prune -af           # 7.2 GB of this run's build cache
colima ssh -- sudo fstrim -av      # the VM's freed blocks back to the Mac: 2.8 GiB free before, 18 GiB after
```

Images that other work on this machine had pulled (`frappe/erpnext`, `mariadb`, `valkey`) were left alone.
