# Package P5: Content (model: Claude Opus 5.5)

Ports: Django 8115, console 3035 (`E2E_API_PORT=8115 E2E_WEB_PORT=3035`), the public site's dev server 3045 if you
run it. Read COMMON.md first.

Plan rows: section 5.10 (every row marked **must**), 5.0, section 7.8's Question and Solution, ReviewTask,
ErrorReport, LegalDeposit rows (QrScanDay, TeacherResource, Redirect, Banner, FaqEntry, MediaAsset and Testimonial are
should or later: not yours). Research: `research-lms-crm-cms.md` sections 2.1 to 2.6, `inventory.md` 3 and 5,
`research-commerce-gst.md` 6 (legal deposit, ISBN).

## What exists (read before building)

`content/models.py` (Board, ClassLevel, Subject, Book, Paper with `is_published`, Question, Solution, all with
simple_history), `content/views.py` (`qr_png`), `content/management/commands/import_papers.py` (from the books
repository; it hard-deletes removed questions), `content/fixtures/papers/` (the test papers), `api/views.py` (the
public papers API and `QrView`), `content/admin.py`, `accounts/roles.py` (CONTENT_EDITOR, REVIEWER and
`staff.publish_paper`), `staff/models.py` `StaffScope` (kind subject: CONTENT_EDITOR is scoped by subject through
`scoped()`), the public site's solution pages (`examleaf-frontend/src/app/(public)/books/[slug]/`, `s/[code]/`, the
KaTeX pipeline in the frontend: find it and reuse its options), Turnstile and the rate limits on the contact form
(`api/views.py` `ContactView`, `accounts/test_turnstile.py`).

## Backend: `content/staff_api.py`, mounted at `/api/v1/staff/content/` (tag "content (staff)")

1. **Books, papers, questions, solutions**: lists and records for the panel (cursor pages, filters by board, class,
   subject, book, paper, state; the subject scope applied), edits with explicit serializers (every field the admin
   edits today), history with a readable diff (`simple_history`'s `diff_against`: a list of field, before, after) and
   restore (`POST …/history/{id}/restore/`, `content.change_*`, audited).
2. **Draft, review and publish**: Question and Solution gain `state` (draft, in_review, published) and a `draft_text`
   kept apart from the live text until approved: an edit of a published solution writes the draft and marks "changed
   since publish"; `content.ReviewTask` (target, stage, assignee, state in_progress | approved | needs_changes |
   cancelled, comments as a list of {author, text, at, field}) with the workflow author → checker → publish: `POST
   …/submit/` (the editor), `POST …/approve/` and `needs-changes/` (REVIEWER, `staff.publish_paper`; the reviewer
   who publishes is never its last editor: refused with a code), `POST …/publish/` applies the draft to the live text
   (an undoable publish: the previous text kept in history; `POST …/rollback/`). Papers keep `is_published` with
   `staff.publish_paper`. A review waiting opens an inbox item for REVIEWER (`InboxItem.Kind.REVIEW`, new) scoped by
   subject; "waiting for me" is the reviewer's queue `GET content/reviews/?mine=1`.
3. **The editor's preview and validation**: the panel renders Markdown and LaTeX client-side through KaTeX with the
   public site's options (`throwOnError: false` in the preview, errors shown in red; `trust: false`; error text
   escaped); on save the backend refuses bad LaTeX: implement `content/latex.py` with a structural check (balanced `$`
   and `$$`, `\(`/`\)` and `\[`/`\]`, braces, environments begin/end matched, no `\href`/`\url`/`\includegraphics`
   and no raw HTML) with its tests, and the console validates with KaTeX `throwOnError: true` before sending (the
   console may add the `katex` npm package, pinned, since the public site uses it: check the frontend's
   package.json and use the same version). Diagrams: an image reference needs alt text or a "decorative" mark (the
   Markdown image syntax checked in `latex.py`'s same pass).
4. **Error reports**: `content.ErrorReport` (section 7.8's fields: target solution | question | quiz item | clip by
   content type and id, paper, question, step, printing as the batch label, category from a fixed list, note, optional
   email, reporter account or none, `teacher_verified`, state reported | confirmed | rejected | fixed_online |
   fixed_in_printing with `fixed_in`, staff note, `reporter_told_at`, `public` for the errata page). The public
   endpoint `POST /api/v1/reports/` (in `api/views.py` or a new `api/reports.py`): one tap from the page or the QR
   route with the paper, question, step and printing prefilled by the page, Turnstile checked the way the contact
   form checks it, rate limits (5 an hour per address, 20 a day), a honeypot, spam quarantine (a `spam` flag set by
   the rules: kept out of the queue and purged after 30 days by a nightly task). The public site gains the "Report a
   mistake" control on every solution page and clip page (one tap, a category, an optional note and email; the
   Answer Script design; its Vitest test; no modal that opens by itself). The triage queue `GET content/reports/`
   (sorted oldest open first; filters state, category, subject, printing, `teacher`), `POST
   content/reports/{id}/<transition>/` (`staff.triage_report`, new, medium: CONTENT_EDITOR, REVIEWER; SUPPORT reads),
   `POST content/reports/{id}/tell/` (email the reporter that the fix is published, if an email was left), the errata
   list per book and printing `GET content/errata/` (public endpoint `GET /api/v1/errata/?book=` too for a later
   public page: the API only). An open report opens an inbox item for CONTENT_EDITOR scoped by subject; an item
   analysis flag from `insights.ItemStat` (`flags` non-empty) joins the same queue as a report with category
   `item_analysis` made by a nightly task that creates one report per flagged item not yet open (idempotent).
5. **Import from the books repository as a job**: `Job.Kind.CONTENT_IMPORT` (`staff.import_content`, new, high):
   parameters subject and commit (or the fixtures' folder for tests), a dry run first that answers created, updated,
   unchanged, unmatched and "would delete" counts and per-row labels (the result), then Apply with the same
   parameters; removed questions are no longer hard-deleted: they are unpublished and kept with history; only what
   changed is written (history stays readable). Refactor `import_papers` into a service both the command and the job
   call. `GET content/imports/` lists the jobs.
6. **QR codes**: `export_qr` stays; `GET content/papers/{id}/qr/` answers the PNG and the address
   (`SITE_URL/s/<CODE>/`), refusing plain http and localhost as today.
7. **Legal deposit**: `content.LegalDeposit` (book, edition, library from the four the Delivery of Books Act names,
   sent on, the proof of dispatch as text and an optional file in the private storage, `erp_delivery_note` as text
   for now) with `GET/POST content/legal-deposits/` (`content.add_legaldeposit`: ADMIN, CONTENT_EDITOR) and a card on
   the module's home listing books with any of the four libraries missing; the 30-day deadline from publication is a
   setting `CONTENT_LEGAL_DEPOSIT_DAYS` (30, "to be verified" in the docs) that opens an inbox item when a published
   book has no deposit within it (nightly task, idempotent).
8. **ISBN**: when a Book is created or its ISBN changed, ISBN-13 with a checksum, unique per format (a new ISBN for a
   substantial change, not for an unchanged reprint: a note in the docs), validated on the product too
   (`shop.Product.isbn` shares the validator: put it in `content/isbn.py` and import it from the shop's `clean`).
9. **Module home** `GET content/summary/`: reports open by category, reviews waiting, drafts changed since publish,
   legal deposits missing, the last import.

Permissions: Django's verbs on content models (exist), `staff.publish_paper` (exists), `staff.triage_report`,
`staff.import_content` (new), `content.view_errorreport`, `content.view_reviewtask`, `content.add_legaldeposit`,
`content.view_legaldeposit`. REVIEWER gets review and publish and the triage; CONTENT_EDITOR edits, submits and
triages within its subjects; SUPPORT reads reports; MARKETING nothing here.

## Tests the exit criteria need

Every endpoint in the matrix; the subject scope narrowing CONTENT_EDITOR's lists and refusing another subject's
record (404); the reviewer who last edited cannot publish; a publish applies the draft and a rollback restores; the
LaTeX check refuses unbalanced and dangerous input and accepts the fixtures' solutions; the public report endpoint
rate-limited and Turnstile-checked, spam quarantined and purged; the triage transitions; the import dry run counts
on the fixtures and the apply writing only changes, a removed question unpublished not deleted; the ISBN checksum;
the legal deposit inbox item once; the item-analysis bridge idempotent; query counts on the lists.

## Console

`/content/` (home: the cards), `/content/books/`, `/content/papers/`, `/content/papers/[id]/` (questions and
solutions as a tree; each solution's editor: source on the left, the rendered solution on the right refreshed as the
editor types, the save bar, submit for review), `/content/reviews/` ("waiting for me", the diff open beside the
preview, approve / needs changes / publish with undo), `/content/reports/` and `/content/reports/[id]/` (triage with
the linked question, step and printing; the transitions; tell the reporter), `/content/errata/`,
`/content/imports/` (pick the subject and commit, the dry run's counts and labels, Apply), `/content/legal-deposits/`,
the paper's QR. Typed confirmation guards nothing here but a paper's unpublish of many; undo guards a publish. Mock
fixtures for every state; mock journey: a report triaged → the solution's editor with a LaTeX error shown → submit →
the review queue → publish. Real journey (`real.spec.ts` + seed): a CONTENT_EDITOR submits a solution's draft, a
REVIEWER publishes it, the audit trail shows both.

## Boundaries

The course's chapters, clips, cards, quiz bank, item statistics and book codes are Course's (P6; it reads your
ErrorReport model for "needs checking" later: keep `ErrorReport.target` generic). Banners, redirects, media and SEO are
should items: not yours. Teacher resources are Phase C. Do not edit `staff/api.py`.
