# B2B channel management and predictive analytics: research for the ExamLeaf admin panel

Research for the Admin Control Panel plan (distributors, schools, teachers, predictions), read on 2026-10-09.
`[n]` is entry n in `sources-b2b-predictive.md`. **Must** = needed for the first season with a handful of
distributors and schools; **Should** = next, once a season has run on it; **Later** = only when volume
justifies it. Names in `code` are proposals unless marked *(exists)*; "exists" facts come from reading
`examleaf-web` (shop, learn, practice, accounts models) on the same day.

---

## 0. Facts that change the brief (read first)

1. **Printed books are exempt, so most of the GST paperwork in the brief does not apply to them.**
   - Printed books (HSN 4901) are nil-rated at entry 119 of Notification 2/2017-CT(Rate) [25]. A registered
     supplier of exempt goods issues a *bill of supply*, not a tax invoice (CGST s.31(3)(c)) [23]. The code
     already does this: shop.Invoice is "a bill of supply while every book is exempt" *(exists)*.
   - Bills of supply are outside e-invoicing: "Bill of Supply and Delivery Challan/Job Work Challan need not
     be reported under E-Invoicing" [26].
   - No e-way bill is needed for goods in the Notification 2/2017 schedule (Rule 138(14)(e)) [22]. The
     ₹50,000 e-way-bill threshold (Rule 138(1)) [22] only matters for a consignment that also carries taxable
     goods (stationery, merchandise).
   - The course is taxable (the code refuses HSN 4901 for a digital product *(exists)*). A course licence
     sold to a GST-registered buyer needs an e-invoice once aggregate turnover passes ₹5 crore (from
     1 Aug 2023) [26][27]. Most schools have no GSTIN, so their purchases are B2C. Ask the CA how to treat
     a course code printed inside an exempt book.
2. **Sale-or-return runs on a six-month clock.** Goods "sent or taken on approval for sale or return" must be
   invoiced at acceptance or "six months from the date of removal, whichever is earlier" (s.31(7)) [23].
   They travel on a delivery challan (Rule 55(1)(c): serially numbered, at most 16 characters, with HSN,
   quantity and value) [24]. In practice the trade sells *firm, with capped exceptions*. LEAD School's
   distributor terms accept returns for damaged books (reported within 1 month), misprints (15 days),
   revised editions and, "in very exceptional cases", unsold books (within 12 months). All returns are capped
   at "a maximum of 10% of gross sales invoiced", books must be in mint condition and in sets, and the
   distributor pays freight [19].
3. **Season shape.** S. Chand books 70–80% of its annual revenue in Jan–Mar, with peak receivables then. It
   takes "return of unsold stock from distributors" in Jul–Sep and does "final reconciliation and closure
   of distributor accounts" in Oct–Dec, before the season [17]. Assam's HS (Class 12) finals ran
   11 Feb–16 Mar 2026, with practicals 27 Jan–7 Feb (news report; check on the ASSEB site) [82].
   Sample-paper demand stops at the exams, so forecasts must be weekly and end on a fixed date.
4. **Children's data law makes "learner at-risk prediction" the riskiest item in the brief.**
   - DPDP Act s.9(3): "A Data Fiduciary shall not undertake tracking or behavioural monitoring of children
     or targeted advertising directed at children". A child is anyone under 18 (s.2(f)) [51]. Class 12 students
     are mostly 17 and turn 18 during or after the year, so the account needs a date of birth.
   - The only exemption for education (Fourth Schedule, Part A, item 3) covers a Data Fiduciary "who is an
     educational institution", and only for tracking and behavioural monitoring "for the educational
     activities of such institution" or the safety of its enrolled children [52]. A publisher is not an
     educational institution.
   - Rules 10 (verifiable parental consent) and 12 (exemptions) come into force 18 months after
     13 Nov 2025 (G.S.R. 846(E)), that is around mid-May 2027 [52][83]. Breaching the obligations on
     children carries a penalty of up to ₹200 crore [51].
   - What follows: learning analytics in the panel stay aggregate. Flags about individual students are
     possible only where a school is the fiduciary and ExamLeaf processes data for it under a valid
     contract (s.8(2)) [51], and only after legal review.
5. **The data some asks need is not stored yet** (from the models):
   - practice.Attempt keeps one self-reported total per paper, so there is no question-level analysis of
     papers.
   - learn.QuizAttempt keeps `correct` only, not the option chosen, so there is no distractor analysis.
   - shop.Order statuses end at delivered, cancelled or refunded. There is no RTO (returned-to-origin)
     outcome, so no RTO model can be trained.
   - shop.Product.stock is a single number, so stock held by distributors cannot be recorded.
   - learn.BookCode has `batch` (the print run) and `redeemed_at`. If batches are tied to shipments, weekly
     redemptions per batch measure sell-through by distributor (1.2).
6. **Machine learning needs volume ExamLeaf will not have for a while.**
   - Zoho's Zia needs "at least 200 records that match the criteria" to train [63].
   - HubSpot's predictive score is Enterprise-only, and "it's not possible to know exactly how each input
     contributes" [62].
   - Moodle turns on four rule-based models by default. Its machine-learning dropout model is off by
     default and has to be trained on finished courses [53][54].
   - So: start with rules and naive baselines.

---

## 1. Distributor management

### 1.1 What others do
- **FMCG distributor management systems (DMS).**
  - Bizom: distributor inventory; primary orders, GRNs and distributor ledgers; billing to retailers;
    returns by SKU or invoice; secondary order booking; schemes at distributor and warehouse level; claims
    for price changes, product returns, damages and promotions; collections; ERP/Tally sync [1].
  - FieldAssist: GST invoices with the e-invoice and e-way bill made in the same step; auto-replenishment;
    expiry and damage alerts; click-to-claim with ERP sync; a multi-slab scheme engine by outlet, zone or
    rep; a distributor app; retailer ordering (eB2B) [2]. Its field sales app adds beat plans and
    geo-tagged check-ins [3].
  - Salesforce Consumer Goods Cloud: visit planning and execution, store audits, order capture, trade
    promotion management with accruals and funds, account hierarchies, targets and forecasting [4].
- **ERPs.**
  - ERPNext: a Sales Partner has a partner type, a default territory, a commission rate, item-group targets
    per fiscal year, commission-summary and target-variance reports, a referral code and an optional
    website listing [5]. Credit limits are set per customer, customer group or company. Exposure counts
    open sales orders plus outstanding invoices, and submission is blocked unless the Credit Manager role
    approves [6]. Pricing rules apply by customer, group, territory or partner, with quantity or amount
    slabs, validity dates, priorities and free-item schemes [7]. Dunning types carry a fixed charge and
    interest [8].
  - Odoo: follow-up levels triggered by days overdue, sent by email, SMS or letter, plus a customer
    statement and an aged-receivables report [9]. Consignment works by setting an "owner" on stock [10].
  - Zoho Inventory: price lists by markup/markdown % or per-item rates, up to 10 volume ranges per item,
    attached to a customer [12]. Sales return → receive → credit note, with "credit-only" handling for
    damaged goods that do not go back into stock [13].
- **Indian education publishers.**
  - Oswaal: "over 1000 direct dealers" and "more than 20,000 bookshops" [16]. Each dealer has a public page
    with a tier ("Platinum"), address, phone and map, next to a "Become Our Dealer / Distributor" link [15].
  - S. Chand: 4,907 distributors and dealers, 697 in-house sales staff and 58 branches (June 2016, from its
    offer document as quoted by an IPO site) [18]; the season calendar in §0 [17]; 89 receivable days in
    Dec 2023, "the lowest receivable days in Q3 in the past 5 years" [17].
  - ABS Publishing House (marketplace listing, low quality): returns accepted until 30 Nov, up to 20% of
    turnover [20].
  - Arihant (whose page loaded without its numbers) and Navneet: no dealer terms found in public [21].

### 1.2 Features

| Feature | Priority | What it is |
|---|---|---|
| Distributor account and KYC | Must | GSTIN (`validate_gstin` *(exists)* checks state code, PAN and check digit), PAN (characters 3–12 of the GSTIN, or typed in if unregistered), cancelled cheque, optional trade licence, agreement file with a valid-until date, contacts. Staff look the GSTIN up on the GST portal's public Search Taxpayer (legal name, status, filing record) [28]. It sits behind a captcha, so a person does the check and the panel records who did it and when, as TeacherProfile does *(exists)*. |
| Territories by district | Must | District names from shop.PinCode *(exists)*. At most one exclusive distributor per district and line, enforced by a database constraint. Competition Act s.3(4) covers exclusive distribution, judged by its effect on competition (rule of reason) [30][31]. That is unremarkable at ExamLeaf's size, but write it into the agreement. |
| Price lists and trade discount | Must | One `PriceList` serves distributors, schools and teachers: discount % off MRP per product, optional quantity slabs [7][12]. Discount levels are a commercial decision; no primary Indian source states the norm. |
| Credit limit and payment terms | Must | Exposure = confirmed unbilled orders + outstanding balance. An order over the limit cannot be confirmed unless staff with the override permission approve it, and the override is logged [6]. Terms in days per account. |
| Orders taken by staff | Must | `B2BOrder` kinds: outright, sale-or-return (SOR), specimen. PO number and file. Documents: a bill of supply for outright sales, a delivery challan for SOR and specimens [23][24]. A distributor portal is Later. |
| SOR ledger and its six-month clock | Must | Each SOR line keeps `removed_on`. A nightly job lists lines at 5 months. Bill when the distributor reports sales, or at 6 months [23]. |
| Returns (RMA) | Must | Reasons: transit damage, misprint, revised edition, unsold. Windows and cap per agreement (LEAD: 1 month, 15 days, 12 months; 10% of gross invoiced) [19]. Flow: receive → inspect → restock or write off ("credit-only") → credit note [13]. |
| Statement of account and ageing | Must | A ledger of bills, credit notes and payments; ageing by due date in 0–30, 31–60, 61–90 and 90+ day buckets; statement as PDF and email [9]. |
| Collections | Must | Reminder levels by days overdue (e.g. 3 days before due, +7, +21, and at +45 new orders are held) [8][9]. A virtual account per distributor (Razorpay Smart Collect: account number + IFSC, NEFT/RTGS/IMPS, automatic reconciliation, webhooks) [32]. Payment Links let the customer pay a set first instalment and send SMS reminders [33]; Razorpay is already used for QuoteRequest *(exists)*. Cheques recorded with number, bank and cleared date. |
| Stock at distributors (SOR stock) | Should | `StockLocation` per distributor + `StockMove`. This is Odoo's owner idea [10] the other way round: ExamLeaf owns stock sitting in the distributor's godown. |
| Sell-through without the distributor typing anything | Should | Allocate a BookCode batch (or code range) to each distributor shipment. Weekly redemptions per batch then give sell-through by distributor and district. Fallback: a monthly stock-statement CSV upload. Full retailer billing, which Bizom and FieldAssist sell [1][2], is not needed. |
| Schemes | Should | Season rules: early-order discount before a date, slab bonus, free copies per N. Accrue on orders; pay as a credit note when the season closes [2][7]. |
| Claims | Should | Transit damage, short supply, scheme payout, price difference. Photo evidence; approve → credit note [1]. |
| Sales reps and commission | Should | Rep ↔ territories. Commission on the amount *collected*, net of returns, so nothing has to be clawed back. Season targets with a variance report [5]. |
| Dealer locator on the site | Should | Public list of active dealers by district: tier, address, phone, map link. A "Become a dealer" form creates a prospect, as Oswaal's pages do [15]. |
| Distributor portal | Later | Read-only first: statement, bills, order status, SOR stock, raise a return or claim. |
| Beat plans, geo check-ins, retailer ordering | Later | The FieldAssist and Salesforce pattern [3][4]. Until there are several reps, the `Activity` log below covers visits. |
| Tally/ERP sync, e-invoicing | Later | E-invoicing applies only to taxable B2B sales once turnover passes ₹5 crore [26]. |

### 1.3 Data model (proposal)

```
Account(TimeStamped, simple_history)   # one table: kind = distributor | retailer | school
  kind, name, trade_name, gstin, pan, udise_code, status, tier, district, pin,
  credit_limit, payment_terms_days, price_list→PriceList, owner→User (rep), agreement_file, agreement_until
AccountContact(account, name, role, phone, email, is_primary)
KycDocument(account, kind, file [private storage], verified_by, verified_at, expires_on)
DistrictAssignment(account, district, exclusive)   # UniqueConstraint(district, line, condition=Q(exclusive=True))
PriceList(name, audience, valid_from, valid_to);  PriceListItem(price_list, product, discount_percent, min_qty)
B2BOrder(account, kind[outright|sor|specimen|school], status, po_number, po_file, ship_to, credit_override_by)
B2BOrderLine(order, product, qty, rate, discount_percent, class_level?, batch?)
Dispatch(order, document_kind[bill_of_supply|delivery_challan], number, removed_on)
LedgerEntry(account, date, due_on, kind[bill|credit_note|payment|opening|adjustment], amount, ref)
ReturnRequest(account, reason, lines, status, received_at, restocked, written_off, credit_note)
Scheme(season, rule JSON);  SchemeAccrual(order, scheme, amount)
Claim(account, kind, amount, evidence, status, credit_note)
StockLocation(account | null);  StockMove(product, qty, from_loc, to_loc, reason, ref, batch)   # Should
Activity(account, contact, by, at, kind[call|visit|demo|webinar|email], outcome, next_on)
```
One `Account` table rather than separate distributor, school and retailer tables keeps statements, ageing,
activities and price lists in one place. Split it only if their fields drift far apart. Extend the existing
Invoice/CreditNote numbering with B2B and challan series rather than writing new numbering code. Ageing is a
query over `LedgerEntry`, not a table.

---

## 2. School management

### 2.1 What others do
- **Publisher programmes.**
  - Oxford Advantage (OUP India): books, an LMS, apps for students, teachers and parents, teacher's
    manuals, CPD workshops, and implementation support visits all year round [35].
  - Pearson MyPedia (trade-press summary): teaching plans; a teacher portal for assigning practice; a
    parent HomeApp; assessments mapped to the school's exam plan; reports at student, teacher and school
    level; school support visits [36].
  - S. Chand: samples and teacher training in Jul–Sep, evaluation by schools in Oct–Dec. It expected
    "30%-40% schools to adopt the new curriculum", and Mylestone targets schools "giving business of at
    least Rs5L/annum" [17]. Adoption is decided every year, and schools are segmented by value.
  - OUP India takes inspection-copy requests through digital order forms [37].
- **Platforms.**
  - Khan Academy Districts: rostering through Clever or ClassLink, synced every weeknight; admin
    dashboards; reports aggregated across schools; an implementation manager [39].
  - Google Classroom: guardian email summaries. The guardian must accept the invitation, and admins turn
    the feature on or off [41].
  - Teachmint: fee management with instalments and reminders, report cards, admissions [43].
  - Classplus: batches, tests, instalment reminders, per-student reports [44].
  - OneRoster CSV: orgs, users, classes and enrollments, sent as full or delta files [45].
  - UDISE+: every recognised school has an 11-digit code (state, district, block, village, school serial)
    and appears in a public "Know Your School" search [46][47].
- **Constraint.** CBSE circular 10/2017 directs schools "to desist from the unhealthy practice of coercing
  parents to buy text books ... from within the premise or from selected vendors only" [34]. Assam's own
  rule is not verified: the 2018 Assam fee act PDF is a scan. So design for "the school recommends, the
  parent buys", alongside the school buying class or library sets.

### 2.2 Features

| Feature | Priority | What it is |
|---|---|---|
| School account | Must | `Account(kind=school)`: UDISE code, board (ASSEB, CBSE, …), management, medium(s), streams, classes, enrolment per class (from the school or its UDISE+ page [46]), district and PIN, GSTIN (usually none), contacts with roles (principal, HS coordinator, subject teacher, accounts). Link QuoteRequest *(exists)*, the inbound form, to the account. |
| Adoption pipeline | Must | `Adoption(account, academic_year, class_level, subject, product, stage, expected_copies, decided_by, decided_on, lost_reason)`. Stages: lead → sample sent → evaluating → recommended/prescribed → ordered → delivered → paid. |
| Specimen and inspection copies | Must | `SpecimenRequest(contact or teacher, account, products, status, dispatched_on, challan_no, follow_up_on)`. One copy per subject taught per season, as Oswal Publishers allows [38]. Sent on a delivery challan [24], with a follow-up date that feeds the pipeline. |
| School orders | Must | `B2BOrder(kind=school)` with lines per class, PO number, delivery to the school, bill of supply, quotation PDF *(exists)*. Payment by NEFT, UPI or cheque, a virtual account [32], or instalments through a payment link [33]. |
| Parent-pays channel | Must | A school link or code applies the school's price list in the shop. Delivery to the home, or consolidated to the school. The school sees counts per class, not names [34]. |
| Renewals | Must | At the start of each year, last year's adoptions become "renewal due" with the new edition, an owner and a due date. |
| Visits and follow-ups | Must | `Activity` (1.3), shared with distributors. |
| Course access for a whole school | Should | `SchoolLicence(account, academic_year, subjects, seats, valid_until)` creates learn.Entitlement rows *(exists; add source = licence)* for rostered students. Alternatively, a BookCode batch per school (`SCH-<udise>-<year>`). Report seats used. |
| Roster import and parent consent at scale | Should | CSV of name, class, section, parent mobile/email (a OneRoster-like subset [45]). Each parent gets a consent link; ConsentRecord already records EMAIL_LINK and SMS_LINK consents *(exists)*. The student's account is created only after consent (DPDP Rule 10) [52], and the notice is offered in Assamese or another Eighth Schedule language (s.5(3)) [51]. Khan Academy leaves permission slips to the school [40]. In India ExamLeaf stays responsible as the fiduciary unless it acts as the school's processor (s.8(1)–(2)) [51]. |
| School dashboard | Should | Class-level aggregates only: students activated, codes redeemed, mean saved marks per paper (labelled self-reported), chapters with the lowest quiz accuracy. Groups under 5 are hidden. |
| Teacher training and webinars | Should | `Event`, registrations, attendance, certificate. OUP, Pearson and S. Chand run these every season [17][35][36]. |
| SIS/ERP sync, OneRoster API | Later | [43][44][45]. |

---

## 3. Teacher management

### 3.1 What others do
- **Verification.**
  - SheerID: documents must show first and last name, school name and a "date showing employment within
    the current school year". SheerID emails "within the next 20 minutes" to confirm or ask for more [48].
  - Pearson: test banks and lecture slides are open only to verified educators, with "download limits, as
    well as discipline category restrictions", to "crack down on exam cheating" [49].
  - Oswal Publishers (a different company from Oswaal Books): asks for institute type, board, class,
    designation, subjects and an uploaded school or coaching ID card; one specimen per subject taught [38].
  - ExamLeaf today: TeacherProfile, checked by staff (for example by phoning the school), with verified_by
    and verified_at *(exists)*.
- **Linking and offboarding.**
  - Khan Academy: teachers may create accounts for under-13s after getting parents' permission, and it
    supplies a sample permission slip [40].
  - Google Classroom: guardians must accept the invitation [41]. When a teacher leaves, an admin transfers
    class ownership without the new teacher having to accept, and the old teacher becomes a co-teacher [42].
- **Incentives.** The benefits of Kahoot!'s ambassador programme are all non-cash: early access, support,
  swag and events. Ambassadors are hand-picked and not renewed automatically [50].
- **Law.**
  - Consent must be "free, specific, informed, unconditional and unambiguous", limited to the purpose, and
    as easy to withdraw as to give (s.6(1), 6(4)) [51].
  - Under-18s need verifiable parental consent (s.9(1), Rule 10) [51][52].
  - Data used for a decision about a person, or disclosed to another fiduciary, must be complete and
    accurate (s.8(3)) [51].
  - A person can ask with whom their data was shared (s.11(1)(b)) [51].
  - Access logs must be kept for at least a year (Rule 6(1)(c),(e)) [52].

### 3.2 Features

| Feature | Priority | What it is |
|---|---|---|
| Verification, version 2 | Must | Evidence: a school ID card, an appointment letter, or a letter on letterhead signed by the principal for the current academic year; the school's UDISE code; the staff phone check *(exists)*. Status: requested → checking → verified or rejected → expired or revoked. Verification expires at the end of the academic year [48]. Link the profile to `Account(kind=school)` and keep the free-text school name for unknown schools. Delete the evidence file N days after the decision; keep the note and the file's hash. |
| Gated teacher resources | Must | Answer keys, marking schemes and PDFs for verified teachers only. Each PDF watermarked with the teacher's name and ID; downloads logged; a daily limit; scoped to the teacher's subjects [49]. |
| Revocation and offboarding | Must | Staff revoke with a reason; a teacher can mark "left this school". Class links end at once, and classes move to another verified teacher at the school [42]. Everything goes in the history/audit log. |
| Error reports | Must | "Report an error" on every paper, solution and clip, marked when the reporter is a verified teacher. A triage queue, an errata page, and named credit for the reporter. |
| Classes and consented links | Should | `TeacherClass(teacher, account, academic_year, class_level, section, subject, join_code)` and `ClassMembership(class, student, status, consent→ConsentRecord, scopes)`. The student joins with a code. For an under-18, the parent gets an itemised request, e.g. "saved marks, course progress and quiz results for Physics, shared with <teacher> at <school>, until 31 Mar <year>". The teacher sees data only after consent. Student and parent can withdraw with one tap [51]. Links expire at the end of the year. |
| Teacher dashboard | Should | Class aggregates first; per-student rows only for members who consented. Weak chapters = lowest class quiz accuracy. Self-reported marks labelled as such. |
| Assignments | Should | `Assignment(class, kind[paper|chapter|quiz], target, due_on)`. Completion is computed from Attempt, QuizAttempt and Progress *(exist)*, as on Khan Academy and MyPedia [36][39]. |
| Teacher pricing and specimen allowance | Should | A PriceList for teachers; one specimen per subject per season [38]. |
| Ambassadors, without cash | Should | Hand-picked verified teachers per district. Benefits: new editions free, early access, review panels, credit for errata, webinar slots, a certificate [50]. Referral codes give the *student* a discount. No commission to a teacher on their own pupils' purchases, the practice CBSE's circular targets [34]. |
| Community forum, teacher-written content | Later | |

---

## 4. Predictive analytics

### 4.1 Rules for every prediction in the panel
- A method must beat a naive baseline in a backtest before the panel shows it [69][71].
- Show the number with a range, the method, the last backtest error, the data's as-of time and the two or
  three signals behind it. Group predictions into buckets with an action for each; give partial
  explanations; hide confidence where it would mislead [79].
- Probabilities must be calibrated. Logistic regression usually is; random forests are not [78].
- No individual predictions about under-18 learners by ExamLeaf (§0.4). No learning data in marketing,
  pricing or offers: s.9(3) also bans targeted advertising at children [51].
- Below roughly 200 labelled outcomes, use rules, not machine learning [63].

### 4.2 Demand forecasting and print runs (Must)
**Inputs:**
- shop.OrderItem (B2C) by week and by district (PIN → district through PinCode).
- B2BOrderLine.
- shop.StockAlert *(exists)*: requests made while a title was out of stock, which is demand the sales data
  hides.
- Adoption.expected_copies × stage probability.
- BookCode redemptions per batch.
- The exam calendar.

**Method ladder** (stop at the rung where the backtest stops improving):
1. **B2C: seasonal naive by week of season.** Week w this season = week w last season × a damped growth
   factor (season to date this year ÷ the same weeks last year) [69]. A new title takes the previous title's
   curve in the same subject, scaled to its first weeks.
2. **B2B is not a time series.** Forecast it as the pipeline: Σ expected copies × stage probability (a fixed
   table, reviewed each season), plus distributor orders already placed.
3. **ETS once there are 2–3 seasons of weekly history.** statsmodels ETSModel gives prediction intervals,
   analytical or from 1,000 simulations [73]. Holt-Winters `ExponentialSmoothing` takes seasonal_periods,
   a damped trend and Box-Cox [74]. Skip Prophet, which "works best with ... several seasons of historical
   data" [75]. Do not forecast tiny district series with Croston's method: it has no prediction intervals
   and its forecasts are biased [72]. Forecast per subject and split by last season's district shares
   instead.

**Print run.** Treat each run as a newsvendor problem: print the demand quantile at the critical ratio
Cu/(Cu+Co) [76]. Cu (cost of one copy short) = blended net price after discounts − unit print cost. Co (cost
of one copy too many) = unit print cost − salvage, with salvage ≈ 0 if the paper changes each year.
- Example: net ₹195, print cost ₹60, salvage ₹5 gives Cu = 135, Co = 55 and a ratio of 0.71, so print the
  P71 of the season forecast.
- If a reprint can arrive before the peak, print less first and set a reprint trigger. Suzuki & Nakaoka
  price the reprint option explicitly, and found demand log-normal in their data [77].

**Reprint trigger.** Reprint when stock + on order ≤ forecast demand over the reprint lead time + safety
stock. The tools ExamLeaf might reach for do not forecast this:
- Zoho Inventory notifies at a reorder point you set yourself [14].
- Odoo's min/max rules act on forecasted stock (on hand + incoming − outgoing), not on a demand forecast
  [11].
- Shopify's Stocky, which forecast "the inventory that you need", stopped being available after
  31 Aug 2026 [68].

**Backtest.** Use a rolling origin across last season's weeks [71]. Report WAPE for totals and seasonal MASE
per title against seasonal naive. Not MAPE: it is undefined in weeks with zero sales [70].

**Alerts.**
- Weeks of cover = (on hand + on order) ÷ forecast weekly demand. Below reprint lead time + 1 week:
  "reprint now".
- Projected leftover at the season end (the last exam) above X% of the run: "move to distributors" or
  "stop the reprint".

### 4.3 Sales projections per subject and district (Should)
Forecast per subject, then split to districts by last season's share (top-down). Show P10–P90. A map can
come later.

### 4.4 Distributor stock, returns and sell-through (Should)
Expected returns = SOR stock − the sales implied by redemptions. Flag low sell-through by mid-January.
Moving stock between distributors before the exams is cheaper than taking it back in Jul–Sep [17].

### 4.5 School and lead scoring (Should, rules)
**Points:**
- Positive: ordered last year; adopted last year; verified teachers at the school; codes redeemed from the
  school's PIN or district; sample sent and followed up; Class 12 enrolment.
- Negative: days since last contact.

**Output:** High, Medium or Low, with the top three reasons [79].

**Compared with the vendors:** HubSpot predicts closing within 90 days, puts a quarter of contacts in each
tier and hides the factors [62]. Zia needs at least 200 records, retrains every fortnight and lists the
fields that push a prediction up or down [63]. Move to machine learning (logistic regression) only after
about 200 schools with known outcomes.

### 4.6 Learner analytics (aggregate is Must; individual only with legal sign-off)
**Evidence:**
- Moodle: the models on by default are rules (no teaching, activities due, no access since the course
  started, no recent access). Its ML dropout model's target is "no student activity in the last quarter
  of the course", predicted from engagement indicators ("cognitive depth", "social breadth"), and it needs
  courses with start and end dates [53][54][55].
- Canvas: "Students in Need of Attention" lets the institution choose criteria: last page view, last
  participation, discussion frequency relative to the class, current score, on-time and missing
  submissions [56].
- Research:
  - LMS activity counts identified 81% of failing students in one course [57].
  - Predictors differ by course, and general models over- or under-estimate [58].
  - Purdue's Course Signals retention gain looked like selection bias (blog analysis) [59].
  - Algorithmic bias across student groups is documented in education [60].

**Signals ExamLeaf has:** days since last activity; clips completed against the plan (Learner.minutes_per_day
and exam_date *(exist)*); quiz accuracy by chapter and its trend; self-reported paper marks; the flash-card
"known" rate.

**What to build:**
- **Must (aggregate only):**
  - Cohort retention by redemption month and by source (book code, paid, grant), measured as the weekly
    active share up to the exam.
  - Code activation by batch and district.
  - Chapter difficulty (4.7).
  - Groups under 5 hidden. No per-student risk lists in the admin panel.
- **Should, after legal review:**
  - An opt-in "on track for your exam date" card for the student, built from their own plan, with no staff
    view. The Act does not define "behavioural monitoring", so whether this counts is for counsel.
  - Flags shown to teachers only in school deployments where the school is the fiduciary and ExamLeaf its
    processor [51][52], using transparent Canvas-style criteria [56].
- **Never:** learning data used for ads, upsell targeting or prices [51].

**Churn:** "no activity for 14 days while the exam date is ahead", reported as cohort curves. Nudges only
through reminders the user turned on (Learner.reminders *(exists)*).

### 4.7 Chapter difficulty and item analysis (Must, aggregate)
**Statistics** (from learn.QuizAttempt, first attempt per learner per item):
- p = share of learners who answered correctly.
- Discrimination = the correlation between the item and the learner's score on the chapter's other items
  (corrected item–total, point-biserial) [61].

**Flags** (the thresholds TIMSS uses) [61]:
- Discrimination below 0.10.
- p above 0.95 (too easy).
- p below 0.25 for multiple choice.
- A distractor with a positive point-biserial, which often means a wrong answer key.

Flag only once 30 learners have answered (an own rule of thumb), and show n. Distractor flags need a `chosen`
field on QuizAttempt (Should).

**Papers:** practice.Attempt gives paper-level difficulty (mean % of maximum) only, and its marks are
self-reported and self-selected, so label them. Question-level analysis needs marks per question, from
AnswerSheetUpload results or a per-question entry (Later).

**Use:** fix bad items, choose webinar topics, find errata.

### 4.8 COD RTO risk (data fix Must, score Should)
**Data fix:** add a shipment outcome (delivered, RTO, lost) and an RTO reason.

**Rule inputs:**
- The PIN code's RTO rate, smoothed toward its district's rate.
- The customer's past RTOs.
- First COD order or not.
- Order value.
- Phone or address problems (PinCode.state_problem *(exists)*).

These match the inputs Shiprocket names: "incorrect address, Incorrect mobile number or past RTO history"
[64][65].

**Actions:**
- High risk: prepaid only, or confirm by SMS or WhatsApp before dispatch, as Unicommerce does for COD [66].
- Medium: a call.
- Low: ship.

Move to logistic regression after about 200 RTOs.

### 4.9 Delivery delay (Should)
Transit days = delivered_at − shipped_at (Shipment *(exists)*), by courier and destination district. Keep the
median and P90. Show the median as the expected delivery date at checkout. Mark a shipment "late" once it
passes P90, then chase the courier. Shiprocket ranks couriers by delivery performance per route [67].

### 4.10 Fraud and abuse (Must, rules)
- **Book codes.** OWASP lists "Token Cracking" (OAT-002): "mass enumeration of coupon numbers, voucher codes,
  discount tokens" [80]. Watch for:
  - failed redemptions per user, IP and device per hour, with an alert on spikes;
  - redemptions from a batch not yet dispatched (a leak);
  - one account redeeming many codes (resale);
  - one code tried by many accounts (a shared photo).
- **Shop:** several accounts sharing a phone or address on coupon or COD orders; repeated COD refusals.
- **Teachers:** the same evidence-file hash on two requests.
- **Distributors:** returns above the cap; frequent claims.

### 4.11 Offer effectiveness (Should)
For each coupon or offer: orders, revenue and discount cost, compared with a holdout or the same weeks last
season. Fix the sample size before starting: in Evan Miller's example, stopping as soon as a test looks
significant turns a 5% false-positive rate into 26.1% [81]. At ExamLeaf's volume most tests will be
inconclusive, so show intervals rather than winners.

### 4.12 Build path
- **Scheduling:** nightly Celery beat tasks (celery and django-celery-beat are installed *(exists)*) that call
  management commands.
- **Tables:**
  - `ForecastRun(created, method, params, data_as_of, code_version)`
  - `Forecast(run, product, district?, week, p10, p50, p90)`
  - `Backtest(run, product, horizon_weeks, wape, mase)`
  - `AccountScore(run, account, score, bucket, reasons)`: schools and distributors only, never students.
  - `ItemStat(item, n, p, discrimination, flags, computed_at)`
- **Libraries:**
  - None at first: seasonal naive, the growth factor, quantiles and correlations are a few lines of Python
    over ORM rows.
  - pandas and statsmodels only once ETS is justified (§4.2).
  - scikit-learn only for logistic regression with about 200 outcomes.
  - No Prophet.
- **Tests:** each job leaves one check. For example, seasonal naive with growth 1.0 reproduces last season,
  and a fixture item's p comes out as expected.
- **Review:** monthly in season. Compare forecast with actual and with the baseline; retire methods that
  lose.

---

## 5. Reports and dashboards for the B2B channel

| Report | Priority | Contents |
|---|---|---|
| Territory sales | Must | district × week × title; this season against last; B2B and B2C shares |
| Distributor statement and ageing | Must | balance; 0–30, 31–60, 61–90, 90+ days; credit used; accounts on hold |
| Collections due | Must | due within 14 days; overdue by reminder level; promised dates; last reminder sent |
| Returns and claims | Must | returns as % of invoiced against the cap, per distributor; reasons; open claims |
| School adoption pipeline | Must | schools per stage; expected copies and value; owner and next action; conversion from samples to adoptions |
| Renewals due | Must | last year's adopters with no order this year, by month |
| Print run and stock | Must | weeks of cover; reprint triggers; projected leftover; forecast against actual |
| Distributor stock and sell-through | Should | SOR stock; redemptions per batch; expected returns |
| Teacher activation | Should | requests, verified, time to verify, expired; verified teachers per school; consented links |
| Scheme payouts | Should | accrued against paid, per scheme and distributor |
| Rep performance | Should | target against actual; commission on collections |
| School learning summary | Should | class aggregates for the school; groups under 5 hidden |

**Default views by season.** S. Chand's calendar [17], shifted to the Assam HS exam dates [82]. Replace with
ExamLeaf's own sales weeks after the first season.
- **Apr–Jun:** close last season (bill SOR, settle returns); renewals list; plan specimens.
- **Jul–Sep:** specimens and teacher webinars; adoption pipeline; process returns.
- **Oct–Dec:** first orders; print runs; reconcile distributor accounts; review credit.
- **Jan–Mar:** reprints; move stock between distributors; collections. Demand ends at the exams.

---

## 6. Not verified, or still open
- Whether Assam has its own rule on schools selling books or naming shops (the 2018 Assam fee act PDF is a
  scanned image).
- The trade discounts and credit days usual for Assam distributors. No primary source was found; ask two or
  three distributors.
- Whether ExamLeaf is a micro or small enterprise under Udyam. If it is, buyers must pay within 45 days, and
  Income-tax s.43B(h) disallows late payments in the buyer's books. This comes from a secondary source
  [29]; it would be a lever for collections. The CA should confirm it, including which buyers it covers.
- GST on a course code printed inside an exempt book (composite or mixed supply). A CA question.
- The Moodle docs and the Canvas community pages sit behind bot checks. Their content above comes from
  Moodle's source code [53][54] and from search summaries [55][56].
- When the DPDP Act's sections (as opposed to the Rules) come into force: the Rules' text is verified [52],
  the Act's commencement notification only through a law-firm summary [83].
