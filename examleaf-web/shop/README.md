# shop

The storefront: products, carts, checkout, payments, orders, invoices and credit notes. The shop as a whole is
described in [README.md](../README.md) "Shop" and operated by [RUNBOOK.md](../RUNBOOK.md) "The shop"; this file holds
the parts built for the Admin Control Panel's modules.

## Tax

What decides the GST on a storefront document (plan 5.9; `docs/research/2026-10-09-admin-control-panel/
research-commerce-gst.md` section 5): the HSN and SAC master with dated rates, the bundles' treatments, the billing
state, the shipping that follows the goods, the document types and their number series, the credit notes' cut-off,
cancelling a document, the threshold monitor, the tax calendar and the GSTR-1 files. ERPNext's India Compliance owns
the returns and the government APIs after the cut-over; until then the platform's documents and export are the record.

| File | What |
|---|---|
| `tax.py` | the rules: the master looked up by date, a bundle's treatment, the billing state, the document type, the series' numbers, the credit notes' cut-off, cancelling, the products that disagree with the master, the threshold monitor, the calendar, the records' retention |
| `invoices.py` | the documents' arithmetic every report reads (the PDFs, the ERPNext contract, the export, the monitor): lines, the charges that follow the goods, round-off, totals, the copies |
| `gstr1.py` | the GSTR-1 files in the GST Offline Tool's CSV templates, for `manage.py export_gstr1` and the panel's job |
| `staff_tax.py` | the staff API, `/api/v1/staff/tax/` ([API.md](../API.md) "Tax (staff)") |
| `models.py` (the end) | `HsnCode`, `HsnRate`, `DocumentSeries`, `TaxThreshold`; the fields added to `Product`, `Order`, `OrderItem`, `Invoice`, `CreditNote` |

### The model

| Model or field | What it is |
|---|---|
| `HsnCode` | a code of the master: `code` (4, 6 or 8 digits; SAC codes are chapter 99's), `kind` (HSN goods, SAC services), `description`, `uqc` (GSTR-1's unit: NOS for books, NA for services) |
| `HsnRate` | a code's rate from a day: `rate`, `taxability` (taxable, nil-rated, exempt, non-GST: a taxed row is above 0, the others at 0), `effective_from`, `effective_to` (empty: until the next row starts), `notification` and `serial`, `note`. Rows are history: never edited or deleted; a new rate starts after the code's latest one |
| `DocumentSeries` | a number series of a financial year: `prefix`, `financial_year`, `document_type`, `live` (off: the test series), `next_number`, taken under a lock on its row |
| `TaxThreshold` | one line of the monitor on a night: `date`, `line`, `financial_year`, `value` (rupees, or documents for the counts), `limit`, `crossed`, `detail` (the documents' numbers for the counts) |
| `Product.hsn`, `tax_treatment`, `tax_note`, `tax_note_date` | the master code (`hsn_code` and `gst_rate` follow it on save: the code's text and today's rate); a bundle's treatment (split, composite, mixed) with the CA's decision as written and its date; `Product.tax_problem` says why it disagrees with the master today (the catalogue's red chip) |
| `Order.billing_state` | the place of supply, set at checkout |
| `OrderItem.parts` | a bundle sold split: its components as sold (product, title, code, rate, MRP, unit price, copies, and any paise its copies could not share), each a line of the invoice |
| `Invoice` and `CreditNote`: `series`, `document_type`, `taxable_value`, `exempt_value`, `tax_amount`, `cancelled_at`, `cancel_reason`, `cancelled_by` | the series' prefix, the type as issued (a credit note: its invoice's), the totals as issued, the cancellation |

The migration (`0021_phase_b_tax`) seeds the master with the rates of research 5.1 and their notifications: printed
books 4901, 4903 and maps 4905 exempt; notebooks 4820 exempt from 22 September 2025 (12 % before); e-books 998431 at
5 %; the revision course 999293 at 18 %; job-work printing 9988 at 5 % (12 % before); paper 4802 and board 4810 at 18 %
(12 % before); courier 9968 and gateway fees 9971 at 18 %. The master begins on 22 September 2025, the day of the last
change: the codes whose rate changed that day also keep the rate before it, from 1 July 2017 (its own start is not
recorded). It links every product whose code is on the master, and fills the orders' billing state (their parcel's
state, else Assam) and the documents' series and types as issued (a tax invoice whenever a line was taxed: the rule
then). Their totals are filled on first use (`tax.fill_totals`: the monitor's first night).

### The rules

- **Rates by date.** `tax.rate_on(code, day)`: the latest row started by then, unless it has ended. At checkout each
  line keeps its code and rate as the master gives them that day (`tax.order_line`); a product not on the master, or
  a day the master has no rate for, keeps its own fields, as before the master, and its chip says so.
- **Bundles** (plan 10.1: the course as its own priced line, all three treatments available): *split* (the default
  and the recommendation) invoices the components as lines, the bundle's price shared by their MRPs in whole paise
  (`tax.apportion`; its share of the discounts shared by their values); *composite* one line at the principal supply's
  code and rate (the component with the largest share of the MRP); *mixed* one line at the highest rate. A change of
  treatment applies to orders from then on, never backwards.
- **Billing state** (`tax.billing_state`): goods are supplied where the parcel goes; courses alone where the buyer says
  at checkout (`billing_state`), else their address, else Assam. A cart with books refuses a billing state other than
  its delivery state.
- **The shipping follows the goods** (`invoices.charges_of`): shared over the goods lines by their amounts and taxed
  with each, so exempt books ship exempt and a course takes none; summed by rate on the document. A cash-on-delivery fee
  would join it there (none is charged today). Each line's tax is worked out of its tax-inclusive amount to the paisa;
  any difference between what was paid and the lines is a round-off line of its own (none while the checkout's sums
  hold).
- **The document's type** (`tax.document_type`): every line taxed, a tax invoice; none, a bill of supply; both, one
  invoice-cum-bill of supply (Rule 46A: the storefront's buyers are unregistered; a registered buyer orders through
  Sales in ERPNext). The PDF: its title, the place of supply with the state's code, "Reverse charge: No", the buyer's
  name and address (always, so also from ₹50,000), codes to `SHOP_HSN_DIGITS` figures, the untaxed lines' reasons
  (each code's notification and serial), and three copies for goods (original for recipient, duplicate for
  transporter, triplicate for supplier), two for services.
- **Series** (`DocumentSeries.take`, `tax.number`): one after the other under the series row's lock, the document made
  in the same transaction (a rolled-back one leaves no gap: the next takes its number), from 1 each 1 April, at most
  `PP/2027-28/99999` (16 characters; beyond, `SeriesFull`). Until FY 2026-27 `EL` holds every invoice and `CN` the
  credit notes; from `SHOP_SERIES_FROM_FY` each type its own prefix (`SHOP_SERIES_PREFIXES`: TI, BS, IB, CN, DN, RV,
  RF until the CA confirms others). The test series `T` and `TC` count apart and reach no return.
- **Credit notes** (`CreditNote.for_refund`, `tax.check_credit_note`): against the invoice's rates and place of supply;
  none after 30 November following the invoice's financial year, nor against a cancelled invoice (`CreditNoteTooLate`,
  `InvoiceCancelled`). The refund goes out regardless; the task opens one `credit_note_missing` inbox item for FINANCE
  with the reason, and `tax.refund_problem(refund)` gives the refund path the same words.
- **Cancelling** (`tax.cancel`): a document keeps its number (Table 13 counts it cancelled) and leaves the returns; its
  PDF is made again, marked cancelled; the order and its refunds are left as they are. An invoice's credit notes are
  cancelled first. A document already reported in a filed GSTR-1 is corrected by a credit note instead (the CA's call).
- **Records** (`tax.held_orders`): an order whose real-series documents are within 72 months of their year's annual
  return (FY 2025-26: to 31 December 2032) keeps its customer's details: `services.forget_orders` passes it by,
  whoever asks. Orders are never deleted and their documents are PROTECTed; an erasure leaves the order with its user
  anonymised.
- **The threshold monitor** (`tax.watch_thresholds`, nightly at 01:45): the financial year's aggregate turnover so far
  (the storefront's taxable and exempt values, without tax, less its credit notes; ERPNext's B2B sales join at the
  cut-over) against ₹2 crore (GSTR-9), ₹4 crore (the warning), ₹5 crore (e-invoicing, leaving QRMP, 6-digit HSN) and
  ₹10 crore (30 days to the IRP); the year's invoices above ₹1 lakh to another state (table 5); the parcels with
  taxable goods above ₹50,000 (an e-way bill). The first night a turnover line is crossed in a year, and each night a
  count grows, one `tax_threshold` inbox item; staff closing it is final.
- **The calendar** (`tax.calendar`): the month's statutory dates from the law and `SHOP_GST_QRMP` (on: quarterly
  GSTR-1 on the 13th with the IFF in the quarter's first two months, PMT-06 on the 25th, GSTR-3B on the 24th for
  Assam; off: GSTR-1 on the 11th and GSTR-3B on the 20th), GSTR-9 on 31 December when the year passed ₹2 crore, the
  30 November cut-off, the Rule 42 true-up in the September return, the quarterly TDS statements.
- **GSTR-1** (`gstr1.py`): b2cl, b2cs (net of their credit notes), cdnur, exemp, hsn-b2b (empty: no registered buyers),
  hsn-b2c and docs in the Offline Tool's templates, and the credit notes' register; the real series only, cancelled
  documents in docs only; read in chunks.

### Permissions and pages

| Permission | Who | What |
|---|---|---|
| `shop.view_hsncode` | FINANCE, AUDITOR, ADMIN, OWNER | the master, a code's history and products, the products that disagree |
| `shop.change_hsncode` | FINANCE, ADMIN, OWNER | a new code with its first rate, a new dated rate |
| `shop.view_documentseries` | FINANCE, AUDITOR, ADMIN, OWNER | the documents, a document with its lines and PDF, Table 13 |
| `shop.view_taxthreshold` | FINANCE, AUDITOR, ADMIN, OWNER | the threshold card, the calendar |
| `staff.cancel_document` | FINANCE, ADMIN, OWNER (high: re-authenticated) | cancel an invoice or a credit note |
| `staff.run_gstr1` | FINANCE, ADMIN, OWNER (medium) | the GSTR-1 job (above the starter's `export_rows`, ADMIN approves first) |

What the panel's Tax module (`examleaf-admin`, `/tax/`) does for each role:

- **FINANCE** keeps the master (a new code, a dated rate from a notification), watches the calendar and the threshold
  card each month, reads the documents and Table 13 before filing, cancels a document issued in error, runs the
  month's (or quarter's) GSTR-1 export for the CA, and answers the inbox's threshold and missing-credit-note items.
- **AUDITOR** reads all of it (the master's history, every document and its PDF, Table 13, the card, the calendar),
  writes nothing.
- **ADMIN and OWNER** do what FINANCE does; ADMIN also approves an export above FINANCE's row limit, and switches
  `SHOP_GST_QRMP` in Settings.
- The other roles do not see the module. The catalogue's product pages (P4) show each product's code, treatment, the
  CA's note and the red chip from the same fields.

### Inbox, jobs, settings

- Inbox kinds: `tax_threshold` (a line crossed: for `shop.change_hsncode`), `credit_note_missing` (a refund without its
  note: for `staff.cancel_document`).
- Job kind: `gstr1_export` (`{"month": "YYYY-MM", "months": 1 or 3}`: a month, or the quarter ending with it), its file
  the CSVs zipped, through the job's result link.
- Settings: `SHOP_SERIES_FROM_FY`, `SHOP_SERIES_PREFIXES`, `SHOP_HSN_DIGITS`, `SHOP_GST_QRMP` (DEPLOYMENT.md "Tax";
  the last also a panel switch).
- ERPNext: the outbox's invoice payload is unchanged (its contract refuses unknown fields): a split bundle sends its
  components as lines, which add up as before; the billing state reaches ERPNext only as the delivery address's state.

### Decisions taken until the CA answers (plan 10.1, 10.2)

The series prefixes TI, BS, IB, CN, DN, RV, RF from FY 2027-28; split as every bundle's default; books under "exempted"
in table 8 (not "nil rated"); the HSN summary and table 8 net of the period's credit notes; NOS and NA as the units;
the shipping exempt with the books it carries; QRMP on.
