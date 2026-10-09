# ExamLeaf admin panel: research for learning, content, CRM, support, analytics and admin UX

Research of 2026-10-09 for the plan of ExamLeaf's staff Admin Control Panel. It covers six areas: learning management
(admin side), content management, CRM and marketing, customer support, analytics, and the admin UX patterns that make
a panel easy and smooth. Every line is a feature or rule the panel could implement. Citations [n] point to
`sources-lms-crm-cms.md` (URL, date fetched, quality note). Vendor docs and regulators' gazettes were read first. Where
only a search-result snippet was available, the sources file says so.

**How to read the checklists**

- Each item reads: `- [ ] **Feature** · M/S/L · what it does`, then which products have it, with [n], then
  "ExamLeaf:" with its status and a note.
- **M** must: in the first release of the panel, or a legal duty. **S** should: the release after. **L** later: when
  volume or a founder decision justifies it. The priorities are for a small Indian publisher: a few staff, one board,
  four subjects, students aged 16 to 18.
- **Have**: built today (examleaf-web README, 2026-10-09). **Part**: partly built, often only as a stock Django admin
  page or a management command. **New**: not built.
- "Competitors" means the products studied: Moodle, Canvas, LearnDash, Teachable, Thinkific, Google Classroom, Graphy,
  Classplus, Teachmint, Physics Wallah, HubSpot, Zoho, Freshsales, Odoo, LeadSquared, Freshdesk, Zendesk, Help Scout,
  Zoho Desk, Gorgias, Shopify, GA4, Metabase, PostHog, Linear, Stripe, Vercel, Notion, GitHub, React-Admin, Refine,
  Payload, Wagtail and Strapi.

## 0. Indian rules that decide what the panel must do

These rules come before any feature list. They turn several "nice to have" items into duties, with dates.

**Children's data: the DPDP Act 2023 and the DPDP Rules 2025.**

- A "child" is anyone under 18 [1]. Most of ExamLeaf's Class 12 students are children in law.
- A Data Fiduciary must not track, behaviourally monitor or target advertising at children (s. 9(3)) [1]. The
  Fourth Schedule lifts this duty, and the parental-consent duty, only in listed cases [2]:
  - an "educational institution", for tracking and behavioural monitoring for its educational activities or for the
    children's safety;
  - a user account whose use is limited to communication by email;
  - checking that a user is not a child.

  Whether a publisher with a revision course counts as "an institution of learning that imparts education" is a
  question for a lawyer. Until then, the panel's marketing tools must not segment or target students by behaviour,
  and its analytics should be aggregate.
- Parents give verifiable consent before a child's data is processed (Rule 10). This means checking that the parent is
  an identifiable adult, from details already held or from DigiLocker-style tokens [2]. ExamLeaf: Part. The
  emailed or texted parent link exists (`PARENTAL_CONSENT_MODE=verified`), but there is no age or identity check of
  the parent.
- Rules 3, 5 to 16, 22 and 23 apply 18 months after 13 November 2025, so from 13 May 2027 [2, 3].
- **Notices** must itemise the data and the purposes, and give a link to withdraw consent as easily as it was given
  (Rule 3; s. 6(4)) [1, 2].
- **Access logs:** the panel must give visibility of who accessed personal data, "through appropriate logs, monitoring
  and review". It must keep those logs and the personal data for one year (Rule 6(1)(c), (e)). It must keep personal
  data, traffic data and processing logs for at least one year from processing (Rule 8(3)) [2]. So a "who
  viewed this student" log is a duty, beyond an edit history.
- **Breaches:** tell each affected person without delay, and give the Data Protection Board a detailed report within
  72 hours (Rule 7) [2]. The panel needs a breach register with a 72-hour clock and a template message to users.
- **Rights requests and grievances:** answer within a reasonable period not exceeding 90 days (Rule 14(3)) [2, 3].
  Publish the contact of a person who answers questions about processing, and give it in every reply to a rights
  request (Rule 9) [2].

**Selling online: the Consumer Protection (E-Commerce) Rules 2020, amended in 2026.**

- Name a grievance officer on the site, with contact details and designation. They acknowledge every complaint within
  48 hours and redress it within one month (rules 4(4), 4(5)) [4].
- From 1 January 2027 the officer must also give the complainant "a copy of the complaint as recorded" (amended rule
  4(5), G.S.R. 789(E) of 9 September 2026) [5].
- As an inventory e-commerce entity, ExamLeaf must give each complaint a ticket number through which the consumer can
  track its status (rule 7(1)(f)) [4]. A support inbox without customer-visible ticket numbers does not comply.
- Consent to a purchase must come from an explicit action, never a pre-ticked box (rule 4(9)) [4].
- Accepted refunds are paid within a reasonable time, as the RBI prescribes (rule 4(10)) [4].
- The entity must not post reviews posing as a consumer (rule 7(2)) [4]. A BIS standard (voluntary, 23 November
  2022) covers collecting, moderating and publishing online reviews [6].
- From 1 January 2027:
  - A reduced price must show the "prior price", meaning the lowest price in the 30 days before the reduction was
    announced. So the panel must keep a price history per product.
  - The site must comply with the Dark Patterns Guidelines 2023, run a yearly self-audit and display a certificate
    "prominently".
  - Joining the National Consumer Helpline's convergence programme becomes mandatory (it was "best effort") [5].
    NCH forwards complaints in real time and expects a response within 30 days [7].

**Dark patterns.** The CCPA's guidelines of 30 November 2023 list 13 patterns [6, 8]: false urgency, basket
sneaking, confirm shaming, forced action, subscription trap, interface interference, bait and switch, drip pricing,
disguised advertisements, nagging, trick wording, SaaS billing and rogue malwares. A CCPA advisory of 5 June 2025
ordered self-audits within three months [8]. On 3 June 2026 the CCPA fined Physics Wallah ₹5 lakh [9]. The
findings:

- A ₹10 donation was pre-selected at checkout (basket sneaking).
- Emotional messages urged buyers to keep it (confirm shaming).
- Courses advertised as "free" opened only after the user gave a phone number and email (forced action).
- The CCPA noted that many of the platform's users are students, including minors.

ExamLeaf's "free solutions behind the QR code" have the same shape when `SOLUTIONS_REQUIRE_LOGIN=1`. Either say "free
with a free account" wherever they are advertised, or keep them open. The panel's discount and banner tools should
make false urgency hard: no countdown timer without a real end date, no "only N left" without real stock.

**Advertising an exam-prep course.** The CCPA's Guidelines for Prevention of Misleading Advertisement in Coaching
Sector 2024 [10] set these rules:

- No guaranteed ranks, marks or selection.
- Use a successful student's name, photo or testimonial only with written consent obtained after the result.
- Show the rank and course details next to the photo, and whether the course was paid.
- Print disclaimers in the same font size as the claims.
- No false scarcity.

Whether a publisher's revision course is "coaching" is a legal question. Either way, the panel should store
testimonials as records backed by consent.

**Messages: TRAI, WhatsApp and the big mailbox providers.**

- **SMS.** TRAI's TCCCPR 2018 as amended on 12 February 2025, read in the PDF [11, 12]:
  - **Headers** end in -P, -S, -T or -G (promotional, service, transactional, government).
  - **Transactional** means a reply to a customer's own action within 30 minutes: OTPs, confirmations, refund
    information.
  - **Service** messages to one's own customers need no explicit consent. Service messages that "facilitate or
    complete" a transaction for someone else need explicit consent, valid seven days.
  - **Promotional** messages carry an opt-out in the same message, and mixing promotion into a service message makes
    it promotional.
  - **Consent** may be sought again only 90 days after it was revoked. The 127xxx short code carries the requests.
  - **Links and numbers**: URLs, APKs, OTT links and call-back numbers are checked against data the sender
    whitelisted.
  - **Templates**: unused for 90 days, they are deactivated. More than three variables need justification. At least
    30% of a template is fixed text. One header per template. Headers and templates are self-certified every year.
  - **Complaints** count only within seven days of the message.
- **WhatsApp.** Meta's developer docs [13, 14, 15, 16]:
  - **Pricing** is per message since 1 July 2025. Messages inside the 24-hour customer-service window are free, and
    so are utility templates sent inside it.
  - **India**: INR billing launched on 1 January 2026, and accounts must move to INR by 31 December 2026 (checked
    on the pricing page).
  - **Opt-in** must name the business.
  - **Templates** are marketing, utility or authentication, reviewed within 24 hours, with quality ratings.
  - **Sending limits** per business portfolio climb 250 → 2,000 → 10,000 → 100,000 → unlimited unique users a day.
- **Email.** Senders of more than 5,000 a day to Gmail need SPF, DKIM, DMARC, a spam rate under 0.3%, and one-click
  unsubscribe (RFC 8058) plus a visible link [17]. Yahoo asks that unsubscribes be honoured within 2 days
  [18]. SES subscription management adds the one-click header and a topic-based preference page
  [19].
- **What follows for the panel:**
  - **Students get service messages only.** Marketing goes to adults (parents, teachers, schools) who opted in.
  - **Every SMS template is a registered record**, with its DLT IDs, its category and when it was last used.

## What ExamLeaf already has (the baseline the panel builds on)

From the examleaf-web README, API.md and models, 2026-10-09 [20]:

- **Staff and safety.**
  - Roles as Django groups: CONTENT_EDITOR, SALES, SUPPORT, ADMIN. Every staff member has a second factor.
  - A branded Django admin with a dashboard: registrations, teacher requests, deletions, orders, revenue, stock.
  - django-simple-history on books, papers, questions, solutions, legal pages, orders and reviews.
  - CSV/XLSX exports, ADMIN only and written to the admin log.
  - Celery beat and Celery results in the admin; django-health-check.
- **Learning.**
  - Chapters. Revisions, which are draft or published.
  - Clips of seven kinds, with ffmpeg HLS processing tracked as a state machine and a free-preview flag.
  - Flash cards, and quiz items: MCQ, true/false, fill in the blank.
  - Book codes, stored hashed, with a `batch` field for the print run.
  - Entitlements from a code, a purchase or a staff grant, with `valid_until`.
  - Progress per clip, every quiz answer (`QuizAttempt.correct`) and every card review (`CardReview.known`). Item
    statistics can be computed from these without new tracking.
- **Content.**
  - Papers, questions and solutions imported from the books repository by `import_papers`. It reports
    created/updated/unchanged and unmatched labels.
  - QR images per paper (`/qr/<CODE>.png`, `export_qr`).
  - Legal pages with placeholders.
- **People.**
  - ConsentRecord (purpose, policy version, by a parent or not, how).
  - Deletion requests with a seven-day grace period, Download my data, teacher verification.
  - The contact form only emails the support address. There is no ticket number, which rule 7(1)(f) requires.
- **Shop.**
  - Coupons, automatic offers, reviews, back-in-stock alerts, school quotations, staff orders, refunds, GST
    invoices and credit notes.
  - SMS log (MSG91, DLT) and an email suppression list (SES).
- **Frontend** [21]:
  - Next.js with shadcn/Radix UI components.
  - Maths rendered by KaTeX through remark-math and rehype-katex. The same pipeline can render a live preview in a
    question editor.
  - hls.js, lean-qr, and code-generated `robots.ts` and `sitemap.ts`.
  - No staff pages yet.

## 1. Learning management (admin side)

ExamLeaf's course is small and fixed: about 51 chapters, a revision of about 12 minutes per chapter, plus cards and
one-mark items. It does not need a general LMS. It needs a fast way to build, check and fix that content, and to see
whether it works. Moodle facts below come from its source code; docs.moodle.org shows a bot challenge and was not
fetched.

### 1.1 Course builder and publishing

- [ ] **Outline page per subject: chapter → revision → clips, cards and quiz items** · M · One tree page with
  titles, kinds, durations, status chips (draft or published), free-preview badges and counts, and the actions on
  each row. Who has it:
  - Moodle: sections and subsections, with "Bulk actions" to move, duplicate, delete and set availability (show,
    hide, or "available but not shown") [22].
  - Teachable: lessons start unpublished; whole sections publish or unpublish at once [23].
  - LearnDash: Course Builder [24].

  ExamLeaf: Part. Models and `order` fields exist; editing happens in stock admin forms.
- [ ] **Reorder without dragging** · M · Drag handles plus a "Move to…" menu: pick a target, then first, before X,
  after X, or last.
  - Canvas offers both, and documents "Move to" as the keyboard path [25]. Moodle has a "Move activity"
    dialog [22]. Teachable and LearnDash are drag-only [23, 24].
  - WCAG 2.2 (2.5.7, level AA) requires a single-pointer alternative to every drag [26].
- [ ] **Bulk actions on clips, cards and items** · S · Select rows, then publish or unpublish, set free preview,
  move to another chapter, or delete, with a count in the confirmation. Moodle [22]; Teachable (publish,
  preview, rename, delete) [23].
- [ ] **Soft delete for clips** · M · A deleted clip goes to a bin for 30 days with its HLS files. Teachable warns
  that a deleted video lesson cannot be recovered [23]. ExamLeaf: New. Re-encoding costs worker time, and
  an editor's mistake should not.
- [ ] **Free-preview flag per clip** · M · Teachable "public preview" lessons need no enrolment and are visible to
  search engines [23]; Thinkific has per-lesson free preview [27]. ExamLeaf: Have
  (`Clip.is_free_preview`, plus `LEARN_FREE_PREVIEW`).
- [ ] **Asset library with "used in"** · S · One searchable store for videos, images and PDFs, showing where each is
  used. Moodle content bank: "Places linked", Public or Unlisted [28]. Thinkific Asset Library (2026) [27].
- [ ] **Draft, review, scheduled publish** · M · Statuses, a reviewer, and a go-live date for a revision or a whole
  chapter.
  - Moodle questions are Ready, Draft or Hidden [29].
  - Wagtail has go-live and expiry dates, run by `publish_scheduled` on cron [30].
  - Strapi Releases group entries to publish together on a date and time [31].

  ExamLeaf: Part. `Revision.status` is draft or published, with no review or schedule.
- [ ] **Course copy with locked master** · L · Canvas Blueprint:
  - one master course syncs to copies, and the first sync is automatic;
  - locked objects overwrite the copies; unlocked edits survive;
  - module order resets on sync [32, 33].

  Moodle's "Copy course" runs in the background [34]. ExamLeaf: needed only when Class 10 or a second
  board arrives.

### 1.2 Video

- [ ] **Processing status you can see and retry** · M · Each clip shows a chip: uploaded, processing, ready or
  failed. A failure gives a plain reason, for example "ffprobe: codec not supported", and a Retry button. Ready
  clips show a poster and a duration. ExamLeaf: Part. A state machine (`Clip.processing`) exists in the stock
  admin.
- [ ] **Captions and transcripts per language** · S · Upload WebVTT per language, and show an "Uncaptioned" filter.
  - Machine captions do not cover ExamLeaf's languages:
    - Mux: en, es, it, pt, de, fr, plus beta European languages; about 0.1× the video's length [35].
    - Cloudflare: 12 languages, no Indian ones [36].
    - VdoCipher: English only [37].
  - Assamese and Bengali captions must be written by people. WCAG 1.2.2 requires captions for prerecorded audio
    (level A) [26].
- [ ] **Short-lived signed playback** · M · Cloudflare signed tokens: expiry up to 24 h (default 1 h), up to 5 access
  rules, allowed origins [38]. ExamLeaf: Have. The app gets links signed for 10 minutes.
- [ ] **Device list per learner** · S · Support sees a learner's devices (last seen, platform) and can sign one
  out. The Moodle app caps push devices per plan [39]. ExamLeaf: Part. Five newest devices are kept per
  account, with no staff view.
- [ ] **Account watermark on playback** · S · The player overlays a short, moving account code. Do not use a
  minor's phone number or email.
  - VdoCipher overlays IP, user ID, email or phone [37].
  - Cloudflare only burns in a static PNG, ≤ 2 MiB, at upload; it cannot be changed later [40].

  ExamLeaf: New. An overlay in the app is enough to trace a screen recording to an account.
- [ ] **DRM (Widevine, FairPlay)** · L · Prices:
  - Mux: $100 a month plus $0.003 per licence; FairPlay needs your own Apple certificate [41].
  - Bunny Enterprise: $99 a month plus $0.005 to $0.003 per licence [42].
  - VdoCipher: Widevine and FairPlay [37].

  Mux blocks screen capture on iOS; on Android it does so only sometimes [41]. Not worth it for short
  revision clips until piracy shows up in the data.
- [ ] **Secure offline download** · L · Mux persistent licences with `licenseExpiration` [41]. Moodle app
  "Download course" [39]. Set the expiry to the end of the year's access.
- [ ] **Per-clip engagement (aggregate)** · S · Starts, completions, and completion rate per clip, by chapter.
  - Mux counts a view as any playback attempt, and watch time includes rebuffering [43].
  - Thinkific explains a "video play rate above 100%" [44].
  - Keep starts, seconds watched and completions as separate counts.

  ExamLeaf: the README says "no video analytics". Per-clip totals from `Progress` give the useful part without
  tracking any one student.

### 1.3 Drip, prerequisites and completion rules

- [ ] **What counts as "completed"** · M · A visible rule per clip type, for example "reached the last 5 seconds" or
  "90% watched". LearnDash video progression:
  - the video must be watched to the end before the lesson's steps open;
  - auto-complete after a delay;
  - pauses when the window loses focus [45].

  Moodle completion conditions: view, grade, passing grade [46]. ExamLeaf: Have a per-clip `completed`
  flag. The rule should be written down in the panel.
- [ ] **Unlock rules (prerequisites)** · L ·
  - Canvas: complete all or one requirement (view, mark done, submit, "score at least"), optionally in order
    [47]. Editing met prerequisites asks to "Re-Lock Modules" [48].
  - Moodle: nested restriction sets, "must / must not" match "all / any", and each condition hidden or shown
    greyed [49, 50].
  - LearnDash: prerequisites, "Any Selected" or "All Selected" [51].

  ExamLeaf: a revision course before an exam should not lock chapters. The pass plan already sets the order.
- [ ] **Drip by days after redemption or by date** · L ·
  - LearnDash: immediately, X days after enrolment (1 day = 24 h), or a set date [52].
  - Teachable: per section, the date at least 48 h ahead, releases at 00:00 UTC; "Grant Full Access" and "Restore
    drip schedule" [53].
  - Thinkific: enrolment date, first open, or a set date [54] (snippet).
  - Canvas: "Lock until" [55]. Moodle core has no "days after enrolment" [49].
- [ ] **Changing a completion rule safely** · S · Moodle makes you "Unlock completion settings and delete user
  completion data" once data exists [46]. Version the rule instead, so old completions keep their meaning.

### 1.4 Question bank and quiz settings

- [ ] **One bank for book questions and app items, with fixed metadata** · M · Subject, chapter, topic, marks,
  difficulty, Bloom level, source (book, paper, question number), and tags. All are filters, all bulk-editable.
  - Moodle custom question fields can be locked (only a capability may edit) and shown to Everyone, Teachers or
    Nobody [56].
  - Moodle categories have subcategories and bulk move [57, 58]. Tags drive random selection
    [59].
  - LearnDash question categories give per-category scores [60].

  ExamLeaf: Part. `QuizItem` has a chapter and tags; book questions have chapter and section tags; the README plans
  a bank as a filtered list.
- [ ] **Status, history, usage and reviewer comments per item** · S · Moodle has:
  - statuses Ready, Draft and Hidden [29];
  - "Version x (of y)" history [61];
  - usage per quiz with "Last used" [62];
  - comment threads [63];
  - questions in use cannot be deleted, only hidden [57].

  ExamLeaf: Part. Questions and solutions have django-simple-history; `QuizItem` has no history.
- [ ] **Re-mark past answers after a key change, with a dry run** · S · Moodle regrade: a "Dry run" first, then
  "Commit regrade", limited to chosen attempts or questions; slots are pinned to "Always latest" or a fixed version
  [59, 64]. ExamLeaf: `QuizAttempt.correct` is fixed when the student answers. A corrected answer key
  should offer "re-mark N past answers", or record that it did not.
- [ ] **Item types** · M (the three of today) · Multiple choice, true or false, and fill in the blank. Fill in the
  blank takes a list of accepted answers and one rule for case and spaces. Later types:
  - numerical with a tolerance;
  - matching (Moodle matching; LearnDash "Matrix sorting");
  - ordering (Moodle ordering; LearnDash sorting).

  Moodle 4.5 ships 17 question-type plugins, counting the unscored "description" [65]. LearnDash has 8
  [60]. ExamLeaf: Have the three, with `is_right()` on the server.
- [ ] **Import and export of items** · S · A spreadsheet with the metadata columns, imported with a preview and
  confirm step (django-import-export) [66, 67]. Interchange formats: GIFT, Aiken and Moodle XML in
  Moodle core, no QTI or CSV [68, 69, 70, 71]; LearnDash XML [72]. ExamLeaf: Part.
  `build_quiz_items` makes items from imported one-mark questions.
- [ ] **Practice-quiz settings** · S · Options seen in the competitors:
  - Shuffle options, if the item allows it [59]; LearnDash "Randomize Answers" [73].
  - Random N items from a pool by tags [59].
  - Feedback at once or at the end [57, 73].
  - A per-quiz wrong-answer penalty, off by default; LearnDash allows negative points [60].
- [ ] **Timed chapter tests** · L · Settings for when real tests arrive:
  - attempts, and a forced delay between them [59, 74];
  - grading by highest, average, first or last [59];
  - a time limit with "submit automatically", "grace period" or "not counted" [59];
  - review options by moment: during, right after, later while open, after close [59];
  - per-student or per-group overrides of dates, time limit and attempts [59].

  Indian test-series tools (sectional timing, ranks, percentiles) were not reachable; see Gaps.

### 1.5 Item analysis (is a question any good?)

- [ ] **Per-item statistics** · M · Computed nightly from answers:
  - **p, or facility**: the share of answers that were right.
  - **Corrected item-total correlation**: the item against the rest of the student's answers. Moodle's
    discrimination index is 100·cov(item, rest of test)/√(var(item)·var(rest)) [75].
  - **Canvas guidance**: p below 0.30 is too hard and above 0.85 too easy; corrected item-total correlation should
    be 0.20 or more [76].
  - **Canvas discrimination bands**: 0.40 or more very good, 0.30–0.39 good, 0.20–0.29 fair, 0.10–0.19 not
    discriminating, below 0.10 poor [76].
  - **Canvas Classic**: top 27%, middle 46%, bottom 27% groups, with +0.25 or more good, plus a point-biserial for
    every distractor [77].

  ExamLeaf: New, and computable. `QuizAttempt` stores `correct` per item and student.
- [ ] **"Needs checking" flag** · M · Moodle's question bank marks discrimination below 30 "Very likely" to need
  checking, 30–49 "Likely", and 50 or more "Unlikely". This was read in `qbank_statistics` source
  [78, 79]. Show the flag in the bank list and send flagged items to the content queue (section 2.4).
- [ ] **Store the answer given, not only right or wrong** · S · Distractor analysis needs the option chosen. Canvas
  exports "AnswerFrequencies" [76]; Moodle has "Analysis of responses" [80]. For fill in the blank,
  the wrong answers show which right variants are missing from the accepted list. ExamLeaf: New. Add `given` to
  `QuizAttempt` and keep it a short time.
- [ ] **Minimum sample and freshness** · M · Show "N/A" under a minimum count. Canvas shows N/A when a value cannot be
  computed and skips items graded for fewer than half the submissions [76]. Moodle stores results with "Last
  calculated … N attempts since" and "Recalculate now" [80, 81].
- [ ] **Quiz reliability** · L · Cronbach's alpha of 0.70 or more is acceptable [76]. Moodle also gives an
  internal-consistency coefficient, error ratio and standard error [81]. Practice sets drawn at random make
  this weak until fixed tests exist.

### 1.6 Flash cards and spaced repetition

- [ ] **One scheduler, set by staff, explained to students** · S · Options in Anki:
  - New cards a day and maximum reviews a day; about 20 new a day leads to about 200 reviews a day.
  - Learning steps "1m 10m" and a maximum interval.
  - FSRS desired retention, 90% by default; above 97% "can be overwhelming".
  - "Optimize" fits the parameters to the review history [82].
  - SM-2 for comparison: intervals 1, 6, then ×EF, with EF never below 1.3 [83].

  ExamLeaf: Part. Cards record "I knew it" or not; wrong quiz answers come back after 1, 3 and 7 days. Cap every
  interval at the days left to the exam.
- [ ] **Card health** · S · Per chapter: cards most often "not known", lapses, and the cards due in the coming week.
  Anki statistics show "Again" counts, a forecast of due cards, and history per card [84]. ExamLeaf: from
  `CardReview`, as aggregates only.

### 1.7 Enrolment, book codes and entitlements

- [ ] **Entitlements: grant, extend, revoke, with reason and bulk** · M · Who has it:
  - Moodle: edit selected enrolments (status, start, end); statuses Active, Suspended, Not current [85, 86].
  - Moodle: "Enrolment expiry action" and "Notify before enrolment expires" with a threshold [85, 87].
  - LearnDash: "Course Access Expiration" in days [51].

  ExamLeaf: Part. `Entitlement` has source, reference, `valid_until` and a note; SUPPORT may add and change.
- [ ] **Keep progress when access ends** · M · LearnDash can delete progress at expiry ("Deleted data cannot be
  recovered") [51]. Do not do this. Progress should go only with the account (DPDP erasure), so a renewed
  pass picks up where it left off.
- [ ] **Book-code batches per print run** · M · On one page:
  - Generate a batch for a print run and export it for the printer.
  - Count redeemed against printed, by week.
  - Void a leaked code or batch.
  - Look up a code a student types (hash lookup) and see its status: unused, redeemed (when, by an account
    shown as a link), or void.

  Moodle's enrolment key is shared per course or group, not one per copy [87]. None of the LMSs read has
  single-use codes per printed book. ExamLeaf: Part. `make_book_codes` and `BookCode.batch` exist; there is no
  panel page.
- [ ] **Bulk enrolment by CSV for schools** · S ·
  - Moodle "Upload users": course1, role1, group1, enrolperiod1 and enrolstatus1 columns [88, 89].
  - Canvas enrollments.csv:
    - status, start and end dates, and `associated_user_id` linking an observer to a student;
    - a "diffing" mode that marks missing rows inactive instead of deleting them [90].

  ExamLeaf: New.
- [ ] **Expiry reminders** · S · Moodle notifies the enroller, or the enroller and the student, a set number of days
  before expiry [85, 87]. This is a service message about a product the student bought, not marketing.

### 1.8 Teachers, parents and schools

- [ ] **Teacher sees only their own students** · L ·
  - LearnDash Group Leaders see only their groups' progress [91, 92]. Canvas
    `limit_section_privileges` [90].
  - ExamLeaf: New. `TeacherProfile` links no students. Needs a founder decision, and a consent path from the
    student or parent.
- [ ] **Parent digest** · L · A weekly email, which the parent opts into.
  - Google Classroom guardian summaries: missing work, upcoming work, announcements; daily or weekly; no grades
    [93].
  - Canvas observers pair with a 6-character code valid 7 days [94], with alert thresholds on grades
    [95].

  ExamLeaf already confirms parents for consent; the digest reuses that link.

### 1.9 Progress, engagement and at-risk learners

- [ ] **Learner page for support** · M · On one page: entitlements, codes redeemed, devices, chapter progress, quiz
  accuracy per chapter, card reviews, and the support tickets.
  - LearnDash ProPanel shows time spent, progress and quiz results with CSV and XLS per attempt [96].
  - LearnDash reporting has filters and CSV export [97].

  ExamLeaf: Part. All the data exists; Download my data assembles it for the student. Every staff view of the
  page goes into the access log (DPDP Rule 6) [2].
- [ ] **Course dashboard, aggregate** · M · Active learners per day and week, clips completed, quiz accuracy by
  chapter, codes redeemed by week, card reviews.
  - LearnDash charts not started / in progress (20/40/60/80/100%) / completed [97].
  - PostHog daily active users and stickiness ("3 of the last 7 days") [98, 99].
- [ ] **"Needs attention" flags per student** · L ·
  - Canvas "Students in Need of Attention" has saved criteria: last page view, last participation, missing
    submissions, score [100, 101].
  - Moodle analytics predicts "Students at risk of dropping out" [102].
  - For minors this is behavioural monitoring. It is allowed only if the educational-institution exemption covers
    ExamLeaf [1, 2]. The student's own pass plan already gives the student this nudge.

### 1.10 Certificates, points, leaderboards (later)

- [ ] **Certificates** · L · LearnDash certificate builder, with course, quiz and group triggers and shortcodes
  [103]. Moodle badges with criteria and expiry [104]. Little value for a revision pass.
- [ ] **Leaderboard** · L · LearnDash: per quiz, with a wait between submissions and a set number of entries
  [105]. If ever built, make it opt-in and show nicknames only.

### 1.11 Communication with learners

- [ ] **Announcements with a display window** · S · Start and end dates, a target (subject or all learners), and a
  preview. Moodle "Display period" [106]; Canvas "Available from / until" [107] (snippet).
- [ ] **One-off push to learners** · S · A service push, for example "Chemistry chapter 5 clips are fixed", to the
  entitled learners of a subject, scheduled, with a count before sending. Moodle caps app devices per plan
  [39]. ExamLeaf: Part. The daily FCM reminder exists. Keep marketing out of push, because the audience is
  minors.
- [ ] **Doubt queue** · L · Not verified in Indian apps (Gaps). Moodle forums offer private replies, post limits
  and "Lock discussions after period of inactivity" [106].
- [ ] **Live classes** · L · BigBlueButton in Moodle: recordings, "Require attendance (minutes)", and engagement
  counts [108].

### 1.12 Languages

- [ ] **Staff and student interface in Assamese, Bengali and English** · S ·
  - Moodle 5.3 language packs: Hindi 91%, Bengali 43%, no Assamese [109].
  - Django's admin is 78% translated to Bengali, with no Assamese [110].

  Plan to write and own an `as` catalogue; section 6 has the technique.

## 2. Content management: solutions, books and the site

ExamLeaf's content is about 5,900 questions with marking-scheme solutions in Markdown and LaTeX, imported from the
books repository, plus legal pages, product pages and the course [20]. In this content, one wrong sign in a
printed solution is the costliest error, so this area weighs heaviest.

### 2.1 Question and solution editor

- [ ] **Markdown and LaTeX editor with live preview** · M · Source on the left. On the right, the solution rendered
  by the site's own pipeline: KaTeX through remark-math and rehype-katex, already in the frontend [21].
  - **Validation**: preview with `throwOnError: false`, so bad LaTeX shows in red, and validate on save with `true`.
    Keep `trust: false`, which blocks `\includegraphics` and `\htmlClass`. Escape error text, because KaTeX error
    messages can echo the source [111, 112].
  - **Live preview elsewhere**: Payload posts every change to an iframe of the real page [113]. Wagtail
    refreshes its preview every 500 ms [114, 115].

  ExamLeaf: Part. Fields are Markdown in stock admin textareas; a staff preview exists only for clips.
- [ ] **Accessible maths** · S · KaTeX outputs HTML and MathML by default (`htmlAndMathml`) [111]. MathJax 4
  adds speech and braille [116]. MathML Core is "Baseline widely available" [117]. Keep the default
  output; never render maths as images.
- [ ] **Diagrams with alt text required** · M · Upload with a required alt text, or a "decorative" tick.
  - Wagtail ImageBlock: alt text plus a decorative flag [118].
  - WordPress: "Alternate text" on each media item [119].
  - Payload uploads: sizes, crop, focal point [120].
- [ ] **Step-structured solutions** · S · Steps as ordered blocks, each with its marks. Editors can insert, reorder,
  duplicate and remove them, as in Wagtail StreamField [121]. ExamLeaf: Part. Solutions carry the
  marking-scheme steps that the planned AI checker compares against [20].
- [ ] **Visual maths input** · L · MathLive web component with a virtual keyboard [122]; MathType and
  ChemType for CKEditor [123]; Tiptap maths nodes [124]. The source is already LaTeX, so a textarea
  with preview is enough.
- [ ] **Turn scanned papers into LaTeX** · L · Mathpix OCR reads images and PDFs. It outputs Mathpix Markdown,
  LaTeX or DOCX [125, 126]. Use it only for an old back catalogue.

### 2.2 Versions, drafts and concurrent editing

- [ ] **History with a readable diff and restore** · M ·
  - django-simple-history: `diff_against()` returns the changed fields [127]. Its admin History page reverts
    to a version, and revert can be switched off [128].
  - Wagtail: "Compare with previous/current version", then "Replace current version", which is logged as a revert
    [121, 129].
  - WordPress compares any two revisions [130]. Payload keeps 100 versions per document by default
    [131].

  ExamLeaf: Part. History is recorded, but there is no side-by-side diff of the Markdown, so build one on
  `diff_against`.
- [ ] **Imports leave history too** · M · Strapi's Content History records only edits made in its editor. API and
  import changes leave no version, and retention is 14 to 90 days [132]. Sanity keeps 3 to 365 days by plan
  [133]. ExamLeaf: Have. `import_papers` changes only what changed, so the history stays meaningful
  [20].
- [ ] **Draft, published and "changed since publish"** · M · Payload shows Draft, Published or Changed, and drafts
  skip validation [134]. Wagtail tracks `live` and `has_unpublished_changes` [129]. Strapi has Draft,
  Modified and Published [135]. ExamLeaf: Part. `Paper.is_published` and `Revision.status` exist; questions and
  solutions have no draft state, so an edit goes live at once.
- [ ] **Autosave** · S · Wagtail 7.3 autosaves every 500 ms and pauses on conflicts [136]. Payload autosaves a
  draft every 800 ms [137]. WordPress keeps one autosave per user per post [130].
- [ ] **Two editors on one solution** · S · Wagtail shows editing-session avatars and offers refresh or overwrite;
  it pings every 10 s [114]. Payload locks for 300 s, with "View in Read-Only" or "Take Over" [138]. A
  soft lock with take-over is enough here.

### 2.3 Review workflow, assignments and scheduling

- [ ] **Author → checker → publish** · M · Every change to a published solution goes through a second person.
  - Wagtail: group-approval tasks with statuses In progress, Approved, Needs changes and Cancelled.
    `WAGTAIL_WORKFLOW_REQUIRE_REAPPROVAL_ON_EDIT` restarts approval after an edit [114, 139].
  - Strapi Review Workflows: stages with roles allowed in and out, an assignee, and a stage required to publish
    (Enterprise plan) [140].

  ExamLeaf: New.
- [ ] **Assignment queue per author** · S · A list per assignee and stage, as Strapi filters [140]. Moodle
  question comments as review notes [63].
- [ ] **Comments pinned to a field or a phrase** · S · Wagtail comments attach to a field or a text selection, with
  replies, resolve, and email notices [121].
- [ ] **Scheduled release of a batch** · S · Example: "the 2027 solutions go live on launch day".
  - Wagtail: go-live and expiry dates, run by `publish_scheduled` on cron [30].
  - Strapi Releases: publish together at a date, time and timezone, with status Blocked, Ready or Done [31].
  - Sanity Releases: up to 1,000 documents per release [141].
  - Payload needs a job runner for scheduled publish [134].

  ExamLeaf has Celery beat [20].

### 2.4 "Report a mistake" and errata

- [ ] **Report link on every solution, quiz item and clip** · M · One tap, a category, an optional note, an
  optional email.
  - Prefill the paper, question, step and printing from the page or the QR route.
  - Khan Academy puts the link at the lower right of every exercise, and its team sees the item and the learner's
    steps [142]. Its categories include content mistake, typo and broken link [143].

  ExamLeaf: New. Forms already have Turnstile and rate limits [20].
- [ ] **Triage queue with states** · M · States: Reported → Confirmed or Rejected → Fixed online → Fixed in
  printing N.
  - O'Reilly separates unconfirmed and confirmed errata, with columns for version, page, "Date corrected" and a
    note from the author or editor [144, 145].
  - O'Reilly's types: serious technical mistake, minor technical mistake, language or formatting, typo, question,
    note, update [144].
  - Items that item analysis flags (section 1.5) join the same queue.
- [ ] **Tell the reporter** · S · Email the reporter when the fix is published, if they gave an address. No product
  doc covered this (Gaps).
- [ ] **Public errata page per book and printing** · S · O'Reilly lists errata per printing with the date
  corrected [144]. Khan shows a correction box on the video itself [146]. A reader with the 2026
  printing sees which of their pages are wrong.

### 2.5 Bulk import from the books repository

- [ ] **"Import from repository" with dry run and confirm** · M · Pick the subject and the commit, run a dry run,
  read the report, then Apply. The work runs as a Celery task.
  - The report shows created, updated, unchanged and unmatched labels, as `import_papers` prints today [20].
  - django-import-export works the same way: preview, then confirm, with `dry_run`, `collect_failed_rows` and
    `rollback_on_validation_errors` [66, 67].
  - Natural keys through `import_id_fields`, plus `skip_unchanged` and `report_skipped` [67].

  ExamLeaf: Part. Today it is a command-line management command.
- [ ] **Imports arrive as drafts when a page is already published** · S · A changed solution waits for the
  checker (2.3) instead of replacing the live text.

### 2.6 QR codes in print

- [ ] **Print an address you control, never the final URL** · M · A printed code cannot be fixed, so it must point at
  a short route that the site can redirect later. Bitly redirects existing codes on paid plans [147] and
  keeps analytics per code [148]. ExamLeaf: Have. The codes encode `SITE_URL/s/<CODE>/`, and `export_qr` refuses
  `localhost` or plain http [20].
- [ ] **QR registry page** · S · Per paper: the code, the target, the printings it appears in, and scan counts per
  day as aggregates, not per person. Bitly can bulk-create and bulk-redirect codes from a spreadsheet [149].
- [ ] **Error-correction level for print** · S · L about 7%, M about 15%, Q about 25%, H about 30% [150].
  Python `qrcode` defaults to M [151]; Bitly uses H [152]. ExamLeaf: M through django-qr-code's
  default, with segno's boost, which raises the level when the symbol size allows. Consider Q for codes printed
  near the spine.
- [ ] **Printing metadata** · S · Book, edition, printing number, date, quantity, printer, and the code batch
  (`BookCode.batch`, e.g. PHY-2027-1) [20]. ONIX edition types (revised, new, student, teacher's) have no
  printing number [153], so record printings yourself.
- DIKSHA's "Energized Textbooks" (QR codes in Indian textbooks) is the national precedent [154]. Its DIAL-code
  tooling could not be read (Gaps).

### 2.7 SEO, redirects, sitemap

- [ ] **Redirects table with automatic entries on slug change** · S ·
  - Wagtail creates permanent redirects when a page's slug changes or the page moves [155]. Shopify pre-selects
    "Create a URL redirect" when a handle changes [156].
  - Import and export redirects as CSV, with a dry run [155, 157].
  - Next.js `redirects()` is fixed at build time and capped at 1,024 on Vercel. Above 1,000, use Proxy with a map
    [158, 159]. A Django table read by the Next.js proxy avoids a redeploy for each redirect.

  ExamLeaf: Part. The shop has `SlugHistory` [20].
- [ ] **SEO fields with a search-result preview** · S · Title, description and URL handle. Shopify warns past 70
  and 320 characters [160, 161]. Next.js metadata supports `title.template`, Open Graph and canonical
  `alternates` [162]. ExamLeaf: Part. Tags and JSON-LD are written in frontend code [21].
- [ ] **Sitemap and robots control** · S · A per-page "hide from search" switch that feeds both the robots meta tag
  and `sitemap.ts`.
  - Next.js `sitemap.ts` and `robots.ts` [163, 164].
  - Google's sitemap limits are 50 MB or 50,000 URLs. It ignores priority and changefreq, and trusts `lastmod` only
    when it is accurate [165].

  ExamLeaf: Have, in code [21].
- [ ] **No FAQ or practice-problem schema editor** · M (as a decision) · Google stopped showing FAQ rich results on
  7 May 2026. Practice-problem results are no longer shown, since January 2026 [166]. MathSolver markup is still
  documented, but only for solver tools [167].

### 2.8 Legal pages, consent versions, FAQ, banners, settings, media

- [ ] **Legal pages with versions tied to consent** · M · Each publish of the privacy policy or terms creates a
  numbered version with an effective date and a diff. Consent rows point at the version accepted.
  - iubenda's Consent Database stores per subject `legal_notices[{identifier, version}]`, the preferences and a
    proof (form snapshot) [168].
  - DPDP Rule 3 requires an itemised notice [2].

  ExamLeaf: Part. Legal pages have history; `ConsentRecord` stores the policy version [20].
- [ ] **Re-consent when a policy changes materially** · S · Show the new notice at next login and record a new
  consent. Withdrawing must stay as easy as giving consent (s. 6(4)) [1].
- [ ] **FAQ manager** · S · Questions with categories, order, languages and "was this helpful" votes. It doubles as
  the help centre (section 4.8). No dedicated product feature was found; Help Scout's article ratings are the model
  [169].
- [ ] **Banners with start and end dates** · S · Shopify's announcement bar rotates up to 12 blocks but cannot be
  scheduled [170]; Shopify Rollouts schedules theme changes [171]. Wagtail snippets get go-live and
  expiry dates [115]. Make the end date required, so a "sale ends Sunday" banner cannot outlive Sunday (false
  urgency) [8].
- [ ] **Site settings with history: shop open, maintenance, COD on, solutions need login** · M ·
  - Wagtail site settings are editable by anyone with "change" permission [172].
  - Shopify's private mode shows a password page with a message [173].
  - Payload Globals hold site-wide singletons with versions [174].

  ExamLeaf: Part. These are environment variables today (`SHOP_COD_ENABLED`, `SOLUTIONS_REQUIRE_LOGIN`). Moving the
  safe ones into a singleton with history lets staff change them without a deploy.
- [ ] **Media library** · S · Grid or list, tags, a focal point by dragging, replace a file everywhere it is used,
  10 MB and 128-megapixel limits (Wagtail) [175, 176, 177]. WordPress filters by type, date and
  "Unattached" [178]. ExamLeaf: Part. Product pictures (AVIF, WebP) exist [20].
- [ ] **A/B tests of copy** · L ·
  - wagtail-ab-testing: a page revision as the variant, a goal, a chi-squared test [179].
  - GrowthBook: experiments through flags, hashed on a user attribute [180].
  - Shopify Rollouts has an "Experiment" type [171].

  Test only on adult-facing pages, such as the school and teacher pages. Assigning children to experiments is
  behavioural processing (section 0).

## 3. CRM and marketing

Two audiences need two rule sets.

- **Students** are mostly minors. Only service messages go to them: orders, codes, course notices. No behavioural
  targeting (section 0).
- **Parents, teachers, schools, distributors and bookshops** are adults. Ordinary CRM and consented marketing
  apply to them.

The bulk-order pipeline for schools and distributors is where a CRM pays for itself here.

### 3.1 People and organisations

- [ ] **One person page with a merged timeline** · M · Orders, payments, code redemptions, a course-use summary,
  tickets, emails and SMS sent, consent events and staff notes, filterable by type and date.
  - HubSpot: timeline filters, full-text search, "Recent/Upcoming activities" cards [181].
  - Odoo: chatter activities coloured by due state (green future, orange today, red overdue) [182].

  ExamLeaf: Part. The shop has a customer page and order timelines; SMS log and consents are separate pages. For
  a minor, show a usage summary, not a trail of behaviour.
- [ ] **Organisations: school, district, distributor, bookshop** · S · A school belongs to a district, and a teacher
  can work at several schools.
  - HubSpot association labels ("Parent/Child"), up to 50 per pair, with reports by label [183, 184].
  - Zoho's "Parent Account" lists member accounts, but deals do not roll up to the parent [185].

  ExamLeaf: New. A quotation request stores the school as text, with a status, a discount and a quotation PDF.
- [ ] **Duplicates and merge** · S ·
  - HubSpot de-duplicates contacts by email and companies by domain [186].
  - Its duplicate finder scores similarity daily; a rejected pair can be undone for 14 days [187].
  - Merging is irreversible: the primary record wins, and the other email becomes an additional email [188].

  Never merge on phone alone, because siblings share a parent's number.
- [ ] **Tags and custom fields** · S · HubSpot object tags and unique-value properties [186, 189].

### 3.2 Pipelines, quotes, tasks (adults only)

- [ ] **School and teacher bulk-order pipeline** · S · Stages: Enquiry → Sample sent → Visit → Quote → Purchase order
  → Delivered → Won or Lost.
  - HubSpot gives each stage a probability and shows weighted amounts. Every pipeline needs a Won and a Lost
    stage. Fields can be required when a deal enters a stage [189].
  - Freshsales sets a "rotting age" per stage [190].
  - Entering a stage can create a task [191].

  ExamLeaf: Part. School quotation requests exist, but a quotation is not turned into a staff order by itself
  [20].
- [ ] **Tasks, reminders, daily digest** · S ·
  - HubSpot tasks: Call, Email or To-do; priority; due date; reminders; repeat every N days, weeks or months;
    queues; a weekday digest at 8 AM [192, 193, 194].
  - Odoo activity types chain the next activity automatically [182].

  ExamLeaf: New.
- [ ] **Guided stages with gates** · L · Zoho Blueprint: states, transitions, required fields, checklists and
  after-actions. Zoho's example caps quote discounts at 25% [195, 196].
- [ ] **Field visits to schools** · L · LeadSquared check-in and check-out on a lead, with time, duration and an
  optional geofence radius [197, 198]. Field Force Insights shows distance travelled and a route map
  [199]. Record staff location in working hours only.
- [ ] **Lead scores and sequences** · L · HubSpot fit and engagement scores with decay [200]. Odoo naive-Bayes
  win probability [201]. HubSpot sequences stop when the contact replies [202]; Freshsales caps sends per
  user per day [203]. For schools and teachers only, never students.

### 3.3 Segments and suppression

- [ ] **Dynamic and static segments** · S ·
  - HubSpot active vs static lists, with up to 250 filters [204].
  - Shopify segments are always dynamic [205].
  - LeadSquared "Smart Views" are saved, counted tabs that admins push to teams [206].
- [ ] **Minors suppressed by default** · M · A fixed rule ahead of every marketing send: exclude every account under
  18, and any account whose age is unknown, unless the parent's verified consent covers marketing.
  - HubSpot has "Don't send to" lists and skips contacts who did not open the last 11 emails [204, 207].
  - SES refuses to send to unsubscribed contacts [19].
  - The law is DPDP s. 9 [1].

### 3.4 Messages and consent

- [ ] **Consent ledger per channel and purpose** · M · Each row: person, channel (email, SMS, WhatsApp), purpose,
  status, source, time, actor, evidence (form version, DLT consent template, parent link).
  - HubSpot logs immutable subscription and channel-consent events with a source such as PREFERENCE_PAGE,
    ONE_CLICK_UNSUBSCRIBE or FORM_SUBMISSION [208].
  - HubSpot never pre-ticks boxes [209] and offers email double opt-in [210].

  ExamLeaf: Part. `ConsentRecord` covers sign-up consent, not each channel.
- [ ] **SMS template registry under DLT** · M · Per template, with an alert before a template goes stale:
  - PE ID, header with its -P/-S/-T/-G suffix, template ID, category and consent template;
  - variables: at most 3 without justification, and at least 30% fixed text;
  - one header per template;
  - last used, because templates idle 90 days are deactivated;
  - the yearly self-certification date [11].

  ExamLeaf: Part. MSG91 templates live in settings, with an SMS log.
- [ ] **Email campaigns to opted-in adults** · S · A subscription type on every email, a send time, and an
  "Unsubscribe" or "Manage preferences" footer [207]. Gmail and Yahoo bulk-sender rules apply [17, 18]. ExamLeaf: New.
  Today only transactional mail goes out, through SES.
- [ ] **Preference centre** · S · SES contact lists with topics add a one-click List-Unsubscribe header and a
  hosted per-topic opt-out page (`{{amazonSESUnsubscribeUrl}}`) [19]. HubSpot cannot email contacts whose
  status is "Not specified" when privacy settings are on [211]. ExamLeaf: Part. SES and a suppression list
  exist.
- [ ] **Quiet hours and frequency caps** · S · HubSpot holds SMS from 8 PM to 8 AM in the contact's time zone
  [212]. Its frequency safeguard caps marketing emails per rolling period [213]. TRAI's own mechanism is
  the recipient's category and time-band preferences through 1909 [12].
- [ ] **WhatsApp Business** · L · Template categories, opt-in naming the business, per-message pricing and
  messaging tiers are in section 0 [13, 14, 15, 16].
  - HubSpot checks a WhatsApp subscription type before each send [214]. LeadSquared stores a compliance-type
    field [215].

  ExamLeaf: New. Needs a verified Meta business [20].

### 3.5 Growth programmes

- [ ] **Coupons and automatic offers** · M ·
  - Shopify: up to 25 active automatic discounts; up to 5 codes plus 1 shipping code per order; the best
    combination is applied for the customer [216, 217].
  - Odoo: bulk single-use coupons, next-order coupons, buy X get Y [218].
  - Add bulk single-use codes per school, and the 30-day "prior price" shown next to any reduced price from
    1 January 2027 [5].

  ExamLeaf: Have coupons with limits, and automatic offers [20].
- [ ] **Teacher ambassador codes** · S ·
  - Thinkific: a link with a 30-day cookie; commissions start "Pending" and are approved or denied; payouts happen
    outside the platform; refunds are deducted; wait 30 days before paying [219, 220].
  - Odoo commission plans [221].

  Adults only. The tax treatment of commissions was not researched.
- [ ] **Review requests after delivery** · S ·
  - Klaviyo starts the request when the item is delivered. A rating of 3 or less opens a support ticket.
    Reviewers can edit for 30 days [222, 223, 224].
  - No staff-written reviews (rule 7(2)) [4]. A BIS standard covers how to moderate and publish them [6].

  ExamLeaf: Part. Buyer reviews with moderation exist.
- [ ] **Testimonials and toppers with consent records** · M · Store written consent given after the result, with
  rank, course, paid or free, and the disclaimer text. The coaching-advertising guidelines ask for exactly this
  [10].
- [ ] **NPS, CSAT, CES** · S · HubSpot NPS 0–10: detractors 0–6, passives 7–8, promoters 9–10. It goes to customers
  of more than 30 days, and a dismissed survey stays hidden 14 days [225]. CES runs after a ticket closes
  [226]; CSAT [227]. Send to parents and teachers, or after support.
- [ ] **Abandoned-cart reminders** · L ·
  - Shopify: a checkout counts as abandoned 10 minutes after the email is entered. No reminder goes out if the cart
    is free, out of stock or high-risk. Abandoned checkouts are deleted after 3 months. A recovery discount can be
    pre-applied [228, 229].
  - Odoo has the same with a "Send after" delay [230].

  ExamLeaf decided against it because buyers may be minors [20]. It is possible only for adult accounts with
  marketing consent.
- [ ] **Referral programme** · L · Not researched; the vendor pages were unreachable (Gaps).

### 3.6 Measurement

- [ ] **UTM builder and source on the order** · S · HubSpot's tracking-URL builder requires a campaign and offers
  source presets and a short link [231]. Tag book QR codes and WhatsApp links: links opened from WhatsApp
  otherwise arrive as "Direct / None" [232]. Store the last non-direct source on the order [233].
- [ ] **Campaign ROI** · S · Zoho: budget, actual cost, expected revenue, ROI = (revenue − spending) / spending
  [234].
- [ ] **Multi-touch attribution** · L · HubSpot first, last, linear, time decay and "empirical" models [235].
  GA4 removed first-click, linear, time-decay and position-based models in November 2023 [233, 236]. The
  order-level source is enough here.

### 3.7 Distributors and bookshops

- [ ] **Price lists per channel** · S · Odoo price lists give discounts, formulas or fixed prices, with a minimum
  quantity, a validity period and a priority order [237]. Use them for distributor, bookshop and school
  slabs. ExamLeaf: New. Staff orders take a one-off staff discount [20].
- [ ] **Partner records with level and status** · S · Odoo Resellers: Gold, Silver or Bronze levels with weights,
  activation states (First Contact, Ramp-up, Fully Operational), and a partnerships report [238].
- [ ] **Territories by district or PIN code** · S · LeadSquared territories are drawn by PIN code or on a map, with
  round-robin and "Seasonal Allocation" [239]. Zoho territories [240].
- [ ] **Partner portal and lead hand-off** · L · Odoo partners answer "I'm interested" or "I'm not interested" on
  forwarded leads, with feedback forms [238]. LeadSquared's distribution engine: round-robin, weighted or
  load-balanced, with an SLA reassignment [241].

## 4. Customer support

Today the contact form sends an email and nothing more [20]. Rule 7(1)(f) requires a ticket number the customer
can track [4]. The 48-hour and one-month grievance clocks [4, 5], the National Consumer Helpline's 30
days [7] and DPDP's 90 days [2] all need timers. So a small helpdesk inside the panel is a **must**, not
a nice-to-have.

### 4.1 Intake

- [ ] **One inbox for the contact form, email, phone log and NCH complaints** · M ·
  - **Email**: forward the support address in. Freshdesk ignores mail whose From equals To (loop guard) and mail
    with more than 50 recipients [242].
  - **Threading**: replies attach by ticket reference and mail headers [242]. WhatsApp threads for 24 h
    [243].
  - **Phone**: start with a "log a call" form (source, duration, notes). Indian IVR providers integrate later
    [244, 245].
  - **NCH**: a "National Consumer Helpline" source with its docket number [7].

  ExamLeaf: Part. Contact form only.
- [ ] **Acknowledgement with ticket number and a copy of the complaint** · M · Sent automatically. Only a human reply
  counts as the first response; Zendesk does not count an autoreply toward the SLA [246].
  - Zendesk triggers [247]; Help Scout auto-reply with variables [248].
  - Due within 48 hours. From 1 January 2027, include the complaint "as recorded" [4, 5].
- [ ] **Spam quarantine** · M · Freshdesk marks spam and can block the sender; spam and trash are purged after
  30 days and kept out of reports [249, 250]. Zendesk suspends mail with a reason, keeps it 14 days, and
  rejects mail scored 99% spam or more [251]. ExamLeaf: Turnstile, honeypot and rate limits on forms exist
  [20].

### 4.2 Ticket model

- [ ] **Fields, statuses, priorities, categories** · M ·
  - **Statuses**: New, Open, Waiting on customer, Waiting on third party, Resolved, Closed. Freshdesk lets a
    status stop the SLA timer [252].
  - **Priorities**: Low, Medium, High, Urgent [252].
  - **Source**: form, email, phone, WhatsApp, NCH.
  - **Categories**: Order, Payment, Book code, QR solutions, Content error, School order, Privacy request,
    Grievance. Freshdesk has dependent category fields, "dynamic sections" (for example refund reason) and
    "Required when closing" [252].
  - **Closing**: Zendesk closes solved tickets after 4 days by automation, or 28 days at most [247, 253].
- [ ] **Legal clocks on every ticket** · M · Clock and due date per ticket type:

  | Ticket type | Clock | Due |
  |---|---|---|
  | Any consumer complaint | acknowledge | 48 h (calendar time) [4] |
  | Any consumer complaint | redress | one month [4] |
  | NCH complaint | respond | 30 days [7] |
  | DPDP rights request (access, correction, erasure, nomination) | answer | 90 days [2] |

  Show each as a countdown. Calendar time cannot be paused, unlike business-hour SLAs.
- [ ] **Merge, split, link** · S ·
  - Zendesk merges are permanent: the last comment is copied, but fields and tags are not [254].
  - A Freshdesk tracker links up to 300 tickets and broadcasts one update to all of them, for example "QR batch
    PHY-2027-1 misprinted" [255].
  - Freshdesk parent-child tickets take up to 50 children [256, 257].

### 4.3 Agent workflow

- [ ] **Queues sorted by due time** · M · Freshdesk sorts by "due by" [258]. Zendesk shared and personal views,
  up to 15 columns [259]. Help Scout folders: Mine, Assigned, Later, Needs Attention [260, 261].
- [ ] **Collision detection** · S · Help Scout shows yellow while someone views and red while someone replies. It
  holds a reply when a newer customer message arrived meanwhile [260, 262]. Freshdesk shows who is
  viewing [263].
- [ ] **Internal notes and @mentions** · M · Help Scout notes and mentions, with "light users" who can only note
  [262]. Zendesk light agents make private comments only [264]. Content editors need this to answer
  errata tickets.
- [ ] **Saved replies with variables, in three languages** · M ·
  - Freshdesk: canned responses with placeholders and "/" shortcuts [265].
  - Zendesk: macros that set fields and text together [266].
  - Help Scout: variables with fallbacks, e.g. `{%customer.firstName,fallback=there%}` [248, 267].
  - Gorgias: macros with order variables [268, 269].
  - Write each reply in Assamese, Bengali and English.
- [ ] **Assignment** · S · Round-robin among agents marked available, plus "claim". Freshdesk Omniroute
  [270], Zendesk routing by capacity and skills [271], Zoho [272]. Skills-based routing is overkill
  for a few agents.
- [ ] **Snooze and follow-up** · S · Help Scout snoozes "if no reply" or "regardless" [261].
- [ ] **Automations** · S · Freshdesk rules on creation, on update and hourly [273]. Zendesk triggers and
  automations, which are capped at 1,000 tickets an hour [247, 253]. Help Scout workflows [274, 275]. ExamLeaf runs
  Celery beat [20].
- [ ] **Keyboard shortcuts** · S · Freshdesk: "?" lists them, then "g t", "g n", "/" [276].
- [ ] **Side conversations** · L · Zendesk emails a third party (printer, courier, Razorpay) from inside the ticket
  [277].

### 4.4 SLAs and escalation

- [ ] **Targets per priority, with business hours and holidays** · S ·
  - Freshdesk: first response, every response and resolution targets; reminders 5 minutes to 4 hours before a
    breach; escalations to managers [258]. Business-hour calendars import holidays [278].
  - Zendesk: 7 SLA metrics, paused while Pending [246]. Zoho: support plans [279].
  - Keep internal targets in business hours (IST, Assam holidays, exam season) and the legal clocks of 4.2 in
    calendar time.
- [ ] **SLA report** · S · Help Scout shows compliance %, a daily trend, and on-time and missed counts per policy
  [280].

### 4.5 Customer context and actions

- [ ] **Sidebar** · M · Orders with Razorpay payment IDs and status, shipments, invoices, entitlements (source, valid
  until), book codes redeemed, devices, past tickets and consents.
  - Zendesk's Shopify panel shows orders, payment and fulfilment status, tracking, and whether an order can be
    refunded [281].
  - Zendesk customer context [282]; Help Scout properties [283]; Gorgias customer timeline
    [284].
- [ ] **Actions from the ticket, each logged** · M · Refund (full or partial), cancel, resend invoice, resend the
  code email, extend access by N days with a reason, look up a book code.
  - Zendesk refunds and cancels Shopify orders from the ticket [281].
  - Gorgias refund quantities start at 0, so nothing is refunded by accident [285].

### 4.6 Refunds and returns

- [ ] **Refund request flow** · M · States: requested → approved or declined → initiated → processed or failed. A
  second approver signs off above a set amount.
  - Zoho Blueprint's refund example [286].
  - Shopify return rules: window, fees, final-sale items [287, 288]. Partial processing [289].
  - Gorgias return eligibility window [290].
  - No cancellation fee unless the seller bears the same when it cancels (rule 4(8)) [4].

  ExamLeaf: Part. Refund actions, automatic refunds of cancelled paid orders, and refund webhooks exist. Refunds of
  offline payments are done by hand [20].
- [ ] **Razorpay rules shown to the agent** · S ·
  - Refunds can be partial, in paise, and only on captured payments.
  - A normal refund of a payment older than 6 months fails.
  - Speed is normal or optimum. Instant refunds carry a fee [291, 292, 293].
  - Typical times: cards 5–10 days, net banking 2–10, UPI 2–7 [294].
  - Webhooks: `refund.processed`, `refund.failed`, `refund.speed_changed` [295].
  - Show the expected days in the reply macro, and warn before refunding a payment older than 6 months.

### 4.7 Satisfaction

- [ ] **CSAT after resolution, with follow-up on bad scores** · S ·
  - Freshdesk: frequency caps and skip logic [296].
  - Zendesk: sends 1 day after Solved [297].
  - Help Scout: Great, Okay or Not Good, changeable for 10 days [298]. Happiness = % Great − % Not Good
    [299]. Workflows act on "Rating = Not Good" [274, 275].
  - A bad rating reopens the ticket to a lead.

### 4.8 Self-service

- [ ] **"My requests" page** · M · The customer sees each ticket's number and status; required by rule 7(1)(f)
  [4]. Freshdesk portal labels [252].
- [ ] **Help centre in three languages** · S ·
  - Freshdesk: categories, folders, articles, per-language masters and translation lists [300, 301].
  - Zendesk: locale in the URL [302, 303].
  - Zoho: machine translation into 50+ languages [304].
  - Assamese support was not confirmed for any vendor (Gaps).
- [ ] **Suggested articles while typing** · S · Help Scout Beacon: up to 5 suggestions per page across 200 pages
  [305]. Zendesk's form suggestions are legacy and end 10 December 2026 [306]. Postgres full-text search
  is enough for the matching.
- [ ] **Article feedback and failed searches** · S · Help Scout article ratings, and a Docs report of searches with
  no result [169, 307]. Zendesk recipe: a downvote opens a ticket [308].

### 4.9 Reporting

- [ ] **Support numbers** · S · Volume by category, first response, resolution time, backlog, breaches, and CSAT per
  agent. Help Scout's report set [307]. Store `first_response_at`, `resolved_at`, `reopened_count` and breach
  flags on the ticket so reports stay plain SQL.
- [ ] **Grievance register export** · M · A dated CSV of complaints for an audit or an NCH query: received,
  acknowledged, resolved, days taken [4, 7].

## 5. Analytics and reporting

The site runs no third-party trackers, by decision. Most of its users are minors, and DPDP s. 9(3) bars tracking
them [1, 20]. So the analytics here are counts from ExamLeaf's own tables, plus an optional cookieless page
counter. Every number comes from orders, payments, codes, progress, quiz answers or tickets that already exist.

### 5.1 Dashboards

- [ ] **A home page per role with 4 to 8 KPI cards** · M ·
  - **Roles and cards**:
    - Owner: revenue net of refunds, orders, codes redeemed, active learners.
    - Sales: orders to pack, quotes open.
    - Support: tickets due, breaches.
    - Content: reports open, flagged items.
  - **How others do it**:
    - Shopify builds its overview from a metric library, with comparisons, targets and insights [309].
    - Metabase Trend cards hold up to 3 comparisons and can invert colours for "lower is better" [310, 311].

  ExamLeaf: Part. A dashboard already shows registrations, orders, revenue net of refunds, bestsellers and low
  stock [20].
- [ ] **One definition per metric** · M · Net revenue, active learner, completed clip and code redeemed are each
  defined once, used everywhere, and explained on hover.
  - Metabase "official metrics" live in a library; editing a metric updates every question using it [312].
  - Metabase models [313].
  - Shopify shows a dated notice when a definition changes [309].
- [ ] **"Data as of" on every card** · S ·
  - Shopify's key metrics update within about a minute [309].
  - GA4 key events take up to 24 h to reach reports [314].
  - Metabase caching by policy [315].
  - Cards computed by a nightly task must say so.
- [ ] **Comparisons and annotations** · S · Plausible compares with the previous period, the previous year, or the
  same weekday [316]. Its annotations pin notes to dates [317]. Annotate exam dates, result day, print
  runs and price changes. GA4 comparisons [318].

### 5.2 Funnels

- [ ] **Two funnels, counted from ExamLeaf's own tables** · S · A book buyer enters the site at the QR code or the
  code screen, not the home page. So keep two funnels:
  - **Shop funnel**: visit → opens a sample paper → registers → buys.
  - **Book funnel**: QR solution opened → registers → redeems code → first clip completed.

  Steps before sign-in are anonymous totals; steps after it are per account. Label the ratio between the two kinds
  as a ratio of totals.
  - **Funnel types**: GA4 open and closed funnels, up to 10 steps, with elapsed time [319]. Plausible
    sequential, flexible or strict [320]. PostHog sequential, strict or any order, with exclusion steps
    [321].
  - **Shopify's default funnel**: sessions → added to cart → reached checkout → completed [322].
  - **Drawing it**: Metabase builds a funnel chart from a step and value table [323].

### 5.3 Cohorts and retention

- [ ] **Cohorts by the month of first purchase or code redemption** · S · Rows are cohorts and columns are months
  after. The return criterion is any course activity or a repeat order. Cells under a minimum count are hidden.
  - Shopify's customer cohorts start from the first order, with retention, sales and AOV as a heatmap or a curve
    [324].
  - GA4 cohort settings [325]; PostHog retention [326].
  - Lifecycle states: new, returning, resurrecting, dormant [327].
- [ ] **No predictive LTV or RFM on students** · M (as a decision) · GA4 predicts purchase and churn probability
  [328], and Shopify sorts customers into 11 RFM groups [324]. On minors both are profiling.

### 5.4 Products, subjects and content

- [ ] **Sales by book, subject, edition and channel; refunds; stock** · M · ExamLeaf: Part. The dashboard shows the
  books sold most and the books running out, and there is a GSTR-1 export [20]. Shopify's sales reports could
  not be read (Gaps).
- [ ] **Content performance** · S · Solutions opened per paper, quiz items by difficulty (1.5), clip completion
  rates, card lapse rates. Use paths only as aggregates: GA4 path exploration [329]; PostHog paths
  [330].
- [ ] **Search terms and zero-result searches** · L · Shopify reports "Searches with no results" [322]. GA4
  reads the search term from the URL [331]. ExamLeaf has no site search by decision [20]. Help-centre
  searches (4.8) come first.

### 5.5 Geography, devices, sources

- [ ] **State and district from shipping PIN codes** · S · ExamLeaf already loads India Post's PIN directory
  [20]. Shopify reports customers by shipping location [324]. GA4 goes to region and city [332].
  Hide districts with fewer than k orders.
- [ ] **Order source** · S · UTM and referrer stored on the order (3.6). Plausible notes that WhatsApp links arrive as
  "Direct / None" without UTM tags [232]. GA4 attribution models [233].
- [ ] **Device mix** · L · GA4 device category [332]; Plausible browser, OS and screen [232].

### 5.6 Learner engagement

- [ ] **Course health** · M · All aggregate, by subject and chapter:
  - **Active learners**: daily, weekly, monthly. PostHog smooths daily actives over 7 or 28 days [98] and
    measures stickiness [99].
  - **Clip completion**: GA4 sends video progress events at 10, 25, 50 and 75% [331]. Mux counts a view as
    any playback attempt [43].
  - **Quiz accuracy** and **card reviews and lapses**: Anki shows "Again" counts and due forecasts [84].

### 5.7 Delivery

- [ ] **Exports everywhere, logged** · M · CSV/XLSX of any list as filtered, with a row cap.
  - Metabase exports to CSV, XLSX, JSON or PNG, with row caps and per-group download permission [333, 334].
  - Plausible exports a ZIP of CSVs [335].

  ExamLeaf: Have. Exports are ADMIN-only and logged; dates of birth and parents' contacts are left out; formula
  cells are escaped [20].
- [ ] **Weekly owner's email and threshold alerts** · S ·
  - **Subscriptions**: Metabase sends hourly to monthly, with CSV or XLSX attached, and can skip empty results
    [336]. PostHog subscriptions [337]. Plausible sends weekly or monthly emails [338].
  - **Alerts**: Metabase alerts when a goal line is crossed [339]. PostHog alerts on rises, falls and
    anomalies [340]. GA4 custom insights [341]. Plausible alerts on traffic spikes and drops
    [342].
  - **Examples**: no orders in 24 h in season, a refund spike, failed SMS, codes redeemed far above the printed run.

  Celery beat and SES can send all of these [20].
- [ ] **Embedded charts** · L · Metabase "guest" embeds signed by Django with a JWT work on the free edition. They
  are view-only, with filters locked by the server [343, 344]. Point Metabase at a read-only user
  [345] and at roll-up views with no names, phone numbers or emails [334]. Row-level security is a Pro
  feature [346, 347].
- [ ] **Warehouse export** · L · GA4 exports to BigQuery daily or by streaming [348]. PostHog batch exports to
  S3, BigQuery or Postgres [349]. For ExamLeaf, a read replica or a nightly dump is enough.

### 5.8 Counting without tracking

- [ ] **Cookieless page counts** · S · Choose one of three:
  - **Own table**: a server-side table of (day, path, count). The smallest option.
  - **Plausible**: a daily-salted hash of IP and user agent, no cookies, IP not stored [350]. The
    self-hosted edition has no funnels [351].
  - **Umami**: self-hosted, no cookies, runs on Postgres [352, 353].

  Costs and cautions:
  - PostHog's cookieless mode inflates unique counts and merges visitors who share an IP, as schools do
    [354]. Self-hosted PostHog needs 4 vCPU and 16 GB [355].
  - Matomo still advises treating cookieless tracking as needing consent under some laws [356].
- [ ] **Minimum cell size** · M · Hide any cell under k, for example 10, in district, school, cohort and
  search-term tables. GA4 withholds small groups automatically [325, 357].
- [ ] **Short raw retention, long aggregates** · S · GA4 keeps user-level data 2 or 14 months [358]. Keep
  per-person event rows only as long as their purpose needs. DPDP Rule 8(3)'s one-year minimum still applies to
  logs of processing [2]. Keep aggregates indefinitely.

## 6. Admin UX: what makes a panel easy and smooth

### 6.1 The build decision first

- [ ] **Keep record editing in the Django admin; build custom screens for workflows** · M ·
  - Django's own docs limit the admin to "an organization's internal management tool". For a "more
    process-centric interface", they say to write your own views [359].
  - The stock admin has none of these: saved views, command palette, undo, record locking, autosave [359].
  - **Cheap upgrades**:
    - Unfold adds a Cmd/Ctrl+K palette. It searches records through `search_fields` when switched on, which the
      docs warn is database-heavy. It also adds dashboards and better filters [360, 361].
    - Jazzmin adds a model search bar and modals instead of pop-ups [362].
  - **Custom screens** for packing, the ticket inbox, refund approvals, the content review queue, code batches and
    the compliance cockpit. The frontend already has shadcn/Radix components for them [21].
  - **Paid parts**: React-Admin's editable grid, record locks and audit log are in its paid Enterprise Edition
    [363, 364, 365]. Refine's undoable and optimistic modes are open source [366].

  ExamLeaf: the admin is themed with django-admin-interface [20]. Moving to Unfold would replace it.

### 6.2 Finding things

- [ ] **Global search on every page (Cmd/Ctrl+K)** · M · Looks up order numbers, email, the last digits of a phone,
  book codes, ISBNs and paper codes (PHY-E01).
  - Shopify: recent searches, type filters, "smart filters" with counts, 7 results then "Show more" [367].
  - Linear: prefixes narrow the search (`i` issues, `u` users) [368].
  - GitHub: the palette is scoped to the current page [369].

  Every lookup of a person goes to the access log (DPDP Rule 6) [2].
- [ ] **Paste an ID to open it; `field:value` syntax** · S · Stripe: `email:`, `status:`, `created:`, `-` to negate,
  plain dates like "last week"; pasting an object ID opens it [370]. Linear matches exact IDs and quoted
  terms [368].
- [ ] **Searches and filters live in the URL** · M · Staff can bookmark them and send them to each other. Stripe
  [370], Linear [371].
- [ ] **Saved views per role, as tabs** · M · Start with fixed views per role:

  | Role | View |
  |---|---|
  | Packer | Paid, not packed |
  | Support | Due today |
  | Content | Reports to triage |
  | Sales | Quotes awaiting reply |

  Personal views come later.
  - Shopify order tabs (snippet) [372].
  - Linear custom views with favourites and subscriptions [373].
  - Notion: personal filters, or "Save for everyone" [374].
  - React-Admin SavedQueriesList [375].
- [ ] **Filters, column chooser, sort and group** · S ·
  - Linear: `F` opens filters, with AND/OR groups and relative dates [371]. Display options are personal
    until "Set as default" [376].
  - React-Admin remembers chosen columns [377].
  - Django has `list_filter`, `date_hierarchy` and `search_fields` [359]; Unfold adds date, dropdown and
    number filters [360].
- [ ] **Peek without leaving the list** · S · In Linear, Space opens a preview and ↑/↓ moves to the next item
  [378]. Useful when support is on a call.
- [ ] **Recent and pinned pages** · S · Stripe "Shortcuts" [379]; Notion's recent pages [380].

### 6.3 Doing things fast

- [ ] **Index tables done right** · M · Row checkboxes, a whole-row click target, actions on hover, pagination,
  columns that stack on narrow screens, and a toast after each action [381]. Create, Export and Import sit on
  the page, with an empty state when there is nothing [382].
- [ ] **Keyboard selection and a bulk bar** · S · Linear: J/K to move, X to select, Shift+↑/↓ to extend, Cmd+A for
  all, with a bulk bar at the bottom [383]. React-Admin bulk buttons [377].
- [ ] **Undo instead of "are you sure?" for frequent, reversible actions** · M · Mark packed, assign, tag, publish a
  clip.
  - React-Admin "undoable" mode applies the change at once, shows Undo for 5 s, then sends it [384].
  - Refine has the same modes [366].
  - Linear's Cmd+Z undoes even a batch edit [385].
  - Shopify toasts can carry an Undo action [386].
- [ ] **Spreadsheet-style edit for price and stock** · S · Shopify's bulk editor: arrow keys, ranges, a fill handle,
  and invalid values that block saving [387]. Django `list_editable` [359]. About 30 products fit on one
  screen.
- [ ] **Contextual save bar on forms** · M · An "Unsaved changes" bar with Save and Discard, and a warning before
  leaving the page [388]. Shopify calls autosave "incongruous" with this model, so use one or the other per
  form [389]. Its apps must use the save bar [390].
- [ ] **Autosave for long text only** · S · Payload saves a draft every 800 ms and shows "last saved" [137].
  Use it for solutions and descriptions; use the save bar for orders and settings.
- [ ] **Form and message rules** · M ·
  - More than 5 inputs means sections. One page per object, and no big forms in modals [389].
  - Errors appear under the field after it loses focus, in red with an icon [391].
  - Error toasts must not vanish on their own [390].
  - Toasts: three words or fewer, for success only [391].
- [ ] **Shortcuts, with a list on "?"** · S · Shopify [392], Linear [393], Stripe [379] and GitHub
  [394] all show the list on "?". Use two-key "go to" sequences (G then O for orders) [392, 394, 395]. WCAG 2.1.4:
  single-letter shortcuts must be possible to switch off or remap [26].
- [ ] **Import with preview and confirm; long jobs in the background** · M ·
  - django-import-export: upload, preview, confirm, optionally run through Celery [66].
  - Shopify CSV import: 15 MB limit, an explicit "overwrite" checkbox, a review step, an email when done [396].

  ExamLeaf: Have. ADMIN-only import-export [20].
- [ ] **Progress you can trust** · M · Under 0.1 s feels instant, 1 s keeps the train of thought, 10 s holds
  attention. Show a percent-done bar past about 10 s [397].
- [ ] **Export what you see** · M · React-Admin exports the current filter and sort, not just the page, and disables
  the button when the list is empty [398]. Stripe makes export its own permission [399]. Vercel emails a
  CSV link valid 24 h [400].

### 6.4 Staying safe

- [ ] **Pick the guard by the damage done** · M ·

  | Kind of action | Guard |
  |---|---|
  | Frequent and reversible | Undo [384, 385] |
  | Irreversible | Confirm dialog [384] |
  | Wide or destructive | Type the name to confirm. GitHub's Danger Zone makes you type the repository name to delete it [401]. Use it for voiding a code batch, erasing a customer, deleting an edition, or a refund above a set amount. |
- [ ] **Soft delete with a 30-day bin** · M · Notion keeps Trash 30 days [402]. GitHub can restore some deleted
  repositories within 90 days [401].
- [ ] **Who changed what, when, on every record** · M ·
  - Shopify's order timeline mixes system events with staff comments. @mentions send email. Comments can be
    edited for 5 minutes [403].
  - simple-history: a history page per record, with revert [128]. ra-audit-log RecordTimeline [365].
  - Notion page history [402].

  ExamLeaf: Have. Content, orders and reviews have a History button. Payments and order notes keep history in the
  database, but the admin does not show it [20].
- [ ] **One audit log, including who viewed personal data** · M ·
  - GitHub keeps org audit logs 180 days, searchable and exportable [404].
  - Stripe's security history covers 180 days. Viewing a live key is itself an event (`api_key_viewed`) [405, 406].
  - Vercel stores before and after JSON for each change [400]. Refine logs every create, update and delete
    [407].
  - DPDP Rule 6: logs of access to personal data, kept one year [2].
- [ ] **Re-authenticate before sensitive actions** · M · GitHub's sudo mode lasts 2 hours [408]. Require it
  before role changes, exports, refunds and settings. ExamLeaf: Have. allauth re-authentication (used for data
  export) and staff MFA [20].
- [ ] **"Log in as" a user, with a banner and audit** · S · django-hijack is superusers-only by default, works only
  through POST with CSRF, shows a banner, and sends started and ended signals for the audit trail [409, 410, 411]. For
  minors' accounts, a read-only "view as" is safer.
- [ ] **Least privilege, with sensitive permissions marked** · M · Shopify flags sensitive permissions, such as
  exporting customer data [412]. Stripe advises the lowest role; invites expire in 10 days [399, 413]. ExamLeaf: Have.
  Roles live in `accounts/roles.py` [20].
- [ ] **Record locking** · S · Payload: Take Over after 300 s idle [138]. React-Admin `useLockOnMount` is paid
  [364].
- [ ] **Test mode that looks different** · M · Stripe sandboxes are separate, and outsiders can be invited into one
  without seeing live data [414]. ExamLeaf has a test and a live mode for payments [20]. Add a fixed TEST
  banner and a different colour.

### 6.5 Knowing what is going on

- [ ] **Notification inbox** · S ·
  - Linear subscribes you when you create, are assigned or are mentioned. Its inbox opens with G then I and has
    snooze. Email digests go out only for unread items [415, 416].
  - Notion groups updates by page and thread [417].
  - Shopify sends @mentions by email and push [403]. Stripe lets each user choose their email events
    [413].
- [ ] **Activity feed on the home page** · S · ra-audit-log Timeline [365]; Unfold dashboard widgets
  [360].
- [ ] **Jobs page** · S · Each scheduled job with its last run, next run and last error, and a pause switch. Examples:
  the daily purge, reminders, invoice retries.
  - django-celery-beat offers interval, crontab, solar and clocked schedules, with `enabled` and `last_run_at`
    [418].
  - Flower shows workers and tasks live [419].

  ExamLeaf: Part. The beat and results tables are in the admin [20].
- [ ] **Health and a status page** · S · django-health-check: database, cache, storage, Celery [420] (Have
  [20]). Statuspage components have five states [421]. Vercel's page shows 90-day uptime and lets users
  subscribe [422]. Self-hosted Uptime Kuma checks every 20 s [423].
- [ ] **Feature flags** · S · django-waffle:
  - Flags: on for users, groups, a percentage, or staff, with a query-string test mode.
  - Switches, and Samples [424, 425, 426].

  Vercel's toolbar flips a flag for you alone [427, 428].
- [ ] **Settings with history** · M · Vercel's audit log stores before and after values [400]. Put settings
  under simple-history (2.8).
- [ ] **System banners** · S · A yellow warning or a red critical message that says what to do next. Once
  dismissed, a banner stays away for the session [391].

### 6.6 Guidance

- [ ] **Empty states that say what to do** · M · A heading, one line and at most 2 buttons. Separate text for
  "nothing yet", "the filter matched nothing" and "not set up" [382, 429].
- [ ] **Role cards and permissions explained in place** · M · Stripe's role cards: "This role is for people who
  need to…" and "They can't…" [399]. Shopify gives each permission a one-line description [412]. Write them
  in three languages.
- [ ] **Navigation shows only what you can do** · M · Payload hides a collection when access is denied, using the
  same rules for the API and the UI [430]. Refine's `CanAccess` and `useCan` hide or disable buttons
  [431].
- [ ] **First-day checklist per role** · S · Five steps or fewer, ticked automatically, dismissible [432].
  Example for a packer: print a test label, scan a test code.
- [ ] **Help in the same place on every page** · S · WCAG 3.2.6 Consistent Help [26, 433]. Labels carry
  units and context [390].
- [ ] **No distractions** · S · No modals that open by themselves, and red only for errors and destructive actions
  [390].

### 6.7 Phones, accessibility, speed, languages

- [ ] **Packer mode on a phone** · M · One column, large targets, the scanner first, and no page-wide sideways
  scrolling. Shopify's app rules require it [390]; its tables stack on narrow screens [381]. Shopify's
  scanner runs on iOS and Android [434].
- [ ] **WCAG 2.2 AA** · M · The new AA rules are the ones a panel breaks most often [26, 433]:
  - 1.4.3: text contrast 4.5:1.
  - 2.4.11: focus not hidden under the sticky save bar.
  - 2.5.7: a click alternative for every drag.
  - 2.5.8: targets of at least 24×24 px.
  - 3.3.7: don't ask for the same data twice.
  - 3.3.8: no memory or puzzle test at log-in.
- [ ] **Speed budget** · M ·
  - INP of 200 ms or less at the 75th percentile [435].
  - Shopify's app bar: LCP ≤ 2.5 s, CLS ≤ 0.1, INP ≤ 200 ms [390].
  - Django lists show 100 rows by default. `show_full_result_count = False` skips the slow total count
    [359].
  - Use a virtual list only when a list really holds thousands of rows [436].
- [ ] **Dark mode** · S · Django's admin already has a light, dark and auto toggle that follows
  `prefers-color-scheme` [359, 437].
- [ ] **Assamese, Bengali, English for staff** · S ·
  - **Django**: `LocaleMiddleware` picks the language from the URL prefix, then a cookie, then Accept-Language;
    strings are collected with `makemessages` [438]. It ships a Bengali admin about 78% translated and no
    Assamese [110].
  - **Next.js**: an `app/[lang]` folder with one dictionary per language [439].
  - **Fonts**: the site's Hind Siliguri Bengali subsets already contain the Assamese letters ৰ and ৱ [440];
    Noto Bengali is a fallback [441].
  - Save each staff member's language on their account.

### 6.8 Printing and scanning

- [ ] **Print templates** · M · A4 invoice, packing slip, 4×6 inch label, and a pick list grouped by book.
  - Shopify prints labels as 4×6 thermal or A4/Letter, at most 100 per batch [442]. Order Printer templates
    cover invoices, packing slips and pick lists [443].
  - CSS `@page { size: 4in 6in }` sets the label size [444, 445].

  ExamLeaf: Part. GST invoices and credit notes are WeasyPrint PDFs [20].
- [ ] **Scan to pack** · S ·
  - **Flow**: scan the order QR on the slip, then each book's ISBN barcode (EAN-13). A wrong or extra book shows
    an error. Then "Mark packed". Shopify's scanner works the same way: scan, "Review scan", then "Apply changes"
    [434].
  - **Browser support**: `BarcodeDetector` reads ean_13 and qr_code. It works in Chrome on Android 83+, but in
    Safari only behind a setting, and not in Firefox [446, 447].
  - **Fallbacks**: iPhones need a JavaScript decoder, or a USB/Bluetooth scanner that types like a keyboard.
- [ ] **Book-code lookup by scan or typing** · S · See 1.7.

## 7. Where ExamLeaf can offer more than the competitors

None of the products studied joins a printed book, its QR codes, its book codes and a course in one panel. These
features come from that join. Each is buildable on data ExamLeaf already stores [20].

- [ ] **Print-run view per book** · S · One page per print run (`BookCode.batch`, e.g. PHY-2027-1) shows:
  - the codes printed and redeemed, and redemptions by week;
  - QR solution opens per paper, counted as aggregates;
  - the mistakes reported against that printing, and the errata published for it.

  A reprint decision ("fix these 6 errors before the next run") is made on that page.
- [ ] **Question health** · S · For every question or quiz item, one row shows:
  - the share answered right, and the discrimination from `QuizAttempt`;
  - the reader reports of a mistake;
  - the edit history.

  An item with a negative discrimination or an open report goes into the content editor's queue. LMSs show item
  statistics (section 1.5). Helpdesks show complaints. None joins the two.
- [ ] **Compliance cockpit** · M · One page with every clock the Indian rules start:
  - complaints unacknowledged at 48 hours and unresolved at one month [4, 5];
  - NCH complaints at 30 days [7];
  - rights requests at 90 days [2];
  - a breach's 72 hours [2];
  - parent confirmations awaited;
  - the yearly dark-pattern self-audit and its certificate [5];
  - the policy version each consent was given under.

  Indian edtech platforms have been fined for dark patterns on interfaces used by minors [9]. Doing this in the
  open is a selling point to schools and parents.
- [ ] **Teacher view built from book codes** · L · A teacher whose school bought a class set links the set's codes
  to a class. The teacher then sees that class's chapter-level progress, aggregated, with the parent-consent rules
  applied. Competitors sell course seats to schools; here the printed book is the seat.
- [ ] **Assamese, Bengali and English for staff and teachers** · S · Django ships a Bengali admin catalogue, about
  78% translated, and none for Assamese [110]. A panel whose interface is fully translated, with Assamese added,
  is rare among the products studied (sections 1.12 and 6.7).

## 8. Gaps, checks made, and what to verify before building

**Checked by hand against the primary text:**
- DPDP Rules 2025 (rules 1, 3, 6–10 and 14, and the Fourth Schedule), read from the gazette PDF [2].
- DPDP Act 2023, ss. 2(f), 6(4) and 9(3) [1].
- E-Commerce Rules 2020, rules 4 and 7 [4], and the 2026 amendment, in force 1 January 2027. The date was read
  off the rendered page [5].
- TRAI 2025 amendment clauses [11].
- Moodle's "Needs checking?" thresholds, in `qbank_statistics` source [78].
- Canvas New Quizzes thresholds, in the page's embedded text [76].
- WhatsApp's India INR dates. A sub-agent's "1 July 2026" was wrong: the launch was 1 January 2026, with
  migration due by 31 December 2026 [13].
- Google's FAQ rich-result end date [166].
- `BarcodeDetector` support data [447].

**Not verified, or thin:**
- **Indian edtech admin tools** (Graphy, Classplus, Teachmint, Physics Wallah, Unacademy, Testbook): only home pages
  were readable [448, 449]. Not confirmed: their doubt queues, test-series settings (negative marking,
  sectional timing, ranks), parent apps and device limits.
- **Blocked sites**:
  - docs.moodle.org shows a bot challenge, so Moodle facts come from its source code.
  - Thinkific's help centre returns 403.
  - Shopify's help centre blocks scripted fetches, so its facts are WebFetch paraphrases. Its sales and acquisition
    reports were not read.
- **Video**: VdoCipher's docs, Mux Data, and per-provider device or concurrent-stream limits.
- **Marketing tools**: Teachable and Kajabi affiliates, ReferralCandy, Friendbuy and Judge.me were not reached.
  WhatsApp's per-user marketing-message caps and India rates were not reached.
- **TRAI**: the August 2024 direction on whitelisting URLs and call-back numbers was not read; its 2025 clause was
  used instead. A fixed national window for promotional SMS was not found in the text read.
- **DIKSHA's DIAL-code tooling**: generation, linking and scan reports could not be read.
- **Helpdesk vendors**: Zoho Desk and Zoho CRM facts come from marketing pages or summaries. Freshdesk's merge and
  custom-status pages need a login. Assamese was not confirmed in any vendor's language list.
- **UX references**: Polaris React's site did not answer, and Primer's "dangerous actions" guidance did not load.
  GitHub's own docs back the typed-confirmation pattern instead.
- **Legal questions for a lawyer before building marketing or learner analytics**:
  - Is ExamLeaf an "educational institution" under the Fourth Schedule [2]?
  - Is the revision course "coaching" under the 2024 guidelines? These were read from PIB's summary, not the
    gazette [10].
  - Do "free" QR solutions behind a sign-up need a disclosure [9]?
  - How exactly does a company join the National Consumer Helpline programme, now mandatory [5, 7]?
- **Method**: the session's 200 web searches ran out partway through, so some URLs were found from vendors' doc
  patterns and sitemaps. The disk filled once during the work, then freed. About 500 page extracts are kept under
  `admin-plan/raw/` for re-checking.

