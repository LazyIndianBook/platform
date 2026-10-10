# Package P16: Deployment carried through Phase B (model: Claude Sonnet 5.5)

No servers needed; `helm` and `make lint` in `deploy/kubernetes/` are available. Read COMMON.md sections 1, 2, 6 and
7 first, then `examleaf-web/DEPLOYMENT.md` (the settings table and sections 21 to 25), `examleaf-web/RESILIENCE.md`
("What the Kubernetes chart must change"), `examleaf-web/docker-compose.yml`, `examleaf-web/Caddyfile`,
`examleaf-web/.env.example`, `deploy/kubernetes/README.md`, `values.yaml`, `values-ha.yaml`, `TESTING.md`, the chart's
templates for web, worker, beat, the ConfigMap and Secret, `examleaf-admin/Dockerfile` and `src/proxy.ts`,
`examleaf-frontend/src/lib/site.ts` (the Django prefixes the proxies know), `.github/workflows/ci.yml`. Your worktree
is a checkout of `phase-b` with every module merged.

The deliverable: every setting, path, task, file and check Phase B added reaches every deployment path, with nothing
undocumented and nothing that only works on a developer's machine.

1. **Settings**: diff `examleaf/settings.py`'s `env(` names against DEPLOYMENT.md's table, `.env.example`,
   `docker-compose.yml`'s environment and the chart's ConfigMap/Secret (the values' keys): every new name present in
   each with its default; secrets (tokens, keys, DSNs) in the Secret, the rest in the ConfigMap; the chart's
   `values.yaml` documents each under the right section; `values-ha.yaml` unchanged unless a setting is per replica.
2. **Paths**: every new Django path (`/api/hooks/support-mail/`, `/api/hooks/sms-events/`, `/api/v1/reports/`,
   `/api/v1/errata/`, `/api/v1/me/tickets/`, `/api/v1/me/nominee/`, the pages' versions, the returns, `/learn/`
   staff files, whatever else `git diff main..HEAD -- examleaf-web/examleaf/urls.py examleaf-web/api/urls.py` shows)
   known to the Caddyfile's Django matcher, the frontend's and the console's proxies (`site.ts`, `proxy.ts`) if
   they list prefixes, and the chart's ingress rules; the admin host rule (`STAFF_APIS` in `staff/middleware.py`)
   covering every staff prefix (a test exists: check it walks the new ones); body-size limits for the new uploads
   (return photos, ticket attachments, the dark-pattern certificate, the import CSVs) in Caddy and the ingress.
3. **Tasks**: every new `CELERY_BEAT_SCHEDULE` entry documented in `staff/README.md`'s jobs table or the app's
   README, its queue right (`media` for anything that renders or processes files), its time limit by kind
   (RESILIENCE.md), and the worker's `--queues` in compose and the chart covering any new queue.
4. **Files**: the private storage holds new files (return photos, attachments, result files, certificates, the
   plain book-code file): the storage settings, the bucket's lifecycle for `jobs/` (24 hours for the code file:
   check it is deleted by the purge task rather than relying on a lifecycle), the backup script's scope.
5. **Logs**: the Docker log caps P8 asked for (`logging: driver: json-file, options: max-size: 50m, max-file`) on
   every compose service, and the chart's equivalent note (node-level log rotation documented in README.md);
   `LOG_TIME_SOURCE` and the NTP note in the chart's README.
6. **CI**: `.github/workflows/ci.yml` writes the pip-audit and npm audit JSON the System page reads
   (`DEPENDENCY_REPORT_PATH`): add the steps that produce `dependency-report.json` as an artifact and the deploy
   note on copying it into the private storage; the console's `npm audit` job if missing; the frontend's.
7. **The chart**: `make lint` clean; the migrate Job runs the new migrations (nothing to do unless a data migration
   needs a setting: check the seeds of the HSN master, templates and historical rows for settings they read);
   a `values.yaml` comment per new setting; TESTING.md gains a "Phase B" note listing what a `kind` run should check
   next (do not run kind: the disk and memory are taken by other agents; say so).
8. **Compose**: `docker compose config` validates (run it with a throwaway `.env` made from `.env.example`); the
   `admin` profile unchanged unless a new environment variable reaches the console (`NEXT_PUBLIC_*`).
9. **The deploy checklist** in DEPLOYMENT.md: the first-deploy steps gain Phase B's (the HSN master seeded by
   migration: nothing; the templates registry seeded: nothing; the disclosures to fill in the panel; the connections
   page's credentials; the series prefixes from the CA before 1 April 2027; the support mail forwarder; the
   dependency report; the restore drill record; the dark-pattern audit before 1 January 2027).

Change no application code; if a setting is unread or misnamed, report it. Commit per concern with the
`Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` trailer. Your report: the table of settings and paths
checked (present where, added where), the chart and compose validation output, and anything the application must
change (file, line, what).
