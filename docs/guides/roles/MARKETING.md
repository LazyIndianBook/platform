# Marketing (MARKETING)

Role guide. Written from `accounts/roles.py` and `staff/catalogue.py` at the merge of Phase B; the panel's People → Roles
page (`/people/roles/`) is the running truth. The index is [README.md](README.md).

## Who this is for

For marketing: coupons and offers (large discounts approved by FINANCE), reviews, the insights and the message templates.
Campaigns, segments and the preference centre are Phase D's: nothing in the panel sends marketing yet, and when it does,
no student under 18 will ever be on its audience, whatever consent says.

## What you can do

- **Coupons and offers** (`/catalogue/coupons/`, `/catalogue/offers/`): make and change them. A coupon takes percent or
  rupees off, a minimum on the books it covers, dates, limits, chosen products and categories in or out, a first order
  only, and stacking with the automatic offers or not. An offer is an automatic discount with its own dates and, if it
  has a countdown, a real end that never moves later once shown. Names, banners and descriptions are checked for false
  urgency and guilt-trip words, and the refusal names the pattern. A discount inside your limit is made at once; beyond
  it, the request waits for FINANCE. A coupon or an offer never names an account.
- **A school's single-use codes:** on a coupon, give how many, a prefix and the school's name; a job makes them, and the
  CSV is the school's (the link lasts 5 minutes, the file a week).
- **Catalogue (read only):** the products and the shelves and collections an offer covers.
- **Reports** (`/reports/forecasts/`, `/reports/cohorts/`): the demand forecasts and print-run advice, and the cohorts. The
  other reports need data your role does not hold. Learner numbers are groups of five or more, and no row names a person.
- **Message templates** (`/settings/templates/`): read what the site sends by SMS, email and WhatsApp as DLT registered it.
- **Approvals and notes:** you ask for an approval and write notes on the records you can see.

## What you cannot do, and who to ask

| You cannot | Who does it |
|---|---|
| Approve your own discount, or any discount beyond 20% | FINANCE (or an owner) in Approvals |
| Moderate reviews (your role may change them, but no panel page for it exists yet and the Django admin is closed to your role) | SALES or ADMIN approve or reject a review in the Django admin, until the Marketing module's pages come in a later phase |
| Change a price, stock or a product | SALES, CONTENT_EDITOR |
| See customers or orders | SUPPORT, SALES |
| Change a message template, or acknowledge a fraud signal | ADMIN |
| Also hold FINANCE | separation of duties: the panel refuses |

## Your limits

| What | Up to |
|---|---|
| A discount, on a coupon or an offer | 20% (beyond: FINANCE approves) |
| Rows in a bulk action (a school's codes) | 100 |
| Refunds, offline payments, exports | none |

My account → "Your limits" shows them.

## How long you stay signed in

30 minutes without a request, and 8 hours after you sign in. An authenticator app or a passkey does.

## The pages you use

| Page | Path | What it is for |
|---|---|---|
| Catalogue | `/catalogue/`, `/catalogue/coupons/`, `/catalogue/offers/` | coupons, offers, a school's codes |
| Reports | `/reports/forecasts/`, `/reports/cohorts/` | the forecasts and cohorts |
| Message templates | `/settings/templates/` | what the site sends, as registered |
| Approvals, Inbox | `/approvals/`, `/inbox/` | the discounts you asked for; what waits |

## Your first day

1. Sign in at `https://admin.<domain>/sign-in/` with your work Google account, or with the email and password an owner
   gave you ([README.md](README.md) "Before a person's first day"); if the console says "Set up two-step sign-in first",
   follow its link, scan the QR code with an authenticator app and keep the ten recovery codes offline.
2. Read and acknowledge each policy the console shows.
3. Open My account: your role, "Your limits" and where you are signed in.
4. Open the Inbox and Home.
5. Make a coupon at a small discount and then one beyond 20%, and watch the second wait in Approvals.

## In RUNBOOK.md

"The shop" ("Coupons", "Offers"); "Insights"; "The inbox".
