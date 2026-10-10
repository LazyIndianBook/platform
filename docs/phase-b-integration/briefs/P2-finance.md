# Package P2: Finance (model: Claude Opus 5.5)

Ports: Django 8112, console 3032 (`E2E_API_PORT=8112 E2E_WEB_PORT=3032`). Read COMMON.md first. Your worktree is a
checkout of the `phase-b` integration branch, which already holds batch A: Orders (`shop/staff_orders.py`: the order
record, refunds with partial lines and the bank path, returns, staff orders, quotes, bulk jobs), Tax
(`shop/tax.py`, `shop/staff_tax.py`: the HSN master, document types and series, the documents register under
`/api/v1/staff/tax/documents/`, the credit-note cut-off), Content, Support (`support/`), Legal and privacy, Staff,
Settings and connections (`integrations/api.py`), System. Read `examleaf-web/CHANGELOG.md`'s Phase B entries and the
API.md sections of Orders, Tax and Connections before building, and reuse what they added.

Plan rows: section 5.8 (every row marked **must** that the platform owns; ERPNext-owned rows are links), 5.0,
section 7.7's Refund row (built by Orders: reuse), section 10.1 ("Tally export or Zoho": neither is built while
ERPNext keeps the books; "GST on Razorpay's fee": the settlement entry). Research: `research-commerce-gst.md` 4,
`research-integrations.md` 4.1, `research-erpnext.md` 4.3 and 5.8, `inventory.md` 4.2 and 4.3.

## What exists (read before building)

`shop/models.py` Payment (the state machine, the late-authorised case), `shop/services.py` (`reconcile(order)`,
`record_capture`, `record_link_payment`, `record_offline_payment`), `shop/payments.py` (the Razorpay client and the
webhook), `shop/management/commands/reconcile_payments.py` (`--older-than`), `shop/tasks.py` (`send_payment_link`),
`staff/api.py` `ReconcileView` (`system/reconcile/`: an order's payment asked of Razorpay again), `staff/approvals.py`
(`Refund`, `OfflinePayment` as extended by Orders), `shipping/models.py` CodRemittance and its API (`shipping/cod/`),
`integrations/` (the client with the call log and circuit breaker; the Razorpay account row if the Connections work
made one), `erp/producers.py` (`razorpay_settlement(settlement)`: the hook into the outbox, and `cod_settlement`),
`erp/contract.py` (`razorpay_settlement` payload and `record_settlement`), `erp/models.py` `ErpMirror` (B2B
documents pulled from ERPNext, `ERP_PULL_B2B`), RUNBOOK "A stuck payment", "A customer paid twice", "Reconciling
Razorpay settlements (monthly)", "Staff orders and payment links", "Payments received offline".

## Backend: `shop/staff_finance.py`, mounted at `/api/v1/staff/finance/` (tag "finance (staff)"), `shop/settlements.py` (the Razorpay settlement fetch and matching)

1. **Payments** `GET finance/payments/`: cursor pages over Payment with the order number, Razorpay ids, method,
   status, amount, created and the fee and settlement once matched (item 4); filters status, method, date range,
   `stuck` (created or authorised and older than `SHOP_STUCK_PAYMENT_MINUTES`, default 15, on an unpaid order; and
   captured on an order still pending: the webhook missed), `livemode`; `q` by order number, Razorpay payment, order or
   link id, an offline reference. `GET finance/payments/{id}/` with the webhook events seen (`WebhookEvent`) and the
   audit events. `POST finance/payments/{id}/reconcile/` asks Razorpay again through `shop.services.reconcile` (the
   existing permission `staff.replay_webhook`), answered with what changed. The late-authorised case (a failed payment
   turning authorised within 3 days) handled by the existing flow: test it from this endpoint and from the nightly
   task (`reconcile_payments` as a beat entry if there is none: 02:30, `--older-than 10`, `single_run`).
2. **Offline payments** `GET finance/offline-payments/` (the pending change requests of `order.offline_payment` and
   the recorded ones) for FINANCE to approve from here (the change-request endpoints exist: link).
3. **Payment links** `GET finance/payment-links/` (every link: order, amount, state, sent, expiry, the Razorpay id),
   `POST finance/payment-links/` (`shop.change_order`: an order's link, resend, cancel; `send_payment_link` exists for
   orders), and links for ERPNext B2B invoices: with an `ErpMirror` row of a B2B invoice (when `ERP_PULL_B2B` keeps
   them) a link made by the platform for its amount, the Razorpay payment recorded against the mirror and posted to
   ERPNext through the outbox as a payment entry against that invoice name if `erp/contract.py`'s
   `create_payment_entry` takes a B2B invoice reference (read `examleaf-erp/API.md`); if the contract cannot take it,
   build the link and the record on the platform, open an inbox item for FINANCE to post the entry by hand, and say so
   in the report and the docs. Links are audited; their expiry 15 days as today.
4. **Razorpay settlements**: `shop.Settlement` (settlement id, date, gross, fees, tax on fees, adjustments, net, UTR,
   state fetched | matched | posted | mismatched, the erp outbox row once posted) and `shop.SettlementLine` (type
   payment | refund | adjustment, the Razorpay entity id, amount, fee, tax, the matched Payment or Refund or none, the
   order), fetched daily (03:15, `single_run`) by `shop/settlements.py` from Razorpay's settlement recon API
   (`GET /v1/settlements/recon/combined?year=&month=&day=`, paged by `count` and `skip`; the exact fields in Razorpay's
   documentation: settlement_id, settlement_utr, entity_type, entity_id, amount, fee, tax, settled_at and so on) through
   the integrations client (the call log, the circuit breaker, timeouts), idempotent on (settlement id, entity id);
   each line matched to the platform's Payment or Refund by Razorpay id; unmatched lines and a net that differs from
   the sum of its lines open one inbox item per settlement for FINANCE; a matched settlement calls
   `erp.producers.razorpay_settlement({id, date, gross, fees, tax, net, utr, payment_ids})` once (the Journal Entry:
   Razorpay Clearing to the bank, fees as an expense, the GST on fees as common input credit, as the contract says).
   Gateway fee accounting: each line's fee and tax kept; the order's record (Orders' `GET orders/{number}/`) can show
   them through a small serializer function you export (`shop.settlements.fees_for(order)`); do not edit
   `shop/staff_orders.py` beyond calling it in its serializer if that is a one-line addition, otherwise expose
   `GET finance/payments/{id}/` only. Test and live keys: the fetch runs for the mode the site runs on (`live_mode()`),
   never mixes. Recorded fixtures for the tests (no network; the response shapes written from the documentation and
   marked `_inferred` where unverified, as `shipping/carriers/fake.py` does). `GET finance/settlements/`,
   `GET finance/settlements/{id}/` (the lines), `POST finance/settlements/{id}/match/` (a line matched by hand to a
   payment: `staff.reconcile_cod`-class permission: `staff.reconcile_settlements`, new, medium; FINANCE), `POST
   finance/settlements/fetch/` (a day, as a job: `Job.Kind.SETTLEMENT_FETCH`). RUNBOOK's monthly shell recipe becomes
   this.
5. **COD remittance reconciliation**: the shipping app owns it (`shipping/cod/`): `GET finance/today/` summarises it
   (open COD receivable, overdue rows, mismatched) with links; no second model.
6. **Refund approvals** are the change requests of `order.refund` (exist) and the bank-path refunds to mark paid
   (Orders built `refunds/{id}/mark-paid/`): `GET finance/refunds/` lists refunds by state with the method, the ARN,
   the credit note, and the pending change requests, for the Finance page; the site's refund timelines by method as
   the copy the console shows (`copy.finance.timelines`, from the research: normal 5 to 7 working days, optimum at
   once for UPI and cards that support it, bank transfers 2 working days after FINANCE records them).
7. **Invoices and credit notes**: the register is Tax's (`tax/documents/`), the order's actions are Orders'; the Finance
   page links both and shows the ERPNext mirror's state per document from `ErpLink` (`GET finance/documents/{number}/erp/`).
8. **Finance today** `GET finance/today/` (`staff.view_cod` or `shop.view_payment`: FINANCE, OWNER, ADMIN, AUDITOR):
   refunds to approve (count and the oldest), bank refunds to mark paid, offline payments to approve, stuck payments,
   unmatched settlement items, COD overdue and mismatched, credit notes the cut-off refused (Tax's inbox items), sync
   differences (the erp app's open differences), disputes "not configured" (should), each with its link; test mode
   excluded.
9. Payouts, purchase bills, period lock, MSME alerts, the chart of accounts and bank reconciliation are ERPNext's:
   the console's Finance page carries the deep links (`NEXT_PUBLIC_ERP_URL` paths) under "In ERPNext" as the modules
   list already does for `/app/accounting`.

Permissions: `shop.view_payment` (exists), `staff.replay_webhook` (exists), `staff.reconcile_settlements` (new,
medium: FINANCE), `shop.view_settlement`, `shop.view_settlementline` by rule, `shop.change_order` for links;
FINANCE and OWNER write, AUDITOR reads, SUPPORT sees payments (`shop.view_payment` is theirs) but no settlements.

## Tests the exit criteria need

Every endpoint in the matrix; the stuck filter's cases (unpaid and old, captured on a pending order) and not a fresh
payment; the late-authorised case through the reconcile endpoint; the settlement fetch idempotent (the same day
twice: one settlement, its lines once), matching by Razorpay id, an unmatched line opening one inbox item, the net
check, the erp hook called once per settlement and not for test mode; the manual match audited; the payment link for
an order and the B2B case (or its documented fallback); the Finance today counts on fixtures with test rows excluded;
query counts on the lists; the beat task `single_run`.

## Console

`/finance/` (the module's home: what FINANCE must do today, each row a link; the ERPNext links under "In ERPNext";
the `finance` entry in `MODULES` replaces the ERPNext-only link: a panel page that also carries the links),
`/finance/payments/` and `/finance/payments/[id]/` (the record, the webhook events, Ask Razorpay again),
`/finance/refunds/`, `/finance/payment-links/` (list, new, resend, cancel), `/finance/settlements/` and
`/finance/settlements/[id]/` (lines, match by hand, the posted state, fetch a day as a job). Mock fixtures for every
state. Mock journey: today → a stuck payment reconciled → settlements → a line matched → the audit trail. Real
journey (`real.spec.ts` + seed): FINANCE opens Finance today and the seeded refund change request from it.

## Boundaries

Orders' endpoints and the refund action are built: call and link, do not duplicate; Tax's documents register likewise;
the shipping app's COD pages likewise. Do not edit `staff/api.py`.
