# Package P6: Course (model: Claude Opus 5.5)

Ports: Django 8116, console 3036 (`E2E_API_PORT=8116 E2E_WEB_PORT=3036`). Read COMMON.md first. Your worktree is a
checkout of the `phase-b` integration branch, which already holds batch A: Content added `content.ErrorReport` (a
generic target by content type and id; category `item_analysis` exists for item-analysis flags) and the triage queue
under `/api/v1/staff/content/reports/`; Support added `support.Ticket`; Orders, Tax, Legal and privacy, Staff,
Settings and System are there too. Read `examleaf-web/CHANGELOG.md`'s Phase B entries and API.md's Content section
before building, and reuse them.

Plan rows: section 5.11 (every row marked **must**), 5.0, section 7.8's Revision, Clip/FlashCard/QuizItem (the
30-day bin), Entitlement rows, section 5.16's codes report row (printed, sold, activated, revoked by batch), section
10.1 ("Learner analytics on under-18s": aggregate only; no per-student lists). Research: `research-lms-crm-cms.md`
1.1 to 1.9, `research-b2b-predictive.md` 4.6, 4.7, 4.10, `inventory.md` 6.

## What exists (read before building)

`learn/models.py` (Chapter, Revision with `status` draft or published, Clip with the `processing` state machine and
`is_free_preview`, FlashCard, QuizItem with `is_right()`, BookCode with `batch` and digests only, Entitlement with
sources and `valid_until`, Learner, Progress, QuizAttempt, CardReview, Device), `learn/` services and tasks
(`process_clip`, `reprocess_clips`, the signed playback links, the redemption throttle), `learn/management/commands/`
(`make_book_codes`: the plain codes printed once; `build_quiz_items`), `learn/admin.py`, `insights/models.py`
(`ItemStat`, `FraudSignal` and its kinds, `RedemptionAttempt`, `CodeActivationStat`), `insights/jobs/` (which fraud
rules exist for codes), `api/learn.py` (the app's and website's course API: keep its shape), `accounts/roles.py`
(CONTENT_EDITOR and REVIEWER on `learn`, SUPPORT on entitlements and `learn.view_bookcode`), `staff/models.py`
`StaffScope` (subject), RUNBOOK "The revision course" (uploading, a failed clip, printing book codes, granting
access, a lost code).

## Backend: `learn/staff_api.py`, mounted at `/api/v1/staff/course/` (tag "course (staff)")

1. **The outline** `GET course/subjects/{subject}/outline/`: chapters → revisions → clips, cards and quiz items with
   kinds, durations, status chips, free-preview badges, counts and processing states, scoped by subject; row
   actions as endpoints: `PATCH` on each (explicit serializers of the admin's fields), **reorder without dragging**:
   `POST course/{kind}/{id}/move/` with `{to: "first" | "last" | "before" | "after", target: id}` rewriting the `order`
   fields of the siblings in one transaction (every drag in the console has this as its keyboard path).
2. **Draft, review and scheduled publish**: Revision gains `reviewer` and `publish_at`; `POST …/submit/`,
   `approve/` (REVIEWER, `staff.publish_paper`'s equivalent for the course: `staff.publish_course`, new, medium),
   `publish/` (now or at `publish_at`), a beat task every 5 minutes publishing due revisions (`single_run`), the
   same for a whole chapter; an inbox item for REVIEWER when a revision waits (`InboxItem.Kind.REVIEW` from Content:
   reuse the kind).
3. **Soft delete**: Clip, FlashCard and QuizItem gain `deleted_at`; `DELETE` sets it (a typed confirmation in the
   console for a clip), `POST …/restore/` within 30 days, the bin `GET course/bin/`, a nightly purge that deletes rows
   past 30 days and a clip's HLS files only then (the storage's delete through the existing upload helpers); the
   app's and website's API never show deleted rows (default managers or explicit filters: test both).
4. **Clips**: processing status with a plain reason and `POST course/clips/{id}/retry/` (`reprocess_clips`'s
   function), the poster and duration once ready, free-preview flag, the signed playback link for the staff player
   (exists in `learn/urls.py`: link it).
5. **The question bank** `GET course/items/`: every QuizItem with chapter, topic tags, marks, difficulty, Bloom
   level, source and tags (add the metadata fields that are missing with sensible defaults and a migration), all
   filters, and the item statistics joined from `insights.ItemStat` (n, p, discrimination, flags, computed at; "N/A"
   under 30 learners as `n_too_small: true`), `PATCH` per item and a bulk metadata edit as a job
   (`Job.Kind.BULK_ACTION` with action `item_metadata`, dry run), `POST course/items/{id}/flag/` ("needs checking":
   creates a `content.ErrorReport` with category `item_analysis` targeting the item, once while one is open), history
   on QuizItem (simple_history; migration with initial rows).
6. **Entitlements** `GET course/entitlements/` (filters by subject, source, validity, `q` by the account's masked
   email hash: a lookup event), `POST course/entitlements/` (grant with a reason), `POST course/entitlements/{id}/extend/`
   (days, reason), `revoke/` (reason), and the bulk versions as a job with a dry run (`learn.change_entitlement`;
   SUPPORT); progress kept when access ends (test: a revoked and regranted entitlement shows the same progress).
7. **Book-code batches** `learn.CodeBatch` (label as `BookCode.batch` uses it, product, printed count, generated by
   and at, `dispatched_at`, `voided_at` with a reason, the print run's note; a data migration creates batches from
   the distinct labels in `BookCode`): `GET course/codes/batches/`, `GET course/codes/batches/{label}/` (printed,
   redeemed by week, void, the fraud signals for it), `POST course/codes/batches/` (`staff.make_book_codes`, new,
   high, alert: a job `Job.Kind.CODE_BATCH` that generates the codes as `make_book_codes` does, storing digests only
   and writing the plain codes once into the job's result file, downloadable by the starter only, for 24 hours, then
   deleted by the files' purge: the printer's file), `POST course/codes/batches/{label}/dispatched/`,
   `POST course/codes/batches/{label}/void/` (`staff.void_book_codes`, new, critical: a typed confirmation in the
   console; every unused code of the batch voided), `POST course/codes/void/` (one code by its hash),
   `POST course/codes/lookup/` (a typed or scanned code: unused | redeemed with when and by whom as a masked link |
   void; a lookup event; throttled), RUNBOOK's shell step replaced.
8. **Code fraud rules** in `insights` (follow `insights/README.md`: keyed hashes, no account rows): failed redemptions
   per account, address and device per hour with an alert on spikes (check what exists; complete), redemptions from a
   batch not yet dispatched (a leak), one account redeeming many codes (resale), one code tried by many accounts (a
   shared photo); each a `FraudSignal` kind feeding the inbox (exists for signals? verify) and the batch page.
9. **The learner page** `GET course/learners/{user}/` (SUPPORT: `learn.view_entitlement` and `accounts.view_user`):
   entitlements, codes redeemed, devices with `POST …/devices/{id}/sign-out/`, chapter progress, quiz accuracy per
   chapter, card reviews, support tickets (`support.Ticket` by the account, lazily), every view a `sensitive_read`
   with a banner line in the answer (`logged: true`); a minor's page carries a usage summary, not a trail (no
   timestamps per clip: counts and last-active week only). No per-student "needs attention" list anywhere (a test
   that no endpoint of yours orders learners by a score).
10. **Codes report** `GET course/codes/report/`: printed, sold (orders' lines of the product), activated, revoked by
    batch, the activation rate, by district with cells under 10 hidden ("fewer than 10").

Permissions: Django's verbs on `learn` (exist in the roles), `staff.publish_course`, `staff.make_book_codes`,
`staff.void_book_codes` (new), `learn.view_codebatch` by rule; CONTENT_EDITOR edits within its subjects, REVIEWER
approves and publishes, SUPPORT entitlements, codes lookup and the learner page, SALES makes code batches for school
orders (`staff.make_book_codes`), ADMIN and OWNER void.

## Tests the exit criteria need

Every endpoint in the matrix; the subject scope; the move endpoint's four forms keeping a dense order; a scheduled
publish by the task once; the bin's restore and the purge deleting files only after 30 days and not before; deleted
rows hidden from the app's API; the flag creating one open report; the entitlement bulk job's dry run; progress kept
across revoke and regrant; the batch job writing digests only and the plain file readable by the starter alone and
gone after 24 hours; voiding a batch refuses redemption of its codes; the lookup's answer and throttle; each fraud rule
on a fixture; the learner page's `sensitive_read` and the minor's summary without timestamps; the codes report's
small cells hidden; query counts.

## Console

`/course/` (subjects → the outline tree with the actions on each row and "Move to…" as the keyboard path for every
drag), `/course/revisions/[id]/` (submit, approve, publish now or at a date), `/course/clips/[id]/` (the failure
reason in words with Retry beside it), `/course/bin/`, `/course/items/` (the bank with the statistics columns and
"N/A"), `/course/entitlements/` (grant, extend, revoke, bulk with dry run), `/course/codes/` (batches: generate with
the file, dispatched, void with a typed confirmation, the lookup box answering in one line), `/course/learners/[id]/`
(opened from a ticket's sidebar; says at the top that the view is logged). Mock fixtures for every state. Mock
journey: outline → move a clip → a revision scheduled; codes → lookup → void a code with the typed confirmation.
Real journey (`real.spec.ts` + seed): SUPPORT looks up a seeded code and opens the learner page; the audit trail
shows the logged view.

## Boundaries

The triage queue and ErrorReport are Content's (create reports, do not list them); tickets are Support's (read
lazily); the customer record is Customers' (link). Do not edit `staff/api.py`.
