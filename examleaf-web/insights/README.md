# Insights: the predictive jobs of the Admin Control Panel

The numbers the panel shows beside the facts: demand forecasts and print runs, the quiz's item analysis, cohorts, code
activation, delivery times, fraud signals and what offers did. The research behind every method is
`docs/research/2026-10-09-admin-control-panel/research-b2b-predictive.md`, section 4 (and section 0 for why).

Each job is a function over the database's rows (`insights/jobs/`) that writes its own rows in one transaction. A
Celery task runs each at night (01:00 to 03:00, `settings.CELERY_BEAT_SCHEDULE`), `manage.py insights_run <job>|all`
runs them by hand, the admin lists their rows read-only (Insights), and `/api/v1/insights/` gives them to staff
(API.md, "Insights (staff)"). The arithmetic is in `insights/stats.py`, on plain lists, checked against numbers worked
out by hand in `insights/tests/test_stats.py`. No library beyond the standard one: seasonal naive, a growth factor,
quantiles and correlations are a few lines each.

## The rules every number follows

- **A method must beat a naive baseline before the panel shows it.** The backtest stores `shown`; the API says
  `shown` and gives the last backtest's errors with every forecast. A forecast whose method has not been backtested
  yet (fewer than two seasons of sales) says so (`backtest: null`, `shown: false`): the panel labels it, or hides it.
- **Every number comes with how it was made:** the method, the data's time (`data_as_of`), the last backtest, the
  sample size (`n`), and a range (P10 to P90) where it is a prediction.
- **Rules before machine learning.** Below about 200 known outcomes (returned parcels, schools won or lost), a model
  only fits noise. Every score here is a rule with its reasons, the strongest three first.
- **Aggregate learner data only.** The DPDP Act, s. 9(3), forbids "tracking or behavioural monitoring of children or
  targeted advertising directed at children"; a child is anyone under 18 and most Class 12 students are. ExamLeaf is
  not an educational institution, so the exemption for schools does not cover it. So: no row in this app points to an
  account (a test asserts that no model has a key to the user or the learner), no per-learner list, risk score or
  ranking, groups under 5 show their size only, and nothing here may feed marketing, prices or offers. Flags about one
  student are for a school that is the data fiduciary, with ExamLeaf its processor, and only after legal review.
- **No raw phone numbers, emails or IP addresses.** What the fraud rules count (an account, an IP address, a phone
  number, an address, a code) is a keyed hash (`INSIGHTS_HASH_SALT`, else `SECRET_KEY`): equal values match, none can
  be read back. A new key starts the counts afresh.

A `district` of null is every district together; "unknown" is a PIN code missing from India Post's directory and
no district typed in the address (or, for book codes, no order to take one from).

## The jobs

### Demand forecast (`forecast_demand`, 01:15)

- **Inputs:** the copies of each printed book sold (orders that count: placed, not cancelled or refunded, not test
  mode on a live site; a bundle's copies count for its books), by week of the season and by district (the order's PIN
  code through `PinCode`, else the district typed); "email me when it is back" requests as copies the stock-out hid;
  the exam seasons staff enter (admin, Insights, Exam seasons). A season is the 52 weeks before its first paper.
- **Method:** a title's line is every printed book of its subject and kind (a new edition is a new product, so a new
  title takes the previous title's curve). Week w this season = week w last season × a damped growth factor: this
  season so far ÷ the same weeks last season, pulled toward 1 while few weeks are in (weight weeks ÷ (weeks + 4)).
  The growth factor is dropped (1, the plain seasonal naive) for a line whose backtest found it worse than none.
  P10 and P90: the 10th and 90th percentiles of last season's one-week-ahead errors (actual ÷ forecast) once there are
  ten weeks of them, else the stated default of 0.6 and 1.5 times the median. Districts: top-down, by last season's
  shares (never Croston's method on tiny district series). Two wanted titles of one line share its forecast by their
  sales this season.
- **Output:** a `ForecastRun` (method, parameters with each title's growth, spread, whether backtested and its share
  of the line, data time, code version) and its `Forecast` rows: per title and week from this week to the exam, every
  district together and each district.
- **How to read it:** P50 is the middle of the week's copies; four weeks in ten fall outside P10 to P90. `n` is the
  copies the forecast stands on: below a few dozen, read the range, not the middle. Nothing is forecast for a line
  with no sales last season: the first season gives the history.

### Backtest (`backtest`, 01:00)

- **Method:** rolling origin across last season's 52 weeks, from each origin (the weeks before it known) the forecast
  1 and 4 weeks ahead from the season before, against the seasonal naive (the same week of the season before). WAPE =
  sum of absolute errors ÷ copies sold (never MAPE: it divides by weeks that sold nothing); seasonal MASE = the
  method's mean absolute error ÷ the seasonal naive's on the same weeks. A row without a title sums every line.
- **How to read it:** MASE below 1 beats the naive, and `shown` is true. Four weeks ahead decides (about a reprint's
  lead time).

### Print-run advice (`advise_print_run`, 01:30)

- **Inputs:** the newest forecast; the title's print cost per copy, salvage per copy, copies on order and reprint
  lead time (admin, Insights, Print costs; ERPNext is to own them); its stock; the blended net price of the last
  year's sales after discounts (the selling price before it sold).
- **Method:** the newsvendor. A copy short loses Cu = net price − print cost, a copy too many costs Co = print cost −
  salvage; print the season's demand at the quantile Cu ÷ (Cu + Co). Net ₹195, print ₹60, salvage ₹5: 135 ÷ 190 =
  0.71, the P71. The quantile comes from the season's P10, P50 and P90 (a log-normal through them, each side its own
  spread). Reprint trigger: reprint once stock + on order ≤ the P90 of the demand over the lead time (the forecast
  plus the safety stock). Weeks of cover: the weeks the supply lasts, walking through the weekly forecasts.
- **Output:** a `PrintRunAdvice` per title: copies to print now, the target, the trigger, weeks of cover, the copies
  left at the exam, and a level: **act** ("reprint now": the supply is at the trigger, or lasts less than the lead time
  and a week), **watch** ("print N more for the season", or a leftover above 10 % of the supply beyond the target:
  move copies to distributors or stop the reprint), **ok**. The night's email lists the "act" ones.
- **Not yet:** printing less first and reprinting before the peak (the reprint option priced), B2B demand (the
  adoption pipeline × stage probabilities, from ERPNext).

### Item analysis (`item_analysis`, 01:45)

- **Inputs:** each learner's first attempt at each quiz item, and the option chosen for multiple choice
  (`learn.QuizAttempt.chosen`, recorded from 9 October 2026).
- **Method:** p = the share right; discrimination = the corrected item-total point-biserial (the answer against the
  learner's share right on the chapter's other items). Flags, TIMSS's thresholds: `low_discrimination` (below 0.10),
  `too_easy` (p above 0.95), `too_hard` (p below 0.25, multiple choice), `distractor_<n>` (a wrong option with a
  positive point-biserial: often a wrong key). Only once 30 learners answered (an own rule of thumb); n is always shown.
  The chapter's accuracy: the mean of its learners' shares right, and the last four weeks' less the four before.
- **How to read it:** fix the flagged items, choose webinar topics from hard chapters, look for errata. A flag is a
  prompt to look, not a verdict: an option chosen by a handful of learners can show a positive point-biserial by
  chance (the seeded data of 9 October did, with six).

### Cohorts (`cohorts`, 02:00)

- **Method:** a cohort is the month a learner's course first opened and how (book code, purchase, staff grant); each
  week since, the share active (a quiz answer, a flash card or a clip that day; a clip counts on the day of its last
  progress only, as the course keeps no more), and the share gone quiet (no activity for 14 days), while the exam is
  ahead (the exam date the learner gave). Groups under 5: the size only.
- **How to read it:** retention curves to compare cohorts; never a list of who left. Nudges go only through the
  reminders a learner turned on.

### Code activation (`code_activation`, 02:15)

Codes printed and redeemed per batch, in all and in the last 7 days, and by district: the redeemer's last order of the
code's subject before the redemption (its PIN code); a code from a book bought in a shop has none ("unknown").
Districts with fewer than 5 redemptions in a batch are counted together as "other districts".

### Delivery (`delivery_stats`, 02:30)

Days from shipped to delivered, per courier and destination district over the last year: the median (what checkout
could promise) and the P90. `insights.jobs.delivery.is_late(shipment)` is true past the route's P90 (5 deliveries
needed, else the courier's anywhere): the time to chase the courier.

### Offer effectiveness (`offer_effectiveness`, 02:45)

For each coupon and offer used in the last year: the orders that used it, their revenue, the discount given, every
order while it ran, every order in the same weeks a year before, and a 95 % interval for the ratio of the two (counts
taken as Poisson, the normal approximation on the log scale). Below 30 orders on either side, or when it ran last year
too, or when the interval holds 1, the note says "Not conclusive". It never names a winner: stopping as soon as a test
looks good turns a 5 % false-positive rate into 26 %.

### Fraud rules (`fraud_rules`, 03:00, then the email)

Each finding is a `FraudSignal`: its kind, the subject's hash, a count, a window, and details with no personal data
(the batches, and the order numbers or book code ids behind it, at most 20, for staff to open):

- failed book codes from one account (5) or one IP address (10) in an hour, and an hour with at least 20 failures
  and three times the median hour of the week before (OWASP's token cracking); every try in the app is kept as a
  `RedemptionAttempt` (hashes of the account, the address and the code, the batch, the outcome; 180 days);
- one account redeeming more than 4 codes in 30 days (resale); one code tried by 3 accounts (a shared photo);
- 3 accounts sharing a phone number or an address on cash-on-delivery or coupon orders in 90 days.

A signal seen again updates the open one; once acknowledged (admin action), it comes back only if it grew. The email
to `INSIGHTS_ALERT_EMAILS` lists the night's new or grown signals and the print runs to act on. Not yet, for want of
data: redemptions from a batch not yet dispatched (no dispatch date: ERPNext's Book Code Batch), repeated COD refusals
(no parcel outcome: the shipping app).

### Rules without a job

- `insights.jobs.risk.rto_risk(order, history)`: a cash-on-delivery order's risk of coming back unpaid. The PIN code's
  return rate smoothed toward its district's (20 parcels' weight), the customer's earlier returns, a first COD order,
  the order's value, a PIN code missing from the directory or in another state: **high** from 4 points (prepaid only,
  or confirm by SMS or WhatsApp), **medium** from 2 (a call), **low** (ship). `history` (`RtoHistory`) is what the
  shipping app will fill from its parcels' outcomes; zeros until then.
- `insights.jobs.risk.score_account(signals)` and `score_accounts(kind, accounts)`: a school's or distributor's
  score (ordered or adopted last year, verified teachers, codes redeemed nearby, a sample followed up, Class 12 pupils,
  months without contact), into `AccountScore`. No data source yet: the schools and distributors will be ERPNext's.

## The monthly review, in season

1. `dj insights_review`: each title's last four complete weeks, the forecast made before each week began, the copies
   sold and the seasonal naive, with the WAPE of both.
2. Read the backtest (admin, Insights, Forecast runs, the newest backtest: its summary). A method that loses to the
   naive two months running is retired; the forecast already drops the growth factor of a line whose backtest it
   lost, and the review shows whether the naive keeps winning this season too.
3. Look at the "act" and "watch" print runs and the fraud signals still open; acknowledge what was handled.
4. Write what changed (a price, an exam date moved, a stock-out) into the season's notes (admin, Insights, Exam
   seasons): next season's review reads them.

## When to graduate a method

- **ETS** (statsmodels' `ETSModel`, Holt-Winters with a damped trend) once there are two or three seasons of weekly
  history, and only if it beats this method in the backtest. pandas and statsmodels come in then, not before.
- **Logistic regression** (scikit-learn) for COD returns after about 200 returned parcels, for schools after about 200
  with a known outcome; its probabilities are calibrated, which a random forest's are not. Prophet: no ("several
  seasons of historical data").
- Never for learners: no model predicts anything about one student here.

## Seams

- The API is on the staff app's rules (`staff.api.StaffAppView`): `staff.view_insights` (FINANCE, MARKETING, ADMIN,
  the owners, AUDITOR) reads, `staff.acknowledge_signal` (ADMIN, the owners) acknowledges a fraud signal there and in
  the admin; on the admin host only; refusals and acknowledgements in the audit log. Fraud signals do not file staff
  inbox items yet (the nightly email tells `INSIGHTS_ALERT_EMAILS`).
- `RtoHistory` waits for the shipping app's parcel outcomes (delivered, returned to origin, lost; the RTO reason); the
  repeated-refusal rule and the RTO model wait for the same.
- `PrintCost` and the stock are to come from ERPNext (Item valuation, purchase orders, stock per warehouse) through the
  integrations; `AccountScore` from its schools and distributors; a batch's dispatch date from its Book Code Batch.
