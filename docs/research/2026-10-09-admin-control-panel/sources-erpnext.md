# Sources: ERPNext research (research-erpnext.md)

The numbers match the [n] citations in research-erpnext.md. Everything was fetched on 2026-10-09. GitHub files and metadata came through api.github.com or raw.githubusercontent.com; forum threads came through Discourse's JSON (author, date and staff/admin/moderator flags recorded).

Quality labels:
- official: Frappe's or the app publisher's own docs, code, CI, or a post by a Frappe staff account;
- forum: any other community post;
- vendor: a commercial seller's page;
- secondary: an aggregator.

Raw copies are in raw-erp/.

1. https://github.com/frappe/frappe/releases | 2026-10-09 | official; release tags and dates through the API (v16.51.0 on 7 Oct 2026, v15.122.0, v16.0.0 on 12 Jan 2026, v15.0.0 on 20 Oct 2023, v14.0.0 on 1 Aug 2022; weekday of each release checked)
2. https://github.com/frappe/erpnext/releases | 2026-10-09 | official; tags and dates (v16.50.0 on 6 Oct 2026, v15.122.0 on 7 Oct 2026); `version-1x` and `-hotfix` branches checked through the API
3. https://github.com/frappe/erpnext/wiki/Supported-Versions | 2026-10-09 | official wiki, edited 19 Jan 2026 by Mihir Kandoi; end-of-life table (v14 31 Jan 2026, v15 end-2027, v16 end-2029, planned)
4. https://docs.frappe.io/framework/user/en/installation | 2026-10-09 | official docs ("last updated 2 months ago"); v14/v15 vs v16 prerequisite table
5. https://github.com/frappe/frappe/blob/version-16/pyproject.toml (also version-15/pyproject.toml) | 2026-10-09 | official source; requires-python, dependency pins
6. https://github.com/frappe/erpnext/blob/version-16/pyproject.toml (also version-15) | 2026-10-09 | official source; required Frappe range
7. https://github.com/frappe/frappe/blob/version-16/frappe/database/mariadb/setup_db.py | 2026-10-09 | official source; MariaDB version warnings (below 10.6, above 11.8)
8. https://discuss.frappe.io/t/erpnext-hrms-frappe-framework-v16-release-dates/156349 | 2026-10-09 | official announcements by Frappe staff (Nabin Hait 3 Nov 2025 and 12 Jan 2026; Ankush Menat 6 and 26 Nov 2025): feature list, delay reasons, performance notes
9. https://github.com/frappe/frappe/wiki/Migrating-to-version-16 | 2026-10-09 | official wiki (edited 17 Aug 2026); breaking changes
10. https://discuss.frappe.io/t/erp-v16-clarifications/158512 | 2026-10-09 | forum; staff answer (Mihir Kandoi, 31 Dec 2025): release date, manual upgrade on Frappe Cloud
11. GitHub repository metadata through api.github.com: licence, default branch, stars, last push, archived flag, releases, branches, workflow files, licence files. Repos: frappe/{frappe, erpnext, hrms, crm, helpdesk, lms, insights, education, drive, wiki, print_designer, books, webshop, payments, raven, gameplan, builder, helm, frappe_docker, ecommerce_integrations, erpnext-shipping, offsite_backups, blog, newsletter, changemakers, telephony, lending, press, suite, frappe-books, bench}; resilient-tech/india-compliance; shridarpatil/frappe_whatsapp; bwhtech/bwh_shipping; harshpwctech/erpnext-shipping; mariadb-operator/mariadb-operator | 2026-10-09 | official metadata; licence files read where GitHub shows NOASSERTION (education "GNU GPL V3"; frappe_whatsapp, erpnext-shipping and twilio-integration MIT)
12. https://www.gnu.org/licenses/gpl-faq.html (#GPLRequireSourcePostedPublic, #InternalDistribution, #GPLPlugins, #UnreleasedMods, #AGPLv3InteractingRemotely) | 2026-10-09 | FSF official FAQ; paraphrased
13. https://discuss.frappe.io/t/licensing-of-app-made-using-frappe-erpnext/9836 | 2026-10-09 | forum; Rushabh Mehta (Frappe) 5 Nov 2016: personal view, not a legal position
14. https://discuss.frappe.io/t/selling-apps-built-on-frappe-and-erpnext/78431 | 2026-10-09 | forum; moderator (peterg) 25 Jul 2021; "not a lawyer"
15. https://frappe.io/blog/legal/protection-of-our-intellectual-property | 2026-10-09 | official blog, 13 Apr 2021; licence notice and trademark guidance
16. https://docs.frappe.io/framework/user/en/guides/database-settings/postgres-database-setup | 2026-10-09 | official docs ("last updated 5 months ago"); minimal page, no ERPNext statement
17. https://github.com/frappe/helm/blob/main/erpnext/README.md | 2026-10-09 | official chart README: ERPNext requires MariaDB; database not deployed by default; RWX requirement and RWO on a single node; jobs through `helm template`; outdated `backup.push` example
18. https://discuss.frappe.io/t/is-erpnext-officially-supported-with-postgresql/163329 | 2026-10-09 | forum with staff answers (Mihir Kandoi, Frappe Team: 29 Jun 2026 "not in v16", 6 Aug 2026 "apart from transaction isolation… done", no commitment); a v17 timing guess by a community member (18 Jul 2026)
19. https://github.com/frappe/erpnext/issues/56865 | 2026-10-09 | official GitHub; bug opened 3 Jul 2026 (six v16 reports failing on Postgres), closed 4 Jul 2026 by collaborator Mihir Kandoi: "Postgres is not supported on v16. Develop only for now."
20. https://discuss.frappe.io/t/postgres-support/162440 | 2026-10-09 | forum; staff (Revant Nandgaonkar) 7 May 2026: no app runs Frappe on Postgres with daily CI, you are on your own
21. https://discuss.frappe.io/t/status-of-compatibility-with-postgres/161316 | 2026-10-09 | forum, 10 Mar 2026 (Aarol D'Souza; no staff flag, author of Frappe multi-DB PRs such as erpnext#52056)
22. https://discuss.frappe.io/t/postgresql-support-in-next-version-of-frappe-framework/160668 | 2026-10-09 | forum; staff (Mihir Kandoi) 2 Jul 2026 "almost there"; a user's summary of framework, ERPNext and app status
23. https://github.com/frappe/erpnext/issues/24389 | 2026-10-09 | official GitHub; "Postgres support for ERPNext", opened by rmehta 18 Jan 2021, closed 21 Jun 2026; timeline of cross-referenced PRs read
24. https://github.com/frappe/erpnext/issues/56241 | 2026-10-09 | official GitHub (Frappe maintainer Mihir Kandoi, 21 Jun 2026); ~35 KB summary of the parity conversion, behaviour differences, audits 1–10, follow-ups
25. https://github.com/frappe/erpnext/blob/develop/.github/workflows/server-tests-postgres.yml (also the version-16 copy) | 2026-10-09 | official CI; develop: nightly 21:30 UTC plus `postgres` label; version-16: old label-only job on postgres:13.3, last changed Dec 2025
26. https://github.com/frappe/frappe/blob/develop/.github/workflows/server-tests.yml | 2026-10-09 | official CI; matrix adds postgres:18.0 only with the `postgres` label; mariadb:11.8 always; no Postgres in version-16's workflow
27. https://github.com/frappe/frappe/pull/43542 (and PRs #43592–#43610, 29–30 Sep 2026) | 2026-10-09 | official GitHub; READ COMMITTED isolation PR closed without merging; other Postgres fixes merged into develop
28. https://github.com/resilient-tech/india-compliance/pull/4481 (and .github/workflows/server-tests-postgres.yml on develop) | 2026-10-09 | official; merged 23 Jul 2026; follow-ups listed; version-15/16 branches have no Postgres workflow
29. https://discuss.frappe.io/t/postgresql-support-for-erpnext/149487 | 2026-10-09 | forum; moderator (Brian Pond) 13 Jul 2025: effort cancelled as of Mar 2025; advises against forks
30. https://discuss.frappe.io/t/support-for-postgresql-it-is-production-ready/84316 | 2026-10-09 | forum; staff (ChillarAnand) 3 Jan 2022: beta in the framework, in progress for ERPNext
31. https://discuss.frappe.io/t/postgresql-compatibility-for-erpnext-meet-frappe-pg/157807 | 2026-10-09 | forum/community; frappe_pg monkey-patch app (9 Dec 2025)
32. https://github.com/frappe/frappe/blob/version-16/frappe/database/postgres/setup_db.py (also develop) | 2026-10-09 | official source; CREATE USER / CREATE DATABASE / GRANT per site through a root connection
33. https://github.com/frappe/helm/blob/main/erpnext/Chart.yaml and values.yaml | 2026-10-09 | official; chart 8.0.84, appVersion v16.50.0, dependencies, defaults (mariadb-sts tag 10.6, valkey 7.2, resources {}, TCP probes, CAP_CHOWN)
34. https://helm.erpnext.com/index.yaml | 2026-10-09 | official chart index; 660 versions; 8.0.0 = 3 Dec 2025 (v15.91.0), 8.0.84 = 6 Oct 2026; 7.x covered 20 Oct 2023 – 2 Dec 2025
35. https://github.com/frappe/helm/blob/main/erpnext/MIGRATION.md and commit 5e1167a8 (3 Dec 2025, "introduce built-in components and deprecate subcharts") | 2026-10-09 | official; Bitnami → built-in database migration with exact restore commands
36. https://github.com/frappe/helm/tree/main/erpnext/templates (job-backup.yaml, job-migrate-site.yaml, hpa-*.yaml, deployment-*.yaml; commit history of job-backup.yaml) | 2026-10-09 | official source; push script removed 17 Jan 2023 (#152); gunicorn HPA uses apps/v2 while the others use apps/v1
37. https://github.com/bitnami/containers/issues/83267 | 2026-10-09 | official Bitnami announcement (16 Jul 2025): legacy repository from 28 Aug 2025, deletion of the public catalogue postponed to 29 Sep 2025
38. https://endoflife.date/api/mariadb.json (and /postgresql.json) | 2026-10-09 | secondary aggregator; MariaDB 10.6 EOL 2026-07-06, 11.8 EOL 2028-06-04, 12.3 EOL 2029-06-12
39. https://github.com/mariadb-operator/mariadb-operator (README, releases) | 2026-10-09 | official project; 26.10.1 on 21 Sep 2026; MIT; feature list; MariaDB ≥10.6, Kubernetes ≥1.31
40. https://docs.frappe.io/framework/user/en/database-optimization-hardware-and-configuration | 2026-10-09 | official docs ("last updated 5 months ago"); hardware starting points, Frappe's MariaDB configuration, monitoring metrics
41. https://github.com/frappe/frappe/wiki/Using-Frappe-with-Amazon-RDS-(or-any-other-DBaaS) | 2026-10-09 | official wiki but dated (10 Dec 2019; MariaDB 10.3 parameters)
42. https://aws.amazon.com/about-aws/whats-new/2025/08/amazon-rds-mariadb-11-8-vector-support | 2026-10-09 | official AWS announcement (Aug 2025); read from a search-result summary
43. https://github.com/frappe/frappe_docker/releases/tag/v4.0.0 | 2026-10-09 | official release notes, 3 Oct 2026 (Debian Trixie, arbitrary UID, validation; notes LLM-summarised by the project)
44. https://github.com/frappe/frappe_docker/blob/main/docs/02-setup/02-build-setup.md | 2026-10-09 | official docs; apps.json, BuildKit secret, build args
45. https://github.com/frappe/frappe_docker/pull/1861 | 2026-10-09 | official PR, merged 15 Apr 2026: APPS_JSON_BASE64 build-arg replaced with a BuildKit secret
46. https://github.com/frappe/frappe_docker/blob/main/images/layered/Containerfile | 2026-10-09 | official source; FRAPPE_BRANCH used for the base/build image tag and `bench init`
47. https://github.com/frappe/frappe_docker/blob/main/docs/11-how-to/06-automated-builds-and-deployment.md | 2026-10-09 | official docs; CACHE_BUST strategies, migrator service
48. https://github.com/frappe/frappe_docker/blob/main/docs/08-reference/06-github-actions-image-workflows.md | 2026-10-09 | official docs; reusable `app-build-image.yml` workflow
49. https://hub.docker.com/v2/repositories/frappe/erpnext/tags (also frappe/base, frappe/build) | 2026-10-09 | official registry API; `latest` = develop; sizes and architectures
50. https://github.com/frappe/frappe_docker/blob/main/docs/02-setup/04-env-variables.md | 2026-10-09 | official docs; GUNICORN_WORKERS/THREADS/TIMEOUT, proxy variables
51. https://github.com/frappe/frappe_docker/tree/main/overrides (compose.mariadb.yaml: mariadb:11.8; compose.postgres.yaml: postgres:15.17; compose.backup-cron.yaml: @every 6h) and resources/core/nginx/security_headers.conf | 2026-10-09 | official source
52. https://github.com/frappe/frappe_docker/blob/main/docs/11-how-to/04-create-backups.md | 2026-10-09 | official docs; restic example; "add it as a CronJob" on Kubernetes
53. https://github.com/frappe/frappe_docker/blob/main/docs/01-getting-started/01-choosing-a-deployment-method.md | 2026-10-09 | official docs; Compose plus overrides is the canonical production method; apps baked in at build time
54. https://docs.k3s.io/installation/requirements | 2026-10-09 | official k3s docs; server minimum 2 cores / 2 GB
55. https://docs.k3s.io/add-ons/storage | 2026-10-09 | official k3s docs; Local Path Provisioner (RWO, binds to the node), Longhorn option
56. https://docs.k3s.io/networking/networking-services | 2026-10-09 | official k3s docs; bundled Traefik ingress and ServiceLB
57. https://longhorn.io/docs/latest/nodes-and-volumes/volumes/rwx-volumes/ | 2026-10-09 | official Longhorn docs; RWX through NFSv4.1 share-manager pods
58. https://docs.frappe.io/cloud/servers/guidelines-for-choosing-a-server-plan | 2026-10-09 | official Frappe Cloud docs ("7 months ago"); a bench needs about 400 MB minimum
59. https://github.com/resilient-tech/india-compliance (README) | 2026-10-09 | official; features, GPLv3, in-app purchases
60. https://docs.indiacompliance.app/docs/getting-started/india_compliance_account (source: github.com/resilient-tech/india-compliance-docs, pages/docs/getting-started/india_compliance_account.md) | 2026-10-09 | official docs; credits, minimum, free trial of 500, validity, bundled free on Frappe Cloud
61. https://indiacompliance.app/faq (content in https://indiacompliance.app/assets/js/faq.js) | 2026-10-09 | official pricing: ₹0.50 / ₹0.40 / ₹0.30 per credit excl. GST; AWS serverless, 99.99%
62. https://discuss.frappe.io/t/introducing-india-compliance/86335 | 2026-10-09 | official announcement by Sagar Vora (Resilient Tech, staff flags), 19 Feb 2022; later posts on pricing and the API Usage report (forum thread 145343)
63. India Compliance source on the version-16 branch: gst_india/api_classes/base.py (BASE_URL https://asp.resilient.tech), doctype/gst_settings/gst_settings.json, utils/e_invoice.py, client_scripts/e_invoice_actions.js, utils/e_waybill.py, overrides/item_tax_template.py, utils/__init__.py (validate_invoice_number, get_place_of_supply), constants (GST_INVOICE_NUMBER_FORMAT), print_format/gst_tax_invoice | 2026-10-09 | official source code
64. India Compliance docs (github.com/resilient-tech/india-compliance-docs, pages/docs/…): configuration/gst_setup, sales_transaction, purchase_transaction, tds_configuration; gst-reports/gstr1, gstr3b, gst_ims; miscellaneous/audit_trail, gstin_verification; purchase-reconciliation/* | 2026-10-09 | official docs
65. https://docs.frappe.io/erpnext/naming-series-as-per-gst-rules | 2026-10-09 | official ERPNext docs; Rule 46(b) 16-character limit
66. https://gstcouncil.gov.in/sites/default/files/2024-05/notification-12-2018-central_tax-english.pdf | 2026-10-09 | official GST Council copy; Rule 138(14)(e) checked in the PDF text
67. research-commerce-gst.md and sources-commerce-gst.md (this folder) | 2026-10-09 | internal sibling research on GST law (rates, 10/2025-CT(R), bill of supply, e-invoice thresholds); not re-verified here
68. https://github.com/frappe/hrms (README; hrms/regional/india/data/salary_components.json, setup.py, utils.py on version-16) | 2026-10-09 | official; India payroll scope
69. https://github.com/frappe/crm (README, compatibility table) | 2026-10-09 | official
70. https://github.com/frappe/helpdesk (README, pyproject.toml, doctype list) | 2026-10-09 | official; telephony dependency, no WhatsApp channel
71. https://github.com/frappe/lms (README) | 2026-10-09 | official
72. https://github.com/frappe/education (README, license.txt) | 2026-10-09 | official
73. https://github.com/frappe/insights (README; insights/insights/doctype/insights_data_source/insights_data_source.json) | 2026-10-09 | official; data source types MariaDB/PostgreSQL/SQLite; tag v3.14.2 dated 29 Sep 2026
74. https://github.com/frappe/drive (README: archived, now part of Suite) and https://github.com/frappe/suite | 2026-10-09 | official
75. https://github.com/frappe/books (README: end of life, superseded by frappe/frappe-books) | 2026-10-09 | official
76. https://github.com/frappe/print_designer (README) and https://cloud.frappe.io/marketplace/apps/print_designer | 2026-10-09 | official; supported versions "Version 15, Nightly"
77. https://github.com/frappe/webshop (README) | 2026-10-09 | official
78. https://github.com/frappe/payments (README; payments/payment_gateways/doctype/razorpay_settings/razorpay_settings.py on version-16) | 2026-10-09 | official source
79. https://github.com/shridarpatil/frappe_whatsapp and https://cloud.frappe.io/marketplace/apps/frappe_whatsapp | 2026-10-09 | community app (publisher Shridhar Patil); Marketplace lists v14–v16
80. https://github.com/frappe/erpnext-shipping (README; PRs #102 open 23 Jul 2026, #72 open 8 Jul 2025) | 2026-10-09 | official app; the PRs are community contributions
81. https://github.com/bwhtech/bwh_shipping | 2026-10-09 | community (BuildWithHussain), created 20 Aug 2026
82. https://github.com/harshpwctech/erpnext-shipping | 2026-10-09 | community fork
83. https://ecosire.com/apps/erpnext/erpnext-delhivery-shipping | 2026-10-09 | vendor; read only from a search-result summary
84. https://cloud.frappe.io/marketplace/apps/<app> for india_compliance, hrms, helpdesk, crm, lms, insights, education, raven, webshop, payments, builder, wiki, gameplan, offsite_backups, ecommerce_integrations, erpnext_shipping | 2026-10-09 | official Marketplace; "Supported versions"
85. https://github.com/frappe/offsite_backups (s3_backup_settings.json on version-16) and https://github.com/frappe/frappe/pull/32351 (merged 17 Jun 2025) | 2026-10-09 | official
86. https://github.com/frappe/ecommerce_integrations (ecommerce_integration_log.py/.json, doctype list on version-16); https://docs.frappe.io/erpnext/shopify_integration; https://docs.frappe.io/erpnext/unicommerce_integration | 2026-10-09 | official
87. https://docs.frappe.io/erpnext/e-commerce-integrations-for-erpnext | 2026-10-09 | official ERPNext docs ("3 months ago"); integration best practices
88. https://github.com/frappe/erpnext/blob/version-16/erpnext/modules.txt; erpnext/setup/install.py (DEFAULT_ROLE_PROFILES); erpnext/accounts/doctype/account/chart_of_accounts/verified/in_standard_chart_of_accounts.json | 2026-10-09 | official source
89. ERPNext docs, https://docs.frappe.io/erpnext/<page>: serial-no, batch, deferred-revenue, subscription, pricing-rule, sales-partner, credit-limit, customer-portal, payment-request, razorpay-integration, period-closing-voucher, bank-reconciliation, stock-reservation, service-level-agreement, issue, customer-group, territory, blanket-order, india-compliance-app, naming-series, data-import, notifications, work-order, bill-of-materials, subcontracting-order | 2026-10-09 | official docs (last-updated from 2 weeks to 7 months ago)
90. https://docs.frappe.io/framework/user/en/api/rest | 2026-10-09 | official docs ("1 week ago")
91. https://github.com/frappe/frappe/blob/version-16/frappe/api/v1.py, api/v2.py, client.py, __init__.py (ping) | 2026-10-09 | official source; routes, insert_many limit of 200, bulk_update
92. https://docs.frappe.io/framework/deployment/rate-limiting | 2026-10-09 | official docs ("1 week ago")
93. https://docs.frappe.io/framework/user/en/guides/integration/webhooks, plus frappe/integrations/doctype/webhook/__init__.py, webhook.py, webhook.json (version-16) | 2026-10-09 | official docs and source; after-commit queue, 3 attempts, 5 s timeout, events
94. https://docs.frappe.io/framework/user/en/desk/scripting/server-script | 2026-10-09 | official docs ("3 weeks ago")
95. https://docs.frappe.io/framework/oauth2 | 2026-10-09 | official docs ("8 months ago"); OAuth Settings, DCR, metadata
96. https://docs.frappe.io/framework/user/en/guides/integration/openid_connect_and_frappe_social_login and frappe/integrations/oauth2.py (version-16) | 2026-10-09 | official docs and source; HS256 id_token, well-known endpoints
97. https://docs.frappe.io/framework/user/en/guides/deployment/how-to-enable-social-logins and frappe/integrations/doctype/social_login_key/social_login_key.json (version-16) | 2026-10-09 | official docs and source; providers, sign_ups Allow/Deny
98. https://support.google.com/cloud/answer/10311615 | 2026-10-09 | Google official help (Manage App Audience: Internal user type); read from a search-result summary
99. Frappe v16 source: core/doctype/user/user.json, role/role.json, system_settings/system_settings.json, and the core doctype directory (system_health_report*, access_log, activity_log, api_request_log, permission_log, deleted_document, personal_data_deletion_request, personal_data_download_request, user_role_profile) | 2026-10-09 | official source; security defaults
100. https://github.com/frappe/frappe/blob/version-16/frappe/model/naming.py (set_new_name, validate_name) and model/document.py (insert(set_name, ignore_if_duplicate)) | 2026-10-09 | official source
101. https://microservices.io/patterns/data/transactional-outbox.html | 2026-10-09 | pattern reference (Chris Richardson); relay may publish more than once, consumers must be idempotent
102. https://docs.frappe.io/framework/user/en/bench/reference/backup | 2026-10-09 | official docs
103. https://docs.frappe.io/framework/user/en/guides/basics/how-to-enable-backup-encryption | 2026-10-09 | official docs ("4 months ago"); also frappe/utils/backups.py (site config backup, backup_encryption_key) and frappe/utils/password.py (Fernet `encryption_key` kept in site_config.json) on version-16
104. https://docs.frappe.io/framework/user/en/logging | 2026-10-09 | official docs ("1 week ago")
105. https://docs.frappe.io/framework/user/en/zero*_downtime_migrations | 2026-10-09 | official docs ("3 weeks ago")
106. https://docs.frappe.io/framework/user/en/security-faqs | 2026-10-09 | official docs ("6 months ago")
107. https://github.com/frappe/frappe/blob/version-16/frappe/www/desk.html, frappe/app.py, frappe/website/page_renderers/web_form.py | 2026-10-09 | official source; inline scripts, CORS, only web forms set CSP, X-Frappe-Request-Id
108. https://github.com/frappe/frappe/security/advisories | 2026-10-09 | official GitHub Security Advisories, counted by year and severity through the API (86 in total)
109. https://github.com/frappe/erpnext/security/advisories (also hrms, crm, lms, insights, helpdesk, india-compliance, payments) | 2026-10-09 | official; ERPNext 89 in total, 87 in 2026
110. https://frappe.io/security | 2026-10-09 | official disclosure policy
111. https://docs.frappe.io/framework/user/en/python-api/hooks | 2026-10-09 | official docs ("3 weeks ago"); fixtures, user_data_fields, doc_events
112. https://docs.frappe.io/framework/user/en/guides/app-development/exporting-customizations | 2026-10-09 | official docs
113. https://docs.frappe.io/framework/user/en/audit-trail | 2026-10-09 | official docs
114. https://frappe.io/cloud/sites | 2026-10-09 | official Frappe Cloud site plans (INR and USD, AWS Mumbai and Hetzner columns)
115. https://frappe.io/cloud/servers | 2026-10-09 | official Frappe Cloud server plans (AWS Regular/Enterprise, DigitalOcean, Hetzner; Mumbai rows)
116. https://frappe.io/cloud/pricing | 2026-10-09 | official overview (sites from ₹410, servers from ₹3,600, features)
117. https://docs.frappe.io/cloud/faq/billing and https://docs.frappe.io/cloud/billing/billing-cycle | 2026-10-09 | official Frappe Cloud docs; daily billing, CPU-time throttling, no user limit
118. https://www.digitalocean.com/pricing/droplets | 2026-10-09 | vendor official price table (Basic Regular: 8 GiB/4 vCPU $48, 16 GiB/8 vCPU $96)
119. https://gstzen.in/e-invoicing-api-integration-pricing | 2026-10-09 | vendor (GSP) published pricing, excluding taxes
120. https://discuss.frappe.io/t/postgresql-powered-sne-bootable-image-for-erpnext-development/164149 | 2026-10-09 | forum/community (third-party vyogo images, 12 Aug 2026)
121. https://github.com/frappe/frappe/wiki/Setup-MariaDB-Server | 2026-10-09 | official wiki (Revant Nandgaonkar, 21 Jan 2025)
122. https://github.com/frappe/frappe_docker/blob/main/docs/05-development/01-development.md | 2026-10-09 | official docs; at least 4 GB RAM for Docker in development
123. local: /Users/chinmoybhuyan/Desktop/Personal/Book/platform/examleaf-web/shop/models.py (Invoice, CreditNote, next_number, Product.hsn_code, Shipment couriers) and DEPLOYMENT.md (2 vCPU / 4 GB starting VM; R2/B2/S3 backups) | 2026-10-09 | the codebase itself
124. research-rbac-security.md (this folder), §1.3 role templates | 2026-10-09 | internal sibling research
125. https://pypi.org/project/rq-exporter | 2026-10-09 | community package; read from a search-result summary only
126. https://github.com/frappe/erpnext/wiki/Migration-Guide-to-ERPNext-version-15 | 2026-10-09 | official wiki; e-commerce moved to the Webshop app in v15
127. https://docs.frappe.io/cloud/benches | 2026-10-09 | official Frappe Cloud docs ("7 months ago"): public benches cannot add custom apps; private benches need site plans of $25 a month or more and a payment method
