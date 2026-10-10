# Package P3: Tax (model: Claude Opus 5.5)

Ports: Django 8113, console 3033 (`E2E_API_PORT=8113 E2E_WEB_PORT=3033`). Read COMMON.md first.

Plan rows: section 5.9 (every row marked **must**), 5.5's HSN and bundle-treatment rows, section 7.7's HsnCode,
HsnRate, DocumentSeries, Invoice and CreditNote, Product (the tax fields) and Order (billing state) rows, section 10.1's
decisions "GST on a book sold with a printed course code" (split supplies: the course as its own priced line at 18%;
all three treatments available per bundle), "One series per document type" (from 1 April 2027; the current `EL`
series closes with FY 2026-27), "The storefront stays B2C", "QRMP". Research: `research-commerce-gst.md` sections 0,
2, 5.1 to 5.16 (read them: the rates, the rules, the dates), `research-erpnext.md` 5.6 and 8. The exit criteria of 9.2
name this package's tests by name.

## What exists (read before building)

`shop/models.py` (`Product.hsn_code` free text default 4901, `gst_rate`, `OrderItem.hsn_code` and `gst_rate` copied
at checkout, `Invoice` and `CreditNote` with `next_number` and the `EL`/`CN` series, the test series `T`/`TC`,
`financial_year`), `shop/invoices.py` (tax-inclusive per line, the discount's share, intra/inter-state, the title
"Tax invoice" or "Bill of supply"), `templates/shop/invoice.html` and `credit_note.html`, `shop/tasks.py`
(generate_invoice, generate_credit_note), `shop/management/commands/export_gstr1.py` (B2C, HSN and credit-note CSVs;
`top_rate` taxes shipping at the cart's highest rate), `shop/cart.py` (`split`: the discount per line),
`api/shop.py` (checkout serializers, the address's state), `erp/contract.py` and `producers.py` (what ERPNext receives
for an invoice: do not change the contract's field names; the erp tests must keep passing), `shop/test_money.py`,
`shop/test_commerce.py`.

## Backend: `shop/tax.py` (the rules) and `shop/staff_tax.py` (the API), mounted at `/api/v1/staff/tax/` (tag "tax (staff)")

1. **The HSN and SAC master**: `shop.HsnCode` (code, kind HSN or SAC, description, taxability taxable | nil | exempt |
   non-GST) and `shop.HsnRate` (code, rate, effective from and to, notification number and serial); a data migration
   seeds the rates the plan lists with their sources (printed books 4901, 4903 and maps 4905 exempt; notebooks 4820
   exempt from 22 September 2025 and 18 %? before: check the research for the earlier rate; e-books 5 %; the revision
   course 18 % under SAC 999293; job-work printing 5 %; paper and board 18 %; courier and gateway fees 18 %), each row
   citing its notification. `rate_on(code, date)` looks the rate up by date; `Product.hsn` becomes a foreign key to
   the master (keep `hsn_code` as the denormalised text kept in step on save for the API and ERPNext contract), the
   rate read from the master by date at checkout and copied onto the `OrderItem` as today; a check that warns when a
   product's `gst_rate` disagrees with the master for today (`Product.tax_problem` for the catalogue list's red chip
   and `manage.py check`-style report endpoint). `GET tax/hsn/`, `GET tax/hsn/{code}/` (`shop.view_hsncode`),
   `POST tax/hsn/` and `POST tax/hsn/{code}/rates/` (`shop.change_hsncode`: FINANCE; a new rate row never edits an
   old one; the dates may not overlap).
2. **Tax treatment per bundle**: `Product.tax_treatment` for bundles (split with apportioned prices: the default and
   the recommendation; composite at the principal supply's rate; mixed at the highest rate) with `tax_note` (the CA's
   decision recorded as text and a date) and the invoice lines made accordingly: a split bundle invoices its components
   as lines with prices apportioned by their MRPs; composite and mixed invoice one line at the treatment's rate. The
   cart, checkout and the order items follow (the storefront's price breakup before checkout shows delivery and tax as
   today, unchanged in shape).
3. **Billing state**: `Order.billing_state` set at checkout (the shipping address's state for goods; for a
   course-only order the address on record, else Assam `AS`), the place of supply on the invoice taken from it;
   `api/shop.py`'s checkout gains an optional `billing_state` for course-only carts (validated against `STATES`).
4. **Allocation**: shipping follows the goods it carries (exempt books: exempt shipping; a course has nothing to
   ship; a mixed cart's shipping is split by the lines' values and taxed with each; a COD fee treated like shipping);
   a cart-level coupon allocated pro rata across lines and shown per line (the existing `split`: check and complete),
   per-line tax-inclusive arithmetic rounded to the paisa with any invoice round-off on its own line. Replace
   `export_gstr1.top_rate`.
5. **Document types and the Rule 46A title**: `Invoice.document_type` (tax_invoice, bill_of_supply,
   invoice_cum_bill_of_supply) decided by the lines (all exempt: bill of supply; all taxed: tax invoice; mixed to an
   unregistered buyer: "Invoice-cum-bill of supply", Rule 46A), the title on the PDF, `CreditNote.document_type`
   following its invoice; `cancelled_at` and `cancel_reason` on both (a cancelled document keeps its number).
   Rule 46 checks: the recipient's name and address printed for an unregistered buyer at ₹50,000 or above, HSN digits
   (4 below ₹5 crore turnover: a setting `SHOP_HSN_DIGITS`), place of supply with the state's name and code, "Reverse
   charge: No", the three copy marks (original for recipient, duplicate for transporter, triplicate for supplier) on
   goods invoices as pages or a mark; the exemption reason on a bill of supply.
6. **Document series**: `shop.DocumentSeries` (document type, a two-character prefix, financial year, next number
   under a row lock, live or test) replacing `next_number`'s scan: gapless under concurrent requests (two threads on
   PostgreSQL get consecutive numbers; a test with `transaction.atomic` and `select_for_update`), rolled over on
   1 April (the first document of a financial year starts the series at 1), never reused, at most 16 characters, the
   test series excluded. The series in force: the existing `EL` (invoices and bills of supply together) and `CN` until
   31 March 2027; from FY 2027-28 one series per document type with the prefixes the CA confirms
   (`SHOP_SERIES_FROM_FY=2027-28` and the prefixes as settings with recommended defaults: `TI`, `BS`, `IB`, `CN`,
   `DN`, `RV`, `RF`; the plan's prefixes are the recommendation until the CA answers; a setting changes them). The
   Table 13 register: `GET tax/series/` (each series: prefix, from, to, total, cancelled; by financial year and month).
7. **Credit notes**: linked to the original invoice with its rate and place of supply (exists); refused after
   30 November following the financial year of the invoice (`generate_credit_note` raises a named error the refund
   path shows; the refund still goes out, the note's absence reported to FINANCE's inbox); the GSTR-1 export shows
   them to registered and unregistered buyers.
8. **GSTR-1 complete**: `export_gstr1` gains the missing sections in the Offline Tool's CSV templates: B2C large by
   state (invoices of ₹1 lakh or more to another state), B2C small by state and rate, credit notes (unregistered,
   CDNUR), Table 8 exempt and nil-rated supplies, the HSN summary split B2B and B2C with the UQC, Table 13 (the
   document register). Streams as today. A staff endpoint `POST tax/gstr1/` that runs it as a job for a month
   (`shop.export_order`-class permission: FINANCE; the result file).
9. **The threshold monitor**: a nightly job (01:45) on rolling financial-year aggregate turnover with exempt book sales
   included: ₹2 crore (GSTR-9), ₹4 crore (warning), ₹5 crore (e-invoicing, leaving QRMP, 6-digit HSN), ₹10 crore;
   B2C large invoices at ₹1 lakh; consignments that may need an e-way bill at ₹50,000; stored as `shop.TaxThreshold`
   rows per day with an inbox item for FINANCE when a line is crossed; `GET tax/thresholds/` the card.
10. **The tax calendar**: `GET tax/calendar/`: the month's due dates computed in code (GSTR-1 or IFF on the 11th or
    13th, GSTR-3B on the 20th or the 24th for Assam under QRMP, PMT-06 on the 25th, GSTR-9 on 31 December, the
    30 November credit-note cut-off, the Rule 42 true-up in the September return, quarterly TDS returns), with the
    QRMP setting (`SHOP_GST_QRMP`, default on per section 10.1) deciding which, and what the threshold monitor says.
11. `GET tax/documents/` (invoices and credit notes by series, type, month, with cancelled ones) for FINANCE and
    AUDITOR, `POST tax/documents/{number}/cancel/` (reason; `staff.cancel_document`, high, FINANCE; a cancelled
    invoice keeps its number and the order's refund path is unchanged).
12. Records and retention: no hard deletion of orders, invoices or credit notes for 72 months after the annual
    return's due date (check the existing PROTECT rules and add the time check to any purge path that could reach
    them: `forget_orders`, the erasure job leaves them with `user=None`).
13. ERPNext: the outbox's invoice payload carries `document_type` and `billing_state` as extra keys only if the
    contract allows extra keys; otherwise leave the contract alone and note it. The erp app's tests stay green.

Permissions: `shop.view_hsncode`, `shop.change_hsncode` (FINANCE, by rule), `shop.view_documentseries`,
`staff.cancel_document` (new, high), `staff.run_gstr1` (new, medium: the export job), `shop.view_taxthreshold`;
FINANCE and OWNER write, AUDITOR reads.

## Tests the exit criteria need

The HSN rate looked up by date across the 22 September 2025 change; series numbers gapless under two concurrent
requests (PostgreSQL semantics: use `select_for_update`, test with threads on SQLite guarded or on the row lock's
logic) and rolled over on 1 April (freeze time: a document on 31 March and one on 1 April); a cancelled document keeps
its number; the Rule 46A title for a mixed cart and the bill of supply for books alone; a course-only order's place of
supply from the billing state and Assam by default; shipping exempt on a books-only cart and split on a mixed one; the
coupon allocated pro rata; the credit note refused after 30 November with the refund still going out; the GSTR-1
sections on a fixture month (totals by table); the threshold monitor crossing ₹4 crore opens one inbox item; the
split bundle invoices its components; the tax problem chip; every endpoint in the matrix; `export_gstr1` still streams.

## Console

`/tax/` (the module's home: the calendar of what is due this month, the threshold card, the series register for the
year; the module entry is new in `MODULES` under group "shop" after Catalogue, opened by `shop.view_hsncode` or
`shop.view_documentseries`), `/tax/hsn/` and `/tax/hsn/[code]/` (the master, the rate history with dates and
notifications, a new dated rate with the save bar), `/tax/documents/` (invoices and credit notes by series and month,
the PDF link, cancel with a typed confirmation), `/tax/series/` (Table 13), `/tax/gstr1/` (run the month's export as
a job with `JobProgress` and the file). Mock fixtures for every state. Mock journey: the calendar → the HSN master → a
new rate; documents → cancel one → the audit trail. No real journey needed beyond the matrix (say so in the report).

## Boundaries

Orders, refunds and returns are P1's (you change `generate_invoice`, `generate_credit_note`, `shop/invoices.py`,
`export_gstr1`, the checkout's tax arithmetic and the Product's tax fields; P1 calls them). The catalogue's product
pages are P4's: you add the `hsn` foreign key, `tax_treatment`, `tax_note` and `tax_problem` to `Product` and the
serializer fields the storefront already exposes; P4 draws them. Do not edit `staff/api.py`. Keep `erp/contract.py`'s
names.
