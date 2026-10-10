# Package P1: Orders (model: Claude Opus 5.5)

Ports: Django 8111, console 3031 (`E2E_API_PORT=8111 E2E_WEB_PORT=3031`), the public site's dev server 3041 if you
run it. Read COMMON.md first.

Plan rows: section 5.3 (every row marked **must**), 5.0, section 7.7's Order, ReturnRequest and Refund rows, section
10.1 "A `returned` order state" (not added: a returned COD order becomes cancelled with the reason and its dispatch
invoice gets a credit note; a returned prepaid order is reshipped or refunded, the customer asked which; the "Returns"
view filters on the shipment's outcome and the return requests) and the RBI rule that refunds go to the original
method unless the customer agrees to another. Research: `research-commerce-gst.md` section 1 and 6, `research-lms-crm-cms.md`
4.5 and 4.6, `inventory.md` 3.8, 4.1, 10, 11.3.

## What exists (read before building)

`shop/models.py` (Order's state machine and `livemode`, OrderItem, OrderNote, Payment, Refund, Invoice, CreditNote,
Shipment, QuoteRequest, StockAlert), `shop/services.py` (create_order, create_staff_order, record_offline_payment,
start_refund, refund_order, cancel_order, pack_order, ship_order, deliver_order, make_quotation, notify),
`shop/invoices.py` and `shop/tasks.py` (generate_invoice, generate_credit_note, send_payment_link), `shop/admin.py`
(the admin's actions, `customer_view`, `export_order`), `staff/approvals.py` (`Refund`, `OfflinePayment`: extend them,
never duplicate), `staff/jobs.py` (`bulk_action`), `staff/signals.py` (refund_started, offline_payment), `shipping/`
(the parcels: booking, labels and the courier are that app's; its `Shipment`/`ShipmentDetail`, outcome, events;
`shipping/messages.py` the customer's shipping messages), `insights/` (`PinRtoRate`? check what the fraud and
delivery jobs keep; `insights/README.md`), `api/shop.py` (the storefront's order API and checkout), the website's
order pages `examleaf-frontend/src/app/(account)/account/orders/[number]/` and `(shop)/orders/[number]/`.

## Backend: `shop/staff_orders.py`, mounted at `/api/v1/staff/orders/` (tag "orders (staff)")

1. **The list** `GET orders/`: cursor pages; filters status, `method` (razorpay, cod, offline), courier, `created`
   range, shipping state, tag, `hold`, `risk`, `livemode` (default: live only; test rows only when asked), and `q`:
   order number, the customer's name, email, the last digits of a phone, AWB, invoice or credit-note number, a book
   code (by its hash, as `learn` stores them). A `q` that is a name, an email or digits is a person lookup: one audit
   event `customer.lookup` with the query's keyed hash (`staff.audit`'s masking) and the count found. No query per row.
   The fixed tabs the plan names (all, to pack, shipped, returns, cancelled, drafts) are URL filters the console
   draws; personal saved views through the existing `saved-views/` with `list_key="orders"`.
2. **The record** `GET orders/{number}/`: lines with HSN and rate, discounts, payments (Razorpay ids, method,
   status), refunds, the invoice and credit notes with their PDF links (the existing signed or staff PDF views),
   shipments with the shipping app's detail and last event, ERPNext links (`erp.ErpLink` rows for the order, if any),
   the customer masked (id, a masked email, `is_minor`; the full view is `users/{id}/`), tags, the hold, the risk
   bucket and reasons, the available transitions for this person (django-fsm's available transitions crossed with the
   person's permissions, so the console's one next action is the API's), and `timeline`: the merged, ordered list of
   the order's history rows (simple_history on Order and Payment), OrderNotes, Refund events, shipments' events, the
   emails and SMS sent for it (what `notify` and `ops.sms` record; link by order number where the models allow),
   `AuditEvent`s targeting it, and ERPNext document links. Opening a record of a minor's order is a `sensitive_read`.
3. **Actions**, each an audit event and each refused with the API's words when the state machine refuses:
   `pack/` (`staff.pack_order`), `ship/` by hand (courier and number: the counter flow; `staff.pack_order`),
   `deliver/`, `cancel/` (reason, `customer_requested` flag; before dispatch; stock released: `cancel_order`),
   `hold/` and `release/` (reason), `tags/` (add and remove; django-taggit is installed), `invoice/regenerate/` and
   `invoice/resend/` (the RUNBOOK shell step becomes a button; `shop.change_order`), `notify/` (send a status message
   again: placed, paid, packed, shipped, delivered, cancelled, refunded, by `shop.services.notify`'s kinds), `notes/`
   is the existing generic notes endpoint (do not add another).
4. **Refunds**: `POST orders/{number}/refunds/` goes through `approvals.ask("order.refund", …)`. Extend
   `staff.approvals.Refund` and `shop.models.Refund`: lines with quantities (partial refunds, quantities start at
   zero; the amount computed from the lines' invoiced values plus a `shipping_amount`), a `restock` switch, a reason,
   `method` (`source`: Razorpay normal or optimum speed; `bank`: for COD and offline payments, the customer's bank
   account or UPI id, encrypted at rest with `integrations.crypto` and masked in every answer and audit event), a
   warning in the answer when the payment is older than 6 months, the `Idempotency-Key` header, the change request
   kept on the refund. The `bank` path: FINANCE records the transfer with `POST refunds/{id}/mark-paid/` (UTR;
   `staff.approve_refund`), which sets the refund processed, issues the credit note and tells the customer; refused to
   SALES and SUPPORT. The customer is told on every step the plan names. A refund above the maker's cap waits for
   FINANCE (exists); test it with partial lines.
5. **Returns**: `shop.ReturnRequest` (section 7.7's fields; `lines` as a JSON list of item id and quantity; photos in
   the private storage) with a django-fsm state machine requested → approved | declined → label_sent → received →
   inspected (restocked | damaged) → refunded | exchanged, each transition an endpoint with its permission
   (`staff.handle_return`: SUPPORT and SALES request, approve and decline; PACKER and SALES receive and inspect;
   `restock` puts the quantity back through the shop's stock functions with the reason; a refund from a return goes
   through item 4; a credit note follows the refund as today; exchanges are out of scope). The customer's own request:
   `POST /api/v1/orders/{number}/returns/` in `api/shop.py` (the signed-in buyer, a delivered order, within
   `SHOP_RETURN_DAYS` of delivery, default 15, a reason code from the fixed list; refused with the reason otherwise)
   and the return's state in the order's API answer; the website's order page gains the form and shows the state
   (`examleaf-frontend`: one form, the state line; its Vitest test; keep the Answer Script design). Inbox item for
   SUPPORT on each customer request, with a 48-hour due time.
6. **Staff orders and the controls**: `POST orders/` (phone, WhatsApp or school: lines, email, address, discount,
   shipping, a payment link or an offline payment) through `create_staff_order`; a discount above the maker's
   `discount_percent` or a ₹0 total waits as `approvals.ask("order.staff_discount", …)` whose `run` creates the order
   (the order does not exist before the approval); `POST orders/{number}/payment-link/` (`send_payment_link`, resend
   and cancel), `POST orders/{number}/offline-payment/` through the existing `order.offline_payment` action. A weekly
   owner's email (Monday 08:00 IST, `single_run`) listing the week's staff discounts, offline payments and ₹0 orders by
   maker.
7. **Quotes**: `GET quotes/`, `GET quotes/{id}/`, `POST quotes/{id}/convert/` (a staff order from the quote's lines,
   discount and shipping, the quote marked converted with the order kept on it; refused twice), the quotation PDF link.
8. **Bulk actions as jobs** (`Job.Kind` values, runners, permissions, dry run, progress, a result file): mark packed,
   print (the packing slips, invoices or labels of the selected orders as one PDF), cancel (reason; at most 250: refuse
   more), export (`shop.export_order`'s columns with the GST fields, the current filter, capped by `export_rows` with
   approval above, logged). The console's undo for "mark packed" is a 5-second delay before the call; the API needs no
   unpack.
9. **Print templates** beside `templates/shop/invoice.html`, rendered by `shop.invoices.render_pdf`'s machinery:
   the A4 packing slip (title, ISBN, quantity, school or class, the order number as a Code 128 or QR image the way
   `content.views.qr_png` makes QR codes), the pick list for a set of orders grouped by book, the 4 × 6 inch label for
   parcels sent by hand. Endpoints `GET orders/{number}/documents/packing-slip/`, `GET
   orders/{number}/documents/label/`, `POST orders/pick-list/` (numbers → PDF), all `staff.pack_order`.
10. **The packing queue** `GET orders/packing/`: paid and not packed, not held, oldest first, with the pick lines,
    the parcel's weight hint from the products, the payment method, a COD badge, scoped (a PACKER sees only
    `ROLE_SCOPES`' statuses); `orders/{number}/pack/` from here.
11. **Risk flags**: at placement, for COD orders, a rule score in `insights` (one function with its test, following
    `insights/README.md`'s rules: the PIN's RTO rate smoothed toward the district's from the outcomes the shipping app
    stores, past RTOs by the phone's and address's keyed hashes, first COD order, a value above
    `SHOP_COD_HIGH_VALUE_INR`, a junk address heuristic) stored on the order as `risk_bucket` (low, medium, high) and
    `risk_reasons` (the strongest three); a high bucket puts the order on hold with the reason "payment check" when
    the setting `SHOP_COD_HIGH_RISK_HOLD` is on (default on); held orders stay out of the packing queue; the row shows
    the badge. Nothing about a person is stored in `insights`.
12. **Address validation** at checkout and on staff orders: PIN code against the district and state in `PinCode`
    (refuse a state that does not match the PIN's states), a phone required, a landmark optional; `state_problem`
    exists: reuse it.
13. **Status messages**: check that every order event the plan lists sends through `notify` (email, SMS, the tracking
    page link); add the missing ones; nothing between 21:00 and 08:00 (the SMS module holds); no marketing.
14. The storefront's order API answer gains the return state and nothing else changes for customers.

Permissions to add (catalogue, roles): `staff.handle_return` (medium), `staff.lookup_customer`? No: the lookup is an
audit event, not a permission. Use the existing `shop.view_order`, `shop.change_order`, `shop.add_order`,
`staff.pack_order`, `staff.refund_order`, `staff.approve_refund`, `staff.record_offline_payment`,
`shop.export_order`, `shop.view_quoterequest`, `shop.change_quoterequest`. PACKER gets the packing queue and the print
documents; SUPPORT asks for refunds and returns; SALES and SALES_REP make staff orders and quotes; FINANCE marks bank
refunds paid; AUDITOR reads.

## Tests the exit criteria need (beside the matrix rows and the query counts)

A partial refund of two lines of three computes the amount from the invoiced values and waits above the cap; the bank
path refused to SALES and marked paid by FINANCE issues the credit note once; the idempotency header answers the first
request again; every return transition's permission and the restock; the customer's return refused after
`SHOP_RETURN_DAYS` and on an undelivered order; a staff discount above the cap creates no order until approved; bulk
cancel refuses 251; the packing queue scoped for PACKER and without held orders; the risk rule on a fixture and the
hold; the print endpoints answer PDFs (see `shop/conftest.py` `quick_pdf`); test orders out of the default list and
counts; the weekly email sent once under two overlapping runs; the lookup event carries a hash and not the query.

## Console

`/orders/` (tabs all, to pack, shipped, returns, cancelled, drafts; the filters in the URL; saved views; the bulk bar
with mark packed with a 5-second undo, print, cancel with a typed count, export; the COD risk badge, the hold and
tags in the row; Space peeks at an order in a side panel), `/orders/[number]/` (the header with the one next action
and the status chip; sections lines, payments, documents, parcels, customer masked with the link to `/users/[id]/`,
risk, hold, tags; the timeline; the danger section: cancel, the refund dialog that shows the Razorpay rules and the
expected days by method and the 6-month warning before the agent confirms, the return request), `/orders/packing/`
(packer mode: one column, large targets, oldest first, mark packed with undo, the print buttons), `/orders/returns/`
and `/orders/returns/[id]/` (the state and its next step), `/orders/new/` (the staff order form with the discount
rule's effect shown before saving and the 202 notice), `/orders/quotes/` and `/orders/quotes/[id]/` (convert). Mock
fixtures for every state. Mock journey: list → order → refund dialog → 202 notice; packing queue → mark packed with
undo. Real journey (`real.spec.ts`, seed in `django.ts`): SALES makes a staff order, FINANCE finds it, SUPPORT asks for
a partial refund above the cap and sees the 202.

## Boundaries with other packages (do not build these)

Payments lists, payment links across orders, settlements and the invoice and credit-note registers are Finance's (P2);
the HSN master, series and billing state are Tax's (P3; you keep calling `generate_invoice`/`generate_credit_note`
and handle their refusals); the catalogue's prices and stock alerts are Catalogue's (P4); the customer page is
Customers' (P10); parcels, booking and labels through Shiprocket are the shipping app's (exists). Do not edit
`staff/api.py` (another agent does); add new views in your own file.
