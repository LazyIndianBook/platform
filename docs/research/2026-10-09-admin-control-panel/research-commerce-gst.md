# Admin panel research: commerce, inventory, accounting, invoicing, GST

ExamLeaf (Assam; Class 12 sample-paper books sold on its own site with Razorpay and COD; revision-course app unlocked by codes printed in the books). Researched 2026-10-09. Sources are numbered [n] in `sources-commerce-gst.md`.

**How to read this**
- Priority. **Must**: needed now, to run the shop or to comply. **Should**: a clear gain within a year. **Later**: only at scale, or if the business changes.
- Who has it. S = Shopify, W = WooCommerce, O = Odoo, E = ERPNext with India Compliance, ZI = Zoho Inventory, ZB = Zoho Books, T = TallyPrime, SR = Shiprocket, RZ = Razorpay.
- "EL now" is what `examleaf-web` already has. I read this from `shop/models.py`, `shop/admin.py`, `shop/invoices.py` and the `shop` management commands. I did not run the app.
- **VERIFY** marks a fact that is uncertain, recently changed, taken from memory rather than a fetched source, or that needs a CA or lawyer to sign off.

---

## 0. Key findings

1. **Tax rates since 22 Sep 2025.**
   - Printed books (HSN 4901) stay exempt (Notification 10/2025-CT(Rate), S.No. 132 [2]).
   - Exercise books and notebooks (4820) and maps, atlases and globes (4905) moved from 12% to exempt [1][2].
   - Online revision courses and coaching (SAC 999293) are 18% [27]. E-books are 5% [26]; Notification 15/2025 did not change that rate [3].
   - Inputs got dearer. Printing paper (4802, other than paper for exercise books) and coated cover board (4810) went from 12% to 18% [1].
   - Job-work printing on the publisher's own paper fell from 12% to 5% [1][3].
   - Books are exempt, so most of this input GST cannot be claimed back as credit. It is a cost, and it belongs in the inventory cost.
2. **The biggest open tax question is a book sold with a printed course code.**
   - If the book and the course share one price and are not a composite supply, it is a mixed supply. Then the highest rate, 18%, applies to the whole price (CGST Act s.8(b), s.2(74)) [8].
   - If the book is the principal supply of a composite supply, the whole thing is exempt (s.2(30), s.8(a)) [8].
   - If each part has its own price, they are separate supplies. The s.2(74) illustration says so [8].
   - ExamLeaf also sells courses on their own. That weakens a composite argument; compare the Rajasthan AAAR ruling, which turned on the kit "not sold separately" [28].
   - **Recommendation:** put the course access on the invoice as its own priced line, and get a CA opinion or an advance ruling (Assam AAR). The panel must let staff set the tax treatment of each bundle.
3. **Documents.**
   - A mixed cart (exempt books plus a taxable course) sold to an *unregistered* buyer can go on one "invoice-cum-bill of supply" (Rule 46A) [6][24].
   - A *registered* buyer needs two documents: a tax invoice for the taxable lines and a bill of supply for the exempt lines.
   - Today `shop/invoices.py` titles any invoice that has a taxed line "Tax invoice".
4. **Place of supply for digital-only orders** is the buyer's address on record (IGST s.12(2)). If there is none, it is ExamLeaf's own state, Assam. The existing GSTR-1 export takes the state from the *shipping* address. A course-only order needs a billing state captured at checkout.
5. **E-invoicing (IRN)** starts once aggregate turnover passes ₹5 crore in any year since 2017-18 [17].
   - Aggregate turnover *includes exempt book sales* (s.2(6)) [8].
   - It applies only to B2B tax invoices, credit notes and debit notes. B2C sales and bills of supply are out of scope [31].
   - From turnover of ₹10 crore, an invoice cannot be reported to the IRP after 30 days [9].
6. **E-way bills.**
   - Printed books (4901), children's books (4903) and maps (4905) are in the Rule 138(14) Annexure. No e-way bill is needed, whatever the value [6].
   - On a mixed invoice, the ₹50,000 consignment value leaves out the exempt goods [6].
   - Paper sent to a printer in *another state* for job work needs an e-way bill whatever its value [6].
7. **Returns changed in 2024–25.**
   - From July 2025, GSTR-3B takes its liability from GSTR-1/1A and it cannot be edited [14]. Table 3.2 (inter-state B2C sales by state) is locked too [15].
   - Table 12 (HSN summary) has had separate B2B and B2C tabs and an HSN dropdown since the February 2025 period [12].
   - Table 13 (documents issued) has been mandatory since the May 2025 period [13].
   - From July 2025, a return cannot be filed more than 3 years after its due date [16].
   - From 1 Oct 2025, a credit note to a registered buyer lowers ExamLeaf's tax only once the buyer has reversed the input tax credit (s.34(2) proviso [20]). This is tracked through IMS (Invoice Management System) [10][11].
8. **Input tax credit (ITC).** The business mixes exempt and taxable supplies, so Rule 42 applies [6]. Shared credit (gateway fees, courier, software, rent) is reversed in proportion to exempt turnover every month, with an annual true-up by the September return. Royalties to authors and foreign SaaS are probably under reverse charge (**VERIFY**).
9. **Consumer Protection (E-Commerce) Rules 2020** [83].
   - ExamLeaf counts as an "inventory e-commerce entity". It must show the total price with its breakup, give a ticket number for every complaint, publish its return and refund terms, and take back goods that are defective or late.
   - The grievance officer must acknowledge a complaint within 48 hours and resolve it within one month. Pre-ticked boxes are not allowed.
   - Rule 4(1)(a) reads that an e-commerce entity "shall… be a company". Check ExamLeaf's legal form.
10. **RBI** [82]. Refunds go to the original payment method unless the customer agrees to another. The site must state its refund timelines.
11. **Publisher duties.**
    - The Delivery of Books Act 1954 requires a copy of every book to go to four public libraries [88].
    - Each format needs its own ISBN, and ISBNs are free [86].
    - The Press and Registration of Periodicals Act 2023 does not cover books [87].
12. **Record retention.**
    - GST: 72 months from the due date of the annual return (s.36) [8]. For FY 2025-26 that is 31 Dec 2032.
    - If ExamLeaf is a company: an audit trail that cannot be switched off, and books kept for 8 years [90].
    - GST also requires a log of every electronic edit or deletion (Rule 56(8)) [6].

---

## 1. Order management

| Feature | What it does | Who has it | Priority | EL now / note |
|---|---|---|---|---|
| Order list with saved views | Filter by status, payment (Razorpay/COD/offline), courier, date, state, tag; save filter sets as tabs | S [47], W [67] | Must | Django admin list; add saved views |
| Universal search | Search by order no., name, phone, email, AWB, invoice no., code | S [47], W [67] | Must | |
| Bulk actions | Mark packed, print slips/invoices/labels, assign courier, export, cancel (S caps bulk cancel at 250) | S [56], W [67], SR [72] | Must | |
| Timeline + internal notes | Event log plus staff comments with mentions and attachments; customer-facing notes kept separate | S [53], W [67] | Must | `OrderNote` (signed) and simple_history exist |
| Tags | Free tags such as "school", "awaiting reprint", "VIP" | S [53] | Should | |
| Risk flags (COD/RTO) | Past RTO by phone/address, pincode RTO rate, first COD, high-value COD, junk address; card AVS/CVV/IP is mostly irrelevant here | S [48], RZ [80], SR [72] | Must | |
| COD confirmation hold | Hold COD until the buyer confirms by SMS, WhatsApp or IVR | SR [73], RZ [80] | Should | SMS module exists |
| Duplicate-order detection | Same phone/email and same items within N hours, or several open COD orders | (apps) | Should | |
| Address validation | PIN to district/state check, required phone, landmark; Shopify validates fully in only 20 countries; the examples it names are the US, Canada, Australia and Western Europe, so check whether India is one [55] | S [55] | Must | `PinCode` exists; PIN-level checks for India are likely a differentiator |
| Fulfilment hold with reason | "Awaiting reprint", "address issue", "payment check" | S [66] | Should | |
| Partial fulfilment and backorders | Ship part now, the rest after reprint; several shipments per order | S [66], O [40], ZI [37] | Should | `Shipment` is one-to-many |
| Packing slips and pick lists | Bulk print with title, ISBN, quantity, school/class | S [54], ZI [37] | Must | |
| Invoice from order | PDF emailed, plus a printed copy in the parcel (Rule 55A: the carrier must have an invoice or bill of supply when no e-way bill is needed [6]) | S [54], W [67] | Must | Invoice PDF exists |
| Shipping labels and manifests | Through an aggregator or courier API | SR [72], Delhivery [74], ZI [37] | Should | |
| Pickup scheduling | Book a courier pickup from the warehouse | SR [72], Delhivery [74] | Should | |
| Multi-courier with serviceability | Rate and serviceability by PIN; recommend a courier (SR: 42 couriers, its "CORE" engine) | SR [72], Delhivery [74], ZI [37] | Should | Courier choices exist, entered by hand |
| India Post | No public booking API found on indiapost.gov.in. Credit billing via "Book Now Pay Later" needs ≥₹10,000 of Speed Post a month [75] | – | Should | Tracking page needs a CAPTCHA (noted in the code) |
| Tracking sync | Courier webhooks or polling set the order to in transit, out for delivery, delivered, NDR or RTO | Delhivery [74], SR [72] | Should | Tracking URLs by hand today |
| NDR queue | Non-delivery reports: reason, then reattempt, change address/phone, or RTO; reach the buyer | SR [73], Delhivery [74] | Should | |
| RTO handling | Mark RTO, inspect, restock or move to damaged; refund prepaid orders; book the RTO cost | SR [72][73] | Must (COD) | |
| COD reconciliation | Expected COD per AWB against courier remittance (UTR, deductions); ageing of unremitted COD; short-remittance flags | SR [72] | Must (if COD via couriers) | |
| Weight-discrepancy disputes | Billed weight against declared weight | SR [72] | Later | |
| Returns (RMA) | Request (customer or staff), reason code, approve/decline, return label, receive and inspect, restock or damaged, refund or exchange | S [52], O [39], ZI [37] | Must: Rule 7(4) duty to take back defective or late goods [83] | |
| Exchanges | Replace a defective or wrong book; credit note plus a new invoice, or a zero-value swap with the stock movement recorded | S [52], O [39] | Should | |
| Refunds | Full or partial by line; shipping refund; restock toggle; to source (Razorpay normal or instant) or manual (COD to bank/UPI); reason; notify customer; credit note issued automatically | S [51], W [69], RZ [78] | Must | `Refund` and `CreditNote` exist |
| Cancellations | Before dispatch: void/refund, restock, reason, customer request flow. No cancellation fee unless ExamLeaf bears the same when it cancels (Rule 4(8) [83]) | S [56], W [68] | Must | |
| Order editing | Add or remove lines, change quantity, discount, shipping; collect the balance or refund it. Once an order is invoiced, a change is a credit/debit note, not an edit | S [49], W [67] | Should | |
| Staff orders (phone/WhatsApp) | Staff build the order and send a payment link | S [50], W [67] | Must | Staff orders, Razorpay Payment Links and offline payments exist |
| Draft orders and quotes | School quote with validity, discount and shipping; convert to order, then invoice | S [50][63], O [40] | Must | `QuoteRequest` and quotation PDF exist |
| Status notifications | Placed, paid, packed, shipped (AWB), out for delivery, delivered, NDR, refunded, cancelled; email/SMS/WhatsApp templates | S, W, SR [72] | Must | SMS module exists |
| SLA timers | Unshipped after N days; NDR waiting for action; refund pending; grievance acknowledgement in 48h and resolution in 1 month [83]; quote reply time | (S Flow) | Should | |
| Abandoned checkouts | List, plus recovery email or link (S: abandoned after 10 minutes, automatic emails) | S [61], W [67] | Should | Carts exist |
| Back-in-stock requests | Email when back in stock | (S apps) | Must | `StockAlert` exists |
| Pre-orders | Next edition or reprint: take the order before stock, no stock taken, notify on arrival. GST: see §5.7 | (W/S extensions) | Should | |
| School and gift bulk orders | Many copies to one school address; split by class; codes for each student | S B2B [63] | Should | |
| Order export | CSV including GST fields | S [46], W [71] | Must | Logged order export exists |

## 2. Catalogue and inventory

| Feature | What it does | Who has it | Priority | EL now / note |
|---|---|---|---|---|
| Products, variants and bundles | Bundles take stock from their components | S, W, O, ZI [37] | Must | Kinds (sample papers, solutions, bundle, digital) and `BundleItem` exist |
| MRP and selling price | Show "MRP (incl. of all taxes)" and the saving | – | Must | `mrp`, `price` exist |
| Scheduled prices and automatic offers | Start and end dates, combinable or not | S [64] | Should | `Offer` with dates and a combinable flag exists |
| Coupon rules | % or fixed; minimum spend; product/category include and exclude; per-customer and total limits; first order; segment only; stacking; bulk codes | S [64], W [70] | Must | `Coupon` exists (check which rules) |
| Shipping rules | Zone/weight/PIN rates, free-shipping threshold, COD fee shown before checkout (no drip pricing [84]) | S, W | Must | `ShippingRate` exists |
| HSN/SAC from a master | Product picks a code from the master; taxability and rate come from the master by date (§5.15) | O [38], T [34] | Must | Today `hsn_code` is free text (default 4901) and `gst_rate` is set per product |
| ISBN and barcode | ISBN-13 with checksum check, one per format; EAN-13 barcode | ISBN rules [86] | Must | `isbn` field exists |
| Stock by location | Warehouse, at printer, school depot, in transit | S [57], O, ZI [37] | Later (one godown) | |
| Inventory states | Available, committed, unavailable (damaged/QC/reserved), incoming | S [57] | Should | |
| Print runs as batches | Batch no., edition/reprint, printer, print date, quantity, unit cost; the base for valuation and recalls | O [43], ZI [37], T [34] | Must | |
| Stock adjustments with reasons | Count, damaged, promotion/donation (specimen copies), received, return restock, theft/loss, correction; full history | S [58] | Must; GST stock account includes free samples and losses (Rule 56(2)) [6] | |
| Low stock and reorder points | Alert levels tuned to exam season | ZI [37], O | Should | |
| Cost and margin | Landed unit cost including GST that cannot be claimed back | O [41] | Should | |
| Book codes as serials | Generate or import codes, link each to a print batch; status printed, sold, activated or revoked; activation log | O [43] | Must (a code is money) | |
| Purchase orders | To printer and paper supplier; partial goods receipt; match the bill | S [59], O, ZI [37] | Should | |
| Job-work tracking | Paper sent to printer on a delivery challan, books received, wastage; inter-state job work needs an e-way bill whatever the value [6] | (GST rule) | Should | |
| Cycle counts | Count by location, review variances, approve | S [60], O [42], E [44] | Should | |
| Damaged/returned stock | Separate bucket; write-off with reason | S [57], O | Must | |
| Inventory valuation | FIFO or weighted average (AS 2 allows both; **VERIFY** with CA); period-end valuation | O [41], T [34], E | Must at year end | |
| Stock movement ledger | Every in and out with its source document | S [58], E | Must | |
| Edition management | 2026-27 against 2027-28 edition; clearance of the old edition | – | Should | |
| Specimen copies | Issue to teachers/schools as free-sample stock movements on delivery challans (Rule 55(1)(c)); track by school | [6] | Should | |

## 3. Customers and B2B

| Feature | What it does | Who has it | Priority | EL now / note |
|---|---|---|---|---|
| Customer profile | Orders, lifetime value, average order, refunds/RTOs, addresses, consents, notes, tags | S [53][62] | Must | Customer page exists |
| Segments | Rule-based (spend, order count, last order, location, tags) for coupons and messages | S [62] | Should | |
| Customer type | Student, parent, teacher, school, dealer | – | Should | |
| GSTIN capture and check | Format and checksum offline; online check through a GSP (GST Suvidha Provider) later; the recipient's GSTIN is required on B2B invoices (Rule 46(d)) [6] | O [38], E | Must for schools and dealers | `validate_gstin` exists |
| Price lists by segment | Dealer discount, school price | S [63], ZI [37] | Should | |
| Credit terms | Net 15/30 for schools and dealers, credit limit, due dates | S [63], ZB | Should | |
| Consolidated school orders | One invoice to the school; one or many deliveries; student list for codes | – | Should | |
| Bill-to/ship-to | Billed to a trust, delivered to a school elsewhere; place of supply follows IGST s.10(1)(b) (**VERIFY**) | O, E | Should | |
| Dealer sale-or-return | Goods on approval: invoice by supply or within 6 months of removal (s.31(7)) [8]; delivery challan meanwhile | – | Later | |
| Statement of account | Invoices, payments, credit notes, balance, ageing | ZB, T [34] | Should | |
| Quote to order to invoice | Quotation PDF, conversion | O [40], S [50] | Must | Exists |
| Erasure with tax retention | Anonymise the person; keep invoices for the GST period (§5.16) | – | Must | Orders keep `user` SET_NULL |

## 4. Accounting

Decide first whether the panel *is* the books of account or *feeds* Tally/Zoho, which the CA keeps. For a small publisher the lazy path is to keep commerce sub-ledgers in the panel and post daily or monthly summary vouchers to Tally/Zoho.

| Feature | What it does | Who has it | Priority |
|---|---|---|---|
| Chart of accounts for a publisher | Sales: books (exempt) / courses (18%); output and input CGST/SGST/IGST; ITC reversal; RCM payable; TDS payable; inventory: books, paper at printer; deferred course revenue; Razorpay clearing; COD in transit; courier payable | O [38], T, ZB | Must (if books kept here) |
| Automatic journals from events | Sale, credit note, shipping, gateway fee, COD remittance, RTO cost | O, ZB | Should |
| Purchase and expense bills | GST split; ITC tag (taxable-only / exempt-only / common / blocked); RCM flag; bill upload | ZB, T | Must (feeds Rule 42) |
| Razorpay settlement reconciliation | Recon API gives each payment, refund and adjustment with fee, tax, `settlement_id` and UTR; domestic settlement is T+2 working days | RZ [76][77] | Must |
| Gateway fee accounting | 2% platform fee plus 18% GST on the fee [79]: expense plus ITC (common credit) | RZ [79] | Must |
| COD remittance reconciliation | Courier statement against AWBs; freight and COD-fee deductions; open COD receivable | SR [72] | Must (if COD) |
| Bank reconciliation | Import statements (CSV/OFX/QIF/CAMT), matching rules | ZB [36], O, T [34] | Should |
| Receivables/payables ageing | By customer or vendor and due date | T [34], ZB | Should |
| Financial statements | P&L, balance sheet, cash flow, trial balance, day book, ledgers | T [34], O, ZB | Should (Later if Tally is the book) |
| Undeletable audit trail | Edit log of every change that cannot be switched off (Companies (Accounts) Rules r.3(1) proviso, FY 2023-24 onwards [90]); GST Rule 56(8) edit/delete log [6] | E [32], T [34] | Must |
| Period lock and year close | Lock dates; closing entry moves profit to equity | E [45], ZB | Must |
| Tally/Zoho export | Vouchers and masters (Tally XML/Excel import, Zoho API/CSV; **VERIFY** current Tally import formats) | T, ZB | Must (if the CA uses Tally) |
| Expense categories and receipts | – | ZB | Should |
| TDS on vendor payments | Printer contracts, professional and author fees, rent. The Income-tax Act 2025 replaced the 194-series with s.393 from 1 Apr 2026 [91]; keep rates and thresholds configurable (**VERIFY**) | O [38], T [34], ZB | Should |
| MSME vendor 45-day alerts | Flag Udyam-registered micro/small vendors; due by the agreed date (max 45 days) or within 15 days if there is no agreement (MSMED s.15); late payments are deductible only when paid (s.43B(h)) [89] | – | Must (printers are often MSEs) |
| Deferred course revenue | Recognise prepaid course access over the access period; roll-forward report (AS 9 / Ind AS 115; **VERIFY** policy) | O | Should |
| Fixed assets | Register and depreciation | O, T | Later |

---

## 5. Invoicing and GST: compliance checklist

### 5.1 Rates that apply to ExamLeaf

| Supply | HSN/SAC | Rate from 22 Sep 2025 | Before | Source |
|---|---|---|---|---|
| Printed books incl. Braille (sample papers, solutions) | 4901 | Exempt (10/2025-CT(R) S.No. 132) | Exempt | [2] |
| Children's picture/drawing/colouring books | 4903 | Exempt (S.No. 134) | Exempt | [2] |
| Exercise books, graph books, lab notebooks, notebooks | 4820 | Exempt (S.No. 130) | 12% | [1][2] |
| Maps, atlases, globes | 4905 | Exempt (S.No. 136) | 12% | [1][2] |
| Newspapers, journals, periodicals | 4902 | Exempt (S.No. 133) | Exempt | [2] |
| E-book (electronic version of a 4901 book supplied online) | 9984 (SAC 998431, **VERIFY**) | 5% (2.5 + 2.5), not amended by 15/2025 | 5% | [3][26] |
| Online revision course, coaching, test series | 9992 / 999293 | 18% (not an "educational institution") | 18% | [27] |
| Job-work printing on the publisher's paper | 9988 | 5% | 12% | [1][3] |
| Printing on the printer's paper, content from the publisher | 9989 | 12% (6 + 6); the entry is not among those amended by 15/2025 (**VERIFY**) | 12% | [3][25] |
| Uncoated printing/writing paper (not for exercise books) | 4802 | 18% | 12% | [1] |
| Coated paper/board (covers) | 4810 | 18% | 12% | [1] |
| Courier, local delivery | 9968 | 18% | 18% | [1] |
| Goods transport agency freight (print runs) | 9965 | 5% with no ITC (reverse charge or the agency pays), or 18% with ITC | 5% / 12% | [1] |
| Payment gateway fees | 9971 | 18% on the fee | 18% | [79] |

The rate notifications took effect on 22 Sep 2025 [1][2][3]. Rule 46's notification 12/2017 (HSN digits) is unchanged [5].

### 5.2 Classification and bundles
- [ ] **Sample-paper books** are 4901 when printed matter predominates. Since 22 Sep 2025, 4820 is exempt as well, so the rate is the same either way [2]. The HSN still drives Table 12 and the e-way bill Annexure: 4820 is *not* in the Annexure [6].
- [ ] **Shipping billed on a book order** is part of a composite supply whose principal supply is the goods (s.2(30) illustration) [8], so it is exempt like the books.
  - EL's `export_gstr1.top_rate` puts shipping at the invoice's *highest* rate. In a book-plus-course cart that taxes shipping at 18%.
  - Fix: shipping follows the goods it carries. A course has nothing to ship.
- [ ] **Book plus course code (§0.2).** Support a per-bundle setting:
  - (a) split lines with apportioned prices (recommended);
  - (b) composite, taxed at the principal supply's HSN and rate;
  - (c) mixed, the whole price at the highest rate.
  Record the CA's decision on each bundle.
- [ ] **COD fee (if charged):** treat it like shipping, as part of the composite supply (**VERIFY**).

### 5.3 Documents and their mandatory fields
- [ ] **Tax invoice (Rule 46)** [6]:
  - supplier name, address and GSTIN; serial number; date;
  - recipient name, address and GSTIN if registered;
  - for an unregistered buyer, name, address, delivery address and state with its code when the taxable value is ≥ ₹50,000, or on request;
  - HSN; description; quantity and unit (UQC); total value; taxable value after discount;
  - rate and amount of each tax; place of supply with the state name (inter-state); delivery address if different; reverse charge Y/N;
  - signature (not required on an electronic invoice); IRN QR code when e-invoicing applies.
- [ ] **HSN digits (Notification 78/2020)** [5]: turnover ≤ ₹5 crore, 4 digits on B2B invoices and optional on B2C; above ₹5 crore, 6 digits.
- [ ] **Bill of supply (Rule 49)** for exempt supplies: no tax fields. Section 31(3)(c) allows skipping it below ₹200 [8]; the site issues one anyway.
- [ ] **Invoice-cum-bill of supply (Rule 46A)** for taxable plus exempt supplies to an *unregistered* buyer. It must carry the Rule 46 and Rule 49 particulars [6][24]. Registered buyers get separate documents.
- [ ] **Copies (Rule 48)** [6]:
  - goods in triplicate: Original for recipient, Duplicate for transporter, Triplicate for supplier;
  - services in duplicate;
  - Rule 55A: a copy travels with the goods when no e-way bill is needed. Put a printed copy in the parcel and email the PDF.
- [ ] **Credit/debit notes (Rule 53(1A))** [6]: document type, serial, date, recipient, the original invoice number(s) and date(s), taxable value, rate, tax.
- [ ] **Receipt voucher (Rule 50)** and **refund voucher (Rule 51)** for advances on services [6].
- [ ] **Delivery challan (Rule 55)** [6]:
  - for job work, specimen copies, goods on approval, and returns to the printer;
  - triplicate: Original for consignee, Duplicate for transporter, Triplicate for consigner.

### 5.4 Numbering
- [ ] At most 16 characters, using A–Z, 0–9, "-" and "/". Numbers are consecutive, unique within the financial year, and one or more series are allowed (Rules 46(b), 49(b), 53, 55) [6].
  - EL's `EL/2026-27/00001` and `CN/2026-27/00001` are exactly 16 characters. Keep the prefix at 2 characters.
- [ ] **Use a separate series for each document type**: tax invoice, bill of supply, invoice-cum-bill of supply, credit note, debit note, receipt voucher, refund voucher, delivery challan.
  - Table 13 reports each document type's from/to, total and cancelled count [7][13].
  - EL uses one `EL` series for both tax invoices and bills of supply.
- [ ] Never delete or reuse a number. A cancelled document keeps its number and is counted as cancelled in Table 13.
- [ ] Hand out numbers with no gaps even under concurrent requests (row lock or DB sequence); roll over on 1 April. The test series ("T…") is excluded from every return (EL does this).

### 5.5 Place of supply (statute not fetched; **VERIFY** wording)
- [ ] **Goods with movement:** where the movement ends, i.e. the delivery state (IGST s.10(1)(a)). Assam (state code 18) to Assam is CGST+SGST; anywhere else is IGST.
- [ ] **Bill-to/ship-to on a third party's direction:** the principal place of business of the third party (IGST s.10(1)(b)).
- [ ] **Services:**
  - registered buyer: the buyer's location (IGST s.12(2)(a));
  - unregistered buyer: the address on record, or the supplier's location if there is none (s.12(2)(b)).
  - So capture a billing state for course-only orders.
- [ ] **B2C inter-state taxable sales** go state by state into GSTR-1 Table 7. From July 2025 they also flow, locked, into GSTR-3B Table 3.2 [15]. A wrong state cannot be fixed in 3B.

### 5.6 Valuation, discounts, rounding, free samples
- [ ] **Checkout coupons** are a pre-supply discount shown on the invoice, so they come out of the value (s.15(3)(a)) [8].
  - Allocate a cart-level discount pro rata across lines and show it on each line.
  - In a mixed cart, this decides the taxable value of the 18% course line.
- [ ] **Post-sale discounts** (dealer year-end, goodwill):
  - Today the discount must be agreed before the sale, linked to the invoices, and the buyer must reverse ITC (s.15(3)(b)) [8].
  - The Finance Act 2026 relaxes this to "credit note plus ITC reversal" from a date to be notified [21][22]. **VERIFY** whether it has been notified.
- [ ] **Tax-inclusive prices (EL):** taxable value = price × 100 / (100 + rate), per line, rounded to the paisa.
  - Section 170 rounds the tax *payable* to the nearest rupee (50 paise and above rounds up) [8].
  - If you round an invoice total, show it as a separate "Round off" line, not as taxable value.
- [ ] **Free samples and specimen copies:**
  - Given free to unrelated persons, they are not a supply.
  - Record them in the stock account (Rule 56(2)) and move them on a delivery challan [6].
  - ITC on gifts and free samples is blocked (s.17(5)(h), **VERIFY**). For exempt books it is moot.

### 5.7 Advances and pre-orders
- [ ] **Goods pre-orders (books):** no GST is due on an advance for goods (Notification 66/2017-CT, **VERIFY**), and books are exempt anyway.
- [ ] **Course pre-sales (services):**
  - The time of supply is the earlier of the invoice and the payment, so GST is due on the advance.
  - Issue a receipt voucher (Rule 50). If the rate is not yet known, pay 18%; if the nature is unknown, treat it as inter-state [6].
  - If it is cancelled, issue a refund voucher (Rule 51) [6].
  - Report in GSTR-1 Table 11A (advance received) and 11B (advance adjusted) [7].

### 5.8 Credit and debit notes
- [ ] **When:** excess value or tax, goods returned, or goods/services deficient (s.34(1)).
- [ ] **Deadline:** declare a credit note by 30 Nov after the financial year ends, or by the annual return date if earlier (s.34(2)) [23]. A debit note goes in the month it is issued. Block credit notes after the cut-off in the panel.
- [ ] **From 1 Oct 2025** there is no reduction in tax if a *registered* buyer has not reversed the ITC, or if the tax was passed on to someone else (s.34(2) proviso, Notification 16/2025-CT) [20].
  - In IMS, buyers accept, reject or keep a credit note pending (pending allowed for one period since Oct 2025) [10][11].
  - Show each B2B credit note's IMS status and chase rejections.
- [ ] A credit note uses the original invoice's rate and place of supply, and links to it (Rule 53(1A)) [6].
- [ ] **B2C credit notes:**
  - Table 7 is "net of debit notes and credit notes" [7], so B2C small credit notes are netted there in their period.
  - Table 9B (CDNUR) is only for B2C large and exports.

### 5.9 E-invoicing (IRN)
- [ ] **Applies** once aggregate turnover passes ₹5 crore in any FY since 2017-18 (Notification 10/2023-CT, from 1 Aug 2023) [17]. Exempt book sales count (s.2(6)) [8].
- [ ] **Scope:** B2B tax invoices, credit notes and debit notes. Not B2C, and not bills of supply for exempt supplies [31].
- [ ] **What changes:** the IRN and signed QR go on the invoice (Rules 46(r), 48(4)). An invoice that needed an IRN but has none is not a valid invoice (Rule 48(5)) [6].
- [ ] **30-day limit:** from 1 Apr 2025, with turnover ≥ ₹10 crore, no document older than 30 days can be reported to an IRP [9].
- [ ] **Cancelling an IRN:** allowed only within a short window on the IRP (24h, **VERIFY**); after that, issue a credit note [31].
- [ ] **Panel:** watch turnover against the thresholds (§5.15). Build the IRP integration through a GSP or IRP API when turnover nears ₹4–5 crore (Later).

### 5.10 E-way bills and delivery challans
- [ ] **Threshold:** an e-way bill is needed for a movement with consignment value > ₹50,000, tax included. On mixed invoices the value leaves out the exempt goods (Rule 138(1), Explanation 2) [6].
- [ ] **Not needed** for goods in the Rule 138(14) Annexure: 4901 printed books, 4903, 4905 [6]. Also not needed for goods in the exemption-notification Schedule (r.138(14)(e) cites 2/2017-CT(R)).
  - 2/2017 was superseded by 10/2025 [2]. **VERIFY** that the cross-reference was updated. It matters for 4820 notebooks.
- [ ] **Who files:** on the consignor's authorisation, a courier or e-commerce operator may file Part A [6].
- [ ] **Job work:** from a principal to a job worker in another state, an e-way bill is needed whatever the value [6].
- [ ] **Validity:** 1 day per 100 km [6].

### 5.11 Returns

**GSTR-1, mapped to ExamLeaf** (Form layout [7]; later changes [12][13][18]):

| Table | What ExamLeaf puts there |
|---|---|
| 4A B2B | Tax invoices to registered buyers (courses sold to institutes or schools with a GSTIN), invoice by invoice |
| 5 B2CL | Inter-state taxable invoices to unregistered buyers above ₹1 lakh (from 1 Aug 2024; was ₹2.5 lakh) [18]; rare |
| 6 | Exports and SEZ (none unless selling abroad) |
| 7 B2CS | Other B2C taxable sales, net of credit and debit notes, by place-of-supply state and rate (courses at 18%) [7] |
| 8 | Nil-rated, exempt and non-GST supplies, split inter/intra × registered/unregistered [7]. Books are exempted by an exemption notification (s.11) rather than a 0% rate, so the "exempted" column (**VERIFY** with CA) |
| 9A/9B/9C | Amendments; credit/debit notes to registered (CDNR) and to unregistered B2C large (CDNUR) [7] |
| 10 | B2C small amendments [7] |
| 11A/11B | Advances received / adjusted (course pre-sales) [7] |
| 12 HSN summary | B2B and B2C tabs since the February 2025 period; HSN from a dropdown; UQC (NOS/PCS for books, NA for services, **VERIFY**); quantity, value, tax; 4 or 6 digits by turnover [5][12]. The B2B tab is mandatory; the B2C tab is not enforced [12]. Value checks against other tables are only warnings for now [13] |
| 13 Documents issued | From/to, total and cancelled for each document type; mandatory since the May 2025 period [13] |
| 14/15 | Supplies through e-commerce operators (only if listed on Amazon/Flipkart etc.; added Jan 2024, **VERIFY**) |

**Monthly and quarterly filing**
- [ ] **GSTR-1A:** optional amendments after GSTR-1 and before GSTR-3B (from the July 2024 period, **VERIFY**). It is now the only way to change 3B liability [14].
- [ ] **GSTR-3B:**
  - From the July 2025 period, the liability comes from GSTR-1/1A/IFF and cannot be edited [14]; Table 3.2 is locked [15].
  - ITC comes from GSTR-2B through IMS, less Rule 42 reversals; reverse-charge tax goes in 3.1(d).
- [ ] **Monthly due dates:** GSTR-1 by the 11th, GSTR-3B by the 20th (**VERIFY**: from memory, not a fetched source).
- [ ] **QRMP**, open to turnover ≤ ₹5 crore [29]:
  - quarterly GSTR-1 by the 13th;
  - IFF for B2B invoices in months 1–2, filed between the 1st and 13th, capped at ₹50 lakh a month;
  - PMT-06 tax payment by the 25th, by fixed sum (35%) or self-assessment;
  - GSTR-3B by the **24th** for Assam.
  For a B2C-heavy publisher, QRMP cuts the filings a lot.

**Annual and limits**
- [ ] **GSTR-9:** not required if turnover ≤ ₹2 crore (FY 2024-25 onwards, Notification 15/2025-CT) [19].
  - GSTR-9C self-certified reconciliation above ₹5 crore (**VERIFY**); due 31 Dec (s.44).
  - The CA audit under the old s.35(5) has been gone since 2021 (**VERIFY**).
- [ ] **Time bar:** from the July 2025 period, no return can be filed more than 3 years after its due date (ss.37(5), 39(11), 44(2); Notification 28/2023-CT) [16].
- [ ] **Late fees and interest:** late fee under s.47 (amounts by notification, **VERIFY**); interest up to 18% under s.50 [8].

### 5.12 Can the panel produce the GSTR-1 JSON itself?
- **Yes, in practice.** The GST portal's "Prepare Offline → Upload" takes a JSON file.
  - Tally exports GSTR-1 JSON directly [33].
  - India Compliance (ERPNext) exports JSON and also talks to the portal through GSP APIs, and can compare books with the portal [30].
- **No standalone public spec, and the format moves.**
  - The JSON follows the GST Offline Tool and the GSP API schema (developer.gst.gov.in, for GSPs; the page was not readable). There is no separate public schema document for the upload JSON.
  - The format shifts with portal releases: the Table 12 B2B/B2C split (Feb 2025), Table 13 becoming mandatory (May 2025), Tables 14/15. A stale exporter means rejected uploads [12][13].
- **Plan:**
  1. Write CSVs in the Offline Tool's import templates: b2b, b2cl, b2cs, cdnr, cdnur, exemp, hsn (b2b), hsn (b2c), docs. The CA imports them and generates the JSON.
  2. Generate JSON directly, with a golden-file test against the current Offline Tool.
  3. At scale, use a GSP/ASP API with OTP consent.
- **EL now:** `export_gstr1` writes B2C, HSN and credit-note CSVs. Missing: B2B, B2C large, CDNR/CDNUR, the Table 8 exempt split, Table 13, and the B2B/B2C split of the HSN summary.

### 5.13 Input tax credit and reverse charge
- [ ] **Rule 42 apportionment** [6]:
  - Tag each purchase line T1 (non-business), T2 (exempt only), T3 (blocked), T4 (taxable only), or common credit C2.
  - Each month reverse D1 = (E/F) × C2, where E is exempt turnover and F is total turnover, plus D2 = 5% of C2 for non-business use.
  - Recompute for the whole year before the due date of the September return of the next FY; pay any shortfall with interest, or take back any excess.
- [ ] **What that means here:**
  - Paper and printing for books are T2: no ITC.
  - Course-only costs (app hosting, video production) are T4: full ITC.
  - Gateway fees, courier, rent and SaaS are common, and mostly reversed because books dominate turnover.
  - Add GST that cannot be claimed to the cost of the inventory or expense (AS 2, **VERIFY**).
- [ ] **Reverse charge register** (**VERIFY** the entries and rates in Notification 13/2017-CT(R) with the CA):
  - author and copyright royalties paid to a publisher;
  - goods transport agency freight where the agency has not opted to pay itself (5%) [1];
  - import of services (foreign SaaS, ads billed from abroad), at IGST;
  - advocate fees;
  - rent from an unregistered landlord (from Oct 2024).
  - Paperwork: self-invoice and payment voucher (Rule 52) [6].
- [ ] **Purchase reconciliation:** match the purchase register to GSTR-2B; accept or reject in IMS; follow up vendors. O [38], ZB [35], T [34] and E [30] all have this.

### 5.14 Schemes that do not fit
- [ ] **Composition:** not available. A composition dealer may not make inter-state outward supplies (s.10(2)(c)), and services are capped at 10% of turnover or ₹5 lakh [8].
- [ ] **GST TCS (s.52):** ExamLeaf's site is an "electronic commerce operator" by definition (s.2(45)). But TCS is collected only on "taxable supplies made through it by other suppliers" [8], so there is no TCS on its own sales.
  - If ExamLeaf lists on a marketplace, that marketplace collects TCS on taxable lines only.
- [ ] **Income-tax TDS for e-commerce:** old s.194-O is now s.393(1) Table 8(v), at 0.1% [91]. It is deducted by marketplaces, not by an own website.

### 5.15 Rate changes and a "Tax updates" module
- [ ] **HSN/SAC master:**
  - code, description, taxability (taxable/nil/exempt/non-GST);
  - rate history rows with effective_from/effective_to, notification number and S.No. Example: 4820 at 12% until 21 Sep 2025, exempt from 22 Sep 2025 [1][2].
  - Products point to the master; the rate is looked up by date and not typed in. Warn when a product disagrees with the master.
- [ ] **Time of supply across a rate change** follows the s.14 matrix [8]: the supply, the invoice and the payment can each fall before or after the change.
  - Credit notes keep the original invoice's rate.
  - On the effective date, reprice open carts, staff draft orders and quotes.
- [ ] **Updates log:** for each update, record:
  - source (CBIC notification or circular, GST Council press release, GSTN advisory, IRP/e-way bill portal news, Assam SGST notification);
  - issue date and effective date;
  - affected HSNs or forms, and a one-line summary;
  - action, owner, status and the linked product changes.
  No official RSS feed was found to automate this; it is a manual review.
- [ ] **Threshold monitor (rolling FY turnover, exempt included):**
  - ₹2 crore: GSTR-9;
  - ₹5 crore: e-invoicing, leaving QRMP, 6-digit HSN;
  - ₹10 crore: the 30-day IRP limit.
  - Also flag B2C large invoices (₹1 lakh) and consignments that may need an e-way bill (₹50,000).
- [ ] **Due-date calendar with reminders:** GSTR-1/IFF, GSTR-3B, PMT-06, GSTR-9, the 30 Nov credit-note cut-off, the Rule 42 annual true-up, quarterly TDS returns.

### 5.16 Records, retention, penalties
- [ ] **Records (s.35, Rule 56)** [6]: stock account (opening, receipts, supplies, lost, destroyed, written off, free samples), advances account, tax register, registers of every document type, supplier and customer addresses.
- [ ] **Electronic edits:** keep a log of every edit or deletion (Rule 56(8)) [6].
- [ ] **Retention:** until 72 months after the due date of the annual return for the year, or 1 year after appeals and proceedings end if that is later (s.36) [8].
  - Example: FY 2025-26 runs to 31 Dec 2032.
  - Block hard deletion of orders, invoices and credit notes in that window, even on a privacy erasure request.
- [ ] **If ExamLeaf is a company:** books kept 8 years, and an audit trail that cannot be disabled [90].
- [ ] **Penalties** [8]:
  - s.122(1)(i), no invoice or a false/incorrect invoice: ₹10,000 or the tax evaded, whichever is higher.
  - s.122(1)(xiv): taxable goods moved without documents.
  - s.125, general penalty: up to ₹25,000.
  - s.126: no penalty for minor, easily fixed mistakes (tax under ₹5,000) made without fraud or gross negligence.

---

## 6. Other Indian commerce compliance

**Consumer Protection (E-Commerce) Rules 2020** [83]. ExamLeaf is an inventory e-commerce entity, so Rules 4 and 7 apply.
- [ ] **Rule 4(1)(a):** the e-commerce entity "shall… be a company" (or a foreign company or branch). Check the legal entity. **VERIFY** with a lawyer if it is a proprietorship or partnership.
- [ ] **Rule 4(1):** a nodal contact person resident in India.
- [ ] **Rule 4(2):** display the legal name, headquarters and branch addresses, website details, and the email and phone of customer care *and* of the grievance officer. Keep these as editable panel settings shown in the footer and on the contact page.
- [ ] **Rule 4(4)–(5):** name the grievance officer (with contact and designation) on the site. Acknowledge every complaint within **48 hours** and resolve it within **one month**. The panel needs a ticketing module with SLA timers.
- [ ] **Rule 4(8):** no cancellation charge unless ExamLeaf bears the same charge when it cancels.
- [ ] **Rule 4(9):** consent by an explicit act only, with no pre-ticked boxes (newsletter, WhatsApp, add-ons).
- [ ] **Rule 4(10):** refunds as prescribed by RBI, within a reasonable time.
- [ ] **Rule 4(11):** no price manipulation for unreasonable profit, and no discrimination between consumers of the same class.
- [ ] **Rule 7(1):** show prominently:
  - (a) return, refund, exchange, warranty, delivery, shipment and return-shipping cost, payment modes, grievance mechanism;
  - (b) mandatory notices;
  - (c) payment methods and their security, fees, charge-back options, and the payment provider's contact (Razorpay);
  - (d) contractual information;
  - (e) **the total price as one figure with its breakup** (delivery, postage, handling, tax);
  - (f) **a ticket number for every complaint**.
- [ ] **Rule 7(2):** no reviews posted by the entity posing as a consumer. Staff must not write reviews as customers; keep a review audit log (EL moderates reviews).
- [ ] **Rule 7(3):** advertising must match the product.
- [ ] **Rule 7(4):** take back and refund goods or services that are defective, deficient, spurious, not as described, or delivered late (force majeure excepted). This covers courses.
- [ ] **Rule 7(5):** if ExamLeaf vouches for authenticity, it bears liability for it.

**Dark Patterns Guidelines 2023** (CCPA, 30 Nov 2023; 13 named patterns) [84]. Panel guardrails:
- [ ] "Only N left" and countdowns appear only when true (false urgency).
- [ ] No items added to the basket on the buyer's behalf, such as donations or insurance (basket sneaking).
- [ ] Every fee shown before checkout (drip pricing).
- [ ] No guilt-trip copy (confirm-shaming).
- [ ] No hard-to-cancel subscriptions, repeated nagging, trick questions, disguised ads, or bait-and-switch.

**RBI payment aggregator guidelines** (17 Mar 2020) [82]
- [ ] Refund to the original payment method unless the customer agrees to another mode (para 12.4).
  - For COD refunds, record the customer's choice of bank account or UPI ID.
- [ ] Show the terms and the return/refund timelines on the site (para 7.2).
- [ ] Merchant settlement is due by T+1 of the relevant trigger date (para 8.4). Razorpay's domestic cycle is T+2 working days [76].

**Legal Metrology (Packaged Commodities) Rules 2011.** **VERIFY**: consumeraffairs.nic.in could not be reached on 2026-10-09, and no primary text was read.
- [ ] Ask whether a loose book is a "pre-packaged commodity". Shrink-wrapped sets and bundles are more likely to be.
- [ ] If the rules apply, Rule 6 declarations go on the pack: maker/packer, country of origin, common name, net quantity in units, month and year, MRP including taxes, consumer care.
- [ ] They also go on the product page (the e-commerce rule).
- [ ] Either way, print MRP and "Country of origin: India" on the book and show both on the page. It is cheap.

**MSME vendors** [89]
- [ ] Pay Udyam-registered micro and small suppliers by the agreed date (no more than 45 days after acceptance), or within 15 days if there is no written agreement (MSMED s.15).
- [ ] A late payment is deductible only in the year it is paid (Income-tax s.43B(h)).
- [ ] Traders are excluded. For companies, MSME Form 1 is a half-yearly return (**VERIFY**).

**Income tax**
- [ ] TDS sections were consolidated into s.393 of the Income-tax Act 2025 from 1 Apr 2026 [91]. Keep the rate tables configurable.
- [ ] **VERIFY** with the CA whether COD (cash collected by couriers) affects the 95%-digital condition for the tax-audit threshold.

**Publisher-specific**
- [ ] **Delivery of Books and Newspapers (Public Libraries) Act 1954:** one copy of every book and edition goes, at ExamLeaf's cost, to the four depository libraries: National Library Kolkata, Connemara Chennai, Asiatic Society Mumbai, Delhi Public Library [88].
  - The deadline is within 30 days of publication (s.3; **VERIFY** against the Act text).
  - Panel: a legal-deposit checklist for each new title or edition, recorded as a free-sample stock movement with a challan and proof of dispatch.
- [ ] **ISBN** [85][86]:
  - free, from the Raja Rammohun Roy National Agency (isbn.gov.in);
  - one per format (print and e-book need different ISBNs);
  - a new ISBN for a substantial text change, but not for an unchanged reprint;
  - printed on the copyright page and, preferably, on the back cover with the EAN-13 barcode.
  - Panel: ISBN-13 checksum, one ISBN per format, barcode output.
- [ ] **Press and Registration of Periodicals Act 2023:** it covers periodicals and excludes books [87]. Registration with the Press Registrar General (PRGI) is needed only if ExamLeaf starts a periodical, such as a monthly current-affairs magazine.
- [ ] **Privacy (DPDP Act):** not researched here. Erasure must yield to the tax retention in §5.16; EL already anonymises rather than deletes orders.

---

## 7. Reporting

| Report | Contents | Who | Priority |
|---|---|---|---|
| Sales by product/subject/class/board/edition/period | Units, gross, discount, net, by day/week/month | S [65], W [71] | Must |
| Sales by state/district/PIN | Doubles as the place-of-supply check | S [65] | Must |
| Sales by channel | Website, staff/phone, school quotes, marketplace | S [65] | Should |
| GST liability | Output tax by rate and place of supply (CGST/SGST/IGST); ties to GSTR-1 and 3B | ZB [35], T [34], O [38], E [30] | Must |
| HSN summary and document register | Table 12 B2B/B2C; Table 13 series with cancelled counts [12][13] | E, T | Must |
| Exempt vs taxable turnover and Rule 42 working | Monthly D1/D2 and the annual true-up [6] | – | Must |
| ITC register and 2B/IMS reconciliation | Matched, missing, rejected | ZB [35], E [30] | Should |
| Inventory | On hand by batch and location, valuation (FIFO or weighted average), movement ledger, ageing, sell-through, days of cover before exams | S [65], O [41] | Must |
| Codes | Printed, sold, activated, revoked by batch; activation rate | – | Must |
| Cohorts and retention | First-purchase month, repeat in the next exam year, lifetime value | S [65] | Should |
| Payment mix | UPI/card/netbanking/COD/offline; success rate; gateway fee % | RZ [81] | Should |
| Courier performance | Days to deliver by courier and state, NDR %, RTO %, cost per parcel | SR [72] | Should |
| Refunds, returns, cancellations | Rates and reasons by product | S, W [69] | Should |
| Coupon and offer performance | Uses, discount given, orders, margin effect | W [71], S | Should |
| COD ageing and remittance | Delivered but unremitted, short-paid | SR [72] | Must (if COD) |
| Razorpay settlements | Gross, fees, GST, refunds, net, UTR for each settlement | RZ [77] | Must |
| Deferred course revenue | Opening + sold − recognised = closing | – | Should |
| P&L by line | Books vs courses; margin including GST that cannot be claimed | O, T [34] | Should |
| Grievance SLA | Acknowledged in 48h, resolved in 30 days, open tickets [83] | – | Must |
| Abandoned checkout recovery | Recovered sessions and sales | S [61] | Later |

---

## 8. Questions for the CA or lawyer
1. How to tax a book sold with a printed course code: split lines, composite or mixed? Is an Assam advance ruling worth seeking?
2. In GSTR-1 Table 8, do 4901 books go under "exempted" or "nil rated"?
3. What is ExamLeaf's legal form? This decides E-Commerce Rule 4(1)(a) and the Companies Act audit trail and retention.
4. Do payments to authors, editors and question-setters fall under reverse charge (copyright transfer, or a plain service)? At what rate?
5. What rate applies when the printer prints on its own paper (12%, or another rate after 22 Sep 2025)?
6. Do the Legal Metrology (Packaged Commodities) Rules apply to single books or to shrink-wrapped sets?
7. What revenue policy fits course access and bundles (AS 9 or Ind AS 115)? Straight-line over the access period?
8. How to report B2C credit notes, netted in Table 7, and refunds after the 30 Nov cut-off?
9. Has Rule 138(14)(e) been updated to point to 10/2025, for notebook consignments?
10. How do shipping and a COD fee behave in mixed carts?
11. Does COD cash affect the tax-audit threshold?
12. Should ExamLeaf opt for QRMP?

---

## Appendix A: what examleaf-web already has against the gaps found here

**Has**
- Tax-inclusive prices, with the HSN and rate copied onto each order line.
- Invoices numbered in a 16-character series per FY, plus a separate credit-note series linked to refunds; invoice PDFs; a test series.
- Staff orders with Razorpay Payment Links; offline payments shown on the invoice; signed internal notes; order history (simple_history).
- `Shipment` with courier and tracking entered by hand.
- `Refund` through Razorpay; `Coupon`, `Offer`, `ShippingRate`, `PinCode`, `StockAlert`, `QuoteRequest` (with GSTIN, discount and shipping); review moderation.
- `export_gstr1` (B2C, HSN and credit-note CSVs) and `reconcile_payments` (finds stuck Razorpay payments).

**Gaps that matter most**
1. Rule 46A document titles, and separate documents for registered buyers.
2. A separate series per document type, plus the Table 13 register.
3. An HSN master with dated rates in place of the per-product `gst_rate`.
4. Billing state, and so place of supply, for digital-only orders.
5. Shipping following the goods in mixed carts.
6. The missing GSTR-1 sections.
7. Purchases and expenses with Rule 42 tags.
8. Razorpay settlement and COD remittance reconciliation.
9. Print-run batches, stock valuation, and book codes as serials.
10. A grievance ticketing module with the 48h/30-day timers.
11. Returns (RMA).
12. A turnover monitor (e-invoicing comes later).
