# Sales representative (SALES_REP)

![For staff](../../assets/badges/audience-staff.svg) ![Component](../../assets/badges/component-console.svg) ![Phase B](../../assets/badges/phase-b-merged.svg)

The one-page guide for a member of staff who holds SALES_REP: what the role can and cannot do, its limits, the pages it
uses and its first day. It is written from `accounts/roles.py` and `staff/catalogue.py` at the merge of Phase B; the
panel's People → Roles page (`/people/roles/`) is the running truth, and the index of every role is
[README.md](README.md).

| Refund | Offline payment | Discount | Export | Bulk action | Signed out after | Second factor |
|---|---|---|---|---|---|---|
| ₹0 | ₹0 | 10% | 200 rows (no export permission yet) | 50 rows | 30 minutes idle, 8 hours in all | an authenticator app or a passkey |

## Who this is for

For school and phone orders: orders, quotations and payment links. You take the order down and send the customer the
way to pay; the money and the parcel belong to others.

## What you can do

- **Orders** (`/orders/`): the list and the records, with notes. A staff order for a phone or school buyer (New order):
  the books found by title or ISBN, the customer's email and address, a discount in rupees and the shipping; the
  panel says before you save whether it is made at once or waits for FINANCE. You turn a quotation into an order once
  (Orders → Quotes), change an order that has not left and cancel it, and send the customer the payment link from the
  order's own Actions ("Send the payment link").
- **Quotation requests:** read and change them; the school's request keeps its order and reads "ordered" afterwards.
- **Catalogue and Content (read only):** products and coupons, to see what to sell and what a code does; the books' list.
- **Approvals and the Inbox:** you ask for an approval (a discount beyond your limit becomes a request for FINANCE) and
  see its state. You write notes on the orders you can see.

## What you cannot do, and who to ask

| You cannot | Who does it |
|---|---|
| Refund, record a payment received offline, or ask for a return | SALES (or SUPPORT for refunds and returns) |
| Pack, ship or mark delivered | PACKER |
| Change a price, a coupon, an offer or stock | SALES (prices, stock, coupons, offers) |
| Approve anything, or your own discount above 10% | FINANCE (or an owner) in Approvals |
| See payments, settlements, customers' records or the Finance pages | FINANCE, SUPPORT |
| Read the audit log, give roles | the auditor or an owner; an owner |

## Your limits

| What | Up to |
|---|---|
| A discount on a staff order | 10% of the books after the offers (beyond it, or a ₹0 total, the order does not exist until FINANCE approves) |
| A refund or a payment recorded offline | none (₹0) |
| Rows in an export | 200 (your role holds no export permission yet) |
| Rows in a bulk action | 50 |

My account → "Your limits" shows them.

## How long you stay signed in

30 minutes without a request, and 8 hours after you sign in. An authenticator app or a passkey does.

## The pages you use

| Page | Path | What it is for |
|---|---|---|
| Home | `/` | your orders and quotes |
| Orders | `/orders/`, `/orders/<number>/` | find an order, its payment link, its notes |
| New order | `/orders/new/` | a phone or school order, with the discount rule's answer before saving |
| Quotes | `/orders/quotes/` | a school's quotation made into an order |
| Catalogue | `/catalogue/products/`, `/catalogue/coupons/` | what is on sale and at what price (read only) |
| Approvals, Inbox | `/approvals/`, `/inbox/` | what you asked for; what waits for you |

## Your first day

1. Sign in at `https://admin.<domain>/sign-in/` with your work Google account, or with your email address and the
   password you chose when you accepted the invitation ([README.md](README.md) "Before a person's first day"); if the
   console says "Set up two-step sign-in first", follow its link, scan the QR code with an authenticator app and keep
   the ten recovery codes offline.
2. Read and acknowledge each policy the console shows.
3. Open My account: your role, "Your limits" and where you are signed in.
4. Open the Inbox and Home.
5. Make a staff order for a test customer, and watch the panel say whether it is made at once or waits for FINANCE.

## In RUNBOOK.md

"The shop": "Staff orders and payment links", "Reviews, school orders and stock" ("School and bulk orders"); "The inbox".

## Related documents

- [Role guides](README.md): every role, who can do what by module, and the first day.
- [RUNBOOK.md](../../../examleaf-web/RUNBOOK.md): the procedures this page names.
- [The staff app](../../../examleaf-web/staff/README.md): the approvals, who asks and who approves.
- [Decisions register](../../decisions.md): the limits above are placeholders until the owner sets them.
- [The shop app](../../../examleaf-web/shop/README.md): staff orders, quotations and payment links.
