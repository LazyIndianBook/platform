# shop: the Orders module of the Admin Control Panel

The staff side of the shop's orders (plan 5.3; the research in `../docs/research/2026-10-09-admin-control-panel/`
`research-commerce-gst.md` 1 and 6, `research-lms-crm-cms.md` 4.5 and 4.6): finding orders, acting on them, refunds by
line or by bank, returns, staff orders and quotes, the packing room and its documents, and the cash-on-delivery risk.
Every rule is the shop's own (`services.py`, the order's state machine); the API checks who may do it and the panel
draws what the API answers. The shop itself (cart, checkout, Razorpay, invoices) is described in
[../README.md](../README.md) "Shop"; the endpoints in [../API.md](../API.md) "Orders (staff)".

| File | What |
|---|---|
| `staff_orders.py` | `/api/v1/staff/orders/`: the list (filters, tabs, search with the person lookups audited), the record and its timeline, the moves, refunds, returns, staff orders and their preview, quotes, the packing queue, the PDFs |
| `order_jobs.py` | the bulk jobs: `orders_pack`, `orders_print` (one PDF), `orders_cancel` (250 at most), `orders_export` (CSV, a line per book with the GST split) |
| `services.py` | holds, tags, `assess_risk`, refunds by line (`refund_lines`, `price_lines`, `refund_with_details`, `mark_bank_refund_paid`), `cancel_returned`, the returns (`request_return` … `inspect_return`), `staff_grants`, `regenerate_documents`, `renotify`, and `notify`'s record of each message |
| `invoices.py` | the print documents (`Print`: the packing slip, the 4×6 hand label, the pick list, invoices merged) beside the invoice and credit notes |
| `models.py` | the order's hold, tags and risk; the refund's lines, shipping, restock, method, encrypted payee, UTR, ARN and change request; `ReturnRequest`; `OrderMessage` |
| `tasks.py` | `weekly_staff_grants` (Mondays 08:00), `send_held_sms` (08:00), the refund task's speed and ARN |
| `../staff/approvals.py` | `order.refund` (with lines, a method, a return) and `order.staff_discount` |
| `../insights/jobs/risk.py` | the COD risk rules: the PIN code's and district's returned parcels, the customer's past returns by keyed hashes, a first COD order, its value, an address no courier could find |

## The rules

- **What a person may do** is the order's state machine crossed with their permissions (`actions` on the record; the
  `primary` one is the header's button): pack, send by hand and deliver are `staff.pack_order`; cancel, hold, release,
  tags, messages, payment links and documents `shop.change_order`; refunds `staff.refund_order`; offline payments
  `staff.record_offline_payment`; asking for, approving and declining returns `staff.handle_return`; receiving and
  inspecting them `staff.receive_return`; bank refunds' accounts and their payment `staff.approve_refund`; exports
  `shop.export_order`. A PACKER sees only the orders to pack and on their way (`ROLE_SCOPES`: paid, packed, shipped,
  and cash-on-delivery orders placed).
- **Refunds** go through `approvals.ask("order.refund", …)`: the amount is the lines' invoiced values (each line's share
  of the coupon and offers taken off; the last copies of a line take what is left of it to the paisa) and the shipping
  asked; within the maker's `refund_inr` it runs at once, above it FINANCE approves. Back to the source through Razorpay
  (normal or optimum speed), or by bank or UPI (cash on delivery and transfers; an online payment only with the
  customer's agreement, RBI's rule): the payee is encrypted with `integrations.crypto` and shown masked; FINANCE reveals
  it with a reason (a `sensitive_read`) and marks the transfer paid with its UTR, which processes the refund, emails the
  customer and makes the credit note, once. An `Idempotency-Key` answers the first request again. A payment older than
  6 months gets the warning before the person confirms.
- **A cash-on-delivery parcel back undelivered** (no `returned` state, the plan's 10.1): `cancel_returned` cancels the
  order, puts its copies back unless damaged and credits its invoice through a refund with method `none` (no money
  moves; ERPNext's payments flow skips it).
- **Returns** (`ReturnRequest`): requested → approved or declined → label sent → received → restocked or damaged →
  refunded. The customer asks on the website within `SHOP_RETURN_DAYS` of delivery (`POST /api/v1/orders/<number>/
  returns/`); staff may ask for them at any time. An inbox item (`return_request`) is due in 48 hours. Restocking adds
  the copies with the return as the reason; its refund (the order's refund naming the return) does not add them twice.
  Exchanges are not built.
- **Staff orders** (`order.staff_discount`): priced as the checkout prices them, the address's PIN code checked against
  its state; within the maker's `discount_percent` of the books (after the offers) the order is made at once, beyond it
  or for a ₹0 total it waits for FINANCE and does not exist until approved (the customer's details travel encrypted in
  the change request; what runs is priced again). `POST orders/preview/` shows the same answer before anything is
  asked. The owners' weekly email lists the week's staff discounts, offline payments and ₹0 orders by who gave them.
- **Holds and risk**: a COD order is scored when placed; a high score holds it ("payment check") while
  `SHOP_COD_HIGH_RISK_HOLD` is on (an inbox item `order_hold`). A held order leaves the packing queue and cannot be
  packed until released. Nothing about a person is stored by the risk rules.
- **Messages**: every status message goes through `notify` and is recorded (`OrderMessage`, with its SMS sent, held or
  dropped); an SMS due between 21:00 and 08:00 is held and sent at 08:00 if it is still true; "send again" sends only a
  message that is still true.
- **Test orders** (test keys on the live site) are out of every list, count and the packing queue unless asked for.
- **Personal data**: contacts are masked in every answer (the packing slip and label print the address whole, for
  `staff.pack_order`); a search for a person is a `customer.lookup` event with the query's keyed hash and the count;
  opening a child's order is a `sensitive_read`. No audit detail, inbox title, label or file name holds a name, an
  email, a phone number or an account.

## What the pages do for each role

The console's pages are `examleaf-admin/src/app/(panel)/orders/` (its README "Routes").

- **SALES** runs the orders: the list with its tabs, filters and saved views; an order's record with the next step,
  holds and tags, messages again, payment links, offline payments, the invoice made or sent again; refunds within
  ₹2,000 (above: FINANCE approves); returns (decide, receive, inspect); staff orders within 20% off and quotes made
  into orders; the bulk bar's cancel.
- **SALES_REP** makes staff orders (within 10% off; beyond it FINANCE approves) and turns quotes into orders; reads the
  list and the records.
- **SUPPORT** finds an order for a customer (a search for a person is recorded), reads its record and timeline, asks for
  refunds (within ₹1,000; above: FINANCE) and for returns, and decides returns.
- **PACKER** has the packing queue: the orders to pack, oldest first, what to pick, the weight hint and the cash to
  collect; marks them packed (5 seconds to undo), prints the packing slips, 4×6 labels and the pick list, sends by hand,
  marks delivered; receives and inspects returns. Nothing else of a customer.
- **FINANCE** approves refunds, offline payments and staff discounts above the makers' limits (the inbox), transfers
  bank refunds and marks them paid, exports the list (CSV with the GST split), and reads every order.
- **ADMIN** and the **owners** do all of it (the owners without a limit; approving money stays FINANCE's and the
  owners'); **AUDITOR** reads.

## Not built

Exchanges (a return is refunded and the customer orders again); payment links across orders, the payments list and the
invoice and credit-note registers (Finance, P2); the HSN master and the series (Tax, P3); prices and stock alerts
(Catalogue, P4); the customer page (P10); couriers' bookings and labels (the shipping app).
