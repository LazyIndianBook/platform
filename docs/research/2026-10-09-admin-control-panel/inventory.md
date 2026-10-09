# ExamLeaf staff/admin inventory (examleaf-web)

Surveyed on branch `design/answer-script` at `a9da6c4` (clean tree), 2026-10-09, by a read-only survey agent for the
Admin Control Panel plan (`docs/examleaf-admin-control-panel-plan.md`). Paths are relative to `examleaf-web/` unless
they start with `docs/`.

## 0. Corrections to the brief (what does not exist)

| Assumed | Reality |
|---|---|
| `ops/views.py`, `ops/urls.py`, ops templates | Don't exist. `ops/` holds `models.py`, `admin.py`, `sms.py`, `tasks.py`, `templatetags/dashboard.py`, `management/commands/upload_backup.py` and migrations. The dashboard is the admin index (section 2.2). |
| Launch checks | No page or command. Readiness signals are scattered (section 8.8), plus a manual checklist in `DEPLOYMENT.md:258-282` ("Going live"). |
| `graph_transitions` installed | `django-fsm-2==4.2.4` is in `requirements.txt:117`, but `django_fsm` isn't in INSTALLED_APPS and graphviz isn't installed. `django_fsm.admin.FSMAdminMixin` ships with the package and is unused. |
| viewflow | Absent. |
| TeacherProfile status (requested/checking/verified) | Only a `verified` boolean plus a note and `verified_at`/`verified_by` (`accounts/models.py:149-167`). "We are checking your request" is frontend wording. |
| FAQ model | None. Contact is a Page row plus a contact form that emails and stores nothing (section 5.4). |
| Soft delete | None anywhere (section 3.9). |
| `learn/dashboard.py` is a staff dashboard | It's the student's dashboard (`GET /api/v1/me/learning/`, `api/learn.py:677-688`). |
| Staff API | None (section 9). |

## 1. Roles, permissions and staff hardening

### 1.1 Groups (`accounts/roles.py`, the single source of truth)

- Constants at `roles.py:8-15`. `STAFF_ROLES = {CONTENT_EDITOR, SALES, SUPPORT, ADMIN}` (`:16`).
- `SUPERUSER_ONLY = ["django_celery_beat", "django_celery_results", "auth", "mfa", "socialaccount"]` (`:21`): ADMIN keeps only `view_*` there (`:87-92`).
- Helpers `crud(app, models, actions=("view","add","change"))` (`:24-25`) and `CATALOGUE = category, collection, collectionitem, producttype, attribute, attributevalue, productimage, bundleitem` (`:28-31`).

| Group | Permissions (`roles.py:34-78`) |
|---|---|
| STUDENT | none (added at sign-up: `accounts/signup.py:118`) |
| TEACHER | none (given by `TeacherProfileAdmin.verify`) |
| CONTENT_EDITOR (`:37-47`) | `content.{book,paper,question,solution}` view/add/change; `content.{board,classlevel,subject}` view; `pages.page` view/change; `shop.product` view/add/change; CATALOGUE view/add/change/delete; `shop.view_slughistory`; `learn.{chapter,revision,clip,flashcard,quizitem}` view/add/change/delete |
| SALES (`:48-59`) | `content.view_book`; `shop.{product,coupon,shippingrate,shipment}` v/a/c; `shop.{productimage,bundleitem,offer}` v/a/c/d; `shop.order` v/a/c (add = phone/school orders; change = pack/ship/deliver/payment-link actions); `shop.refund` v/a; `shop.payment` v/a (offline payment); `shop.ordernote` v/a/c; `shop.{orderitem,orderdiscount,invoice,creditnote,stockalert,address}` view; `shop.{review,quoterequest}` view/change; CATALOGUE minus productimage/bundleitem: view |
| SUPPORT (`:60-76`) | `accounts.{user,consentrecord,deletionrequest}` view; `accounts.teacherprofile` view/change; `account.view_emailaddress`; `ops.view_smslog`; `ops.emailsuppression` view/delete; `practice.view_attempt`; `shop.{order,orderitem,payment,shipment,refund,invoice,creditnote,product,address}` view; `shop.{orderdiscount,ordernote,review,quoterequest,stockalert}` view; `learn.entitlement` v/a/c; `learn.view_bookcode` |
| ADMIN (`:77`) | `ALL`, except non-view permissions of SUPERUSER_ONLY apps |

Machinery: `sync_roles(Group, Permission)` (`roles.py:81-102`) sets each group to exactly its list; `bootstrap_roles`
runs in the Makefile, the compose web command and DEPLOYMENT.md (changes made to groups in the admin are undone).
Migrations calling `sync_roles`: `accounts/0004_roles.py`, `shop/0002_roles.py`, `shop/0019_store_roles.py`. User
helpers `role_names`, `has_role`, `is_student/is_teacher/is_editor/is_sales/is_support/is_admin`
(`accounts/models.py:119-132`). Role assignment in the admin: `set_role()` (`accounts/admin.py:46-52`) and 12
generated actions gated by `auth.change_group` (`:94-95`), in practice superusers only.

### 1.2 Custom model permissions (export and import)

`accounts.export_user` (`accounts/models.py:105`), `accounts.export_consentrecord` (`:195`),
`practice.export_attempt` (`practice/models.py:38`), `shop.export_product`/`import_product` (`shop/models.py:163`),
`shop.export_category`/`import_category` (`:294`), `shop.export_order` (`:785`). Settings:
`IMPORT_EXPORT_EXPORT_PERMISSION_CODE="export"`, `IMPORT_EXPORT_ESCAPE_FORMULAE_ON_EXPORT=True`, `EXPORT_FORMATS=[CSV]`,
`IMPORT_EXPORT_IMPORT_PERMISSION_CODE="import"` (`settings.py:535-576`). Only ADMIN and superusers hold these.
Admin-action permission hooks: `assign_roles` (`accounts/admin.py:94`), `refund` = `shop.add_refund`
(`shop/admin.py:511-512`), `record_payment` = `shop.add_payment` (`:514-515`).

### 1.3 `is_staff` and permission checks outside the admin's defaults

| Where | What |
|---|---|
| `examleaf/middleware.py:80-104` | `needs_mfa_setup(user)`; `StaffMFAMiddleware` redirects to `{SITE_URL}/account/2fa/` or answers a JSON 403 `mfa_setup_required` under `/api/`; `STATIC_URL` and `/_allauth/` stay open |
| `accounts/models.py:23-29` | `STAFF_SESSION = 8h`; `shorter_staff_sessions` on allauth's `user_logged_in` |
| `accounts/adapter.py:101-109` | `pre_login`: staff can't log in with a passkey alone |
| `api/auth.py:233-238, 269-286` | no JWT from a password, SMS or email code alone for staff or MFA accounts; `ExchangeView` 403 when MFA is not set up |
| `api/shop.py:66-75` | `ShopOpen`: staff bypass `SHOP_OPEN=0` |
| `learn/services.py:24-36` | `entitled_subjects`: staff see every subject |
| `learn/uploads.py:112-129` | `LargeBodyGuard`: only signed-in staff may POST large bodies to the clip admin |
| `learn/views.py:74-85` | `/learn/preview/<pk>/`: `staff_member_required` plus `learn.view_clip` |
| `accounts/admin.py:97-103` | non-superusers can't edit `is_superuser`, `groups` or `user_permissions` |
| `shop/services.py:616-621` | `staff_emails(role=SALES)` |
| `accounts/models.py:284` | account deletion clears `is_staff` and `is_superuser` |

### 1.4 MFA, axes, sessions

- MFA (`settings.py:220-228`): TOTP, WebAuthn, recovery codes; passkey login; `MFAAdapter` (`accounts/adapter.py:119-123`). The setup UI is the frontend's `/account/2fa/`.
- Axes (`settings.py:248-255`): 10 failures per username+IP, 15-minute cool-off, `axes_username` normalises phones; `reset-failed-logins` at 03:30 wipes attempts daily (`ops/tasks.py:79-82`); ADMIN can delete an attempt row to unlock. allauth's own limits `ACCOUNT_RATE_LIMITS` (`settings.py:197-205`).
- Sessions: database sessions, no `SESSION_COOKIE_AGE` (2-week default), staff sessions absolute 8 hours, no idle timeout; `allauth.usersessions` with `USERSESSIONS_TRACK_ACTIVITY=True`; the admin for sessions is read-only (`accounts/admin.py:173-182`); `clear_sessions` at 03:45; `ACCOUNT_REAUTHENTICATION_REQUIRED=True`; the API's `recently_authenticated` window is 5 minutes (`api/views.py:318-326`). "Log everyone out" is a shell recipe (`RUNBOOK.md:111`).
- Admin URL hardening: `path("admin/", admin.site.urls)` (`examleaf/urls.py:80`); `secure_admin_login` (`:50`); no IP allowlist (`SECURITY_REVIEW.md:114`); CSP on Django pages (`settings.py:281-311`); Caddy body limit 10 MB (500 MB for clip uploads).

## 2. The Django admin

### 2.1 Site-level configuration

`ops/admin.py:9-10` sets the index template and the header; `shop/admin.py:64` overrides the index template with
`shop/admin/index.html`, which extends the ops dashboard. The theme is django-admin-interface: `ops/migrations/0001`
(navy header, leaf buttons, no related modals because of the CSP) and `0004` (the design tokens).

### 2.2 The dashboard (admin index)

| Block | Source | Shows | Gating |
|---|---|---|---|
| "ExamLeaf at a glance" | `ops/templatetags/dashboard.py:16-39` | today and last-30-day registrations, confirmed emails, attempts | none |
| "Waiting:" | same | teachers waiting, deletions waiting, pages with placeholders, failed clips | failed clips only with `learn.view_clip`; the rest unconditionally (SALES gets a 403 when following) |
| Shop table | `shop/templatetags/shop.py:21-55` | orders and revenue net of refunds, today and 30 days | `shop.view_order` |
| Shop "Waiting:" | same | to pack, to deliver, reviews waiting, quotes waiting | same |
| Sales by day, most sold, running out | `store_stats()` (`:58-82`) | 14 days, top 5 titles, products below `SHOP_LOW_STOCK` | same |

No chart, no loading state, no date picker; test-mode orders count in the numbers.

### 2.3 Custom admin views, URLs and templates

| URL | View | Permission |
|---|---|---|
| `/admin/shop/order/add/` | `OrderAdmin.add_view` (`shop/admin.py:647-691`) → `staff_order.html` | `shop.add_order` |
| `/admin/shop/order/customer/<user_id>/` | `OrderAdmin.customer_view` (`:517-519, 727-749`) → `customer.html` | `shop.view_order` + per-section perms |
| `/admin/shop/invoice/<pk>/pdf/`, `/admin/shop/creditnote/<pk>/pdf/` | `DocumentAdmin.pdf_view` (`:792-813`) | view |
| `/admin/shop/quoterequest/<pk>/quotation/` | `QuoteRequestAdmin.download_quotation` (`:901-909`) | view |
| `/admin/learn/clip/upload-url/` (POST) | `ClipAdmin.upload_url` (`learn/admin.py:134-144`) | add or change clip |
| action pages | `OrderAdmin._form_page` (`shop/admin.py:751-761`) → `action_form.html` | per action |
| `/learn/preview/<pk>/` | `learn/views.py:74-85` | staff + `learn.view_clip` |

### 2.4 ModelAdmins, our apps (39 models)

- accounts: `UserAdmin` (export resource without password/DOB/parent contact; list email, name, class, board, district, under_18, created; filters groups, class, board, is_staff, is_active; 12 role actions; no inlines), `TeacherProfileAdmin` (verify/revoke actions), `ConsentRecordAdmin` (read-only, export), `DeletionRequestAdmin` (read-only), `UserSessionAdmin` (read-only).
- ops: `EmailSuppressionAdmin` (delete = email again), `SmsLogAdmin` (search by whole number through the hash), `LoggedExportMixin` (writes a LogEntry per export).
- content: Board, ClassLevel, Subject, `BookAdmin`, `PaperAdmin` (`is_published` editable in the list), `QuestionAdmin` (SolutionInline), `SolutionAdmin`; all with history; no actions.
- pages: `PageAdmin` (five fixed pages, history, placeholders count; no add or delete).
- practice: `AttemptAdmin` (export), `AnswerSheetUploadAdmin`.
- learn: `ChapterAdmin` (FlashCardInline), `RevisionAdmin` (ClipInline, publish/unpublish actions, ffmpeg queued on save), `ClipAdmin` (direct upload to the bucket, move up/down, process again, preview), `FlashCardAdmin`, `QuizItemAdmin`, `EntitlementAdmin` (an add = a staff grant), `BookCodeAdmin` (read-only; search by whole code through the digest).
- shop: `ProductAdmin` (import/export, publish/unpublish/set stock, inlines for bundle items, attributes, images, slug history; the live stock guarded), `CategoryAdmin` (tree), `CollectionAdmin`, `ProductTypeAdmin`, `CouponAdmin`, `OfferAdmin`, `ShippingRateAdmin`, `OrderAdmin` (read-only form; inlines for items, discounts, payments, refunds, shipments, notes; actions mark packed/shipped/delivered, cancel, refund, payment link, offline payment; no delete; custom add and customer views), `PaymentAdmin`, `RefundAdmin`, `InvoiceAdmin`/`CreditNoteAdmin` (PDF views), `ReviewAdmin` (approve/reject), `QuoteRequestAdmin` (make quotation), `StockAlertAdmin`.

### 2.5 Library admins (20 models)

auth.Group (superuser), account.EmailAddress (ADMIN), mfa.Authenticator (superuser), socialaccount.* (superuser),
axes.* (ADMIN), django_celery_beat.* (superuser), django_celery_results.* (superuser), taggit.Tag (ADMIN),
token_blacklist.* (ADMIN), admin_interface.Theme (ADMIN). Total 59 models in 18 apps.

### 2.6 Models with no admin of their own

shop: Shipment (inline only), PinCode, Address (customer page only), Cart, CartItem, OrderItem/OrderDiscount/OrderNote
(inline only), WebhookEvent, the catalogue inlines; learn: Learner, Progress, QuizAttempt, CardReview, Device; Django:
admin.LogEntry (no audit-log viewer), sessions.Session.

### 2.7 Tests that pin the admin

`ops/test_admin_pages.py:57` (every admin page for a superuser), `ops/tests.py:92,103` (dashboard),
`shop/test_admin.py:39-131`, `shop/test_store_admin.py:36-133`, `shop/test_staff_orders.py:53-155`,
`accounts/test_roles.py:24-119`, `learn/test_preview.py`, `learn/test_uploads.py`.

## 3. Models per app

- accounts: `User` (email unique, full_name, phone, class_level, board, district, date_of_birth, parent_name, parent_contact, consent_at, login_phone, login_phone_verified, sms_updates, is_active, is_staff; `is_minor`, `consent_pending`, `pending_deletion`; no history), `TeacherProfile` (school_name, district, subject, verified, verification_note, verified_at, verified_by), `ConsentRecord` (event given/withdrawn, method declared/email_link/sms_link, purpose, notice_version, by_parent, verified_at, ip_hash), `DeletionRequest` (7-day grace, pending/cancelled/done, `complete()` anonymises).
- content: Board, ClassLevel, Subject, Book (history), Paper (code, tier E/M/H, number, marks, `is_published` default True, `is_sample` one per book, history, `qr_image()`, `landing_url()`), Question (order, labels, text_md, options_json, marks_text, tags, history), Solution (body_md, history). No draft/version field beyond history; no publish flag on Book, Question, Solution.
- practice: Attempt (daily cap 20; consent-pending blocked), AnswerSheetUpload (model only).
- pages: Page (five fixed slugs, body_md, version, updated, history, placeholders).
- ops: EmailSuppression (from Anymail tracking; `pre_send` drops suppressed), SmsLog (90 days).
- shop (30): Product (kind sample-papers/solutions/bundle/digital; mrp, price, `gst_rate` default 0, `hsn_code` default 4901, weight, stock, is_active, SEO, product_type, categories, related; slug history), ProductImage, BundleItem, SlugHistory, Category (MP_Node), Collection/CollectionItem, ProductType/Attribute/AttributeValue, Coupon (percent/fixed, min order, dates, max uses, per customer), Offer (scopes cart/products/categories/collections, combinable), ShippingRate (states list, fee, free_above), PinCode (pin → states/districts), Address, Cart/CartItem (guest token), **Order** (number EL-YYYY-NNNNNN, token, email, shipping_address snapshot, money fields, coupon, payment_method razorpay/cod/offline, FSM status pending/paid/packed/shipped/delivered/cancelled/refunded, placed_at, stock_reserved, livemode, created_by, history), OrderItem (snapshots incl. hsn and gst_rate), OrderDiscount, **Payment** (FSM created/authorized/captured/failed/refunded, Razorpay ids, payment link, offline reference, raw_payload 180 days, history), OrderNote (history), Refund (pending/processed/failed), Shipment (courier choices with tracking URL templates), Review (pending/approved/rejected, history), Invoice/CreditNote (number ≤16 chars, financial_year, serial; T-series for test mode), StockAlert, QuoteRequest (QT-YYYY-NNNNN, gstin, items JSON, status new/quoted/ordered/closed, discount, shipping, quotation PDF valid 15 days), WebhookEvent (event_id/digest unique).
- learn (12): Chapter (weight, frequency, must_do), Revision (draft/published, target_minutes), **Clip** (kind, FSM processing uploaded/processing/ready/failed, hls_path, poster, duration, notes, is_free_preview, questions, tags), FlashCard, QuizItem (mcq/true_false/fill_blank, source question), BookCode (HMAC digest, subject, batch, redeemed_by/at), Entitlement (source book_code/purchase/grant, valid_until), Learner, Progress, QuizAttempt, CardReview, Device.

### 3.8 State machines (django-fsm-2)

Order.status: pay (pending→paid, not COD), pack (paid, pending→packed, `ready_to_pack`), ship (packed→shipped),
deliver (shipped→delivered), deliver_digital (paid→delivered), cancel (pending/paid/packed→cancelled), mark_refunded
(paid/packed/shipped/delivered/cancelled→refunded). Payment.status: authorize, capture, fail, refund. Clip.processing:
start, finish, fail. `protected=True` + `ConcurrentTransitionMixin` on Order and Payment. FSM signals and
`FSMAdminMixin` unused.

### 3.9 Cross-cutting patterns

simple_history on Book, Paper, Question, Solution, Page, Order, Payment, OrderNote, Review (not on User,
TeacherProfile, Product, Coupon, Offer, ShippingRate, Entitlement, Revision, Clip). TimeStampedModel widely. No soft
delete: `is_active` flags, `Paper.is_published`, `Revision.status`, anonymisation on deletion, PROTECT on tax records,
`OrderAdmin.has_delete_permission=False`.

## 4. Shop operations

### 4.1 Flows (`shop/services.py`)

`create_order` (190-214), `create_staff_order` (217-230), `save_order` (233-265), `place_cod` (272-286),
`record_capture` (307-339, idempotent; refunds a wrong amount or a sold-out order), `mark_paid` (342-357: claim
coupon and offers → reserve stock → pay → grant course → deliver if digital → notify → invoice task),
`record_link_payment` (381-389), `record_offline_payment` (392-408), `record_failure` (430-436), `start_refund`
(439-454, Razorpay only) → `tasks.refund_payment`, `refund_processed`/`refund_failed` (457-495), `cancel_order`
(498-515), `pack_order`/`ship_order`/`deliver_order` (518-554), `refund_order` (557-567), `forget_orders` (574-587),
`expire_unpaid_orders` (590-613; 2 days, staff orders 16 days), `notify` (85-106), `staff_emails`/`email_staff`
(616-632), `make_quotation` (635-646). Constants `COD_OPEN_ORDERS=2`, `FORGET_UNSOLD_AFTER=30d`.

### 4.2 Razorpay (`shop/payments.py`)

`razorpay_order_id`, `checkout_options`, `send_payment_link` (15 days), `confirm_return`, `reconcile(order)`,
`handle_webhook` (secret per mode, signature, 7-day age, `WebhookEvent` idempotency), `_dispatch` (payment.captured,
order.paid, payment.failed, payment_link.paid, refund.processed, refund.failed). Endpoint `/shop/webhooks/razorpay/`
(300 per 60 s, open while Redis is down). `reconcile_payments --older-than 10`.

### 4.3 Invoices, credit notes, quotations (`shop/invoices.py`)

Numbering per financial year: `EL/2026-27/00001`, `CN/2026-27/00001`; test series `T/…`, `TC/…`. "Tax invoice" when
any line has a GST rate, else "Bill of supply". Prices include tax: taxable = amount × 100 / (100 + rate); CGST+SGST
in `SELLER_STATE`, else IGST. `check_seller(live)` blocks real documents while `SHOP_SELLER` holds a placeholder.
WeasyPrint. Tasks `generate_invoice` (on pay; COD on ship) and `generate_credit_note`. No buyer GSTIN on orders → no
B2B invoices (only `QuoteRequest.gstin`).

### 4.4 `export_gstr1`

`--from --to [--out]`: real series only; writes `-b2c.csv` (place_of_supply, rate, invoices, taxable, igst, cgst,
sgst, shipping), `-hsn.csv` (hsn, uqc NOS, rate, quantity, total, taxable, taxes) and `-credit-notes.csv`.

### 4.5 Shipments, stock, alerts

Shipments only through `ship_order`; courier list with tracking URL templates (India Post, Delhivery, Blue Dart,
Ekart, DTDC, Xpressbees, Other → 17TRACK); no courier API. Stock reserved on pay/COD under `select_for_update`,
released on cancel; `set_stock` action; `low_stock_report` at 08:00 to SALES; `StockAlert` emailed hourly.

### 4.6 Coupons, offers, reviews, quotes, PIN codes, staff orders

Pricing order in `shop/cart.py:169-210`: coupon, offers, staff discount, shipping; claimed again under lock.
Reviews: delivered buyers only, approve/reject. Quotes: form → API → email to SALES → `make_quotation` PDF; no
conversion to an order. `import_pincodes` replaces the table. Staff orders: forms in `shop/forms.py:21-114`; the
customer page. `seed_shop`. `clean_up` daily at 04:30.

## 5. Content operations

`import_papers` (upsert with `_change_reason`, hard-deletes removed questions), `export_qr` (all papers; refuses a
non-https `SITE_URL` without `--force`; `/qr/<code>.png` serves published papers), `build_covers`, `PageAdmin` with
placeholders, the contact form (stores nothing; 5 an hour; 503 without a support address). No FAQ.

## 6. Learning operations

Clip uploads direct to the bucket; `process_clip` on queue `media` (3 retries, 1-hour limit; HLS 480p/720p);
`reprocess_clips`; signed HLS links 600 s; `import_chapter_insights`; `build_quiz_items`; `make_book_codes <subject>
<count> --batch` (digests only; `LEARN_CODE_SECRET` required; redemption throttled 5/hour per user and address);
entitlements (grants in the admin; purchases via `grant_for_order`); `send_reminders` at 18:00 via FCM; no admin for
Progress, QuizAttempt, CardReview, Learner, Device.

## 7. Accounts operations

Sign-up sets consent and the STUDENT group; parental consent links by email/SMS (7 days, 3 a day, resend every 10
minutes) — no staff action to resend or list who is pending (a shell recipe); data export (`export_user_data`,
password or 5-minute reauthentication); deletion with the 7-day purge at 03:00; teacher verify/revoke in the admin
with no notification of new requests and no teacher–student link; `login_phone` after code confirmation.

## 8. Ops and infrastructure

- Celery tasks: `ops.tasks.send_email` (5 retries), `reset_failed_logins`, `clear_sessions`, `ops.sms.send_sms`
  (daily cap, per-number/account/purpose limits), `accounts.tasks.purge_due_deletions`, `shop.tasks.refund_payment`,
  `generate_invoice`, `generate_credit_note`, `clean_up`, `make_og_image`, `send_stock_alerts`, `low_stock_report`,
  `learn.tasks.process_clip` (queue media), `send_reminders`, `api.tasks.flush_expired_tokens`, django-pictures.
  Backups are `scripts/backup.sh` from the host's crontab (+ `upload_backup`), not a task.
- Beat: deletions 03:00, failed logins 03:30, sessions 03:45, backend cleanup 04:00, shop clean-up 04:30, JWT flush
  04:30, stock alerts hourly :15, low stock 08:00, reminders 18:00. Periodic tasks are superuser-only to change.
- Health: `/health/` and `/health/web/` (database, cache, storage, Celery ping), cached 20 s, Caddy requires
  `X-Health-Token`.
- Logging: django-guid request IDs in JSON logs; Sentry with scrubbing; refused refunds, SMS cap hits and payment
  mismatches are only log lines (no staff notification).
- Settings: the full env table (core, database, SMS, proxy, sign-in, email, Celery, shop/seller, logs, storage,
  learn/app, API throttles, compose) with defaults; `ConfigView` exposes the public subset.
- Compose: db, redis, redis-cache, web (migrate → bootstrap_roles → health → gunicorn), worker, beat, media-worker,
  caddy, frontend. Caddy `@django` matcher: `/api/* /_allauth/* /admin/* /shop/webhooks/* /anymail/* /health* /shop/media/* /learn/preview/* /learn/hls/* /account/google/* /qr/* /static/*`; mirrored in the frontend's
  `DJANGO_PREFIXES` (`examleaf-frontend/src/lib/site.ts:8-24`). **A new Django path must be added to both.**
- Launch-readiness signals exist but are scattered (placeholders, `check_seller`, `support_email()`, `learn.E001`,
  start-up guards, `live_mode()`, `/health/`, `check --deploy`, the manual checklist in `DEPLOYMENT.md:258-282`).

## 9. Staff-facing API

None: nothing in `api/` uses IsAdminUser or DjangoModelPermissions; staff only change how public endpoints behave.
`me/` exposes `roles`, not `is_staff`. OpenAPI through drf-spectacular with tags and `ENUM_NAME_OVERRIDES`; schema,
Swagger and Redoc are public.

## 10. Documentation that already plans staff features

Platform plan §4 decision 4 ("Roles that can grow"); phase 5 (A5 SMS log, A7 suppression, B7 reviews, B8 quotation,
B9 low stock, B10 GSTR-1); phase 6 (D1 clip admin, D8 staff player, E3 staff orders, E4 "Admin experience": sortable
images not done, filters, bulk actions, timeline, dashboard, import/export, roles); phase 8 (the admin stays in
Django); coverage matrix J4, G3, §3.1 G, §3.2 (the per-role access table), G14, T4; README "Staff", "Operations",
"Roles and permissions", "Personal data", "Admin", "Staff orders", "Admin (Shop)", "Teacher tools", "Small gaps";
CHANGELOG entries per phase; RUNBOOK procedures that need a shell today: staff onboarding and MFA reset, log everyone
out, data requests by letter, purge of 8-year-old orders, consent-pending list, stuck payments, test/live fix-up,
regenerate an invoice, GSTR-1, reprocess clips, print book codes, axes unlock; SECURITY_REVIEW: the Caddy allowlist
not done; SECURITY_REVIEW_PHASE5_6: L11 offline refunds (open), **I6 "one person can give goods away"** (a cap on staff
discounts, approval of offline payments above a value and of ₹0 orders, a weekly list of grants: open, for the
founder); DEPLOYMENT §6, §12, §13.

## 11. Gaps and constraints for the control panel

1. No staff UI outside the Django admin and `/learn/preview/`, no staff API, no launch-check page.
2. The dashboard's "Waiting" line isn't permission-gated, ignores `livemode`, has no charts or loading state.
3. No audit-log viewer; history missing on User, Product, Coupon, Offer, ShippingRate, Entitlement, Revision, Clip;
   Payment and OrderNote history not viewable.
4. FSM admin integration and `graph_transitions` available but not wired.
5. Many models without an admin (section 2.6).
6. Staff aren't notified of teacher requests, deletion requests, failed refunds, failed clips, the SMS cap; only
   SALES gets emails (low stock, quote requests).
7. Open business items: I6 controls, L11 offline refunds, quotation-to-order conversion, B2B invoices (no buyer
   GSTIN on orders).
8. Shell-only operations (section 10).
9. Routing: a new Django prefix goes into the Caddyfile `@django` matcher and `DJANGO_PREFIXES`; the CSP allows no
   inline scripts and no frames; staff sessions are 8 hours, absolute.
10. Reuse rather than rebuild: `shop.services.*`, `payments.*`, `accounts.roles`, `ops.admin.LoggedExportMixin`,
    the dashboard stats tags, `export_user_data`, `request_deletion`, `send_parent_link`, `learn.services.make_codes`
    and `redeem`, `learn.tasks.queue_processing`; the two duplicate `ReadOnlyAdmin` classes.
11. Tests to keep green: the admin crawl, role tests, dashboard tests, `shop/test_admin.py`, `shop/test_staff_orders.py`.
