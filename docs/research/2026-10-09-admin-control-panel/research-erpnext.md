# ERPNext as ExamLeaf's back office: versions, the database question, Kubernetes, apps, integration, operations, costs

Researched 9 Oct 2026 from primary sources: GitHub repositories, releases and CI files read through the GitHub API, docs.frappe.io, the Frappe forum (Discourse JSON, with each author's staff flag), and docs.indiacompliance.app. Citations [n] point to sources-erpnext.md. "Official" means Frappe's or the app publisher's own docs, code, CI or a post by a Frappe staff account. "Forum" or "community" means anyone else. Statements labelled *estimate* are mine.

## 0. Key findings

1. **Current stable release is v16.** Frappe v16.51.0 shipped 7 Oct 2026 and ERPNext v16.50.0 on 6 Oct 2026. v15 is still patched (v15.122.0). v16.0.0 came out on 12 Jan 2026 [1][2]. Planned end of life: v15 at end-2027, v16 at end-2029. v14 ended on 31 Jan 2026 [3]. Frappe tags a minor release every Tuesday, and ERPNext usually follows within a day [1][2]. v17 exists only as `develop` and has no release date.
2. **ERPNext cannot use PostgreSQL in production today. It needs MariaDB.** On 4 Jul 2026 a Frappe maintainer closed a v16 Postgres bug report, replying that v16 does not support Postgres and that support exists only on `develop` [19] (quoted in §2.1). The official Helm chart's README also says ERPNext requires MariaDB [17].
   - In June 2026 Frappe made ERPNext's `develop` branch pass its server test suite on both MariaDB and Postgres [24]. India Compliance followed in July 2026 [28].
   - Transaction isolation is still open (Aug–Sep 2026) [18][27].
   - The Postgres CI runs only nightly or on labelled pull requests [25][26]. HRMS, CRM, Helpdesk, LMS, Insights, Payments and Print Designer have no Postgres CI at all [11].
   - **So the owner's "same Postgres engine" cannot be met on a supported release in 2026.** Run ERPNext v16 on MariaDB 11.8, keep Django on PostgreSQL 17, and look again when v17 ships.
3. **Even on Postgres, Frappe would not share Django's database.** It creates its own database and role for each site, using root credentials [32]. "Same engine" could at most mean the same server, and that would tie the ERP's migrations and backups to the shop's database.
4. **The Kubernetes chart exists and is current, but it is thin.** It is `frappe/helm` erpnext chart 8.0.84 (6 Oct 2026, appVersion v16.50.0) [33][34]. It deploys nginx, gunicorn, three worker queues, the scheduler, socketio and two Valkey instances. No database is deployed unless you enable one [17]. Gaps:
   - the built-in MariaDB image defaults to 10.6, which reached end of life on 6 Jul 2026 [33][38];
   - the backup Job only runs `bench backup` on the volume (offsite push was removed in 2023), and there is no CronJob [36];
   - the gunicorn HPA points at `apps/v2`, which looks like a bug [36];
   - there are no resource requests, and the probes only check open ports [33];
   - the Bitnami subcharts are frozen on `bitnamilegacy` images [37].
5. **Image building changed this year.** `frappe_docker` v4.0.0 (3 Oct 2026) builds custom images from `apps.json` passed as a BuildKit secret. The old `APPS_JSON_BASE64` build-arg was removed on 15 Apr 2026 for security reasons [43][44][45]. On Docker Hub, `frappe/erpnext:latest` is `develop`, so always pin a tag [49].
6. **Simplest working setup.** Frappe calls `frappe_docker` Compose its canonical production method [53]. If Kubernetes is a hard requirement, use a single-node k3s cluster with:
   - local-path (RWO) storage, which the chart allows on one node [17][55];
   - MariaDB 11.8, either as the chart's built-in StatefulSet or through mariadb-operator;
   - a CronJob that runs `bench backup` and copies the files to R2.
   Size the node at 4 vCPU / 8 GB as a floor and 8 vCPU / 16 GB to be comfortable (*estimate*, §3.6).
7. **Apps ("all its extensions").**
   - Install: `india_compliance` (GPLv3, v16.10.0) and `offsite_backups` (MIT; S3 backups moved here in v16).
   - Optional: `hrms` (GPLv3), `insights` (AGPL; it can also query Django's Postgres), `helpdesk`, `crm`.
   - Skip: LMS (it duplicates our own course), Education (built for running a school), Webshop (we already have a shop), Payments (Razorpay stays in Django), Print Designer (not offered for v16 on the Marketplace), Drive (archived), Books (end of life), Raven, Gameplan, Builder and Changemakers.
   - Shiprocket: there is no official connector, so keep shipping in Django (§4.2).
8. **India Compliance covers our GST needs.** GST masters, e-invoice (B2B only), e-way bill, GSTR-1 filing over the API, 2A/2B reconciliation, IMS, TDS and the MCA audit trail.
   - API credits cost ₹0.50 each for the first 10,000, ₹0.40 for the next 40,000 and ₹0.30 beyond, plus GST. The minimum purchase is 1,000 a year [61].
   - Credits are free on Frappe Cloud [60].
   - Every API call goes through Resilient Tech's server `asp.resilient.tech` [63].
9. **Licences.** Running a private custom app in-house does not oblige us to publish its source, because GPL duties start on distribution [12]. AGPL only matters if we modify an AGPL app (Helpdesk, CRM, Insights) and let outside users reach it.
10. **Integration needs our own reliability layer.**
   - Frappe gives REST (`/api/resource`, `/api/v2/document`), per-user API tokens, a time-based site rate limit (HTTP 429), and `insert_many` of up to 200 documents per call [90][91][92].
   - Webhooks fire after commit and carry an HMAC header, but each event gets only 3 attempts [93].
   - Design: a Django outbox calls our own custom-app endpoints with an idempotency key. They create invoices with `set_name`, so ERPNext's names equal Django's legal numbers. `EL/2026-27/00001` passes both Frappe's and India Compliance's checks [63][100].
11. **Patch every week.** So far in 2026 GitHub lists 87 ERPNext advisories (8 critical) and 53 Frappe advisories (2 critical) [108][109].
    - Keep ERPNext staff-only behind SSO, with no public portal.
    - Require 2FA by role.
    - Turn off email-link login, which is on by default.
    - Cut the 170-hour default session [99].
12. **Costs.**
    - Frappe Cloud runs custom apps only on private benches, which need a site plan of $25 (₹2,050) a month or more [114][127]. The ₹4,100 plan adds SSH and database access and Product Warranty. A dedicated AWS Mumbai server with 2 vCPU / 4 GB costs ₹10,000/month [115].
    - Self-hosting means one node (e.g. DigitalOcean 8 vCPU / 16 GiB at $96/month [118]), R2 storage, India Compliance credits and our own operations time.

---

## 1. Versions, support, requirements, licences

### 1.1 Releases and branches (official, read 9 Oct 2026) [1][2][3]
| | Frappe Framework | ERPNext |
|---|---|---|
| Latest v16 | v16.51.0 (7 Oct 2026) | v16.50.0 (6 Oct 2026) |
| Latest v15 | v15.122.0 (6 Oct 2026) | v15.122.0 (7 Oct 2026) |
| v16.0.0 | 12 Jan 2026 (beta 17 Nov 2025, RC 23 Dec 2025) | same |
| v15.0.0 / v14.0.0 | 20 Oct 2023 / 1 Aug 2022 | same |
| Branches | `version-15`, `version-16` and their `-hotfix` branches; `develop` (future v17); no `version-17` | same |

- **Cadence.**
  - Frappe tags a minor release every Tuesday on both lines (1 Sep to 6 Oct 2026 were all Tuesdays) and adds hotfix point releases in between [1].
  - ERPNext releases weekly too, mostly on Tuesday or Wednesday [2].
  - Majors so far were 14 and 27 months apart.
- **v16 schedule.** The final release was first set for 6 Dec 2025 and slipped to 12 Jan 2026, to allow for UI polish and a security audit (Frappe staff, forum [8]).
- **Support window.** Frappe supports two majors at a time, about 2.5–3 years each. v14 ended on 31 Jan 2026; v15 is planned to end at end-2027 and v16 at end-2029 (wiki edited 19 Jan 2026 [3]). Fixes go to `develop` first and are then backported [3].
- **Upgrade path.**
  - Go one major at a time (switch branches, then `bench migrate`).
  - On Frappe Cloud a major upgrade must be started by hand (staff, 31 Dec 2025 [10]).
  - v16 changes that affect custom apps [9]:
    - Python 3.14 and Node 24;
    - Desk moved from `/app` to `/desk`;
    - document hooks can no longer call `frappe.db.commit()`;
    - `has_permission` hooks must return `True`;
    - lists sort by `creation` by default;
    - `get_all`/`get_list` run on the new query builder;
    - logout, upload and send-login-link calls must be POST;
    - S3, Dropbox and Google Drive backups moved to the `offsite_backups` app.
  - **ExamLeaf starts fresh, so begin on v16 and skip v15.**

### 1.2 Runtime requirements (official) [4][5][6][7]
| | v15 | v16 / develop |
|---|---|---|
| Python | ≥3.10 <3.15 (pyproject) | **3.14 only** (`>=3.14,<3.15`) |
| Node | 18+ | **24** |
| MariaDB | 10.6.6+ | **11.8** per the docs. The code warns below 10.6 and above 11.8 [7] |
| Redis / Valkey | 6 | 6+ |
| Other | Yarn 1.12+, wkhtmltopdf 0.12.6 (patched Qt) | Yarn 1.22+, pip 25.3+. Debian 13 or Ubuntu 24.04+ for bare-metal installs. v16 adds a Chrome-based PDF renderer [8] |
| ERPNext pins | `frappe >=15.111,<16` | `frappe >=16.50.0,<17.0.0` [6] |

MariaDB end-of-life dates (endoflife.date, secondary [38]):
- 10.6: 6 Jul 2026 (already past);
- 11.8 LTS: 4 Jun 2028;
- 12.3 LTS: 12 Jun 2029.

v16 is supported until end-2029, so one MariaDB major upgrade will fall inside its life.

### 1.3 Licences (GitHub metadata [11]; licence files checked where GitHub shows "NOASSERTION")
| Licence | Apps |
|---|---|
| MIT | frappe, payments, builder, wiki, offsite_backups, erpnext-shipping, blog, helm chart, frappe_docker, frappe_whatsapp (community), bwh_shipping (community) |
| GPL-3.0 | **erpnext, india_compliance, hrms**, education (licence file says GPL v3), webshop, ecommerce_integrations, lending, bench |
| AGPL-3.0 | crm, helpdesk, lms, insights, print_designer, raven, gameplan, drive (archived), books, press, telephony, suite, changemakers |

What this means for us (paraphrased, not legal advice):
- **GPL.** You may modify GPL software and run it inside your own organisation without releasing anything. Copies made within one company are not "distribution". Handing copies to contractors for off-site use is. A plug-in that dynamically links and shares data structures counts as part of the combined work (FSF GPL FAQ [12]).
  - A private custom app that imports ERPNext and runs only on our servers therefore owes nothing.
  - If we ever ship it to a third party (a reseller, another company), it must go out under GPLv3.
- **What Frappe people have said.** In 2016 Rushabh Mehta (Frappe's CEO) said he was unsure the GPL applies if the code is not distributed, called apps and plugins a grey area, and suggested keeping specific code in a separate app that is not redistributed (forum, 5 Nov 2016 [13]). A 2021 forum moderator noted that closed derived work is possible on Frappe (MIT) but not on ERPNext (GPL) [14].
- **Trademark.** Frappe's 13 Apr 2021 legal post says "Frappe" and "ERPNext" are registered trademarks, and using the ERPNext name or logo in a product or company name needs permission [15]. Our app should be called `examleaf_erp`, not "ERPNext-something".
- **AGPL apps.** Using them unmodified is fine. If we modify an AGPL app and outside users reach it over the network (for example Helpdesk's customer portal), we must offer those users the modified source [12].

---

## 2. The database engine: the facts

### 2.1 Official positions, newest first
| Date | Who | Where | What they said |
|---|---|---|---|
| 29 Sep 2026 | Frappe PR #43542, closed without merging | GitHub [27] | The PR would have switched Postgres to READ COMMITTED to match production MariaDB's locking behaviour. It was not merged, so isolation is still open on `develop` |
| 6 Aug 2026 | Mihir Kandoi (Frappe Team) | forum [18] | Apart from transaction isolation the work is essentially done, but Frappe cannot commit to a date |
| 4 Jul 2026 | Mihir Kandoi (collaborator) | GitHub #56865 [19] | **"Postgres is not supported on v16. Develop only for now."** He closed a bug about six v16 sales reports failing on Postgres |
| 2 Jul 2026 | Mihir Kandoi | forum [22] | Says he made many framework changes so ERPNext could run on Postgres and considers the work nearly finished. In the same thread a user summed up: framework support is experimental, ERPNext support exists only on develop, and CRM/HRMS/Helpdesk have none |
| 29 Jun 2026 | Mihir Kandoi | forum [18] | Not in v16; only develop/nightly |
| 21 Jun 2026 | Mihir Kandoi | GitHub #24389 / #56241 [23][24] | Closed the 2021 Postgres-support issue (opened by Rushabh Mehta) as completed once the server suite passed on both engines |
| 7 May 2026 | Revant Nandgaonkar (staff; maintains frappe_docker and helm) | forum [20] | The Postgres override exists only because the framework supports Postgres. No open-source app runs Frappe on Postgres with daily CI. MariaDB bugs get fixed quickly; Postgres users are on their own |
| 10 Mar 2026 | Aarol D'Souza (forum account without a staff flag; he authors Frappe's multi-DB PRs) | forum [21] | Postgres support is experimental and not planned for v15 or v16, though multi-DB issues are being fixed |
| Docs (no date) | docs.frappe.io | [16] | The Postgres page is three lines: the `bench new-site --db-type postgres` command and a note to install Postgres 9 or later. It says nothing about ERPNext |
| Chart README (2026) | frappe/helm | [17] | ERPNext requires MariaDB; PostgreSQL is for custom Frappe apps that support it |
| Older history | staff (2022), moderator (Jul 2025) | forum [30][29][32] | 2022: beta in the framework, in progress for ERPNext. As of Mar 2025: maintainers had dropped the effort. From Jan 2026: Frappe developers resumed multi-DB fixes [21][23]; the main push came in June 2026 [24] |

### 2.2 What changed in 2026 (official GitHub)
- **ERPNext `develop`, June 2026** [24]:
  - about 60 merged PRs;
  - an audit of about 4,200 queries;
  - the full server suite passes on both engines from one codebase;
  - the rule was that MariaDB output must not change.
  - The CI (`server-tests-postgres.yml`) runs nightly at 03:00 IST and on PRs labelled `postgres`, not on every PR [25]. `version-16` still has an old, label-only Postgres job on `postgres:13.3`, untouched since Dec 2025 [25].
- **Frappe `develop`.** The server-test matrix adds `postgres:18.0` only for PRs labelled `postgres`; MariaDB 11.8 always runs [26]. Many Postgres fixes landed on `develop` on 29–30 Sep 2026: savepoints after caught errors, index names, COPY bulk insert, scoping the site role to its own database [27].
- **India Compliance `develop`.** PR #4481 (merged 23 Jul 2026) added a Postgres CI (label-gated and nightly), a static checker and query fixes. Its follow-ups are still open: about 10 `UPDATE…JOIN` statements in patches and savepoint handling in one patch. The `version-15` and `version-16` branches have no Postgres CI [28].
- **Community.** `frappe_pg`, a monkey-patch app (Dec 2025) [31]. A third-party developer image `vyogo/erpnext:sne-postgres-develop` on PostgreSQL 15 (Aug 2026) [120]. Neither is fit for production.

### 2.3 What breaks on Postgres (from the June 2026 audit [24] and the v16 bug report [19])
- **Loose `GROUP BY`.** MariaDB accepts non-grouped columns; Postgres rejects them.
- **MySQL-only functions.** `IF()`, `TIMESTAMP()`, `TIMEDIFF()`, `DATEDIFF()`, `STR_TO_DATE`, and `UPDATE … JOIN`.
- **Quoting.** Single-quoted aliases (`as 'x'`); `HAVING` that refers to a select alias; `DISTINCT … ORDER BY` on a column not in the select list.
- **Types and comparisons.** Integer division truncates on Postgres. Postgres will not coerce `varchar` to numbers or booleans. Text comparisons are case-sensitive. `''` and `NULL` differ. NULLs sort last.
- **Transactions.** A failed statement aborts the whole Postgres transaction (`InFailedSqlTransaction`), so catch-and-continue code breaks.
- **Report JSON** whose `order_by` names a column the query does not select.
- **What the framework already translates.** `ifnull→coalesce`, `locate→strpos`, `REGEXP→~*` and backticks to double quotes. `frappe.qb` (PyPika) builds engine-neutral SQL, so code written with qb or the ORM mostly ports; raw `frappe.db.sql` and SQL Query Reports are what break. India Compliance has no SQL query reports and only 8 raw `frappe.db.sql` calls [28].
- **Affected in v16 (Jul 2026)** [19]: Inactive Customers, Sales Partners Commission, Available Stock for Packing Items, Pending SO Items for Purchase Request, Sales Funnel, Sales Person-wise Transaction Summary.

### 2.4 Postgres status by app (CI files read 9 Oct 2026 [11][25][26][28])
| App | Postgres status |
|---|---|
| frappe | experimental; tested only on labelled PRs on `develop` (Postgres 18) |
| erpnext | v15/v16: not supported [19]. `develop`: suite passes; CI nightly and label-gated |
| india_compliance | `develop` only (since 23 Jul 2026) |
| hrms, crm, helpdesk, lms, insights, payments, print_designer, webshop, education | **no Postgres CI at all** |

### 2.5 Conclusion on "same Postgres engine"
- **Not possible on a supported ERPNext in 2026.** The options:
  1. **Recommended: ERPNext v16 on MariaDB 11.8.**
     - Keep Django on PostgreSQL 17.
     - For reports across both systems, use Insights, which can connect to PostgreSQL as an extra data source [73], or a nightly ETL into a read replica.
  2. **Wait for v17.**
     - It has no date; majors come every 14–27 months, and one forum member guessed winter 2026 to summer 2027 [18].
     - Even then: isolation is still open, the Postgres CI is not run on every PR, and HRMS/Helpdesk/CRM are untested on Postgres.
     - Postgres would also be a separate database and role on the cluster [32].
     - The tested versions are Postgres 18 (framework CI) and Postgres 15 (frappe_docker and chart defaults) [26][51][33], not our 17.
  3. **Run `develop` on Postgres now: rejected.** It has no releases, changes weekly, and no Frappe support.
  4. **Community forks: rejected** [29][31].
- **Migration later is possible.** Moving MariaDB → Postgres at v17 would mean dump, convert and restore. That is not a supported, tested path, so plan it as its own project with a full reconciliation run (*estimate*).

### 2.6 MariaDB on Kubernetes: options
| Option | What you get | Verdict |
|---|---|---|
| Chart built-in `mariadb-sts` (since chart 8.0.0, 3 Dec 2025) [35] | One StatefulSet on the official `mariadb` image with your `my.cnf`. **The default tag is `10.6` (end of life 6 Jul 2026); set `11.8`.** No backups and no metrics | Smallest. Enough if `bench backup` to R2 every few hours meets the RPO |
| **mariadb-operator** 26.10.1 (21 Sep 2026, MIT) [39] | Standalone, replication or Galera; physical backups (mariadb-backup) to S3/R2 on a schedule; PITR from archived binlogs; ServiceMonitor; declarative users and grants. Supports MariaDB ≥10.6 on Kubernetes ≥1.31 | Best if we want point-in-time recovery or a replica. Use `standalone` or async replication, not Galera, at our size |
| Bitnami subchart (legacy) | Pinned to `bitnamilegacy/mariadb:10.6.17`, an image that gets no more updates (Bitnami moved free images to "legacy" from 28 Aug 2025 [37]) | Do not use |
| Managed (AWS RDS for MariaDB) | Supports 11.8 (Aug 2025 [42]). The chart has `dbHost`, `dbRds` and `dbExistingSecret` [33]. The Frappe wiki's RDS page is from 2019 (MariaDB 10.3 parameters) [41] | Good but costly; data in ap-south-1 |
| Self-hosted MariaDB VM outside the cluster | The chart README's second choice after a managed database. Frappe's wiki has the steps: block volume at `/var/lib/mysql`, unattended upgrades, `bind-address` plus a firewall [17][121] | Fine if the cluster stays app-only |
| Percona operators | They run MySQL, PXC or MongoDB, not MariaDB. Frappe tests only MariaDB | Not applicable |

- **Settings.** Use `utf8mb4` / `utf8mb4_unicode_ci` and `skip-character-set-client-handshake`, as frappe_docker's 11.8 Compose does [51]. Frappe's production template [40] adds:
  - `innodb-buffer-pool-size` at about 60% of RAM;
  - `innodb-flush-log-at-trx-commit=1`;
  - `O_DIRECT`;
  - the slow query log;
  - binlog with 14-day expiry;
  - `max-allowed-packet` 256M–512M.
- **Official sizing advice** [40]:
  - put the database on its own server (the chart's StatefulSet, operator or RDS);
  - start at 2 vCPU and 8 GB RAM, 50 GB disk and about 3× the data size, 2,000–3,000 IOPS;
  - scale up vertically before adding a read replica (Frappe can send reads to a replica).
- **For a small publisher** (*estimate*): the database will likely stay under 5 GB for years. A 2–3 GB buffer pool with 4 GB for the pod is enough to start, below the official 8 GB guidance. Watch the buffer-pool hit ratio, which should stay above 99%.

---

## 3. Kubernetes packaging

### 3.1 `frappe/helm` → chart `erpnext` 8.0.84 (6 Oct 2026, appVersion v16.50.0) [33][34]
- **Scope.** The chart says it tracks the latest stable ERPNext branch.
  - Chart 7.x covered v15 (20 Oct 2023 – 2 Dec 2025).
  - Chart 8.0.0 (3 Dec 2025, still on v15.91.0) introduced the built-in components.
  - Chart 8.0.15 (13 Jan 2026) was the first on v16. Chart 8.0.14 (8 Jan 2026, v15.94.1) is the last that ships v15 [34].
- **What it deploys** [17][36]:
  - Deployments: `nginx` (static assets and proxy, port 8080), `gunicorn` (8000), `worker-default`, `worker-short`, `worker-long`, `scheduler`, `socketio` (9000);
  - optional HPAs for each Deployment;
  - an Ingress or Gateway API `HTTPRoute`;
  - a ConfigMap for nginx;
  - PVCs `erpnext` (sites, **8Gi ReadWriteMany** by default) and `erpnext-logs` (off by default);
  - a Secret for an external database password;
  - a ServiceAccount.
- **Cache and queue.** Valkey 7.2 for both by default (official `valkey-io` chart 0.9.3). Dragonfly or Bitnami Redis are alternatives, or point `externalRedis.cache/queue` at your own [33].
- **Database.** Not deployed by default. Choices: `mariadb-sts`, `postgresql-sts` (postgres:15), the legacy subcharts, or `dbHost`/`dbPort`/`dbRootUser`/`dbExistingSecret` (with `dbRds`) for an external database [17][33].
- **Jobs.** You generate them with `helm template … -s templates/job-*.yaml | kubectl apply`; each Job name carries a timestamp, so they fit GitOps [17].
  - `configure` (bench-conf, on by default): writes the database and Redis hosts into `common_site_config.json`;
  - `volumePermissions`;
  - `createSite` / `createMultipleSites` (with `installApps`, `dbType`, admin password from a Secret);
  - `dropSite`;
  - `backup` (`bench --site X backup --with-files`);
  - `migrate` (maintenance mode on → `bench migrate` → off);
  - `clearCache` (optionally waits for the gunicorn rollout, then flushes Redis);
  - `custom` (any containers) [36].
- **Gaps and bugs found on 9 Oct 2026:**
  - The README still shows `jobs.backup.push` (S3), but the push script was removed on 17 Jan 2023 (PR #152). The template only writes to the sites PVC [36].
  - There is no CronJob and nothing runs `migrate` on `helm upgrade`, so we need our own CronJob and an Argo CD PreSync hook or CI step.
  - `hpa-gunicorn.yaml` sets `scaleTargetRef.apiVersion: apps/v2`; the other five HPAs use `apps/v1`. Do not enable the gunicorn HPA without patching it [36].
  - Every component has `resources: {}`.
  - Probes only check that ports are open. nginx, gunicorn and socketio use `tcpSocket`. Workers and the scheduler run `wait-for-it` against the database and Valkey. Nothing makes an HTTP application check such as `/api/method/ping` [33].
  - The pods add `CAP_CHOWN`; `runAsNonRoot` and `readOnlyRootFilesystem` are left commented out [33].
  - There is no `values.schema.json` [33].
- **Custom image.** Set `image.repository` and `image.tag` (and `imagePullSecrets`); the same image runs every component [33]. To tune gunicorn, set `GUNICORN_WORKERS` (default 2; the doc suggests 2 × cores + 1), `GUNICORN_THREADS` (4) and `GUNICORN_TIMEOUT` (120) through `worker.gunicorn.envVars` [50].

### 3.2 Building the image (`frappe_docker` v4.0.0, 3 Oct 2026) [43][44][46]
- **`apps.json`**, for example:
  ```json
  [{"url":"https://github.com/frappe/erpnext","branch":"v16.50.0"},
   {"url":"https://github.com/resilient-tech/india-compliance","branch":"v16.10.0"},
   {"url":"https://github.com/frappe/hrms","branch":"v16.50.0"},
   {"url":"https://github.com/frappe/offsite_backups","branch":"version-16"},
   {"url":"https://<token>@github.com/examleaf/examleaf_erp","branch":"v1.0.0"}]
  ```
  Pin tags rather than moving branches; `branch` accepts a tag because `bench` clones with `git --branch`.
- **Build:**
  ```
  docker build --build-arg=FRAPPE_BRANCH=v16.50.0 \
    --secret=id=apps_json,src=apps.json \
    -f images/layered/Containerfile -t ghcr.io/examleaf/erp:16.50.0-<sha> .
  ```
  - The `layered` Containerfile starts from the prebuilt `frappe/build:<ref>` and `frappe/base:<ref>` images and runs `bench init --apps_path`.
  - **`FRAPPE_BRANCH` sets both the framework's git ref and the base and build image tag**, so it must exist in both places. On 9 Oct 2026 `v16.50.0` exists on Docker Hub; `v16.51.0` (framework only) does not [46][49].
  - Assets end up in the image layer.
  - The token in `apps.json` never enters an image layer.
  - **`--build-arg APPS_JSON_BASE64` is gone (PR #1861, 15 Apr 2026)**, because build-args stay visible in `docker image history` [45].
  - Images use Debian Trixie and accept an arbitrary UID (OpenShift-friendly) from v4.0.0 [43].
- **Cache.** The secret does not invalidate the layer cache. Pass `CACHE_BUST` (the commit SHA, or a hash of `apps.json` when tags are pinned) [47].
- **CI.** frappe_docker publishes a reusable workflow, `frappe/frappe_docker/.github/workflows/app-build-image.yml@main` (inputs `app_repo`, `app_ref`, `frappe_ref`, `image_name`, `registry`, `push`), which builds `images/layered` from GHCR `base`/`build` images [48]. Our own pipeline: lint and test the app (Frappe's `bench run-tests` against MariaDB in CI), then build and scan (Trivy), push, `helm upgrade` with the new tag, run the migrate Job, then clear cache.
- **Upstream tags** (Docker Hub, 7 Oct 2026) [49]:
  - `v16.50.0`, `v16`, `version-16` (1.38 GB, amd64 and arm64);
  - `v15.122.0`, `v15`;
  - **`latest` = `develop`**: never deploy it.

### 3.3 Day-2 procedures with the chart
- **Install.** First `helm install`. Then apply the `createSite` Job with `installApps: [erpnext, india_compliance, hrms, offsite_backups, examleaf_erp]` and `dbType: mariadb` [36].
- **Add an app later.** Rebuild the image with the new `apps.json`, then `helm upgrade` with the new tag. Run `bench --site <site> install-app <app>` in a `custom` Job (or `kubectl exec`), then the `migrate` Job and the `clearCache` Job. Apps must be baked into the image; a running pod cannot `bench get-app` [53].
- **Upgrade** (weekly patch or major):
  1. Take a backup with the backup Job.
  2. Bump `image.tag` and run `helm upgrade`.
  3. Run the `migrate` Job (`bench migrate`, wrapped in maintenance mode).
  4. Run `clearCache`.
- **Read-only upgrades.** `allow_reads_during_maintenance=1` keeps the site readable during `migrate` (Frappe's zero-downtime mode, which suits an internal ERP) [105].
- **Restore.** Use a pod with the sites PVC: `bench --site X restore <db.sql.gz> --with-public-files … --with-private-files …`, adding `--db-root-*` for an external database. MIGRATION.md gives the exact command for moving from Bitnami to the built-in StatefulSet [35].

### 3.4 Storage
- **RWX sites volume.** Every pod mounts `sites/`, which holds configs, uploaded files and local backups, so the volume must be RWX on a multi-node cluster [17]. Options:
  - EFS, Filestore or Azure Files;
  - an NFS provisioner, either in-cluster (nfs-ganesha) or external;
  - rook-cephfs;
  - Longhorn RWX, which serves a Longhorn volume over NFSv4.1 from a share-manager pod [57].
- **Single node.** RWO is fine: the README allows it on single-node clusters or with node affinity [17]. k3s ships the Local Path Provisioner, which is RWO and binds the pod to its node [55].
- **Database.** Its own RWO volume, managed by the StatefulSet or the operator.

### 3.5 Single-node k3s recipe (small deployment)
1. **k3s.** Minimum 2 cores and 2 GB RAM for the server node itself [54]. It bundles the Traefik ingress and ServiceLB on ports 80/443 [56] and the local-path storage class [55].
2. **TLS.** cert-manager with Let's Encrypt, then Ingress on the `traefik` class (or keep Caddy in front). `nginx.environment.upstreamRealIPAddress` must trust the proxy so client IPs survive [33].
3. **Chart values:**
   - `persistence.worker.accessModes: [ReadWriteOnce]`, `storageClass: local-path`, `size: 20Gi`;
   - `mariadb-sts.enabled: true` with `image.tag: "11.8"`, `persistence.size: 50Gi`, a `myCnf` that includes `innodb-buffer-pool-size`, and the password from a Secret (or `dbHost` pointing at a mariadb-operator `MariaDB`);
   - Valkey defaults;
   - resources set per §3.6;
   - `ingress.enabled: true`.
4. **CronJob** every 6 hours (frappe_docker's own default is `@every 6h` [51]): `bench --site all backup --with-files`, then `rclone`/`restic` to R2. frappe_docker's backup guide says: on Kubernetes, add it as a `CronJob` [52]. The alternative is S3 Backup Settings in `offsite_backups` (§6.1).
5. **Network.** No public route to ERPNext except through SSO; webhooks to Django stay inside the cluster or private network (§6.6).

### 3.6 Minimum resources
Official data points:
- A Frappe Cloud bench needs about 400 MB of memory at minimum, with 2 gunicorn workers and 1 set of background workers [58].
- The database should start at 2 vCPU / 8 GB [40].
- frappe_docker asks for at least 4 GB of RAM for Docker in development [122].

*Estimate* for 5–15 staff users plus API sync of a few hundred orders a day:

| Component | Requests → limits |
|---|---|
| gunicorn ×1 (3 workers × 4 threads) | 0.5 vCPU / 1 GiB → 2 GiB |
| worker-default, worker-short | 0.1 vCPU / 256 MiB each → 512 MiB |
| worker-long (GSTR-1 generation, reports, imports) | 0.2 vCPU / 512 MiB → 1.5 GiB |
| scheduler | 0.05 vCPU / 192 MiB |
| socketio | 0.05 vCPU / 128 MiB |
| nginx | 0.05 vCPU / 64 MiB |
| valkey-cache | 256 MiB |
| valkey-queue (persistent) | 128 MiB |
| MariaDB | 1 vCPU / 3–4 GiB (buffer pool 2–2.5 GiB) |
| k3s plus monitoring | about 1 GiB |

Total: about 6–8 GiB in steady state. **Floor: 4 vCPU / 8 GB. Comfortable: 8 vCPU / 16 GB.** The larger node leaves room for monthly GSTR runs and for patch-day migrations, when two image versions briefly run side by side.

---

## 4. The app ecosystem ("all its extensions")

### 4.1 India Compliance (Resilient Tech; GPLv3; v16.10.0 and v15.32.0, both 24 Sep 2026; repo pushed 8 Oct 2026; 274★) [11][59]
- **Status.** The designated India localisation since v14, when India features left ERPNext. ERPNext's own docs point to it [89]. It was announced on 19 Feb 2022 by Sagar Vora of Resilient Tech, a Frappe forum "Leader" with staff flags [62]. Branches `version-15` and `version-16`; Marketplace lists v14, v15, v16 and nightly [84].
- **GST masters and validation** [63][64]:
  - more than 12,000 HSN/SAC codes in the `GST HSN Code` master;
  - HSN required on sales items, minimum 4, 6 or 8 digits (default 6; Notification 78/2020);
  - GSTIN format and checksum are checked offline at no cost;
  - party autofill and a status refresh every 30 days go through the API and use credits;
  - GST category on the company, customer, supplier and address.
- **Tax configuration.** Item Tax Templates carry a **`gst_treatment`**: `Taxable`, `Nil-Rated`, `Exempted`, `Non-GST` or `Zero-Rated`. Validation forbids a zero rate on a `Taxable` template [63].
  - **Printed books (HSN 4901):** an Item Tax Template with treatment "Exempted" and 0%. The law: books are exempt (Notification 10/2025-CT(R) Sl. 132 from 22 Sep 2025, which replaced 2/2017; see research-commerce-gst.md [67]). Ask the CA whether GSTR-1 Table 8 wants "Nil" or "Exempted"; the sibling file leaves that open [67].
  - **Digital courses and app access:** a SAC code on the item plus a "Taxable" template at the applicable rate. Use 18% if the CA confirms (rates in [67]).
  - **Invoice with both books and a course:** item-level treatments handle it. India Compliance sums taxable and nil/exempt values separately for GSTR-1 and 3B [63].
- **Bill of Supply vs Tax Invoice.**
  - ERPNext has one Sales Invoice doctype. The bundled "GST Tax Invoice" print format uses the document's Print Heading, default "Tax Invoice" [63]. Create a Print Heading "Bill of Supply" for all-exempt invoices (set it per invoice in our sync, from the Django flag).
  - India Compliance already sends an all-non-taxable Sales Invoice to the e-way bill API as document type "BIL" (Bill of Supply) [63].
  - The numbering rule (Rule 46(b): at most 16 characters, letters, digits, `-` and `/`, unique per financial year) is enforced by `validate_invoice_number`, using the pattern `^[^\W_][A-Za-z0-9\-\/]{0,15}$` [63][65]. Django's `EL/2026-27/00001` and `CN/2026-27/00001` pass [123].
- **Place of supply.**
  - For a registered party it comes from the GSTIN's state code. For an unregistered party it comes from the address's `gst_state`.
  - The address used is the billing or shipping address, per the "Determine Address Tax Category From" setting in Accounts Settings. Use **Shipping Address** for B2C book deliveries.
  - Exports get "96-Other Countries" [63].
- **e-Invoice (IRN, signed QR)** [63]:
  - not applicable to B2C (needs a billing GSTIN or an export);
  - controlled by an applicability date or a per-company list;
  - "Nil/Exempted/Non-GST items in e-Invoice" defaults to **Do Not Generate**;
  - can auto-generate on submit, auto-cancel within NIC's time limits, and retry failed generations.
  - ExamLeaf needs IRNs only after aggregate turnover passes ₹5 crore, and only for B2B (schools and distributors with a GSTIN) [67].
- **e-Way Bill** [63][66]:
  - generated from Sales Invoice, Delivery Note, Purchase Invoice/Receipt, Stock Entry or subcontracting;
  - default threshold ₹50,000, with state-wise intra-state thresholds;
  - can generate together with the e-invoice, attach a PDF, update or cancel.
  - Book-only consignments need none: Rule 138(14)(e) of notification 12/2018-CT exempts goods in the exemption schedule of 2/2017-CT(R) [66]. 10/2025 replaced 2/2017, and the sibling file flags that cross-reference for checking [67].
  - Configure that and keep the setting for any mixed or taxable goods.
- **Returns** [64]:
  - "GSTR-1 Beta": generate, compare with the portal, upload, reset and **file over the API with an OTP**; can lock invoices after filing ("Restrict Changes After Filing" plus an override role); JSON and Excel export;
  - GSTR-3B report and JSON; ITC claim period;
  - **IMS** (Invoice Management System) actions;
  - purchase reconciliation against GSTR-2A/2B, with optional auto-reconcile on chosen weekdays.
- **Other features** [63][64]:
  - Bill of Entry for imports;
  - Input Service Distributor (ISD);
  - reverse charge;
  - sales through e-commerce operators (GST TCS u/s 52, if we list on Amazon or Flipkart);
  - TDS, using ERPNext's Tax Withholding Category with 28 Indian categories preloaded, plus Lower Deduction Certificates;
  - Schedule III balance sheet and P&L templates (v16).
- **Audit trail (MCA rule in force since 1 Apr 2023).** Once enabled in Accounts Settings it cannot be turned off. It forces Track Changes on financial and stock doctypes and blocks deleting ledger entries [64]. **Turn it on during setup.**
- **The GST API, its gateway and pricing** [60][61][63]:
  - Every call goes to `https://asp.resilient.tech`, which relays to a GSP that the docs do not name. Their FAQ says it runs on AWS serverless with 99.99% uptime, excluding GSTN/NIC maintenance. **Invoice and party data therefore pass through a third party**, so record it as a processor in our DPDP records.
  - 1 credit = 1 API request. The "India Compliance API Usage" report shows usage by endpoint and document [62].
  - Price, excluding GST: ₹0.50 each for the first 10,000, ₹0.40 for the next 40,000, ₹0.30 beyond. Minimum 1,000 a year, then multiples of 1,000.
  - Credits last 12 months and are extended by any new purchase. No refunds.
  - Free trial: 500 credits for 3 months.
  - **On Frappe Cloud the API features are bundled at no charge.**
  - For comparison, GSP GSTZen charges 18 paise per e-invoice with a 50,000-a-year minimum, or 50 paise with a 25,000 minimum and 7-year storage, excluding taxes [119].
  - *Estimate for ExamLeaf:* GSTIN checks, monthly GSTR-1 and 2B pulls and occasional e-way bills come to under 5,000 credits a year, so ₹500–2,500 plus GST.

### 4.2 Other apps (metadata [11], Marketplace versions [84])
| App | Licence, publisher | Latest release, activity | What it is | ExamLeaf fit |
|---|---|---|---|---|
| **Frappe HR (hrms)** | GPLv3, Frappe | v16.50.0 and v15.64.3 (7 Oct 2026) | Employees, attendance and check-ins, shifts, leave, payroll, expense claims, advances, onboarding and separation, appraisals, recruitment, full-and-final, gratuity. **India** [68]: salary components (Basic, HRA, PF, Professional Tax, Arrear, Leave Encashment), HRA exemption, PAN and PF account fields, income-tax slabs with marginal relief, exemption declarations and proofs (TDS on salary). **No ESI component and no PF ECR or ESIC return files**: those are formula components plus manual filing | Optional. Worth it once there is more than a handful of salaried staff; otherwise keep the payroll provider |
| **Frappe CRM** | AGPLv3, Frappe | v1.86.0 (30 Sep 2026); main branch works with v15 and v16 | Leads and deals, kanban; Twilio and **Exotel** calling built in; WhatsApp via frappe_whatsapp; ERPNext integration [69] | Maybe, for the school and distributor pipeline; Django already has QuoteRequest |
| **Helpdesk** | AGPLv3, Frappe | v1.30.1 (3 Sep 2026); needs `telephony` | Tickets, SLAs with business hours and holidays, assignment rules, knowledge base, saved replies, agent and customer portals, email channels. **No WhatsApp channel** [70] | Maybe. It is AGPL, and exposing its portal to customers invokes the network clause (§1.3) |
| **Learning (LMS)** | AGPLv3, Frappe | v2.64.0 (30 Sep 2026) | Courses with chapters and lessons, batches, Zoom live classes, quizzes, assignments, certificates; payments through the `payments` app [71] | **Skip**: duplicates ExamLeaf's own course app |
| **Education** | GPLv3, Frappe | v16.1.0 (29 Jun 2026) | Students, admissions, programmes, fees, timetable, student portal [72] | **Skip**: for schools that run themselves, not for a publisher selling to them |
| **Insights** | AGPLv3, Frappe | v3.14.2 tag (29 Sep 2026) | BI: query builder, charts and dashboards, Ibis-based. **Data sources: MariaDB, PostgreSQL, SQLite** (v3 also lists DuckDB and BigQuery) [73] | **Useful**: one BI view over ERPNext and Django's Postgres replica |
| Drive | AGPLv3 | **archived** (last release v0.3.0, Oct 2025) | Now part of Frappe Suite, which is still a work in progress [74] | Skip |
| Wiki | MIT | v3.4.0 (8 Oct 2026) | Internal wiki | Optional, for SOPs |
| Print Designer | AGPLv3, Frappe | v1.6.7 (10 Feb 2026); **Marketplace lists v15 and Nightly only, not v16** [76] | Drag-and-drop print formats | Skip on v16. Use core Jinja print formats and v16's Chrome PDF renderer |
| Books | AGPLv3 | Electron app **end of life**, replaced by `frappe/frappe-books` (a Frappe app on `develop`, created 28 Aug 2026) [75] | Small-business accounting | No |
| Webshop | GPLv3, Frappe | `version-16` branch, no tagged releases | ERPNext's own storefront (moved out of core in v15) [77][126] | Skip: we have the Next.js shop |
| Payments | MIT, Frappe | `version-16` branch | Gateway settings for Razorpay, Stripe, PayPal, Braintree, Paytm, GoCardless, M-Pesa, Paymob, used by Payment Requests and web forms. Razorpay uses the orders API, an ERPNext-hosted checkout and subscriptions; it works only for INR companies [78][89] | Skip: Django owns Razorpay. If staff need links for B2B invoices, create Razorpay Payment Links from Django |
| frappe_whatsapp | MIT, **community** (Shridhar Patil) | v1.0.11 (25 Nov 2025); last commit 4 Aug 2026; Marketplace v14–v16 | WhatsApp Cloud API: templates, notifications on DocType events, two-way chat, bulk sends [79] | Only for ERPNext-originated staff messages; customer messaging stays in Django |
| ERPNext Shipping | MIT, Frappe | v16.0.2 (21 Aug 2026) | **Only LetMeShip and SendCloud.** Shiprocket PRs #102 (Jul 2026) and #72 (Jul 2025) are open and unmerged [80] | No India carriers |
| bwh_shipping | MIT, community (BuildWithHussain) | created 20 Aug 2026, 3★ | Shiprocket and AfterShip: rates, labels, tracking webhooks, pickups and manifests [81] | Too new. Watch it |
| harshpwctech/erpnext-shipping | community fork, 1★ | commit 5 Oct 2026 | Adds Shiprocket and Dunzo to an older ERPNext Shipping [82] | No |
| Delhivery connector | commercial (ECOSIRE), built to order | not an open listing | Pincode serviceability, rates, waybills, COD reconciliation [83] (search summary only) | No: Django already records shipments (Delhivery, Blue Dart, Ekart) [123] |
| ecommerce_integrations | GPLv3, Frappe | v16.0.0 (18 Feb 2026) | Shopify, **Unicommerce** (India marketplace aggregator), Amazon SP-API, Zenoti [86] | Reference design (§5.7). Install only if we sell through Unicommerce |
| offsite_backups | MIT, Frappe | `version-16` only | S3 (custom `endpoint_url`, so R2 works), Dropbox, Google Drive; moved out of the framework by PR #32351 (merged 17 Jun 2025) [85] | **Install** on v16 |
| Raven / Gameplan / Builder | AGPL / AGPL / MIT | v3.0.0 (18 Sep 2026) / no releases / v1.35.1 (4 Oct 2026) | Chat / discussions / website builder | Skip |
| Changemakers | AGPLv3 | last push Apr 2024 | NGO beneficiary management | Irrelevant (inactive) |

### 4.3 ERPNext core modules (v16 modules: Accounts, CRM, Buying, Projects, Selling, Setup, Manufacturing, Stock, Support, Utilities, Assets, Portal, Maintenance, Regional, ERPNext Integrations, Quality Management, Communication, Telephony, Bulk Transaction, Subcontracting, EDI [88]); fit for ExamLeaf (docs [89])
| Area | Feature | Use for ExamLeaf |
|---|---|---|
| Selling | Quotation → Sales Order → Delivery Note → Sales Invoice; Credit Note (return Sales Invoice); POS | **B2B** (schools and distributors) natively in ERPNext. **B2C**: mirror only Django's invoices, credit notes and dispatches (§5.8). POS only for book fairs |
| Customers | Customer Groups (price list, payment terms, credit defaults), Territories, Price Lists, Pricing Rules and Promotional Schemes, **Credit Limits** (customer → group → company, with an approver role), Payment Terms, Dunning, **Blanket Orders** | Groups: Distributor, School, Bookseller, Online B2C. Distributor price list. Credit limits and payment terms for schools. A Blanket Order for each school's annual commitment |
| Sales Partners | Commission, targets, Sales Partner Commission report | Commission agents or school reps. Distributors who *buy* are Customers, not Sales Partners |
| Stock | Items, Item Groups, Product Bundle, Warehouses, Stock Entry, **Stock Reconciliation**, reorder levels → Material Request, **Stock Reservation** (since v15), Pick List, Packing Slip; Batches; Serial Nos | **ERPNext owns physical stock** (§5.8). One **Batch per print run** (edition and print date). **Do not use Serial Nos for book unlock codes**: the codes live in Django, and a serial on every copy adds a Serial and Batch Bundle to every stock line; negative stock is blocked for serial and batch items since v15 [89] |
| Buying | Supplier (the printers), Request for Quotation, Supplier Quotation, Purchase Order, **Purchase Receipt**, Purchase Invoice, **Landed Cost Voucher** (freight) | Print runs bought as finished books. Use Subcontracting Orders only if ExamLeaf supplies the paper |
| Manufacturing | BOM, Work Order, Job Card | Not needed unless we print in-house. A bundle is a Product Bundle, not a BOM |
| Accounts | **India standard chart of accounts** (`in_standard_chart_of_accounts.json` [88]); Payment Entry; Journal Entry; **Bank Reconciliation** with statement import; Payment Reconciliation; **Deferred Revenue** (course access sold for 12 months); Period Closing Voucher plus Accounting Period / Frozen Upto; budgets; accounting dimensions; v16 custom financial statement templates | Razorpay: "Razorpay Clearing" bank account → settlement Journal Entry net of fees, with ITC on the GST charged on fees. COD: courier remittance → Payment Entry. Monthly close and GST returns run here |
| Subscriptions | Subscription Plans → recurring invoices | School annual subscriptions, if any |
| Projects, Quality, Assets, Maintenance | Projects with timesheets; inspections; fixed-asset register with depreciation | Assets register yes; the rest optional |
| Support | Issue with SLA (core) | Use Helpdesk instead if we want tickets |
| Portal | Customer and supplier portal for Website Users (orders, invoices, shipments, issues) | **Do not expose.** Customers use examleaf.in |
| Customisation | Custom Fields, Property Setters, Client Scripts, Server Scripts (**off by default since v15**: `bench set-config -g server_script_enabled true` [94]), Workflows (approvals; `workflow_transition` webhook event), Notifications (email or system alerts on events or dates), Document Naming Rules, Print Formats | All schema and behaviour in `examleaf_erp` as code: fixtures and Export Customizations [111][112], `doc_events` hooks. No Server Scripts in production |
| Data and reports | Data Import (CSV/XLSX, runs in the background), Report Builder, Query and Script Reports, Dashboards, Number Cards, Prepared Reports, Auto Email Report | Initial migration and finance dashboards |

---

## 5. Integration with an external system of record

### 5.1 REST API (official) [90][91][92]
- **Endpoints.** v1: `/api/resource/<Doctype>` (list: `fields`, `filters`, `or_filters`, `order_by`, `limit_start`, `limit_page_length`, `expand`; CRUD: GET, POST, PUT, DELETE; POST to a document runs a document method) and `/api/method/<dotted.path>`, which needs `@frappe.whitelist`; POST auto-commits. v2: `/api/v2/document/<Doctype>[/<name>]` (PATCH and copy), `/api/v2/doctype/<Doctype>/meta|count`, `/api/v2/method/<Doctype>/<method>`.
- **Auth:**
  - `Authorization: token <api_key>:<api_secret>`. The key and secret are generated on a User, and every call is checked against that user's roles.
  - A session cookie from `/api/method/login`.
  - An OAuth2 bearer token.
- **Bulk:**
  - `frappe.client.insert_many` takes up to **200 documents per request**;
  - `frappe.client.bulk_update` takes a list with `docname`;
  - Data Import for large loads (it runs with `in_import`, which also keeps given names).
- **Rate limiting:**
  - Site-wide, in `site_config.json`: `"rate_limit": {"limit": <seconds of processing>, "window": <seconds>}`. It is a fixed window on total request *time*, not request count. Over the limit, Frappe returns **HTTP 429** with `Retry-After` and `X-RateLimit-*` headers.
  - Per endpoint: the `@rate_limit(limit, seconds, methods, ip_based)` decorator counts requests.
  - Our relay must honour 429 and back off.

### 5.2 Webhooks (official docs and v16 code) [93]
- **Events:** `after_insert`, `on_update`, `on_submit`, `on_cancel`, `on_trash`, `on_update_after_submit`, `on_change`, `workflow_transition`.
- **Options:**
  - Jinja conditions;
  - POST, PUT or DELETE;
  - a form or JSON body (Jinja template);
  - custom headers;
  - dynamic URL;
  - choice of queue;
  - timeout (default 5 s).
- **Security.** "Webhook Secret" adds `X-Frappe-Webhook-Signature`: a base64 HMAC-SHA256 of the payload.
- **Delivery:**
  - queued **after the database commit** and coalesced to the last version of the document in that transaction;
  - **3 attempts** with sleeps of 1, 4 and 7 s;
  - every attempt is logged in `Webhook Request Log`.
- **There is no durable retry beyond that.** Treat a webhook as a doorbell, and have Django re-read state through the API and reconcile (§5.8).

### 5.3 Server Scripts vs a custom app
- Server Scripts use RestrictedPython, are off by default since v15, and Frappe Cloud allows them only on private benches [94].
- Put everything in `examleaf_erp`:
  - whitelisted API methods;
  - `doc_events` hooks;
  - scheduled jobs;
  - fixtures for Custom Fields, Property Setters, Roles, Workflows and Print Formats [111][112].
- This keeps it in git, testable, and part of the image.

### 5.4 SSO and identity
- **Frappe as an OAuth2/OIDC provider** [95][96]:
  - `OAuth Client` records hold client id, secret, redirect URIs and scopes such as `openid all`. Endpoints: `/api/method/frappe.integrations.oauth2.authorize|get_token|openid_profile|revoke_token`.
  - Discovery at `/.well-known/openid-configuration`.
  - Optional RFC 7591 dynamic client registration and RFC 8414/9728 metadata (OAuth Settings).
  - **The `id_token` is HS256 only, signed with the client secret** (no JWKS/RS256).
  - So Django could log in through ERPNext, but **we do not want the ERP as the identity provider**.
- **Frappe as a client (Social Login Key)** [97]:
  - providers: Google, Office 365, GitHub, Facebook, Salesforce, Frappe, fairlogin, **Keycloak** and **Custom** (authorize, token and userinfo URLs, `auth_url_data`);
  - Frappe matches the provider's email to an existing User;
  - **`sign_ups: Deny`** stops strangers from creating accounts.
- **Google Workspace with a domain restriction:**
  - Frappe has no domain check of its own.
  - Use a Google OAuth client whose consent-screen audience is **Internal**, so only accounts in our Workspace organisation can authorise (Google support [98], read from a search snippet), together with `sign_ups: Deny` and pre-created Users.
  - Passing `{"hd":"examleaf.in"}` in `auth_url_data` only hints the account picker.
- **Recommendation:**
  - Google Workspace is the identity provider for staff on both Django admin and ERPNext.
  - On ERPNext also set `disable_user_pass_login=1` for staff once SSO works.
  - Keep `Administrator` as a sealed break-glass account [99].

### 5.5 Users, roles and provisioning
- **APIs.** `User` (`enabled`, `user_type`, `roles` child table; **v16 adds `role_profiles` (multi-select)** next to `role_profile_name`; `module_profile`, `restrict_ip`, `api_key`), `Role` (per-role **two-factor** flag, desk access), `Role Profile`, `User Permission` (limits a user to specific records, for example a Territory or Customer Group) [99]. ERPNext ships role profiles Inventory, Manufacturing, Accounts, Sales and Purchase [88].
- **Role map** (ExamLeaf roles from research-rbac-security.md [124]):

| ExamLeaf role | ERPNext role profile and roles |
|---|---|
| OWNER | System Manager + Accounts Manager (named user, 2FA); `Administrator` kept sealed |
| ADMIN | custom "EL Admin": System Manager without Accounts Manager |
| FINANCE | Accounts (Accounts User, Accounts Manager) + GST/India Compliance pages; Auditor read-only role for the CA |
| PACKER | Inventory, reduced to Stock User (Delivery Note, Pick List, Stock Entry) |
| SALES (B2B) | Sales (Sales User, Stock User, Sales Manager), with a User Permission per Territory if needed |
| Purchasing | Purchase |
| SUPPORT | Support Team (Issues) or Helpdesk agent |
| HR | HR User / HR Manager (hrms) |
| AUDITOR | ERPNext "Auditor" plus read-only Report roles; time-bound in Django |
| SERVICE | integration user `erp-sync@` with a custom role holding only the doctypes it writes; API key in a Kubernetes Secret; `restrict_ip` (needs v16.33.0+ or v15.120.0+, where an API-key bypass of `restrict_ip` was fixed [108]) |
| CONTENT_EDITOR, REVIEWER, MARKETING, TEACHER_PARTNER | no ERPNext access |

- **Provisioning.** Lazy path: for fewer than about 15 staff, create users by hand with Google login and the right role profile. Later, Django's role-grant flow can call `PUT /api/resource/User/<email>` (`role_profiles`, `enabled=0` on leave) through the same outbox. Disable users, never delete them, so audit links survive.

### 5.6 Idempotency and naming
- **Names are generated.** Frappe clears any `name` you pass unless the doctype's autoname is `prompt` or `UUID`, or the insert runs as a data import. Sales Invoice uses a naming series, so a REST POST cannot fix the name [100].
- **The custom app must therefore call `doc.insert(set_name="EL/2026-27/00001")`** (supported in v16 [100]). Frappe forbids only `<` and `>` in names, and India Compliance accepts `/` and `-` [63].
- **Add a unique custom field `examleaf_ref`** (Django event or entity id) to every synced doctype (Customer, Address, Item, Sales Invoice, Payment Entry, Delivery Note, Journal Entry).
  - The endpoint first looks up `examleaf_ref` and returns the existing document.
  - `insert(ignore_if_duplicate=True)` catches races on the name (primary key) [100].
- **Do not cancel and amend GST invoices.** An amendment gets a `-1` suffix and can break the 16-character limit. Use credit notes (Sales Invoice with `is_return=1` and `return_against`), as Django already does [123].

### 5.7 What Frappe's own connectors do (ecommerce_integrations) [86][87]
- **`Ecommerce Integration Log`.** Fields: `status` (Queued, Error, Success), `method`, `request_data`, `response_data`, `traceback`. A "Resync" or bulk retry re-enqueues the method after commit. Success logs are purged after 90 days.
- **`Ecommerce Item`** maps external ids to ERPNext items. Shopify webhooks are HMAC-verified.
- **Frappe's stated best practices** [87]:
  - keep ERPNext the source of truth for stock and accounting;
  - use stable external ids;
  - log every sync attempt so failures can be retried;
  - use least-privilege API keys;
  - test on a staging site first.

### 5.8 Recommended sync design for ExamLeaf
**Ownership: one writer per fact.**
| Fact | Master | Flow |
|---|---|---|
| Catalogue (items, HSN/SAC, rates, bundles) | Django (`Product`, `BundleItem` [123]) | Django → ERPNext Item, Product Bundle, Item Tax Template link |
| B2C customers | Django (students and parents) | **Not copied one by one.** Every B2C invoice uses one ERPNext Customer, "Online Customers (B2C)", with the per-invoice shipping state, place of supply and `examleaf_order_no`. This is data minimisation under DPDP; names and phones stay in Django |
| B2B customers (schools, distributors, booksellers with a GSTIN) | **ERPNext** (credit limits, price lists, payment terms) | ERPNext → Django (read-only copy for the school portal and teacher partner) |
| Orders, invoices, credit notes (B2C) | Django (legal numbers `EL/…`, `CN/…`) | Django → ERPNext Sales Invoice / return created with `set_name`; Print Heading "Bill of Supply" when all items are exempt |
| B2B quotations, orders, invoices | ERPNext | ERPNext → Django by webhook doorbell plus pull, if the website must show them |
| Payments | Django (Razorpay, COD) | Django → ERPNext Payment Entry (with Razorpay payment id); Razorpay settlement and COD remittance as Journal Entries |
| Physical stock (receipts from printers, counts, transfers, returns) | **ERPNext** | ERPNext → Django: on Purchase Receipt or Stock Reconciliation submit, a webhook doorbell, then Django pulls the bin quantity |
| Availability and reservations at checkout | Django | Dispatch posts an ERPNext Delivery Note against the invoice (stock out) |
| Staff | Google Workspace and Django RBAC | §5.5 |
| Book codes and course entitlements | Django | Never in ERPNext |

**Mechanics:**
1. **Transactional outbox in Django.**
   - The `ErpOutbox` row (`id`, `aggregate`, `aggregate_id`, `event`, `payload`, `attempts`, `next_at`, `status`) is written **in the same database transaction** as the order, invoice or refund. A relay may send a message more than once, so the consumer must be idempotent [101].
   - A Celery beat relay sends events in order per aggregate (customer → invoice → payment → delivery) to our own `examleaf_erp.api.*` methods, with the outbox id as the idempotency key.
   - Retries back off exponentially and honour 429 `Retry-After`. After N failures a row goes to a dead-letter state with a staff alert.
2. **A mirror log in ERPNext** (an "ExamLeaf Sync Log" doctype modelled on the Ecommerce Integration Log) for finance-side visibility and replays.
3. **Reverse direction:**
   - Webhooks with a secret from ERPNext to an internal Django URL.
   - Django verifies the HMAC, then **re-reads** the document through the API, so a lost webhook is caught by the next pull.
   - A pull every 15 minutes for stock and B2B documents changed since `modified > cursor`.
4. **Nightly reconciliation** (Celery). For each day compare Django and ERPNext on:
   - number and total of invoices;
   - taxable and exempt split;
   - number and total of credit notes;
   - payments by method;
   - shipped quantities.
   Also check the stock invariant: ERPNext bin quantity minus copies reserved and not yet shipped equals Django's available stock. Differences open a task for staff.
5. **Initial load.** Data Import (keeps names) for opening stock, open B2B receivables and the item master. Then switch on the outbox.
6. **What a lost ERPNext backup costs.** Synced documents can be rebuilt by replaying the outbox. Only ERPNext-only entries (purchases, journals, payroll) depend on ERPNext backups (§6.1).

---

## 6. Operations

### 6.1 Backups
- **`bench backup`.** Writes a compressed SQL dump, plus public and private files with `--with-files`, and a site_config backup, to `sites/<site>/private/backups`. Options: `--compress`, `--exclude/--only` DocTypes, `--backup-path*` [102]. "Number of Backups" (`backup_limit`, default 3) caps how many are kept locally [99].
- **Encryption.** System Settings → Encrypt Backup: GPG with a `backup_encryption_key` stored in `site_config.json` [103]. `site_config.json` also holds the Fernet `encryption_key` that decrypts every Password field (API secrets, email passwords) [103]. **Back up `site_config.json` separately and keep it as a secret.** Without it, restored secrets are unreadable.
- **Offsite:**
  1. A CronJob (`bench --site all backup --with-files`, then `rclone` or `restic` to R2) [52];
  2. `offsite_backups` → S3 Backup Settings (`endpoint_url`, so R2 works; Daily/Weekly/Monthly; files optional) [85];
  3. mariadb-operator physical backups plus PITR to R2 [39].
  Pick (1) or (2) for the site and files, and add (3) if we need an RPO under 6 hours.
- **Restore drill** every quarter into a scratch namespace (§3.3).

### 6.2 Monitoring and logs
- **No built-in Prometheus exporter.**
  - Frappe recommends Prometheus and Grafana with node exporter, mysqld exporter or PMM, and lists metrics to watch: buffer-pool miss rate, row-lock waits, LRU churn [40].
  - Add `rq-exporter` (community, PyPI) for queue depth [125], or use mariadb-operator's ServiceMonitor [39].
- **Health checks.** `/api/method/ping` (guest-allowed, returns "pong") for HTTP probes [91]. The v16 System Health Report doctype in Desk has child tables for queues, workers, failing jobs, errors and tables [99]. `X-Frappe-Request-Id` on responses for tracing [107].
- **Logs:**
  - in the database: Error Log, Scheduled Job Log, Access Log, Activity Log;
  - in files: `frappe.web.log` (with `enable_frappe_logger`), `worker.log`, `scheduler.log`, `bench.log`, error snapshots [104].
  - In Kubernetes, ship stdout to Loki or similar; the chart's own logs PVC is off by default [33].

### 6.3 Upgrades and multi-site
- Patch every week in a maintenance window using §3.3 (backup → new tag → migrate → clear cache).
- Apply each major only after a staging run.
- **Multi-site.** One bench (the image) can serve several sites: `createMultipleSites`, `migrateMultipleSites` [36]. Use one production site, plus a staging site in a separate release or namespace.

### 6.4 Performance
- **gunicorn:** workers about 2 × cores + 1, threads 4, timeout 120 s [50].
- **Background workers:** add a custom queue for heavy GST and report jobs [58].
- **MariaDB:** buffer pool about 60% of RAM, slow query log, read replica for heavy reports [40].
- **v16 is about 2× faster on typical requests:** fewer Redis round-trips, and the C database connector is 3–5× faster at parsing results (Ankush Menat, Frappe, 6 Nov 2025 [8]).

### 6.5 Security features and settings (v16 defaults from `system_settings.json` [99])
- **Login:**
  - 2FA: `enable_two_factor_auth`, method OTP App, SMS or Email; can be required **per Role**.
  - Lockout: `allow_consecutive_login_attempts`=10 and `allow_login_after_fail`=60 s.
  - Password policy: minimum score 2 of 4 (raise to 3).
  - **`session_expiry` 170:00 hours** (shorten to about 8–12 hours for staff).
  - `deny_multiple_sessions`.
  - **`login_with_email_link` is on by default: turn it off.**
  - `disable_user_pass_login` once SSO works.
- **Per user:** `restrict_ip`, `simultaneous_sessions`.
- **Audit and history:**
  - Version (Track Changes), Activity Log, **Access Log** (exports, prints, report views), **API Request Log** (`log_api_requests`), Permission Log, Deleted Document;
  - the Audit Trail page compares up to 5 amended versions [113];
  - India Compliance's irreversible audit trail [64].
- **Stored secrets.** Passwords are hashed with PBKDF2-SHA256; Password fields are Fernet-encrypted. Frappe declines to block uploads by content (no antivirus; there is an allowed-extensions list) and leaves tracebacks visible unless disabled [106].
- **Headers and CSP:**
  - Frappe emits no global CSP; only web forms get `frame-ancestors`. CORS comes from `allow_cors` [107].
  - frappe_docker's nginx adds `X-Frame-Options`, HSTS, `nosniff` and `Referrer-Policy` [51].
  - Desk uses inline `<script>` blocks [107], so a strict `script-src` CSP needs testing (likely `'unsafe-inline'`). Set headers at the ingress.
- **Personal data:**
  - Personal Data Download and Deletion Requests (core website doctypes), driven by each app's `user_data_fields` hook, which defines what to redact or anonymise [111][99].
  - Our design keeps B2C personal data out of ERPNext, which keeps that surface small (§5.8).
- **Disclosure.** Report to security@ (Frappe asks for 10–15 days to respond) [110].

### 6.6 Advisories and patch cadence (GitHub Security Advisories, 9 Oct 2026) [108][109]
| Repo | 2024 | 2025 | 2026 to date |
|---|---|---|---|
| frappe | 6 | 17 (1 critical, 10 high) | **53** (2 critical, 11 high, 34 medium, 6 low) |
| erpnext | 0 | 2 high | **87** (8 critical, 30 high, 49 medium) |
| lms / crm / hrms / insights / helpdesk | | | 21 / 8 / 8 / 3 (2 critical) / 1 |
| india_compliance / payments | | | 0 / 0 |

- **Examples from 2026:**
  - Frappe critical: arbitrary file read via outgoing email HTML (fixed v16.30.0 / v15.117.0) and path traversal (v16.15.0).
  - Frappe high: TarSlip RCE in Package Import (v16.23.0), host-header poisoning of magic login links (v16.18.3).
  - Frappe medium: `restrict_ip` bypass with API keys (v16.33.0).
  - ERPNext critical: several server-side template injection, RCE and missing-validation issues (v16.22.0–v16.34.0).
- Most fixes land in the Tuesday releases for **both** v15 and v16, so **patch weekly (within 7 days for critical or high)**.
- Keep ERPNext **off the public internet**: SSO plus an IP allowlist or VPN for Desk, and no portal. Every authenticated-user bug then needs a staff account first.

---

## 7. Costs

| Option | Monthly cost (INR) | Notes |
|---|---|---|
| Frappe Cloud site, AWS Mumbai [114][116][117][127] | ₹410 (0.5 CPU-hours/day, 250 MB DB) → ₹820 → **₹2,050** (2 h, 1 GB DB, 25 GB, **private benches**, which custom apps need, and offsite backups) → ₹3,075 → **₹4,100** (4 h, 2 GB DB, 50 GB, **SSH and database access, Product Warranty**) | Billed daily; no user limit, but requests are dropped once the daily CPU allowance is used up. **India Compliance API included free** [60]. Hetzner plans cost the same with more CPU but no production guarantees. Major upgrades are started by hand [10]. No Kubernetes and no Postgres |
| Frappe Cloud dedicated server, AWS Mumbai [115] | Unified app and database server, 2 vCPU / 4 GB / 25 GB **₹10,000** ($125); 2 vCPU / 8 GB / 50 GB ₹12,000 | The page lists Regular and Enterprise tiers (Enterprise adds Product Warranty and L1/L2 support). DigitalOcean servers start at ₹5,400 (Toronto and Singapore only). Hetzner servers start at ₹3,600 (2 vCPU / 4 GB, German regions) with incident support only |
| Self-hosted single-node k3s | One node, e.g. DigitalOcean Basic 4 vCPU / 8 GiB $48 or 8 vCPU / 16 GiB **$96/month** [118] (≈₹4,000–8,000). R2 storage for backups costs little at our size (*estimate*). India Compliance credits ≈₹500–2,500 a year [61]. Optional AWS RDS MariaDB instead of the StatefulSet | Plus our own operations time: about 2–4 hours a week for weekly patches, migrations, restore drills and reconciliation alerts (*estimate*) |
| India Compliance on its own (self-hosted) | ₹0.50 / ₹0.40 / ₹0.30 per credit (+GST), minimum 1,000 a year [61] | Compare GSTZen e-invoice: 18 paise each with a 50,000 minimum, ₹9,000 a year minimum, excluding tax [119] |

The platform's DEPLOYMENT.md sizes today's stack at 2 vCPU / 4 GB [123]. ERPNext needs about 2–4× that again (§3.6), or a Frappe Cloud plan from ₹2,050/month.

---

## 8. Decisions for the owner
1. **Accept MariaDB 11.8 for ERPNext**, with Django staying on PostgreSQL 17. Revisit Postgres when v17 ships with India Compliance and HRMS tested on it (§2.5).
2. **Kubernetes or Compose.** Compose is the canonical production method and less work [53]. If Kubernetes stays, use single-node k3s and the §3.5 recipe.
3. **Where ERPNext runs.** Self-hosted (our Kubernetes, data in our VPC; pay for India Compliance credits) or Frappe Cloud from ₹2,050–4,100/month (credits included; not Kubernetes).
4. **Ownership.** Agree the matrix in §5.8, especially that ERPNext owns physical stock and B2B customers, and that Django keeps the legal invoice numbers.
5. **Apps to install:** india_compliance, offsite_backups and the custom app `examleaf_erp`. Optional: hrms, insights, helpdesk.
6. **Ask the CA:**
   - "Exempted" or "Nil-Rated" for HSN 4901;
   - a separate "Bill of Supply" series or the shared `EL/` series;
   - whether ERPNext should file GSTR-1 instead of Django's export.
