# Package P11: Home and Reports (model: Claude Sonnet 5.5)

Ports: Django 8121, console 3041 (`E2E_API_PORT=8121 E2E_WEB_PORT=3041`). Read COMMON.md first. Your worktree is a
checkout of the `phase-b` integration branch, which already holds batch A (Orders, Tax, Content, Support, Legal and
privacy, Staff, Settings and System) and, in parallel with you, Finance, Catalogue, Course and Customers are being
built (import their models lazily and skip a card when an app or model is absent, so your branch works alone). Read
`examleaf-web/CHANGELOG.md`'s Phase B entries and the Phase B sections of API.md before building.

Plan rows: section 5.1 (every row marked **must**), section 5.16 (every row marked **must** that the platform owns:
sales by product, subject, class, board and period; sales by state, district and PIN with the minimum cell; codes by
batch; course health aggregates; learner cohorts aggregate only; the minimum cell size settings; exports; COD ageing
and settlements; the rules for predictions (exist in `insights`); the fraud rules exist), 5.0. Research:
`research-lms-crm-cms.md` 5.1 to 5.8, `research-commerce-gst.md` 7, `research-b2b-predictive.md` 4.1, 4.6, 5.

## What exists (read before building)

`insights/` (`README.md`: the rules every number follows; `models.py`; `api.py`: forecasts, print runs, backtests,
item stats, chapter stats, cohorts, code activation, delivery, fraud signals, offers; `stats.py`: the arithmetic;
`jobs/`), `ops/templatetags/dashboard.py` and `shop/templatetags/shop.py` (the admin index's "ExamLeaf at a glance",
`store_stats()`, the "Waiting" line that counts test orders), `shop/admin.py`'s dashboard pieces, `staff/api.py`
(`SystemView`, the inbox count), the console's Home page (`src/app/(panel)/page.tsx`: inbox, approvals, clocks,
health, quick links) and `src/lib/modules.ts` (`insights` is a `soon` module), `shipping/` (CodRemittance, the
delivery stats), `shop/models.py` (Order with `livemode`, OrderItem), `learn/models.py` (BookCode, Progress,
QuizAttempt, CardReview), `content/models.py`.

## Backend: `insights/metrics.py` (one function per metric), `insights/reports.py` (the report queries), `insights/staff_api.py` mounted at `/api/v1/staff/home/` and `/api/v1/staff/reports/` (two `include` lines, tags "home (staff)" and "reports (staff)")

1. **Metric definitions**: `insights/metrics.py` with one function per metric, each with a docstring that is the
   definition the panel shows on hover, a `Metric` dataclass answer `{key, label, value, definition, as_of, period}`
   and test mode excluded by construction: net revenue (captured payments less refunds processed, in the period),
   orders placed, orders to pack, codes redeemed, active learners (accounts with any course activity in the last 7
   days, as a count), completed clips, quotes open, tickets due today and breached (from `support` lazily), reports
   open and items flagged (from `content` lazily), refunds to approve and bank refunds to mark paid (from the
   change requests and `shop.Refund`), unmatched settlement items (from `shop.Settlement` lazily), COD overdue (from
   `shipping`), legal clocks nearest (exists on Home: keep). Each used by Home and Reports and by nothing else that
   defines the same number (replace `store_stats()`'s duplicates with calls into this module where the admin's
   dashboard still uses them, keeping the admin's output).
2. **Home** `GET home/` (any staff: the manifest's permissions decide the cards; the backend returns only the cards
   the person's permissions allow, with `as_of`): the cards per role of section 5.1 (owner: net revenue, orders,
   codes redeemed, active learners; sales: to pack, quotes open; support: tickets due, breaches; content: reports
   open, flagged items; packer: to pack; finance: refunds to approve, unmatched settlement items, COD overdue), each a
   link to the list it counts already filtered (`href` with the filters in the URL as the modules draw them), a
   comparison with the previous period for the money and count cards (same length, as a plain number, no chart), and
   `test_mode` flagged when any test row would otherwise show. The existing Home parts (inbox, approvals, clocks,
   health, quick links) stay.
3. **Reports** under `reports/` (`staff.view_insights` and the data's own `view_` permissions where a report reads
   another app: name both on the endpoint through a callable permission that requires `staff.view_insights` and the
   model's view permission): `sales/` (by product, subject, class, board, edition if present, and period, with
   units, gross, discount, net, by day, week and month; the period bounded to 13 months), `sales-by-place/` (state,
   district, PIN; cells under the minimum hidden as `{hidden: true, under: 10}`), `codes/` (printed, sold, activated,
   revoked by batch and the activation rate; by district with the minimum cell; reuse `CodeActivationStat` where it
   has the numbers), `course-health/` (aggregate by subject and chapter: active learners per day, week and month
   smoothed over 7 and 28 days, clip completion, quiz accuracy, card reviews and lapses, codes redeemed by week),
   `cohorts/` (exists in `insights/api.py`: link, do not duplicate), `cod/` (ageing and remittance from `shipping`),
   `settlements/` (gross, fees, GST, refunds, net and UTR per settlement from `shop.Settlement` lazily; "not
   configured" when absent), `print-run/` (`POST`: the newsvendor inputs net price, print cost and salvage for a
   product, recomputed with `insights.stats`' function, answered with the critical ratio and the recommended size at
   that percentile from the latest forecast; the forecast and backtest endpoints exist). Minimum cell sizes as
   settings (`INSIGHTS_MIN_CELL` 10 for district, school, cohort and search tables; 5 for a class's aggregates),
   applied by one helper used by every report. Every report answers `{definition, computed_at or as_of, rows}`.
4. **Exports** of any report as a job (`Job.Kind.REPORT_EXPORT`, `staff.export_report`, new, high: FINANCE, ADMIN,
   OWNER, AUDITOR): the current filter, logged, capped by `export_rows` with approval above, formula cells escaped,
   never a date of birth or a parent's contact (the reports carry none: a test).
5. The admin index's "Waiting" line gated and without test orders (fix the existing templatetag through the metrics).
6. No per-student rows anywhere in your endpoints (a test that no report has a key to a user).

## Tests the exit criteria need

Each metric on a fixture with a test order excluded; the home cards by role (an OWNER gets the money card, a PACKER
only to pack and the inbox); the comparison with the previous period; each report's totals on fixtures; the minimum
cell hiding; the export job and its cap; the print-run recomputation against a hand-worked example (critical ratio
0.71 for net 195, cost 60, salvage 5); every endpoint in the matrix; query counts (one query per report, not per row).

## Console

Home draws the role's cards from `GET home/` first (streamed: the cards that are ready show first), each a link,
with "Data as of" and the definition on hover (a `title` and a visible "How this is counted" disclosure for keyboards),
the existing parts below; on a phone the packer's and support's queues first. `/reports/` (the `insights` entry of
`MODULES` becomes `reports`: sales, place, codes, course health, cohorts, COD, settlements, forecasts and print runs
(the recommended run with its range, the method and last season's error in one panel; the newsvendor inputs as
editable fields with the result recomputed), each page saying how each number is defined and when it was computed; a
small cell shows "fewer than 10"; export as a job with `JobProgress`). No chart needs a legend to be read: use tables
and plain bars (CSS widths), no chart library. Mock fixtures for every state. Mock journey: Home cards for OWNER and
PACKER (the `staff_mock_role` cookie) → reports → sales → export job. Real journey (`real.spec.ts`): the OWNER's Home
shows the money card with the seeded order counted once.

## Boundaries

The forecasts, backtests, item stats and fraud signals exist in `insights/api.py`: draw them, do not rebuild them.
Finance's settlements, Course's codes and Support's tickets are read lazily. Do not edit `staff/api.py`.
