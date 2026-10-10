# Finance (FINANCE)

![For staff](../../assets/badges/audience-staff.svg) ![Component](../../assets/badges/component-console.svg) ![Phase B](../../assets/badges/phase-b-merged.svg)

The one-page guide for a member of staff who holds FINANCE: what the role can and cannot do, its limits, the pages it
uses and its first day. It is written from `accounts/roles.py` and `staff/catalogue.py` at the merge of Phase B; the
panel's People → Roles page (`/people/roles/`) is the running truth, and the index of every role is
[README.md](README.md).

| Refund | Offline payment | Discount | Export | Bulk action | Signed out after | Second factor |
|---|---|---|---|---|---|---|
| ₹10,000 | ₹50,000 | 50% | 10,000 rows | 500 rows | 15 minutes idle, 8 hours in all | a passkey or a security key |

## Who this is for

For the accountant: payments, refunds and their approval, offline payments, Razorpay's settlements, invoices, cash on
delivery and the ERPNext reconciliation. You keep the money and the tax documents, and you are the second person for
money that others ask to move.

## What you can do

- **Finance** (`/finance/`): Finance today, a line for each duty and each a link to where it is dealt with; payments, with
  the stuck ones and "Ask Razorpay again" (an authorised payment is captured first); refunds with their timelines to tell
  a customer; offline payments to approve and recorded; payment links (you read them, ask Razorpay again about a B2B
  invoice's and record its ERPNext entry once you have posted the Payment Entry there); Razorpay's settlements, with a
  day fetched again as a job and each unmatched line matched by hand with a note.
- **Money you approve** (Approvals and the Inbox): refunds above the maker's limit, offline payments above theirs, and the
  prices, coupons, offers and staff-order discounts beyond their discount limit. You open the request, read its payload
  and approve with the hash you read, or reject with a reason.
- **Orders:** you read every order. You refund and record offline payments yourself inside your limits, show a bank
  refund's account (with a reason) and mark it paid with its UTR, which makes the credit note, and export orders as a
  file with the GST split.
- **Tax** (`/tax/`): the HSN and SAC master and a new dated rate when a notification changes one; the documents with their
  PDFs, cancelling one issued in error (its number typed); table 13; the threshold card and the month's calendar; the
  month's or quarter's GSTR-1 export for the CA. On a product (Catalogue) you set its HSN or SAC code, a bundle's tax
  treatment and the CA's note.
- **Cash on delivery and ERPNext:** you read the cash couriers collected and have not remitted and match remittances with
  the bank's credits (the staff API; the console's Shipping page is the next phase's); you read the ERPNext sync and
  resolve the nightly reconciliation's differences with a note.
- **Legal holds:** you put a hold on an order, invoice, payment, refund or account for a chargeback or a dispute over
  money, and release it (Legal and privacy → Legal holds).
- **Reports** (`/reports/`): sales, sales by place, cash on delivery and Razorpay's settlements, the forecasts and cohorts,
  and any report as a file.
- **Read only:** customers (masked), products, coupons and offers, and the Connections page (the payment settings).

## What you cannot do, and who to ask

| You cannot | Who does it |
|---|---|
| Pack, ship or mark a parcel delivered | PACKER, or SALES for failed deliveries |
| Change a price, make a coupon or an offer, or set stock | SALES (prices and stock), SALES or MARKETING (coupons and offers); you approve them |
| Make, send again or cancel a payment link | SALES |
| Reveal a customer's masked contact; sign in as a customer | SUPPORT |
| Give roles, make API keys, read the audit log | an owner (the log: also the auditor) |
| Replay or give up an ERPNext dead letter; export above 10,000 rows | ADMIN (`erp.replay_sync`, `staff.approve_export`) |
| Approve your own refund or payment above your limit | another FINANCE member or an owner |
| Hold PACKER or MARKETING as well | separation of duties: the panel refuses |

## Your limits

| What | Up to |
|---|---|
| A refund you make | ₹10,000 (above: another holder of the approval, or an owner) |
| A payment recorded offline | ₹50,000 |
| Rows in an export | 10,000 (above: ADMIN approves) |
| Rows in a bulk action | 500 |

My account → "Your limits" shows them.

## How long you stay signed in

15 minutes without a request, and 8 hours after you sign in. You must hold a passkey or a security key.

## The pages you use

| Page | Path | What it is for |
|---|---|---|
| Finance today | `/finance/` | what waits for you; an invoice's copy in ERPNext (`?document=`); links to ERPNext's books |
| Payments, refunds, offline payments | `/finance/payments/`, `/finance/refunds/`, `/finance/offline-payments/` | the stuck ones, the approvals, the timelines |
| Payment links | `/finance/payment-links/` | links open, paid and posted; a B2B invoice's entry recorded |
| Settlements | `/finance/settlements/` | each day's payout, its lines matched, a day fetched again |
| Orders and bank refunds | `/orders/`, `/orders/returns/` | an order's money; the transfer to make |
| Tax | `/tax/`, `/tax/hsn/`, `/tax/documents/`, `/tax/series/`, `/tax/gstr1/` | rates, documents, table 13, the GSTR-1 export |
| Reports | `/reports/` and its tabs | the numbers, and files of them |
| Legal holds | `/privacy/holds/` | holds for a dispute |
| Approvals, Inbox | `/approvals/`, `/inbox/` | what you approve; settlements, bank refunds, thresholds, missing credit notes |
| The ERPNext sync | `/system/sync/` (by its address) | the outbox and each night's reconciliation |

## Your first day

1. Sign in at `https://admin.<domain>/sign-in/` with your work Google account, or with your email address and the
   password you chose when you accepted the invitation ([README.md](README.md) "Before a person's first day"); if the
   console says "Set up two-step sign-in first", follow its link, scan the QR code with an authenticator app and keep
   the ten recovery codes offline.
2. Add a passkey or a security key when the console asks for one.
3. Read and acknowledge each policy the console shows.
4. Open My account: your role, "Your limits" and where you are signed in.
5. Open the Inbox and Home: the refunds, bank transfers, unmatched settlement lines, cash on delivery overdue and the net
   revenue are your cards. Then Finance today, and read this morning's settlement (Finance → Settlements).
6. Read the morning's ERPNext reconciliation email and inbox item if the sync is on (`ERP_ALERT_EMAILS`).

## In RUNBOOK.md

"The shop": "A stuck payment", "I have not got my refund", "A customer paid twice", "Test mode and live mode", "Razorpay
settlements", "An invoice or credit note is missing", "GST returns (GSTR-1 export)", "Tax: rates, documents, series",
"Staff orders and payment links", "Payments received offline"; "Couriers and integrations" ("COD remittances"); "ERPNext"
("The morning's reconciliation differences"); "Data requests and privacy" ("Legal holds"); "Connections" (read only);
"The inbox".

## Related documents

- [Role guides](README.md): every role, who can do what by module, and the first day.
- [RUNBOOK.md](../../../examleaf-web/RUNBOOK.md): the procedures this page names.
- [The staff app](../../../examleaf-web/staff/README.md): the approvals, who asks and who approves.
- [Decisions register](../../decisions.md): the limits above are placeholders until the owner sets them.
- [The shop app](../../../examleaf-web/shop/README.md): payments, refunds, settlements and tax.
- [The ERPNext sync](../../../examleaf-web/erp/README.md): the outbox and the nightly reconciliation.
