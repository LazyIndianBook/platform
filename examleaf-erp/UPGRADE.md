# Upgrading ERPNext (the weekly patch, and a new app release)

Frappe tags a framework release every Tuesday and ERPNext follows within a day; most security fixes land in those
releases for v15 and v16 alike. GitHub listed 87 ERPNext and 53 Frappe advisories in 2026 by 9 October, 10 of them
critical (research-erpnext.md 6.6). So: patch every week, and within 7 days of a critical or high advisory.

Every version is pinned in three places, and an upgrade changes all three in one commit:

| What | Where |
|---|---|
| Frappe (also the tag of the `frappe/base` and `frappe/build` images) | `image/build.sh` `FRAPPE_BRANCH`, `ERP_VERSION`; `compose/dev.Containerfile` `FROM frappe/erpnext:<tag>` |
| ERPNext, India Compliance, HRMS, offsite_backups | `image/apps.json`; `compose/dev.Containerfile` (`INDIA_COMPLIANCE_REF`) |
| The app's lower bounds | `apps/examleaf_erp/pyproject.toml` `[tool.bench.frappe-dependencies]` |

## 1. Before anything: does the release exist everywhere?

- The ERPNext tag (`https://github.com/frappe/erpnext/releases`) and, for that framework version, **both**
  `frappe/base:<tag>` and `frappe/build:<tag>` on Docker Hub. `FRAPPE_BRANCH` is both the framework's git ref and the
  base/build image tag (frappe_docker's layered Containerfile), so a framework release without its images cannot be
  built: on 9 October 2026 `v16.50.0` existed, `v16.51.0` (framework only) did not. `image/build.sh` checks this first
  and stops.
- India Compliance's matching release (`https://github.com/resilient-tech/india-compliance/releases`): its
  `check_version_compatibility` patch refuses to migrate against a framework it does not support.
- HRMS's tag of the same number. offsite_backups has no tags: `build.sh` records the `version-16` commit it built in
  the image label `org.examleaf.offsite_backups` and in the cache key.
- Read the release notes for anything under "breaking" and for removed or renamed fields this app touches
  (`grep -rn` the field names of `fixtures/01_custom_field.json` and `api.py`).

## 2. Build and test

```sh
# bump the pins (above), then
cd examleaf-erp/compose && ./dev.sh down && docker compose --env-file .env build && ./dev.sh up --minimal
./dev.sh bench --site erp.localhost migrate     # the dev site, as production will
./dev.sh test                                  # the app's tests on the new versions
git commit -am "ERPNext v16.x.y, India Compliance v16.x.y: <what the release notes said>"
git tag erp-v16.x.y-1 && git push --tags       # CI: lint, tests on MariaDB 11.8, build, Trivy, push
```

The image is `ghcr.io/examleaf/erp:<erpnext version>-<commit>`, the tag `image/build.sh` prints.

## 3. Roll out (the Helm chart, research 3.3)

1. **Backup**: run the chart's `backup` Job (`bench --site <site> backup --with-files`) and check the files reached R2.
   Keep `site_config.json` with them: its `encryption_key` decrypts every stored password.
2. **New tag**: set `image.tag` to the new tag and `helm upgrade`. The pods roll; nothing migrates yet.
3. **Migrate Job**: the chart's `migrate` Job (maintenance mode on, `bench --site <site> migrate`, off). With
   `allow_reads_during_maintenance: 1` in the site config, staff can still read during it. `migrate` imports every
   fixture again and runs `examleaf_erp.setup.after_sync` (trees rebuilt, EL Sync's permissions, webhooks from the site
   config, Mode of Payment accounts).
4. **Clear cache Job**: the chart's `clearCache` Job (after the gunicorn rollout).
5. Smoke test: `POST /api/method/examleaf_erp.api.ping` with the sync user's token answers the new versions; open one
   invoice's print preview.

To roll back: the previous tag, then the backup's restore if the migrate changed the schema (a patch release rarely
does; read the Job's log).

## A new app (or a new examleaf_erp release only)

The same pipeline; an app that is not installed yet also needs, after step 3, a `custom` Job running
`bench --site <site> install-app <app>`, then the `migrate` and `clearCache` Jobs again. Apps must be baked into the
image: a running pod cannot `bench get-app` (research 3.3).

## A major (v17)

Not a weekly patch: one major at a time, after a full rehearsal on a restored copy of production, with the
reconciliation (`daily_totals` against the platform) compared before and after. v17 is also when PostgreSQL may be
looked at again (research 2.5).
