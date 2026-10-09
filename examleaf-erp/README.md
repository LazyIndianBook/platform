# ExamLeaf ERP

ExamLeaf's back office: ERPNext v16.50.0 with India Compliance v16.10.0 (GST), HRMS v16.50.0, offsite_backups and
`examleaf_erp`, the private Frappe app in this directory. ERPNext keeps the books, the GST returns, the stock by print
run and the B2B side (schools, distributors, booksellers); the platform (`examleaf-web/`) stays the shop and the master
of B2C orders, which reach ERPNext through `examleaf_erp`'s API (`API.md`). The decisions behind it are
`docs/research/2026-10-09-admin-control-panel/research-erpnext.md` ("research n" below).

| Path | What it holds |
|---|---|
| `apps/examleaf_erp/` | the Frappe app: hooks, fixtures, five doctypes, the sync API (`api.py`, `sync.py`), GST rules (`gst.py`, `events.py`), scheduled jobs (`tasks.py`), the bootstrap (`setup.py`), five print formats, 56 tests |
| `API.md` | the contract with the platform's Django `erp` app: methods, idempotency, answers, errors, webhooks, and the contract deviations |
| `compose/` | the development stack (`./dev.sh`): MariaDB 11.8.9, Valkey 8.1.10, `frappe/erpnext:v16.50.0` with India Compliance, the app mounted from here |
| `image/` | the production image: `build.sh`, `apps.json`, the second-stage `Containerfile` |
| `UPGRADE.md` | the weekly patch, a new app, the next major |
| `../.github/workflows/erp-image.yml` | lint, tests on MariaDB, image build, Trivy, push on an `erp-v*` tag |

## Who owns what (research 5.8)

One writer per fact.

| Fact | Master | Flow |
|---|---|---|
| Catalogue (items, HSN/SAC, GST rates, MRP, bundles) | platform (`Product`, `BundleItem`) | `upsert_item`, `upsert_bundle` |
| B2C customers | platform | not copied: every B2C invoice goes to one customer, "Online Customers (B2C)", with the parcel's city, district, state and PIN only (DPDP: names, phones and streets stay in the platform) |
| B2C invoices and credit notes | platform (legal numbers `EL/…`, `CN/…`) | `create_sales_invoice`, `create_credit_note`, named with those numbers |
| Payments, refunds, settlements | platform (Razorpay, COD) | `create_payment_entry`, `record_settlement` |
| Dispatch (stock out) | platform (`Shipment`) | `create_delivery_note`; ERPNext picks the print runs |
| Physical stock (receipts from printers, counts, transfers, damaged copies) | **ERPNext** | webhook doorbell, then the platform pulls `get_stock` |
| B2B customers, quotations, orders, invoices, credit, price lists, terms | **ERPNext** | webhook doorbell and `get_changes_since`, if the website must show them; `upsert_b2b_customer` only for the first load |
| School adoptions, specimen copies, distributor agreements, sale-or-return dispatches | **ERPNext** (this app's doctypes) | |
| Purchases, journals, payroll, GST returns | **ERPNext** | |
| Staff identity | Google Workspace and the platform's RBAC | Google sign-in on both, roles below |
| Book codes, course entitlements | platform | never in ERPNext |

Every night the platform compares its day with `daily_totals` (invoices, taxable and exempt values, credit notes,
payments by mode, shipped copies); differences open a task for staff.

## For the Kubernetes chart (`deploy/`)

- **Image**: `ghcr.io/lazyindianbook/examleaf-erp:16.50.0-<commit>`, the tag `image/build.sh` prints (CI pushes it on an `erp-v*`
  tag). Set `image.repository: ghcr.io/lazyindianbook/examleaf-erp` and `image.tag`; the same image runs every component.
- **createSite Job**: `installApps: [erpnext, india_compliance, hrms, offsite_backups, examleaf_erp]`, `dbType:
  mariadb` (MariaDB 11.8).
- **Then, once** (a `custom` Job, or `kubectl exec` into a worker pod, not the gunicorn one): the site config keys
  below (`bench --site <site> set-config <key> <value>`, secrets from a Kubernetes Secret), the outgoing Email Account,
  then `bench --site <site> execute examleaf_erp.setup.bootstrap`, then the sync user's keys (below).
- **Every upgrade**: backup Job, new tag, `migrate` Job, `clearCache` Job (`UPGRADE.md`). `migrate` re-imports the
  fixtures and runs `examleaf_erp.setup.after_sync`.
- **Network**: ERPNext is staff-only and not on the public internet (research 6.6): Desk behind Google sign-in and an
  IP allowlist or VPN; the platform reaches the API, and ERPNext reaches the platform's webhook URL, inside the cluster.
- `allow_reads_during_maintenance: 1` in the site config keeps Desk readable during `migrate`.
- Do not run `bench browse` in the gunicorn pod: gunicorn is PID 1 there, reaps the `xdg-open` that browse leaves
  behind, and shuts down on its exit code 3 (seen on the dev stack; `./dev.sh login` runs it in a container of its own).

## Site config

The bootstrap and the hooks read `examleaf_*` keys from the site config (`compose/site_config.example.json` holds
placeholders; nothing secret is in the repository).

| Key | What |
|---|---|
| `examleaf_company_name`, `examleaf_company_abbr` | "ExamLeaf LLP", "EL" (the abbreviation is in every account name: `Main Bank - EL`) |
| `examleaf_gstin` | the company's GSTIN (required; the bootstrap stops without it) |
| `examleaf_address_line1`, `examleaf_address_line2`, `examleaf_city`, `examleaf_pincode`, `examleaf_state` | the registered address printed on every document |
| `examleaf_email`, `examleaf_phone` | the company's contact on documents |
| `examleaf_bank_account` | the bank account the wizard makes ("Main Bank") |
| `examleaf_sync_user`, `examleaf_sync_user_restrict_ip` | the integration user (`erp-sync@examleaf.in`) and the platform's egress IPs |
| `examleaf_webhook_base`, `examleaf_webhook_secret` | the platform's webhook URL and HMAC secret; the six webhooks stay off until both are set |
| `examleaf_google_domain`, `examleaf_google_client_id`, `examleaf_google_client_secret` | Google sign-in (off until the id and secret are set) |
| `examleaf_allow_test_series` | `1` on development and staging only: the `T/` and `TC/` series |
| `rate_limit` | Frappe's own: `429` with `Retry-After` past it |

## Local setup

Nothing is installed on the Mac (ERPNext v16 wants Python 3.14 and Node 24): everything runs in Docker (colima or
Docker Desktop), about 1.5 GB of memory.

```sh
cd examleaf-erp/compose
./dev.sh up --minimal     # waits until 3 GB are free; builds the dev image once; without scheduler and workers
./dev.sh build            # the dev image again, after a change of dev.Containerfile (asks the registry for the base)
./dev.sh new-site         # erp.localhost: ERPNext, India Compliance, examleaf_erp, the bootstrap (some minutes)
./dev.sh test             # the app's 56 tests
./dev.sh login            # a Desk sign-in link for Administrator, http://127.0.0.1:8300/app?sid=…
./dev.sh keys             # the sync user's key into compose/.sync-keys, then:
curl -X POST http://127.0.0.1:8300/api/method/examleaf_erp.api.ping \
  -H "Authorization: token $(cat .sync-keys)" -H "Content-Type: application/json" -d '{}'
./dev.sh down             # stop (keeps the data); ./dev.sh destroy drops it
```

- `compose/.env` (made on first use, gitignored) holds random passwords for MariaDB's root and Administrator.
- **Edits**: the app is mounted, so bench commands and tests see an edit at once; after a Python edit,
  `./dev.sh restart` for the web and worker processes (gunicorn loads the app once). Schema changes (doctypes, custom
  fields): `./dev.sh bench --site erp.localhost migrate`.
- **Signing in**: the bootstrap turns on two-factor sign-in, which Administrator needs too (it holds every role, EL
  Admin among them), and its first use emails the authenticator's set-up; the dev stack sends no email, hence
  `./dev.sh login`.
- **Developer mode** (to make or change doctypes and print formats as files): `./dev.sh bench --site erp.localhost
  set-config developer_mode 1`, then `./dev.sh restart`.

## The app

### Fixtures

`hooks.py` lists 18 fixtures, numbered in that order (`fixture_auto_order`): the custom fields and property setters of
module ExamLeaf ERP, the EL roles and role profiles, price lists (MRP, School, Distributor Tier 1 and 2), payment terms
and templates, the five modes of payment, the three GST print headings, the customer groups (Online B2C, School,
Distributor, Bookseller, Teacher), the territory tree, the item groups, two example pricing rules (disabled), the
Quotation and Distributor Agreement approval workflows, six webhooks (off) and three notifications.

**Frappe imports every fixture again on every `migrate`** (delete and insert): a change made in Desk is lost at the
next upgrade. So a fixture changes in a development site and in git:

1. change it in the dev site (Desk, or `./dev.sh bench --site erp.localhost console`);
2. `./dev.sh bench --site erp.localhost export-fixtures --app examleaf_erp`;
3. review the diff of `apps/examleaf_erp/examleaf_erp/fixtures/` and commit it.

Export from a site whose config has no webhook URL: the webhooks' `request_url` is exported (their secret is not).
The filters export by name, so a new role, pricing rule, webhook or notification is named `EL …`.

**No Server Scripts** (research 5.3): they are off by default since v15 and run in RestrictedPython; everything here
is code in the app, in git, tested, and in the image.

### Adding a custom field or a doctype

- A **custom field**: Customize Form in the dev site, module **ExamLeaf ERP** (the fixture filter), then export as
  above. A field that must hold for a document the API makes also goes into `api.py` and a test.
- A **doctype**: developer mode on (Local setup), then New DocType in Desk with module ExamLeaf ERP and "Is Custom"
  off: Frappe writes `apps/examleaf_erp/examleaf_erp/examleaf_erp/doctype/<name>/` through the mount. Add the
  controller's rules and a test in `tests/`, then `migrate` the other sites.
- A **print format**: `apps/examleaf_erp/examleaf_erp/examleaf_erp/print_format/<name>/` (`.json` with `standard:
  "Yes"` and `pdf_generator: "chrome"`, the template in the `.html` beside it, sharing the macros of
  `apps/examleaf_erp/examleaf_erp/templates/print/answer_script.html`); the numbers come from the jinja methods in
  `printing.py`. Desk's PDF button uses the format's Chrome renderer; a call to
  `/api/method/frappe.utils.print_format.download_pdf` must say `pdf_generator=chrome` (without it, wkhtmltopdf).

### Territories

India > Assam > its 35 districts (the India Post directory's spelling, as the platform's `import_pincodes` stores
them; Bajali and Tamulpur included), India > North East > the other seven north-eastern states, India > Rest of India.
A B2C invoice takes the parcel's district, or Assam, or its north-eastern state, or Rest of India. A district the
directory adds or renames: one line in `constants.ASSAM_DISTRICTS` and in `fixtures/11_territory.json`.

### Doctypes

- **ExamLeaf Sync Log**: one row per API call (inbound) and per nightly snapshot; Resync for EL Admin and EL Finance;
  successful rows deleted after 90 days.
- **School Adoption**: which school uses which book, per academic year, class and subject (one row each), and why a
  lost school left.
- **Distributor Agreement** (submittable, approval workflow): districts, item groups, exclusivity (refused if another
  customer's approved agreement overlaps in district, period and item group and either is exclusive), discount; on
  approval it sets the customer's payment terms, credit limit, agreement end and sale-or-return cap, and a pricing
  rule.
- **Specimen Request**: free copies for teachers, with the delivery challan that took them and a follow-up date.
- **SOR Dispatch**: copies sent on sale or return; CGST s.31(7) wants them invoiced or returned within six months, so a
  daily job marks them Due Soon at five months and Overdue after six (and notifies).

### Hooks and jobs

- `examleaf_ref` on nine doctypes, unique and fixed once set.
- A platform-numbered invoice cannot be cancelled or amended (a credit note instead; Rule 46(b) numbers are never
  issued again).
- Each Sales Invoice gets its document kind and print heading from its lines' GST treatment; exempt books are left out
  of India Compliance's e-way bill threshold (Rule 138(14)); a quotation records its highest discount for the
  approval workflow.
- Daily: the SOR clock, the Sync Log purge. 02:00: a snapshot of `daily_totals` for the day before.
- `user_data_fields` (DPDP): a Personal Data Deletion Request also redacts the phone of a B2B customer found by the
  person's email, and covers the Sync Log rows the person made.

### The bootstrap

`bench --site <site> execute examleaf_erp.setup.bootstrap` makes, or completes, the company through ERPNext's setup
wizard (India's chart of accounts, India Compliance's GST accounts and templates, the audit trail on), the Razorpay
Clearing and COD in Transit accounts, the Main, Damaged and At Printer warehouses, the GST Exempted template and the
HSN links, the delivery charge item, the B2C customer, the Mode of Payment accounts, the sync user and its
permissions, and the webhooks. Running it again changes nothing. The **settings** (hardening below, GST, stock,
selling) are applied on its first run only, so a later run never undoes what Finance changed after go-live;
`--kwargs "{'reset_settings': 1}"` applies them again.

### The sync user

`erp-sync@examleaf.in`, role EL Sync only: no Desk, no password, write on what the API makes and nothing else
(`setup.SYNC_PERMISSIONS`; a test runs the whole API as this user). Its key:

```sh
bench --site <site> execute frappe.core.doctype.user.user.generate_keys --args "['erp-sync@examleaf.in']"
```

prints `api_key` and `api_secret` once: put them in the platform's Kubernetes Secret (`Authorization: token
key:secret`), never in git. Set `examleaf_sync_user_restrict_ip` to the platform's egress addresses (a `restrict_ip`
bypass with API keys was fixed in v16.33.0). Generating keys again revokes the old secret.

## Roles (research 5.5)

| Platform role | ERPNext role profiles | Holds |
|---|---|---|
| OWNER | EL Admin + EL Finance | everything; a named user with two-factor sign-in; Administrator stays sealed (break-glass) |
| ADMIN | EL Admin | System Manager, Sales, Stock, Purchase and Item managers, Report Manager; two-factor |
| FINANCE | EL Finance | Accounts Manager and User, Report Manager, India Compliance's GST pages; two-factor |
| PACKER | EL Packer | Stock User (delivery notes, pick lists, stock entries) |
| SALES (B2B) | EL Sales | Sales User and Manager, Stock User; a User Permission per territory if needed |
| AUDITOR | EL Auditor | Auditor (read); time-bound in the platform |
| HR | HRMS's HR User or HR Manager | |
| SERVICE | the sync user | EL Sync |
| SUPPORT, CONTENT_EDITOR, REVIEWER, MARKETING, TEACHER_PARTNER | none | no ERPNext access |

v16 users can hold several role profiles. Make users by hand (fewer than about 15 staff) with Google sign-in; disable
them, never delete, so the audit links stay.

## Hardening checklist (research 6.5, 6.6)

Set by the bootstrap:

- [x] sessions expire after 8 hours (default 170), one session per user
- [x] two-factor sign-in (authenticator app) for EL Admin and EL Finance, so for Administrator too
- [x] no sign-in by email link (on by default); password strength 3 of 4; lockout after 5 failed attempts
- [x] tracebacks hidden from users (they stay in the Error Log); telemetry off
- [x] no website sign-ups; Google sign-in with sign-ups denied (only users made beforehand), hinting the
      `examleaf.in` domain
- [x] the audit trail on (irreversible, MCA rule since 1 April 2023)
- [x] the sync user least-privileged; webhooks signed (HMAC-SHA256)

For the operators:

- [ ] the outgoing Email Account before the first sign-in (two-factor set-up is emailed)
- [ ] the Google OAuth client with an **Internal** audience (the real domain lock: `hd` only hints), then
      `disable_user_pass_login` for staff once Google sign-in works
- [ ] Administrator's password in the vault, used only to break glass
- [ ] ERPNext off the public internet: Google sign-in plus an IP allowlist or VPN for Desk, no portal, no sign-ups
- [ ] `examleaf_sync_user_restrict_ip` set
- [ ] security headers at the ingress (HSTS, `nosniff`, `Referrer-Policy`, `frame-ancestors`; a strict CSP needs
      testing, Desk uses inline scripts)
- [ ] the weekly patch, and within 7 days of a critical or high advisory (`UPGRADE.md`; 2026 to 9 October: 87 ERPNext
      and 53 Frappe advisories, 10 critical)
- [ ] backups every 6 hours to R2 with their `site_config.json` (its `encryption_key` decrypts the stored secrets),
      and a restore rehearsed
- [ ] `rate_limit` in the site config

## India Compliance's GST API: a processor

India Compliance's API features (GSTIN details and status, e-way bills, e-invoices, filing GSTR-1 and pulling 2A/2B)
call `https://asp.resilient.tech`, Resilient Tech's gateway, which relays to a GSP it does not name (research 4.1).
Invoice and party data therefore pass through a third party: record it as a processor in the DPDP records before
buying credits (₹0.50 to ₹0.30 a call, 1,000 a year at least; under 5,000 calls a year expected). Nothing here turns
the API on; GSTIN format and checksum are checked offline without it, and e-invoicing stays off until turnover passes
₹5 crore.

## Licences (research 1.3)

ERPNext, India Compliance and HRMS are GPLv3; Frappe and offsite_backups are MIT. `examleaf_erp` links them and is
GPLv3 too (`apps/examleaf_erp/license.txt`). It runs only on ExamLeaf's servers and is not distributed, which the GPL
allows without publishing it; if a copy is ever given to anyone outside ExamLeaf LLP, it goes with its source under
GPLv3. "Frappe" and "ERPNext" are registered trademarks: the app is `examleaf_erp`, never "ERPNext" anything.

## Open questions

- **GST rounding**: ERPNext rounds each tax on the invoice's taxable value; the platform's `shop.invoices` may print a
  tax 0.01 apart on a taxed line (`API.md`, deviation 7). Totals agree; decide whether the platform adopts ERPNext's
  rounding or the reconciliation keeps its 0.01 tolerance.
- **For the CA**: books as "Exempted" or "Nil-Rated" in GSTR-1 Table 8; bills of supply sharing the `EL/` series with
  tax invoices; who files GSTR-1 (India Compliance over the API, or the CA's software from the export); Razorpay's fee
  GST as input tax through the settlement journal or through a purchase invoice.
- **Repeated value-only credits** on one line stop once its units are used (`API.md`, create_credit_note).
- **The webhook receiver's URL** on the platform (`examleaf_webhook_base`) and its secret.
