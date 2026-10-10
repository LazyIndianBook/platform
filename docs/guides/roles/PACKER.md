# Packer (PACKER)

Role guide. Written from `accounts/roles.py` and `staff/catalogue.py` at the merge of Phase B; the panel's People → Roles
page (`/people/roles/`) is the running truth. The index is [README.md](README.md).

## Who this is for

For the packing room: the orders to pack, their parcels, labels, pickups and manifests. You see the orders that are paid
and waiting, packed, or on their way, and cash-on-delivery orders placed and not yet shipped, and nothing else of the
business.

## What you can do

- **The packing queue** (`/orders/packing/`): the orders to pack, oldest first, with what to pick, a weight hint and the
  cash to collect on a cash-on-delivery parcel. "Mark packed" gives you five seconds to undo it; the list's bulk bar marks
  many at once (up to your bulk limit).
- **Print:** the packing slips (A4, with a QR code), the 4×6 labels for parcels you send by hand, and the pick list, as
  one PDF made in the background.
- **Send by hand:** for India Post or a courier without our booking, open the order → "Send by hand": the courier, the
  tracking number and, optionally, the tracking address; then "Mark sent", and later "Mark delivered".
- **Returns** (`/orders/returns/`): you receive a returned parcel, add photographs and inspect it: the copies go back into
  stock, or are marked damaged.
- **Parcels:** you read parcels, their timelines and exceptions, and book them with a courier (the quote, the label,
  pickups, the manifest). Booking with Shiprocket goes through the staff API; the console's Shipping page is the next
  phase's.
- **Inbox:** what is yours to do. You have no Approvals page and no notes.

## What you cannot do, and who to ask

| You cannot | Who does it |
|---|---|
| See a customer's record, a payment, a refund or any money | SALES, SUPPORT, FINANCE |
| Hold, release, tag or cancel an order | SALES or ADMIN |
| Refund, or ask for a refund or a return | SALES or SUPPORT |
| Change prices, stock or a product | SALES (prices, stock), CONTENT_EDITOR (the page) |
| Deal with a failed delivery (call the customer, re-attempt) | SALES (the parcel's exceptions are theirs) |
| Open the Django admin | it is closed to your role (its lists are not narrowed to your orders): you work in the panel |
| Also hold FINANCE | separation of duties: the panel refuses |

## Your limits

| What | Up to |
|---|---|
| Rows in a bulk action | 100 |
| Refunds, offline payments, discounts, exports | none (₹0, 0%, 0 rows) |

My account → "Your limits" shows them.

## How long you stay signed in

15 minutes without a request, and 8 hours after you sign in. An authenticator app or a passkey does. The packing page
works on a phone: one column, large buttons.

## The pages you use

| Page | Path | What it is for |
|---|---|---|
| Home | `/` | the orders to pack |
| Packing queue | `/orders/packing/` | pick, pack, print |
| Orders | `/orders/`, `/orders/<number>/` | an order's books, parcel and next step (only the orders in your scope) |
| Returns | `/orders/returns/` | receive and inspect a parcel that came back |
| Catalogue | `/catalogue/products/` | the books' titles, to match a parcel (read only) |
| Inbox | `/inbox/` | what is yours to do |

## Your first day

1. Sign in at `https://admin.<domain>/sign-in/` with your work Google account, or with the email and password an owner
   gave you ([README.md](README.md) "Before a person's first day"); if the console says "Set up two-step sign-in first",
   follow its link, scan the QR code with an authenticator app and keep the ten recovery codes offline.
2. Read and acknowledge each policy the console shows.
3. Open My account: your role, "Your limits" and where you are signed in.
4. Open the packing queue and pack one order with a colleague beside you: Mark packed, undo it within the five seconds,
   mark it again, print its slip.
5. Try "Send by hand" on a test order, then open a returned parcel's page.

## In RUNBOOK.md

"The shop": "Shipping with tracking links"; "Couriers and integrations" ("A failed delivery (NDR)", "A parcel coming back
(RTO), lost or damaged"); "Reviews, school orders and stock" ("Returns", "Stock"); "The inbox".
