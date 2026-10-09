# The sync in shadow mode against a real ERPNext: what was run and what it showed

One run on 10 October 2026, 01:45 to 02:32 India time, of this app against the ERPNext of `examleaf-erp/compose/`
standing in for the staging site, with every flow switched on through the panel as `README.md` "Shadow mode and the
cut-over" says. Everything below is the platform's own code on `phase-b` (a28d5fc) and the fixes the run made (section
10). The machine: a MacBook (Apple silicon, 16 GB) whose Docker is a Colima VM of 4 CPUs, 6 GiB and a 60 GiB disk
(Docker 29.2.1, Compose 2.39.1), shared with five other agents' work; the Mac's disk was 98 % full.

| | |
|---|---|
| ERPNext | Frappe 16.50.0, ERPNext 16.50.0, India Compliance 16.10.0, examleaf_erp 1.0.0; MariaDB 11.8.9, Valkey 8.1.10 |
| Its site | `erp.localhost` on `http://127.0.0.1:8300`, on the volumes an earlier run made on 9 October (its own test documents dated that day: 153 invoices, 38 credit notes); `examleaf_allow_test_series: 1` |
| The platform | Python 3.14, Django 6.1.2, Celery 5.6.3; a SQLite file of its own; Django on `127.0.0.1:8123`, a Celery worker (2 processes) and beat on the Mac's Redis (database 11, the cache on 12: the other agents use 2, 9 and 14) |
| Its settings | `ERP_MODE=erpnext`, `ERP_ENABLED=1`, `ERP_PULL_STOCK=1`, `ERP_PULL_B2B=1`, the five `ERP_SYNC_*` off until the panel switched them on, `ERP_STOCK_PROJECTION=0`; Razorpay's test keys (`rzp_test_…`), so its orders are numbered in the T series and are not test orders of a live site (`Order.is_test` is false: they sync) |
| Money | no Razorpay account: a capture and a refund were recorded as their webhooks record them (`record_capture`, `refund_processed`) |

## 1. The stack and the platform

```sh
cd examleaf-erp/compose
docker compose --env-file .env up -d --no-build      # 01:53:49 → 01:54:00 (./dev.sh up does this now, the image there)
./dev.sh new-site                                     # 01:55:11 → 01:55:18: the site existed; config and bootstrap again
./dev.sh bench --site erp.localhost migrate           # 01:55:23 → 01:55:43
./dev.sh keys                                         # the sync user's key into compose/.sync-keys
curl -X POST http://127.0.0.1:8300/api/method/examleaf_erp.api.ping -H "Authorization: token $(cat .sync-keys)" \
  -H "Content-Type: application/json" -d '{}'         # 200 in 158 ms, as erp-sync@examleaf.in
```

- **The dev image** was not on the machine (its volumes were). `./dev.sh up` first hung in `docker-credential-desktop
  get` (the user's Docker config names Docker Desktop's credential store, and Docker here is Colima: the run used a
  config of its own without one), then BuildKit asked the registry for `frappe/erpnext:v16.50.0`, which had been pushed
  again (digest `ac5b4591…` there, `833bceb5…` here, built 7 October), and started pulling 1.3 GB of new base layers.
  Stopped; the classic builder (`DOCKER_BUILDKIT=0 docker build -f dev.Containerfile …`) used the local base and built
  `examleaf/erp-dev:16.50.0-ic16.10.0` in 90 seconds. `./dev.sh up` now builds only when the image is missing
  (2bc7d4f).
- **Memory**: 2,814 MB free at 01:52, so the start waited until 3,325 MB were free (01:53:27), as `dev.sh` asks.
- **The doorbell's way back**: ERPNext's containers reach the Mac at Colima's gateway, `192.168.5.2`; a Compose
  override (`extra_hosts`, not in the repository) named it `platform.localhost`, because the platform with `DEBUG=1`
  accepts only `*.localhost` hosts. `examleaf_webhook_base` was `http://platform.localhost:8123/api/hooks/erp-events/`,
  `examleaf_webhook_secret` the account's webhook token, and `bench execute examleaf_erp.setup.configure_webhooks`
  turned the six webhooks on.
- **The platform**: `migrate` (212 migrations, 26 s); `import_pincodes shop/fixtures/pincodes-sample.csv`; `seed_shop
  --stock 20` (the starting catalogue: eight books and the Physics bundle); one product more, the Physics revision
  course (SAC 999293, 18 %, ₹999), for a taxed line; the ERPNext account (provider `erpnext`, mode test, credentials
  `{api_key, api_secret, base_url: http://127.0.0.1:8300, site_name: erp.localhost}`): its connection test answered
  "Connected: ERPNext answered the ping (erp.localhost, examleaf_erp 1.0.0)". An OWNER with an authenticator app (and
  a passkey's row, as the staff API asks of the privileged roles) signed in over HTTP through allauth's headless flow,
  password then the authenticator's code, before each batch of panel calls: a fresh sign-in, so the high-risk ones
  (flags, replay, discard) were within their 5-minute re-authentication.
- **Two things a local run needs** (now in `README.md` "Development"): the worker's pool on macOS spawns its children,
  which then fail every task (`not enough values to unpack`) unless `FORKED_BY_MULTIPROCESSING=1`; and Django, a
  worker and beat on one SQLite file lock each other out (`database is locked`) without
  `?timeout=30&transaction_mode=IMMEDIATE` in `DATABASE_URL` (quoted in a shell: the `&`).
- **The first pull** (beat, 02:00): from the start of ERPNext's history, `Stock Ledger Entry` 86 rows, `Sales Invoice`
  192, `Quotation` 6, `Customer` 51, in 5.9 seconds and 256 calls. It read every storefront invoice back over REST to
  mirror one B2B invoice, and mirrored 50 schools and distributors as "Draft" (fixed: 4290309, section 10).

## 2. The initial load

```sh
PUT /api/v1/staff/flags/ERP_SYNC_CATALOGUE/ {"value": true, "reason": "…"}    # 02:01:11, 200 in 0.07 s
manage.py erp_initial_load            # Dry run, nothing written; would write: 1 bundle.upserted, 10 item.upserted.
manage.py erp_initial_load --apply    # 02:01:21: Wrote: 1 bundle.upserted, 10 item.upserted.
```

The relay, nudged at the commit, sent the eleven rows in 1.76 seconds, each answered `created: true`. In ERPNext,
`EL-00001` to `EL-00010` with `examleaf_ref` `item:1` to `item:10`: the books in Sample Papers and Solutions as stock
items kept by batch, HSN 4901 and "GST Exempted - EL", the bundle `EL-00003` a non-stock item with its Product Bundle
(`EL-00001` and `EL-00002`, one each), the course in Digital Courses at SAC 999293 and "GST 18% - EL", each with its
MRP Item Price.

## 3. The mirrored documents

The four other flows went on one at a time (`PUT /api/v1/staff/flags/ERP_SYNC_INVOICES/`, `…PAYMENTS/`,
`…DELIVERIES/`, `…SETTLEMENTS/`, 02:03:29, each 200 in 0.03 s, `GET /api/v1/staff/erp/status/` after each showing it
on). Then two orders through the shop's own services, `erp_status` after each stage.

**Order A**, `EL-2026-000001`, paid online: two Physics Sample Papers at ₹299 (exempt) and the course at ₹999 (18 %),
to Guwahati, ₹1,597.00. The capture (02:03:49) made the worker issue `T/2026-27/00001`, an invoice-cum-bill of supply;
its producer wrote the invoice and the payment, and the relay sent both within a second:

| ERPNext | What it holds |
|---|---|
| Sales Invoice `T/2026-27/00001` | customer "Online Customers (B2C)", place of supply 18-Assam, territory Kamrup Metro, grand total 1,597.00, CGST 76.19 and SGST 76.19 (152.38; the last paisa to round-off), `examleaf_order_no` EL-2026-000001, channel web; its address "B2C 781001 Guwahati-Shipping": city, district, state and PIN, no name, phone or street |
| Payment Entry `ACC-PAY-2026-00035` | Receive, Razorpay, 1,597.00 into Razorpay Clearing, reference `pay_p15_1`, `payment:1` |

Packed and handed over by hand (India Post, 02:03:50): the delivery note was **refused**, `422 insufficient_stock`
("Main - EL has 0 of EL-00001 in its batches, 2 needed"): ERPNext held no copies yet. The row was tried again after
its backoff, and the order's later rows waited behind it, as designed. The course refunded (the panel's refund of a
chosen line, ₹999) made `TC/2026-27/00001`. The printer's receipt of section 5 came at 02:05:18; at the 02:07 relay
the delivery note went on its third try, then the credit note and the refund (1.3 s for the three):

| ERPNext | What it holds |
|---|---|
| Delivery Note `DN-26-00019` | against `T/2026-27/00001`, 2 copies of `EL-00001` from print run `PR-EL-00001-2026-1` (the oldest first) |
| Sales Invoice `TC/2026-27/00001` | a return against `T/2026-27/00001`: −999.00, tax −152.38 (ERPNext warned that the return keeps its own outstanding, "Update Outstanding for Self") |
| Payment Entry `ACC-PAY-2026-00036` | Pay 999.00 against the credit note; outstanding after: 0.00 |

**Order B**, `EL-2026-000002`, cash on delivery (the panel's `SHOP_COD_ENABLED` setting switched on first):
Chemistry Solutions at ₹249 and ₹40 of shipping, ₹289.00. Handed over by hand before it had a bill; the worker issued
`T/2026-27/00002` at the dispatch, and its producer wrote the invoice and then the delivery note of the parcel that had
already left (the race of `README.md` "The flows"): `DN-26-00020`. Delivered: the COD payment, `ACC-PAY-2026-00037`
(reference the AWB, into COD in Transit). The courier's remittance matched with its UTR (`reconcile_cod`): Journal
Entry `ACC-JV-2026-00002` (`settlement:cod-1`). All of it in 2.3 seconds.

`daily_totals` for the day then: invoices 2 (1,886.00; taxable 846.61, exempt 887.00, GST 152.38), credit notes 1
(999.00), payments received by Razorpay 1,597.00 and COD 289.00, refunds 999.00, the COD settlement 289.00, 2
delivery notes. The reconciliation at that point (`erp_reconcile --date 2026-10-10`, run #1, 3 s with Django's start)
found **0 differences**.

## 4. Idempotency

- **One event sent twice**: row #12 (the invoice of order A) put back to `sending` with its lease run out, as a worker
  killed after ERPNext committed and before the platform saved the answer leaves it. The next relay sent it again with
  the same key, `12`: ERPNext answered its first answer again with `duplicate: true` (Sync Log 1072, "Duplicate of"
  1055), one call, 0.5 seconds. ERPNext kept one Sales Invoice, the platform one link.
- **Resent after a restore**: `erp_replay --sent-since 2026-10-10T02:07:46` sent again the five rows ERPNext had
  answered since then (order B's four and #12): five duplicates, the same five documents, 0.5 seconds.
- **The contract's answers**, the platform's own payloads posted with the sync user's token:

| Call | Answer |
|---|---|
| the same key and body again (a lost answer) | 200, the first answer, `duplicate: true` |
| the same reference under a new key | 200, the short form `{name, duplicate: true, docstatus}` |
| the same key with another body | 409 `idempotency_key_reused` |
| **a second order with the same number**: order B's invoice under `T/2026-27/00001` | **200, `duplicate: true`** before the fix; after it, 409 `conflict` (`order_number`): "Sales Invoice T/2026-27/00001 is EL-2026-000001's, not EL-2026-000002's." |
| the number `T/2026-27/00001` under another reference | 409 `conflict` (`invoice_number`) |

The fourth was a gap: the reference of an invoice is its number, so a number issued again for another order (a
platform restored from an old backup, a second platform on one site) was answered as the first order's duplicate, and
the platform would have marked the second invoice sent and linked it to the first one's document. examleaf_erp now
checks that a reference's invoice is the same order's, and a credit note's the same invoice's (649646f, a2f78e1); the
relay takes the conflict as permanent: a dead letter for staff. At the end of the run ERPNext held exactly one document
per reference for the day: 5 sales invoices, 5 payment entries, 3 delivery notes, 1 journal entry.

## 5. The doorbells and the pull

```text
02:05:18  Stock Entry MAT-STE-00059 (Material Receipt into Main: the eight books, 20 copies each, a batch each)
02:05:19  POST /api/hooks/erp-events/ 200 (36 ms) … eight of them by 02:05:23, 13 to 36 ms each
02:05:19  the first: a stock read queued 30 s ahead; the other seven: "a stock read is queued already"
02:05:50  get_stock (0.35 s): eight snapshots, 20 copies each with their batch
```

Each signature was checked, each body kept once (`InboundEvent`), each answered at once. The platform's own delivery
notes rang too (a Stock Ledger Entry each), and the 02:15 pull read 10 stock rows and 3 invoices in 0.95 seconds.
The stock invariant held after each: for `EL-00001`, ERPNext's 20 less the 2 shipped but not yet in ERPNext was the
platform's 18; once the delivery note was in, 18 and 18.

**The projection**, tried for one receipt: `ERP_STOCK_PROJECTION` on through the panel (02:21:27), a second print run
of 5 copies of `EL-00001` (`MAT-STE-00060`), its doorbell, the stock read at 02:22:06: "ExamLeaf Physics Sample Papers
2027's copies for sale 18 → 23 (ERPNext free: 23.0)". Off again through the panel (02:22:13): the copies for sale
stayed at 23, as the last projection left them.

**A B2B doorbell**: the school "Cotton Collegiate H.S. School" saved in ERPNext (02:28:24) rang `EL Customer on_update`
at 02:28:25; the platform read it again over REST and its mirror took the change (medium English), status "Enabled",
no contact field. Thirteen doorbells in all (12 for stock, read 5 times), each accepted in 13 to 36 ms; the app's
tests (section 9) rang six more.

## 6. The planted difference

```sh
bench execute: frappe.db.set_value("Sales Invoice", "T/2026-27/00002", "grand_total", 298)   # 02:22:25, was 289
manage.py erp_reconcile --date 2026-10-10    # run #2, 3 s: 1 difference(s). - invoices total: 1886.00 here, 1895.00 there
GET /api/v1/staff/inbox/                     # #4 "ERPNext reconciliation of 10 Oct 2026: 1 difference(s) to resolve"
GET /api/v1/staff/erp/differences/?open=true # #1: kind invoices, key total, 1886.00 / 1895.00
```

Finance set the invoice back to 289.00 in ERPNext, then `POST /api/v1/staff/erp/differences/1/resolve/` with the note
(200, 0.03 s): resolved by the OWNER, the inbox item done, an audit event `erp.resolve` (the run, the day, the kind,
the key; the note as its reason). Reconciled again (run #3): 0 differences. The difference names the day's total, not
the invoice: here there were two to look at; at the parallel run's volume see section 12.

## 7. Dead letters

Made on purpose on the catalogue (so that the day's documents stay as they were): an item made by hand in ERPNext as
`EL-00012` (02:24:49), then two books added on the platform (02:25:04), the first with HSN `49019990`, which India
Compliance's master of 18,687 codes does not have, the second the product whose code is `EL-00012`:

| Row | ERPNext's refusal | Dead letter, inbox |
|---|---|---|
| #21 `item:11` | 400 `invalid_request` (`hsn_code`): "49019990 is not in India Compliance's HSN/SAC master." | #1, item #5 `sync_failed` for `erp.replay_sync` |
| #22 `item:12` | 409 `conflict` (`item_code`): "Item EL-00012 exists without this examleaf_ref." | #2, item #6 |

Both dead at their first try, as permanent refusals are. Finance added `49019990` to ERPNext's HSN master; then,
through the panel (02:25:16): `GET /api/v1/staff/erp/dead-letters/` (both), `POST …/21/replay/` (pending, then sent at
02:25:17 in 0.18 s: `EL-00011`), `POST …/22/discard/` with the reason ("EL-00012 was made by hand in ERPNext before the
sync; Finance links it there…"). Dead letter #1 replayed, #2 discarded, both inbox items done, audit events
`erp.replay` and `erp.discard` (with the reason). Finance then set `examleaf_ref` `item:12` on the hand-made item, and
the product's next save on the platform went through (`created: false`): ERPNext's item took the platform's name.

## 8. The rollback by flag

| Time | Through the panel | What followed |
|---|---|---|
| 02:26:28 | `ERP_ENABLED` off | order C (`EL-2026-000003`, ₹339) paid: its invoice and payment rows pending; the relay: `{"skipped": "ERP_ENABLED is off"}` |
| 02:26:55 | `ERP_SYNC_PAYMENTS` off, `ERP_ENABLED` on | C's invoice sent; C's payment pending (its flow off); C's parcel handed over: its delivery note's row pending behind the payment; order D (`EL-2026-000004`, ₹289) paid: its invoice sent, no payment row written (its flow off) |
| 02:27:19 | `ERP_SYNC_PAYMENTS` on | C's payment `ACC-PAY-2026-00038`, then its delivery note `DN-26-00021`, in order, 0.9 s |
| 02:27:34 | `erp_initial_load --invoices-from 2026-10-10` | dry run: "would write: 1 payment.received" (only D's: everything else was in the outbox); `--apply`: D's payment `ACC-PAY-2026-00039` |

No duplicates: section 4's count was taken after this.

## 9. A clean day

`erp_reconcile --date 2026-10-10` (run #4, 02:28:03, 0.4 s): **0 differences**.

| | The platform | ERPNext's `daily_totals` |
|---|---|---|
| Invoices | 4; 2,514.00; exempt 1,515.00; taxable 846.61; GST 152.39 | 4; 2,514.00; exempt 1,515.00; taxable 846.61; GST 152.38 |
| Credit notes | 1; 999.00; taxable 846.61; GST 152.39 | 1; 999.00; taxable 846.61; GST 152.38 |
| Payments in | Razorpay 3, 2,225.00; COD 1, 289.00 | the same |
| Refunds | Razorpay 1, 999.00 | the same |
| Settlements | COD 1, 289.00 | the same |
| Delivery notes | 3: `EL-00001` 2, `EL-00005` 1, `EL-00006` 1 | the same |
| Stock invariant | ten books (the two new ones at 0); `EL-00009`: 19 for sale = ERPNext's 20 less order D's copy not yet shipped | holds for each |

GST differs by 0.01 on each taxed document, the course's: the platform rounds each tax on each line and takes the tax
as the price less the taxable value (152.39), ERPNext rounds each of CGST and SGST once on the taxable value (76.19
twice, 152.38) and books the paisa to round-off (`examleaf-erp/API.md`, deviation 7). The reconciliation's tolerance,
0.01 for each taxed document, absorbed it; whether the platform adopts ERPNext's rounding is still the open question of
`examleaf-erp/README.md`.

**The app's tests, last** (`./dev.sh test`, run after the clean day because they commit documents dated the day):
the 56 and the two of section 4's fix, 58. The first run (02:28 to 02:29:55) failed two, both fixed in a2f78e1
(section 10); the second (02:30:55 to 02:31:32) passed all 58 in 31 seconds, the site's webhooks still on. The day
reconciled once more after them (run #5) had 23 differences: their 36 invoices, 10 credit notes and 4 delivery notes
(section 12).

## 10. What failed, and what changed

| Found | Fix |
|---|---|
| A second order under an invoice's number answered as a duplicate (section 4) | 649646f, a2f78e1: 409 `conflict` on `order_number` (a credit note: `invoice_number`); two Frappe tests, the fake refusing the same, a relay test that such a row dies; `examleaf-erp/API.md` deviation 3 |
| `erp_status` gave its times in UTC: the oldest row "waiting since 2026-10-09 20:33" for one written at 02:03 on the 10th | 5b4fda6: India's time, with a test |
| The pull read every storefront invoice and credit note over REST (191 of the first 192), only to ignore them | 4290309: `get_changes_since` gives each row's `examleaf_ref`; the pull skips the platform's own (`contract.own`); with a test. Read from the start again after the fix: 195 invoices and 51 customers in 1.1 s and 55 calls |
| B2B customers mirrored as "Draft" (a Customer has no status, and docstatus 0) | 4290309: Enabled or Disabled, with a test |
| The app's tests on a site configured for a platform: `test_the_webhooks_are_off_until_configured` assumed none, and its clean-up would have switched that site's webhooks off; the order check answered a cancelled invoice's reference with a conflict | a2f78e1 |
| `./dev.sh up` rebuilt the image on every start, pulling a re-pushed base | 2bc7d4f: built once; `./dev.sh build` on purpose |
| The documents: the chart's README still said ERPNext's in-cluster webhooks needed `X-Forwarded-Proto` (the hook's path has been exempt from the https redirect since f00d1c7); `ERP_INSTANCE_PREFIX` was said to let two platforms share a site; the opening stock's place in the shadow mode | this record's commit: `deploy/kubernetes/README.md`, `DEPLOYMENT.md`, `.env.example`, `README.md` |

Not changed, worth knowing: a reconciliation difference names a day's total, not its document (section 12); the
ERPNext account's last error stays on `erp_status` and the status API beside a later success (read it with its time);
an inbox item closed by an action records no `done_by` (the audit event has the person); and the three `failed_job`
items the worker's first start left (the macOS spawn above), not the sync's.

## 11. The numbers

| | |
|---|---|
| Outbox rows | 28: 13 `item.upserted`, 1 `bundle.upserted`, 4 `invoice.issued`, 1 `credit_note.issued`, 4 `payment.received`, 1 `refund.paid`, 3 `parcel.dispatched`, 1 `settlement.received`; 27 sent (25 at their first try; #14 at its third, #21 when replayed), 1 discarded (#22) |
| Documents made in ERPNext | 11 items (a 12th adopted), 1 Product Bundle, 4 sales invoices, 1 credit note, 5 payment entries, 3 delivery notes, 1 journal entry; 27 links on the platform |
| Calls to ERPNext | 370 by the clean day: 366 answered 200, one 400, one 409, two 422; 196 of them reads of sales invoices (192 by the first pull, before the fix) and 103 of customers (two pulls from the start, one doorbell) |
| Doorbells | 13 (12 stock, 1 B2B customer), all signed and accepted in 13 to 36 ms; 5 stock reads for the 12 |
| Time from a commit to ERPNext's answer | under a second for a row whose relay was nudged (the beat's minute otherwise) |
| Reconciliations | 5 runs: 0, 1 (planted), 0, 0 differences, then 23 after the app's tests (section 9) |

**Resources.** The stack's containers used 677 MiB once warm (MariaDB 263, gunicorn 137, the scheduler 94, the three
workers 45 to 48 each, Socket.IO 22, the two Valkeys 11 and 6, nginx 6), well under `dev.sh`'s 1.5 GB estimate; the
platform's three processes about 50 MiB each resident; the Mac had 2.9 GB free during the run with the other agents'
work, 4.8 GB once everything was down. Docker's disk, before and after: images 13.18 GB to 13.24 GB (the dev image's
own layer, India Compliance), volumes 767 MB to 790 MB (kept), the build cache 0 B to 0 B (the stopped BuildKit
attempts' 78 MB pruned). Time: 43 minutes from the first command (01:45) to the clean day (02:28), 7 of them on the
image and the memory wait; the app's 58 tests 31 seconds; the stack down at 02:41:57.

## 12. What the staging site needs beyond this

- **The site's set-up on the cluster**: the dev stack ran the bootstrap from `./dev.sh new-site`; the cluster's is the
  `erp-site-setup` Job (`deploy/kubernetes/README.md` "The site, its Jobs and its upgrades"), rendered but never run
  (`TESTING.md` section 9), then the sync user's key straight into a Secret and the integration account.
- **`examleaf_sync_user_restrict_ip`**: empty here; on staging the platform's egress addresses (the nodes' or the NAT's),
  so that the key works from nowhere else.
- **The webhook base over the cluster network**: `http://examleaf-web.examleaf.svc:8000/api/hooks/erp-events/`. Plain
  http is fine (the hook's path is exempt from the https redirect; `examleaf/test_resilience.py` posts to it as
  ERPNext does), the chart adds web's Service names to `ALLOWED_HOSTS` with ERPNext on, and the NetworkPolicy lets
  ERPNext's pods reach web. Here the same plain-http doorbells reached a platform outside ERPNext's network.
- **The opening stock before the deliveries**: without the copies in ERPNext every delivery note is refused
  (`insufficient_stock`), tried again for 4 to 8 hours and then dead, holding its order's later rows (section 3).
- **One ERPNext site per platform**: `ERP_INSTANCE_PREFIX` keeps two platforms' idempotency keys apart, not their
  references (`item:1`, `payment:1` are database ids), which would answer each other's.
- **No tests on the staging site**: the app's tests commit their documents with the day's date and a reference; after
  its two runs here the day's reconciliation found 23 differences (40 invoices there for 4 here). Frappe runs them only
  where `allow_tests` is set: keep it off on staging and production.
- **Finding a difference's document**: the nightly differences are totals per day; in the parallel run's hundreds of
  invoices a day, a total 9.00 apart needs the day's list of references and totals from ERPNext (a method beside
  `daily_totals`, and the platform's comparison of it) to point at the one invoice. Until then, Finance compares the
  day's invoices in ERPNext's Sales Invoice report with the platform's.
- **Razorpay's settlements**: `producers.razorpay_settlement` is still the hook only; COD's remittance went through.

## 13. Not tested, and why

- **ERPNext on Kubernetes, its MariaDB operator and backups**: the dev stack stood in (`deploy/kubernetes/TESTING.md`
  section 9 covers the chart).
- **Razorpay itself**, its refunds' API and settlements; **India Compliance's GST API** (GSTIN, e-way bills): no
  accounts on a laptop.
- **The 15-minute pull of a long history at scale, and the nightly run at 03:30 by beat**: the pull ran at 02:00 and
  02:15 by beat and by hand; the reconciliations ran by hand (`erp_reconcile`, the nightly task's work).
- **Two relays racing for one row** and **429 with `Retry-After`**: the dev site has no `rate_limit`; both are in the
  fake's tests (`erp/tests/test_relay.py`).
- **HRMS and offsite_backups**: the dev image has India Compliance only (the production image has all four).

## 14. Running it again, and cleaning up

The scripts were a scratch directory's (the shop's flows through `shop.services` and `shipping.services`, the panel's
calls through allauth's headless sign-in), not the repository's; every step above names the services and endpoints they
called. The stack was left as follows:

```sh
./dev.sh bench --site erp.localhost set-config examleaf_webhook_base ""     # the webhooks off again
./dev.sh bench --site erp.localhost set-config examleaf_webhook_secret ""
./dev.sh bench --site erp.localhost execute examleaf_erp.setup.configure_webhooks
./dev.sh down                       # the volumes kept: the next run starts in seconds on the same site
docker builder prune -af            # the stopped BuildKit attempts' cache, 78 MB (it was empty before the run)
```

The volumes keep the site with its documents (this run's on 10 October, earlier test runs' on 9 October and this
run's two test runs on 10 October). Their MariaDB root password is the one of the run that made them on 9 October,
whose `compose/.env` is gone: `new-site` needs it only to make a site, so a second site, or a clean one, needs
`./dev.sh destroy` first. The platform's processes were stopped, its database deleted, its two Redis databases
emptied and the sync user's key file (`compose/.sync-keys`) removed: `./dev.sh keys` makes a new one.
