# Sales (SALES)

![For staff](../../assets/badges/audience-staff.svg) ![Component](../../assets/badges/component-console.svg) ![Phase B](../../assets/badges/phase-b-merged.svg)

The one-page guide for a member of staff who holds SALES: what the role can and cannot do, its limits, the pages it
uses and its first day. It is written from `accounts/roles.py` and `staff/catalogue.py` at the merge of Phase B; the
panel's People → Roles page (`/people/roles/`) is the running truth, and the index of every role is
[README.md](README.md).

| Refund | Offline payment | Discount | Export | Bulk action | Signed out after | Second factor |
|---|---|---|---|---|---|---|
| ₹2,000 | ₹5,000 | 20% | 500 rows (no export permission yet) | 100 rows | 30 minutes idle, 8 hours in all | an authenticator app or a passkey |

## Who this is for

For sales and school orders: storefront orders, payment links, coupons and offers, prices and stock, quotations. You run
the orders from the phone call or the school's quotation to the parcel being packed, and you keep the prices and stock.

## What you can do

- **Orders** (`/orders/`): the list with its tabs, filters and saved views; an order's record with its next step, holds
  and tags, messages sent again, the invoice made or sent again, notes; staff orders for phone and school buyers (New
  order, with the discount rule's answer shown before saving); quotations made into orders; cancelling an order that has
  not left; payment links; offline payments; refunds; returns (ask for one, approve or decline it, receive and inspect it).
  The money steps run at once inside your limits and otherwise wait for FINANCE.
- **Catalogue** (`/catalogue/`): a product's prices (the MRP and the selling price) and its stock set by hand with the
  reason; the product page, pictures, bundles and the courier's weight and size; coupons and offers (made and changed
  inside your discount limit), a school's single-use codes (a job makes them, the CSV is the school's) and the delivery
  rates. You read the shelves and the products' tax.
- **Course** (`/course/`, for a school order): make a print run of book codes (the printer's file, once, for 24 hours; the
  owners are told) and mark it dispatched; you read the print runs and the codes report. Voiding is ADMIN's and the
  owners'.
- **Support** (`/support/`): the tickets about orders, payments and school orders: reply, note, assign, move on, refund
  from the ticket inside your limit; the saved replies, read and put in.
- **Finance** (`/finance/`): payments, refunds and payment links; you make, send again and cancel a link. You read cash on
  delivery. **Reports** (`/reports/`): sales, sales by place, cash on delivery, forecasts and cohorts.
- **Parcels:** you act on failed deliveries (the staff API; the console's Shipping page is the next phase's).
- **Reviews and quotation requests:** you approve reviews and answer quotation requests in the Django admin, which your
  role may open.

## What you cannot do, and who to ask

| You cannot | Who does it |
|---|---|
| Approve a refund above ₹2,000, an offline payment above ₹5,000, a price or a staff discount beyond 20% | FINANCE (or an owner) in Approvals; you see its state |
| Pack, send by hand or mark an order delivered | PACKER |
| Set an HSN or SAC code, a bundle's tax treatment | FINANCE |
| Void a book code or a print run | ADMIN or an owner |
| See the Customers pages, reveal a contact, sign in as a customer | SUPPORT |
| Export orders, import or export products | FINANCE (orders); ADMIN (products) |
| Read the audit log, give roles | the auditor or an owner; an owner |

## Your limits

| What | Up to |
|---|---|
| A refund you make | ₹2,000 |
| A payment recorded offline | ₹5,000 |
| A discount, on a price, coupon, offer or staff order | 20% |
| Rows in an export | 500 (your role holds no export permission yet) |
| Rows in a bulk action | 100 |

Tickets: you see the categories order, payment and school order (a scope of your role). My account → "Your limits" shows
the numbers.

## How long you stay signed in

30 minutes without a request, and 8 hours after you sign in. An authenticator app or a passkey does.

## The pages you use

| Page | Path | What it is for |
|---|---|---|
| Home | `/` | the orders to pack and the quotes open |
| Orders | `/orders/`, `/orders/<number>/` | find, act on and refund orders |
| New order, quotes | `/orders/new/`, `/orders/quotes/` | a phone or school order; a quotation made into an order |
| Returns | `/orders/returns/` | returns to decide, receive and inspect |
| Catalogue | `/catalogue/`, `/catalogue/products/`, `/catalogue/coupons/`, `/catalogue/offers/`, `/catalogue/shipping-rates/` | prices, stock, coupons, offers, rates |
| Course codes | `/course/codes/`, `/course/report/` | a school's print run; the codes report |
| Support | `/support/` | the tickets of your categories |
| Finance | `/finance/payments/`, `/finance/refunds/`, `/finance/payment-links/` | payments, refunds, links |
| Reports | `/reports/sales/`, `/reports/place/`, `/reports/cod/` | the numbers |
| Approvals, Inbox | `/approvals/`, `/inbox/` | what you asked, and what waits for you |

## Your first day

1. Sign in at `https://admin.<domain>/sign-in/` with your work Google account, or with your email address and the
   password you chose when you accepted the invitation ([README.md](README.md) "Before a person's first day"); if the
   console says "Set up two-step sign-in first", follow its link, scan the QR code with an authenticator app and keep
   the ten recovery codes offline.
2. Read and acknowledge each policy the console shows.
3. Open My account: your role, "Your limits" and where you are signed in.
4. Open the Inbox and Home: orders held for a payment check, returns due in 48 hours, tickets due.
5. Try New order with a test customer before a real one: the answer to "is it made at once or does it wait?" shows before
   you save.

## In RUNBOOK.md

"The shop": "Staff orders and payment links", "Payments received offline", "I have not got my refund", "Coupons",
"Offers", "Reviews, school orders and stock" ("School and bulk orders", "Returns", "Stock"); "The revision course"
("Printing book codes"); "Support"; "The inbox".

## Related documents

- [Role guides](README.md): every role, who can do what by module, and the first day.
- [RUNBOOK.md](../../../examleaf-web/RUNBOOK.md): the procedures this page names.
- [The staff app](../../../examleaf-web/staff/README.md): the approvals, who asks and who approves.
- [Decisions register](../../decisions.md): the limits above are placeholders until the owner sets them.
- [The shop app](../../../examleaf-web/shop/README.md): orders, prices, coupons and offers.
