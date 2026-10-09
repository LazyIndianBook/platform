# erp: the platform kept in step with ERPNext

ERPNext is the system of record for the business (the books, GST returns, physical stock by print run, the B2B side);
the platform stays the system of record for the product (accounts, content, the course, the storefront and its
documents). This app mirrors the platform's facts into ERPNext through an outbox and reads ERPNext's back. Its
contract is the Frappe app `examleaf_erp` (`../../examleaf-erp/API.md`), mapped in one module, `contract.py`. The
plan is `../../docs/examleaf-admin-control-panel-plan.md` sections 3.1, 3.2, 7.5 and 9.3; the research
`../../docs/research/2026-10-09-admin-control-panel/research-erpnext.md` section 5.

| File | What |
|---|---|
| `contract.py` | examleaf_erp's methods, fields, references, answers and errors, and the payloads, in one place (a rename on either side is a change here only) |
| `producers.py` | when the platform's facts become outbox rows (signal receivers), the switches, the initial load |
| `tasks.py` | the relay (every minute and nudged), the doorbells' task, the pull, the nightly reconciliation, `status()` |
| `inbound.py` | ERPNext's webhook (`/api/hooks/erp-events/`), the stock read back and the projection, the B2B mirrors, the pull |
| `reconcile.py` | the nightly comparison of a day, and the stock invariant |
| `inbox.py` | the staff inbox's items: dead letters, reconciliation differences |
| `client.py` | ERPNext's API on the integrations client (call log, circuit breaker, Retry-After) |
| `fake.py` | an in-memory ERPNext with examleaf_erp, for the tests and `ERP_MODE=fake` |
| `api.py` | the panel's API under `/api/v1/staff/erp/` (API.md "ERPNext sync (staff)") |
| `admin.py`, `management/commands/` | the admin pages; `erp_status`, `erp_replay`, `erp_initial_load`, `erp_reconcile`, `erp_pull` |

## Who owns what (plan 3.1)

One writer per fact; nothing else is copied. Personal data of B2C customers never leaves the platform: every
storefront invoice goes to ERPNext's one customer "Online Customers (B2C)" with the parcel's city, district, state and
PIN only (examleaf_erp refuses a `name`, `phone` or `line1`).

| Fact | Owner | Flow | Switch |
|---|---|---|---|
| Catalogue: products, bundles, HSN/SAC, GST rate, MRP | platform | `upsert_item`, `upsert_bundle` | `ERP_SYNC_CATALOGUE` |
| Storefront invoices and credit notes, with their legal numbers | platform | `create_sales_invoice`, `create_credit_note` (named with the number) | `ERP_SYNC_INVOICES` |
| Payments in (Razorpay, COD on delivery, transfers recorded by staff) and refunds out | platform | `create_payment_entry` (a refund against its credit note) | `ERP_SYNC_PAYMENTS` |
| Dispatch: the parcel that leaves (stock out of the print-run batches) | platform (`shipping`) | `create_delivery_note` | `ERP_SYNC_DELIVERIES` |
| COD remittances and Razorpay settlements (`shop/settlements.py`: posted once matched) | platform | `record_settlement` | `ERP_SYNC_SETTLEMENTS` |
| A B2B invoice's payment by the platform's link (`shop.InvoicePaymentLink`) | platform records it; FINANCE posts the Payment Entry in ERPNext by hand (`create_payment_entry` takes only the platform's own invoices) and records its name | none: a `b2b_payment` inbox item | `ERP_PULL_B2B` (the invoice's copy) |
| Physical stock: receipts, counts, transfers, damaged copies | **ERPNext** | doorbell, then `get_stock`; the 15-minute pull | `ERP_PULL_STOCK`, `ERP_STOCK_PROJECTION` |
| B2B customers, quotations, B2B invoices | **ERPNext** | doorbell, then a REST re-read into `ErpMirror`; the pull | `ERP_PULL_B2B` |
| Book codes, course entitlements, accounts, consent | platform | never in ERPNext | |

`ERP_ENABLED` is the master switch for talking to ERPNext (the relay, the pull, the reconciliation, its webhooks).
Every switch is an environment setting (`settings.py`, all off by default) **and** a staff feature flag of the same
name: once the panel sets one (`PUT /api/v1/staff/flags/ERP_SYNC_INVOICES/`, with its history and an audit event), it
wins over the environment until it is set back to null (`producers.switch`).

## The flows

**The outbox** (`ErpOutbox`): each fact is a row written **in the transaction of the change it describes** (an
invoice and its row commit or roll back together), by a receiver of the shop's and the shipping app's own signals:

| Event | When | examleaf_ref | Aggregate |
|---|---|---|---|
| `item.upserted` | a product saved with a change ERPNext would see (or deleted: disabled) | `item:<product id>` | the product |
| `bundle.upserted` | a bundle's lines changed (none: nothing) | `bundle:<product id>` | the product, after its item |
| `invoice.issued` | `shop.Invoice` created (at payment; COD: at dispatch) | `invoice:<number>` | the order |
| `payment.received` | a payment captured, once the invoice is in the outbox | `payment:<payment id>` | the order |
| `parcel.dispatched` | a parcel left (the order's shipped step, or a courier's first scan that says so, a re-shipment too), once the invoice is in the outbox | `delivery:<shipment id>` | the order |
| `credit_note.issued` | `shop.CreditNote` created | `credit_note:<number>` | the order |
| `refund.paid` | the credit note's refund, money out against it | `refund:<refund id>` | the order |
| `settlement.received` | a COD remittance remitted (`shipping.CodRemittance`) | `settlement:cod-<id>` | the order |
| `settlement.received` | a Razorpay settlement matched, live keys only (`shop.Settlement`, once; the Journal Entry moves Razorpay Clearing to the bank, the fees to an expense, their GST to input credit) | `settlement:<setl_ id>` | the settlement |

What hangs on an invoice is written only once the invoice is in the outbox; when it comes first (a COD parcel leaves
before its bill is made, a payment is captured before its invoice), the invoice's own producer writes it. Both lock
the order's row, so neither misses the other. Each document is written once (by its reference); an upsert again only
when its payload changed, and a newer upsert replaces an older one ERPNext refused (fix the product, save, done).
Test-mode orders (made with test keys on a live site) never sync. A producer never breaks the change it describes:
its own failure is undone in a savepoint and logged, and the nightly reconciliation names the document missing; a
payload that cannot be built is written without one and built again at the send.

**The relay** (`tasks.relay`, beat every minute and nudged at each commit that wrote rows): per aggregate, its first
row not sent, of the flows switched on (an earlier row that failed holds its aggregate's later rows, never another
aggregate's; a flow switched off holds its rows, and what follows them in their aggregate). A row is claimed with a
lease first, so two relays never send one; no transaction is held during the call. The body is the payload plus
`examleaf_ref` and `idempotency_key` (the row's id, after `ERP_INSTANCE_PREFIX`). Then:

- an answer, `duplicate` or not (ERPNext had it): sent, the answer kept on the row, its `ErpLink` written;
- the circuit open (no call made): waits 5 minutes, no try counted, the run stops;
- 429: waits what `Retry-After` says (else the backoff), no try counted, the run stops;
- a refusal that never succeeds unchanged (`contract.PERMANENT`: `invalid_request`, `conflict`, `cancelled`,
  `amendment_refused`, `doc_kind_mismatch`, `total_mismatch`, `over_credit`, `overpayment`, `nothing_to_deliver`,
  `idempotency_key_reused`): dead at once; an invalid `posting_date` is tried again (a clock just past midnight);
- anything else (unreachable, 5xx, `not_found`: a document of another aggregate not there yet, `insufficient_stock`,
  `tax_template_mismatch`, `permission_denied`, a payload that cannot be built): a try counted, again after a delay
  that doubles from a minute to six hours, jittered; dead after `ERP_MAX_ATTEMPTS` (10 tries: some 4 to 8 hours);
- Frappe's own 401 or 403 (the token): a try counted, the run stops.

A dead row is a dead letter (`integrations.IntegrationFailure`, task `erp.tasks.replay_row`, `dead_letter_created`)
and an item in the staff inbox; it holds its aggregate until staff replay it (from its first try) or discard it with a
reason (its aggregate goes on). Replayed or discarded in Admin → Integrations, the outbox follows.

**Reading ERPNext back** (`inbound.py`). ERPNext's webhooks are doorbells (Frappe tries three times, then gives up):
`POST /api/hooks/erp-events/` checks `X-Frappe-Webhook-Signature` (base64 HMAC-SHA256 of the raw body) in constant
time against the ERPNext account's webhook secret, or the previous one for 24 hours after a rotation; keeps the body
(`InboundEvent`, once per SHA-256: a replayed body is a duplicate); answers 200 at once. A missing or wrong signature,
no enabled account or `ERP_ENABLED` off: 403, kept as rejected without its body. The task then reads again:

- stock (`Stock Ledger Entry`, `Purchase Receipt`, `Stock Reconciliation`, …; `ERP_PULL_STOCK`): one `get_stock` of
  the storefront's warehouse (`ERP_WAREHOUSE`, examleaf_erp's `Main`) for a burst of doorbells (30 seconds), kept as
  `ErpStockSnapshot` per item (actual, reserved by ERPNext's own orders, projected, the batches);
- B2B documents (`Sales Invoice` without an examleaf_ref, `Quotation`, `Customer` of a B2B group; `ERP_PULL_B2B`):
  `GET /api/resource/…`, kept as `ErpMirror` with the fields `contract.MIRROR_FIELDS` lists (never a contact's);
- anything else: logged and ignored.

The pull (`tasks.pull`, every 15 minutes) reads `get_changes_since` per doctype from its cursor (`ErpCursor`:
`modified` and name, so documents saved in one microsecond are neither skipped nor repeated), page by page while
`has_more`: B2B pages mirrored and the cursor moved; stock's read to their end, then one `get_stock`, then the
cursor moved. A doctype ERPNext could not be asked about keeps its cursor for the next run.

**The projection** (`ERP_STOCK_PROJECTION`): with it on, each snapshot sets the product's copies for sale to
ERPNext's actual copies, less those ERPNext's own orders hold, less those reserved here and not shipped (paid or
placed with COD and not shipped, or shipped with the delivery note not yet in ERPNext), never below 0; under a lock
on the product, as checkout's reservation is. Off (shadow mode), the snapshots are only compared, nightly.

**The reconciliation** (`reconcile.py`, 03:30 India time for yesterday; `erp_reconcile --date`): ERPNext's
`daily_totals` against the platform's day, for each flow on: the invoices and credit notes (count, total and exempt
value exactly; taxable value and GST within 0.01 a taxed document: ERPNext rounds each tax once per invoice, the
platform's invoices each line, examleaf-erp/API.md deviation 7), payments and refunds by mode, COD settlements and the
Razorpay settlements posted for the day (their gross), the delivery notes and the copies they took per item; every
document of the day ERPNext has not answered for (no `ErpLink`), with where its outbox row is; with `ERP_PULL_STOCK`
the stock invariant per item (ERPNext's free copies less those reserved here and not shipped = the copies for sale
here). Differences are rows (`ErpReconciliationDifference`), one inbox item a run for those who may resolve them, a
`reconciliation_difference` signal each, and an email to `ERP_ALERT_EMAILS`: references, item codes and totals, no
personal data.

## The contract, field by field (examleaf-erp/API.md)

`contract.py` holds every name; this is what it sends. Money is rupees as strings with 2 decimals, dates `YYYY-MM-DD`
in India's time.

| Method | Fields sent | Read back |
|---|---|---|
| `upsert_item` | `item_code` (`EL-<product id, 5 digits>`, or ERPNext's name once linked), `item_name`, `kind` (the product's), `hsn_code`, `gst_rate`, `mrp`, `weight_grams`, `is_active`, and when known `isbn` (only a valid one), `subject`, `class_level`, `board`, `edition` | `name` |
| `upsert_bundle` | `item_code`, `items: [{item_code, qty}]`, `is_active` | `name` |
| `create_sales_invoice` | `invoice_number`, `posting_date`, `order_number`, `channel` (`staff` for an order staff made, else `web`), `doc_kind` (checked by ERPNext), `shipping_address: {city, district, state, pin}`, `items: [{item_code, qty, rate, discount (the line's rupees off), hsn_code, gst_rate}]`, `shipping_fee`, `total`; `shipping_hsn_code` and `shipping_gst_rate` only when ERPNext cannot tell (no goods, or goods at several rates) | `name`, `grand_total`, `taxable_value`, `exempt_value`, `tax_total` |
| `create_credit_note` | `credit_note_number`, `invoice_number`, `posting_date`, `reason` (`Refund <id> of order <number>`: never staff's words), `items: [{item_code, amount}]` (each line's credit, tax included; no `qty`: the platform does not know which copies came back), `shipping_credit`, `total` | `name`, `total_credit` |
| `create_payment_entry` | `invoice_number` (the credit note's for a refund), `amount`, `posting_date` (the day it was captured; a refund's, processed), `mode`, `reference_no` | `name`, `payment_type`, `outstanding_after` |
| `record_settlement` | `kind`, `settlement_id`, `posting_date`, `gross_amount`, `fee`, `tax_on_fee`, `net_amount`, `utr` | `name` |
| `create_delivery_note` | `invoice_number`, `posting_date` (the day it left), `warehouse`, `courier`, `tracking_number` (no `items`: everything not yet delivered) | `name`, `batches` |
| `get_stock` | `warehouse`, `by_batch` | `items: [{item_code, actual_qty, projected_qty, reserved_qty, batches}]` |
| `get_changes_since` | `doctype`, `modified_after` (`2000-01-01 00:00:00` before the first read), `after_name`, `limit` | `rows`, `has_more`, `next` |
| `daily_totals` | `date` | `invoices`, `credit_notes`, `payments.receive`, `payments.refund`, `settlements`, `shipped` |
| `ping` | nothing | `name`, `versions` (the connection test) |

Payment modes: `razorpay`, `cod`; a payment staff recorded offline is `neft` unless its reference says UPI (`upi`) or
cheque (`cheque`), and its reference keeps only its words with a digit in them (a UTR, never a name typed beside it).
COD's reference is the parcel's AWB. `upsert_b2b_customer` is in the fake but not called: the B2B parties are loaded
in ERPNext by Data Import (plan 9.3).

## Shadow mode and the cut-over (plan 9.3)

1. **Shadow mode, from Phase B**: an account for the staging ERPNext site, `ERP_ENABLED`, the five `ERP_SYNC_*`,
   `ERP_PULL_STOCK` and `ERP_PULL_B2B` on, `ERP_STOCK_PROJECTION` off. The storefront's stock stays its own; the
   reconciliation reports what differs every night.
2. **The initial load** (below), on the staging site, then the parallel run from 1 January 2027: the outbox mirrors
   every live document, the reconciliation runs every night. The switch needs 30 days in a row without an unexplained
   difference, and one month's GSTR-1 from India Compliance matching the platform's export table by table.
3. **The night of 31 March 2027**: the last FY 2026-27 documents numbered; the account switched to production's site
   (a second account, mode live, enabled; the staging one disabled); the flows switched on in order: catalogue, then
   stock (`ERP_PULL_STOCK`, then `ERP_STOCK_PROJECTION`: ERPNext sets the copies for sale), then invoices and credit
   notes, payments, deliveries, settlements; a reconciliation the next morning (`erp_reconcile`).
4. **After**: nightly, read every morning by FINANCE for the first two weeks.

**Rollback by switch**: a flow switched off writes no new rows and holds the rows it has (and their aggregates'
later ones); switched on again, they go. What it did not write meanwhile is written by the initial load again
(`--invoices-from` the day it went off: what the outbox has is not written twice). `ERP_ENABLED` off stops the talking
only: the flows still write, and the rows wait. For stock, `ERP_STOCK_PROJECTION` off hands the copies for sale back to
the platform's own number, as the last projection left it; check it with a count. The platform never stops being the
record of its documents, so ERPNext's mirror can be rebuilt by replaying the outbox.

## Operations

- **Status**: `manage.py erp_status` (or `GET /api/v1/staff/erp/status/`): the switches, the account and its circuit,
  the outbox by state with its oldest row waiting, the aggregates held by a dead row, the cursors, the last
  reconciliation. `/health/integrations/` fails while dead letters wait.
- **A dead letter** (an inbox item, Admin → ERPNext sync → Outbox rows, or `/api/v1/staff/erp/dead-letters/`): read
  its error (ERPNext's code and words, its Sync Log row's id in the answer), fix the cause there or here, then replay
  it (`erp_replay <id>`, `--dead` for all) or discard it with a reason (made by hand in ERPNext, for instance).
- **Differences** (the morning's email, an inbox item, Admin → Reconciliation runs): each says what, here and there;
  find the document (its reference), fix it, resolve the difference with a note (`erp.resolve_difference`).
- **The initial load**: from the panel, the staff job `erp_initial_load` (`POST /api/v1/staff/jobs/`, `dry_run` first;
  above the starter's `bulk_rows` an approver passes it first), or `manage.py erp_initial_load [--invoices-from
  YYYY-MM-DD] [--apply]`. It writes every product's item, then the bundles, then each invoice since the day with what
  hangs on it, in order, each flow while its switch is on, each document once. Each run is an audit event
  (`erp.initial_load`), and an applied one tells the owners. Opening stock, suppliers and open B2B receivables go into
  ERPNext by its own Data Import.
- **The pull by hand**: `erp_pull [--doctype "Sales Invoice"] [--restart]` (restart: the cursors from the start, the
  mirrors rebuilt).
- **What a lost ERPNext backup costs** (research 6.1): the documents the platform mirrored are rebuilt by replaying
  the outbox (`erp_replay --sent-since` the backup's time: every row ERPNext answered since is sent again, in order and
  with its key, ERPNext answering duplicates for what the backup kept; the initial load would not, as it writes only
  what the outbox lacks); what only ERPNext held (purchases, journals, stock receipts and counts, B2B documents,
  payroll) is lost back to its last backup, which is why ERPNext's own backups run every 6 hours. The platform's
  mirrors of B2B documents and stock snapshots are rebuilt by `erp_pull --restart`.

## The staff app (the panel)

| Permission | Catalogue (area "ERP sync") | Roles |
|---|---|---|
| `erp.view_sync` | low: every read of `/api/v1/staff/erp/` | OWNER, ADMIN, FINANCE, AUDITOR |
| `erp.replay_sync` | high (a re-authentication within 5 minutes): replay or discard a dead letter | OWNER, ADMIN |
| `erp.resolve_difference` | medium: resolve a reconciliation's difference | OWNER, ADMIN, FINANCE |
| `erp.run_initial_load` | high, the owners told: the initial load's job | OWNER, ADMIN |

The endpoints are `staff.api.StaffView`s under `/api/v1/staff/erp/`, so they answer on the admin host only and every
refusal is an `authz_fail` event; replay, discard, resolve and the initial load are audit events (`erp.replay`,
`erp.discard`, `erp.resolve`, `erp.initial_load`; `erp.resend` for `erp_replay --sent-since`) from wherever they are
done (the panel, the admin, a command). The inbox kinds `sync_failed` (a dead letter, for `erp.replay_sync`) and
`reconciliation` (a run's differences, for `erp.resolve_difference`) are done once the row is replayed or discarded,
or the run's last difference resolved.

## Development

`ERP_MODE=fake` answers from `fake.py` (in one process: with a broker, the worker has its own). Make an integration
account (Admin → Integrations: provider ERPNext, mode test, enabled, any credentials), switch `ERP_ENABLED` and the
flows on in `.env`, and the outbox, the relay, the pull and the reconciliation run against it. Against the dev stack
of `examleaf-erp/` (`./dev.sh up`, `./dev.sh keys`): `ERP_MODE=erpnext` and the credentials
`{"api_key": …, "api_secret": …, "base_url": "http://127.0.0.1:8300", "site_name": "erp.localhost"}`.

The tests (`pytest erp`) run everything against the fake, which refuses what examleaf_erp refuses (unknown fields,
missing items and invoices, stock it has not got) and rounds GST as ERPNext does.
