# Resilience

What keeps the Django backend from hanging, from falling over, and from depending on any one web or worker process: the
audit of 9 October 2026 (the checklist below, item by item), the load test that measured it, every knob an operator
can turn, what the Kubernetes chart must change, and what was left for later and why. Every fix left a test behind
that fails without it, where one could; the tests are named in the table.

Contents: [the checklist](#the-checklist) · [task by task](#celery-task-by-task) · [the load test](#the-load-test) ·
[settings](#settings-for-operators) · [the pooler and the connections](#the-pooler-and-the-connections) ·
[the Kubernetes chart](#what-the-kubernetes-chart-must-change) · [deferred](#deferred)

## The checklist

"Fixed" names the change and its file; "already right" names where the existing code does it. Line numbers are those
of this commit.

| # | Item | Finding | Fixed / already right | Proven by |
|---|---|---|---|---|
| 1.1 | Razorpay (checkout's Razorpay order, Checkout's return, refunds, payment links, reconcile) | one 10 s value for connect and read; the SDK's retries off | fixed: `(3, 10)` connect/read (`shop/payments.py` `TIMEOUT`); the SDK's retries stay off (a page retries by the customer's click, a task by Celery); every SDK call goes through a bulkhead (1.12) | `shop/test_resilience.py`: a Razorpay that never answers, through the real SDK and requests: the payment page answers 503 "could not be reached" within the timeout, the refund task raises for Celery's retry; both hang without a timeout |
| 1.2 | MSG91 | 10 s for everything | fixed: `httpx.Timeout(10, connect=3)` (`ops/sms.py` `TIMEOUT`); 3 retries with backoff in the task (already); in a request (queue down) one try (already) | `ops/test_resilience.py::test_a_silent_msg91…` |
| 1.3 | SES (anymail) and its SNS webhook | boto3's defaults: 60 s to connect, 60 s per read, the legacy five tries: with the queue down an email sent from the web process could hold a thread for minutes | fixed: connect 3 s, read 10 s, three tries in standard mode; anymail's HTTP backends (Brevo, Postmark) `(3, 10)` instead of 30 s (`examleaf/settings.py`, the resilience block) | `examleaf/test_resilience.py::test_email_through_ses…` |
| 1.4 | The buckets (R2, AWS S3; django-storages) and the backups bucket | boto3's defaults (as 1.3); the health check's write and every invoice upload use them | fixed: `client_config` connect 3 s, read 20 s (per read: a clip's video is read in parts), three tries, standard mode, for every S3 storage (`settings.py`, the resilience block); the public storage still deconstructs to its class alone, so no option reaches Celery | `examleaf/test_resilience.py::test_the_buckets_give_up…` |
| 1.5 | FFmpeg | — | already right: `subprocess.run(timeout=)` 3000 s and ffprobe 60 s (`learn/media.py:22,44`), the task's own 3500/3600 s (`learn/tasks.py:25`); at the soft limit `subprocess.run` kills ffmpeg (it kills its child on any exception) | `learn/test_media.py` (existing) |
| 1.6 | WeasyPrint | invoices and credit notes already in the worker; the quotation PDF rendered in the admin's request; no limit of its own | fixed: the admin's "Make the quotation PDF" queues `shop.tasks.make_quotation` (here only while the queue is down, as emails do); invoice, credit note and quotation tasks have 60 s soft, 90 s hard (`examleaf/celery.py` `PDF_TASK`). Measured in the image: 0.07 to 0.18 s a render | `shop/test_resilience.py::test_the_quotation_pdf_is_made_by_the_worker…` |
| 1.7 | Firebase (the daily reminder) | firebase-admin's default: 120 s a call | fixed: 20 s (`learn/tasks.py` `FCM_TIMEOUT`, the app's `httpTimeout`) | `examleaf/test_resilience.py::test_firebase_calls_wait_twenty_seconds…` |
| 1.8 | Shiprocket and ERPNext | — | already right: the integrations client, 5 s to connect and 20 s to read, its circuit breaker and call log (`integrations/client.py:154`); the quote 3 s (`SHIPPING_QUOTE_TIMEOUT`); ERPNext's 429 waits its Retry-After without counting a try (`erp/tasks.py` `deliver`) | `integrations/tests`, `erp/tests` (existing) |
| 1.9 | Turnstile, Pwned Passwords | — | already right: 5 s and 1 s, both letting the form through when out of reach (`accounts/forms.py:31`; settings) | existing tests |
| 1.10 | PostgreSQL itself | no connect timeout (libpq waits the system's TCP timeout, minutes) | fixed: `connect_timeout` 5 s (`DB_CONNECT_TIMEOUT`) | `examleaf/test_resilience.py::test_statements_have_a_time_limit_by_role` |
| 1.11 | `requests.get` (or any HTTP call) without a timeout | none found (every `requests`, `httpx`, `urlopen` and boto3 call reviewed) | — | — |
| 1.12 | A slow provider and the thread budget | with gthread a slow call holds a thread for its whole timeout; a proxy's kept-alive connections stay with one process, so once all eight threads of a process waited on Razorpay the catalogue on that process waited too (the load test: the fast endpoints' slowest 1% at 8 s with new connections, 13 s kept alive) | fixed: a bulkhead (`examleaf/bulkhead.py`): Razorpay's and MSG91's calls share half a process's threads (`GUNICORN_THREADS // 2`), a call over it fails at once with the provider's own "unreachable" answer | `shop/test_resilience.py::test_a_razorpay_call_over_the_providers_half…`, `ops/test_resilience.py::test_an_msg91_call_over…`; the load test: the slowest 1% at 2.0 to 2.3 s |
| 2.1 | `CONN_MAX_AGE`, `CONN_HEALTH_CHECKS` | — | already right: 60 s, checked before reuse (`settings.py:134-135`), one connection per gunicorn thread or Celery process; Celery's Django fixup closes obsolete ones between tasks | — |
| 2.2 | `statement_timeout` | none | fixed: by role, as libpq startup options: 15 s in gunicorn, 600 s in Celery, none in `manage.py` (migrations, imports); `idle_in_transaction_session_timeout` 60 s and 600 s (a thread stuck while holding row locks); `python -m gunicorn` and `python -m celery` count as theirs (`settings.py`, the resilience block). Through the HA profile's PgBouncer (its URL disables server-side cursors) none are sent, since PgBouncer refuses or drops them: the limits are then the pooler's (see the pooler) | `examleaf/test_resilience.py`: the options by role, none through the pooler; on PostgreSQL, a statement over a 1 s limit is cancelled |
| 2.3 | `select_for_update` that can hang | `refund_payment` locked the refund, its payment and its order during two Razorpay calls: a second task for the same refund, and any request touching the order, waited behind them | fixed: the refund's row alone (`of=("self",)`) and `skip_locked` (`shop/tasks.py`): a second task returns at once. The other locks are short and DB-only (checkout, capture, refunds, the coupon and offers, a book code, the audit chain's head) | `shop/test_resilience.py::test_a_refund_another_worker_is_making…` (PostgreSQL): returns within a second where it waited the whole hold |
| 2.4 | Long commands and reports | `export_gstr1` read a period's invoices at once | fixed: `iterator(chunk_size=500)`; already streaming: `clear_sessions`, the insights item analysis, the audit chain's check and export, the panel's audit export. Loops that write the rows they read (the order purge, the expiry) left as they are: SQLite cannot isolate such a cursor, and they are small | `shop/test_commerce.py::test_gstr1_export…` (existing) |
| 2.5 | `ATOMIC_REQUESTS` | — | already right: off; explicit transactions, none open across a provider's call on the hot paths (`confirm_return` closes its own before asking Razorpay; the integrations client's rule) | — |
| 2.6 | A query per row on the storefront's hot paths | none found | already right, now proven: the product page, the cart, the orders, an order and an order's link read as many queries with one row as with four | `shop/test_query_counts.py`; `api/tests.py:93` (the catalogue, existing) |
| 3 | gunicorn | the image ran sync workers unless `GUNICORN_CMD_ARGS` said otherwise; no graceful timeout, keep-alive or heartbeat directory; compose and the chart spelled their own arguments; with gthread `--timeout` bounds no request (only a process whose main loop is stuck) | fixed: `gunicorn.conf.py`, read by the Dockerfile's command and compose's: workers and threads from the environment, timeouts, recycling (5000 requests, a jitter of 2500: measured, 3), the site imported once in the master (`preload_app`: a recycled process is forked in milliseconds; the chaos run's pods, recycling their processes together while each imported Django, answered nothing for 14 to 20 s), `/dev/shm`, no control socket, JSON logs, a timed-out process's thread stacks dumped | `examleaf/test_resilience.py::test_gunicorn_runs_from_one_config_file…`: through gunicorn's own setting checks and logging set-up; the Dockerfile, compose and the chart's arguments agree; `::test_the_site_opens_no_connection_and_starts_no_thread…` (what preload needs) |
| 4.1 | `task_acks_late`, idempotency | acknowledged at the start: a task cut short (a pod killed after its grace period, a lost node, compose's 10-second stop) was lost (the chaos run saw it) | fixed: acks late, every task checked (next section); `send_sms` skips an SMS its row says went, `send_email` one its task id marks as sent (the cache, a day); the reminder and the data export stay acknowledged early | `examleaf/test_resilience.py::test_tasks_are_acknowledged_once_run…`, `ops/test_resilience.py::test_an_sms_task_run_again…`, `::test_an_email_task_delivered_again…` |
| 4.2 | `task_reject_on_worker_lost` | off: a task whose process alone died (killed for its memory, a crash in a C library) was marked failed and lost | fixed: on. **The trade-off**: Celery 5.6 puts such a task back at once without any limit, so one that kills its process every time would loop for ever, silently (no failure is recorded while it is put back). `examleaf.celery.Task`, every task's base: a run delivered again writes its STARTED state with the count of earlier runs that started and never ended; after three lost processes it fails, acknowledged, with its reason in the results and Sentry (`LostTooOften`; RUNBOOK.md). A first delivery reads and writes nothing. When the whole worker dies (a pod OOM-killed as a group, a lost node), Redis gives the task to another worker after the visibility timeout (4.6), never while it still runs | `examleaf/test_resilience.py::test_a_task_that_kills_its_process_every_time…` (through Celery's own tracer) |
| 4.3 | `worker_prefetch_multiplier` | Celery's 4: a media worker held three clips behind the one it was making, where another media worker could have taken them | fixed: 1 | the same test |
| 4.4 | Time limits by kind | one 300 s hard limit for all, no soft one | fixed: 270 s soft by default; PDFs 60/90; the long jobs 1500/1800 (the clean-up, the reminders, every insights job, the parcel tracking, the PIN survey, the audit chain's check and copy, panel jobs, the ERPNext reconciliation); clips 3500/3600 (already) | the same test: soft < hard < the visibility timeout, for every task |
| 4.5 | `broker_connection_retry_on_startup` | unset (Celery 6 will stop retrying at start) | fixed: on | the same test |
| 4.6 | Redis `visibility_timeout` | Redis's default hour: a retry an hour away (refunds, integrations) or a clip of an hour would have gone to a second worker | fixed: two hours | the same test, for every task's limit and countdown |
| 4.7 | `result_expires` | — | already right: 7 days (`settings.py:352`) | — |
| 4.8 | `worker_max_tasks_per_child`, `worker_max_memory_per_child` | none; measured in the image: Django and the tasks 163 MB, then about 1 MB more per invoice | fixed: 200 tasks, 300 MB (`CELERY_WORKER_MAX_*`) | the same test |
| 4.9 | Beat | — | already right: one instance by design: one compose service; the chart's Recreate and a PodDisruptionBudget of 0 (`values.yaml:230-240`); the schedule in the database (django-celery-beat) | — |
| 4.10 | Periodic jobs that would send twice | overlapping runs of the stock alerts or the morning's held SMS sent them twice | fixed: `examleaf.celery.single_run` (a cache lock for the task's hard limit) on the jobs that send or alert; the stock alerts and the held SMS also claim each message before it goes (so overlapping runs send once even with Redis down) | `shop/test_resilience.py::test_two_overlapping_stock_alert_runs…`, `::test_a_periodic_job_that_finds_itself_running…`, `shipping/tests/test_messages.py::test_two_overlapping_morning_runs…` (twice on the old code) |
| 4.11 | The queue's Redis down | — | already right: publish retried once (`settings.py:350`), 2 s socket timeouts; emails and SMS sent from the web process, pictures made there, the rest queued again by the daily clean-up | `ops/test_resilience.py`, `ops/tests.py` (existing) |
| 4.12 | The staff and erp apps' workers | the defaults for all their tasks | fixed: the long limits for the audit chain's check and copy, panel jobs and the reconciliation, the single-run lock on the three that alert or email, the data export acknowledged early. Already right: the ERPNext relay calls through the integrations client (5 s, 20 s, its circuit breaker), waits a 429's Retry-After without counting a try, claims each row with a 5-minute lease and sends an aggregate's rows in order (an earlier row that failed holds only its own aggregate), stops taking rows after 240 s (within the 270 s soft limit), holds no transaction during a call; the pull moves its cursor page by page; a panel job stops at its next row once cancelled and writes its progress at most once a second; the audit copy skips a day the bucket has (whose client has the timeouts of 1.4); the audit chain's head row is the one lock every audited event takes (by design: the chain's order) | `examleaf/test_resilience.py::test_tasks_are_acknowledged_once_run…` (every task's limits); `staff/tests`, `erp/tests` (existing) |
| 5 | The cache's Redis down or silent | down: already soft (misses, `add` "stored", the throttles let requests through, the shop's own limits refuse). Silent (packets dropped): each of a request's 4 to 14 cache calls waited its 1 s timeout | fixed: SoftRedisCache pauses after a failed call: 5 s of misses at once, then a new try, one warning a pause (`examleaf/cache.py`) | `ops/test_resilience.py::test_a_silent_cache_redis…` (20 calls take 1 s, not 20); `ops/tests.py::test_the_site_keeps_working_while_redis_is_down` (existing) |
| 6.1 | Body and field limits | — | already right: `DATA_UPLOAD_MAX_MEMORY_SIZE` 1 MB (DRF reads `request.body` for JSON, so the API's 413 applies to every endpoint), `DATA_UPLOAD_MAX_NUMBER_FIELDS` Django's 1000, `FILE_UPLOAD_MAX_MEMORY_SIZE` 2.5 MB (`settings.py:323-325`); Caddy and Traefik stop bodies at 10 MB | `api/tests.py::test_request_bodies_are_limited…` (existing) |
| 6.2 | The 500 MB clip | — | already right: the browser sends it to the bucket on a presigned PUT (`learn/uploads.py:41`); without a bucket the form's file is streamed to a temporary file past 2.5 MB, and only signed-in staff may send that much (`LargeBodyGuard`, `learn/uploads.py:112`) | `learn/test_uploads.py` (existing) |
| 6.3 | Pagination caps | a product's reviews came all in one answer | fixed: its newest 200, with the average and the count of all; already right: every routed collection at 200 a page at most (`api/pagination.py:8`) | `api/test_bounds.py` |
| 6.4 | Search | `?search=` of a thousand words made a thousand LIKE clauses per field, and a cache entry of its own | fixed: the first five words of 50 characters (`api/filters.py`) | `api/test_bounds.py::test_a_search_of_many_words…` |
| 7 | Statelessness | — | already right: sessions in the database, CSRF in its cookie, allauth's state in the session, axes in the database, throttles and allauth's limits in the shared cache, uploads in the buckets (or, without them, the shared media volume, which then needs ReadWriteMany for pods on several nodes), invoices and labels in the private storage, no file written outside `/tmp` and `MEDIA_ROOT`; `SECRET_KEY` and every key from the environment. In-process state: the health checks' 20-second results (acceptable: per process, never a user's) and the Markdown renderer's `lru_cache` (deterministic, bounded at 20,000 texts) | the load test: a session signed in on one gunicorn and used on a second (section [load test](#the-load-test)) |
| 8 | Health and probes | no liveness endpoint (the chart probed the TCP port, which accepts even with every thread stuck); `/health/web/`, the chart's readiness, checked the cache and a write to the bucket: their outage took every pod out of traffic at once although the site runs without them, and the frontend's 2-second check saw a slow bucket as Django down; no migration check | fixed: `/health/live/` (the process answers; no database, no Redis; compose's container check); `/health/web/` = the database and the migrations (`examleaf.health.Migrations`; the start gate before gunicorn too); `/health/` = everything, for the monitor. The chart has meanwhile moved readiness to a static file (its storage check timed out on both pods at once under load): `/health/web/` is now the light one it can switch back to, a `SELECT 1` and the migrations, no cache and no storage, kept 20 s per process | `examleaf/test_resilience.py::test_liveness_answers_without…` (database blocked, a cache that fails on any use), `::test_readiness_fails_while_a_migration…`; `ops/tests.py` (Redis down: `/health/` 500, `/health/web/` 200) |
| 9.1 | An exception kills no process | — | already right: Django turns every exception into a 500 (JSON under `/api/`, `examleaf/views.py`); a gunicorn process killed or recycled is logged in JSON ("Worker exiting", "WORKER TIMEOUT", with its threads' stacks), to count with the log search in RUNBOOK.md | — |
| 9.2 | Sentry | — | already right: no PII, no local variables, every field scrubbed (`examleaf/sentry.py`; `settings.py:461-462`) | `ops/tests.py` (existing) |
| 9.3 | Webhooks answer fast | — | already right: Razorpay's handled in one database transaction with its record, no provider call, follow-ups queued (`shop/payments.py` `handle_webhook`); the parcel events and ERPNext's stored and answered, then processed by a task (`shipping/webhooks.py:25`); anymail's tracking a row written (`ops/models.py:32`) | existing tests |
| 9.3.1 | Webhooks from inside the cluster | ERPNext posts to web's Service over plain http (no ingress, no `X-Forwarded-Proto`): the https redirect answered 301 (the chaos run) | fixed: `SECURE_REDIRECT_EXEMPT` = `^api/hooks/erp-events/`: authenticated by the HMAC signature of each body (`erp/inbound.py`), not by TLS; through Traefik it arrives over https as before. Judged and left redirected: Shiprocket's `/api/hooks/parcel-events/` (a static token in a header: plain http would expose it), anymail's (HTTP basic auth, the same), Razorpay's (signed, but sent from the internet over https, a customer's details in its body) | `examleaf/test_resilience.py::test_erpnext_webhooks_reach_django_over_plain_http…` |
| 9.4 | Idempotency of money and state | place order: the same cash-on-delivery checkout sent twice at once placed two orders | fixed: one checkout of a cart at a time under its row's lock, the cart emptied in the same transaction (`api/shop.py` `OrderViewSet.create`); already right: pay (the Razorpay order made once; capture once by its state: `record_capture`), the webhooks (`WebhookEvent`), refunds (state, the refund task's lock and notes), cancel (the state machine), book codes (`learn/services.py:66`), consent (`api/parent_link.py:69`), the panel's bulk actions (an idempotency key per target) | `shop/test_resilience.py::test_the_same_cash_on_delivery_checkout_sent_twice_at_once…` (PostgreSQL: two placed on the old code); `shop/test_razorpay.py`, `shop/test_robustness.py`, `shop/test_api.py`, `learn/test_api.py:178`, `api/test_parent_link.py:17` (existing) |
| 9.5 | SIGTERM | compose stopped every container after Docker's 10 seconds | fixed: compose gives web 40 s (gunicorn's 30 for the requests in progress) and the Celery workers 5 minutes (warm shutdown); the chart already gives web 70 s and the workers 300 s | measured (the load test's section): gunicorn finished a request 2 s into a 10-second Razorpay call, then exited; a Celery worker finished a refund's 10-second try, queued its retry and exited, nothing left unacknowledged |
| 10 | Logs and tracing | no request was logged (gunicorn wrote no access log, and the frontend's calls never pass Caddy); task logs had no task id | fixed: one JSON line per request (`examleaf.middleware.RequestLogMiddleware`): the URL pattern (never the address itself, which can hold an order link's or a consent link's secret), status, milliseconds, the account's id; a warning past 2 s (`SLOW_REQUEST_SECONDS`); `task_id` and `task_name` on every line inside a task (`examleaf.celery.TaskIds`), beside the request id django-guid passes on (already); gunicorn's own lines JSON too. RUNBOOK.md "Reading the logs" | `examleaf/test_resilience.py::test_each_request_is_logged_once…`, `::test_a_tasks_log_lines_name_the_task…` |
| 10.1 | The frontend's contract | — | already right: `X-Request-ID` from the proxy taken when it is a UUID and sent back (django-guid), the internal token compared in constant time and removed before the view (`examleaf.middleware.FrontendClientMiddleware`), the forwarded headers trusted only behind `PROXY_COUNT` proxies and `USE_X_FORWARDED_HOST`. The frontend sends no `X-Request-ID` of its own and puts no timeout on its server-side calls (deferred) | `ops/tests.py::test_the_request_id_from_the_proxy…`, `api/tests.py` (the internal token; existing) |
| 11 | The load test | | below | below |

## Celery, task by task

Every task now runs with `acks_late` and `reject_on_worker_lost`: it is acknowledged once it has run, so one cut short
runs again on another worker (at once if only its process died, after the visibility timeout if its whole worker did;
three lost processes at most: 4.2). Each is safe to run twice, or is acknowledged early on purpose:

| Task | Run twice | Notes |
|---|---|---|
| `ops.send_email` | not sent again: its task id marks it sent (the cache, a day) | a worker killed between the send and the mark, or the cache down: it may go twice (a code twice is better than none) |
| `ops.send_sms` | not sent again (its SmsLog row: sent or refused) | fixed in this pass |
| `shop.refund_payment` | adopts the refund it made (its id in the notes); a second task skips the locked row | |
| `shop.generate_invoice`, `generate_credit_note` | one invoice per order (unique), the PDF made once | an orphan file at worst |
| `shop.make_quotation` | the PDF made again, the earlier one deleted | new: from the admin's request |
| `shop.clean_up`, `send_stock_alerts`, `low_stock_report` | state-based; the alerts claimed one by one; single run | |
| `shop.make_og_image`, pictures' sizes | made again under a new name | |
| `learn.process_clip` | a new HLS folder, the old one deleted | redelivered after the visibility timeout if a media pod is killed |
| `learn.send_reminders` | would remind everybody twice | acknowledged early; single run |
| `accounts.purge_due_deletions` | the pending ones only | single run |
| `ops.reset_failed_logins`, `clear_sessions`, `api.flush_expired_tokens`, `integrations.purge_old_records` | idempotent | |
| `insights.*` | a second run's rows; the latest counts | the fraud digest: single run |
| `shipping.*` | IntegrationTask: looks before it creates; scans unique; held SMS claimed | tracking and the survey: long limits, single run |
| `staff.verify_audit_chain`, `export_audit_log` | a second check's event; a day's copy written once (it skips a day there) | long limits, single run |
| `staff.run_job` | finds the job running and does nothing | long limits: past the soft one the job ends failed with its reason |
| `staff.email_data_export` | would email the data twice | acknowledged early |
| `staff.expire_*`, `watch` | state-based | |
| `erp.relay`, `replay_row`, `process_inbound_event`, `pull`, `refresh_stock` | each row claimed with a 5-minute lease (and ERPNext's idempotency keys); events once; cursors move page by page | the relay stops taking rows after 240 s, within the soft limit |
| `erp.reconcile_day` | a second set of differences | long limits, single run |

## The load test

`scripts/loadtest.py` (the standard library only): `stub` is a Razorpay and an MSG91 that answer after 10 seconds
(Razorpay with a server error, MSG91 with a success); `seed` makes 300 accounts with confirmed mobile numbers and 200
guest orders awaiting payment on top of `seed_shop` and the fixture papers; `application()` is gunicorn's app factory
with the site's calls sent to the stub; `run` keeps N connections busy for a while (new connections, or kept alive as
a proxy's are) and reports each endpoint's statuses and percentiles and gunicorn's memory.

The set-up, production-like: `DEBUG=0`, PostgreSQL 17 (local), the cache on a Redis of its own, the queue's Redis down
(so a log-in code's SMS is sent inside the request, the fallback path), gunicorn from `gunicorn.conf.py` with 3
processes of 8 threads (24), the frontend's `X-Internal-Token` so each request counts for its own address, 60 seconds
and 50 connections a run. The fast connections ask the catalogue (`products/`, a product, `books/`), a paper and its
solutions, their guest cart (`cart/`, add a book) and `config/`; the slow ones start a guest order's payment
(Razorpay's order is made in the request) or ask a log-in code by SMS. The machine was a laptop shared with other
work (load average 15 to 30): compare the runs with one another, not with a server.

| Run | Fast req/s | Fast p50 | p95 | p99 | max | Slow requests |
|---|---|---|---|---|---|---|
| 50 fast, new connections | 197 | 184 ms | 717 ms | 1.0 s | 1.7 s | — |
| 10 Razorpay + 5 SMS + 35 fast, no bulkhead, new connections | 89 | 92 ms | 1.4 s | **8.0 s** | 9.1 s | 503 / 200 at 10.4 s median, 19 s at most |
| the same, kept alive | 29 | 200 ms | **11.6 s** | 12.9 s | 13.3 s | as above |
| the same, at most 10 connections a process, new connections | 72 | 419 ms | 1.0 s | 1.9 s | 2.7 s | |
| the same, at most 10 connections a process, kept alive | 97 | 96 ms | 485 ms | 1.6 s | **53 s** (connections waiting to be taken) | |
| 10 Razorpay + 5 SMS + 35 fast, the bulkhead, new connections | 69 | 317 ms | 1.5 s | 2.1 s | 3.2 s | over the providers' half: answered at once (median 0.8 s); the rest at 10 to 12.6 s |
| the same, kept alive | 36 | 917 ms | 1.7 s | 2.0 s | 2.3 s | as above, 13.2 s at most |
| 20 Razorpay + 10 SMS + 20 fast (more slow than the 24 threads), the bulkhead | 29 | 591 ms | 1.8 s | 2.3 s | 2.8 s | median 0.7 s, 13.4 s at most |
| On the rebased tree (with the staff and erp apps): 50 fast, new connections | 219 | 166 ms | 662 ms | 1.15 s | 2.5 s | — |
| On the rebased tree: 10 Razorpay + 5 SMS + 35 fast, the bulkhead, kept alive | 160 | 221 ms | 422 ms | 773 ms | 1.1 s | Razorpay over the providers' half at once, the rest at 10.4 s; the SMS by then mostly refused by the limits per number (429 at once) |

What it shows:

- **No request came near gunicorn's 60 seconds:** a slow one ended with its honest answer at the provider's timeout
  (Razorpay: 503 "could not be reached" at 10 s plus the time it waited for a thread), 19 s at the very most without
  the bulkhead and 13.4 s with it.
- **The slow dependency took more than its share of threads without the bulkhead**: 15 slow connections are fewer than
  the 24 threads, yet one fast request in a hundred waited 8 seconds (13 with a proxy's kept-alive connections), behind
  a process whose eight threads all waited on Razorpay. Capping the connections a process takes
  (`GUNICORN_WORKER_CONNECTIONS`) helps with new connections and starves kept-alive ones (53 s), so it stays at
  gunicorn's 1000. **With the bulkhead** a slow provider gets at most half a process's threads: the fast endpoints'
  p99 stays at 2.0 to 2.3 s, also with more slow connections than threads; the calls over the providers' half answer
  at once (the customer tries again).
- **Memory stays flat:** each process held 90 to 130 MB through a run of about 3,500 requests, 200 to 220 MB on the
  rebased tree at its busiest (more apps loaded), with no growth after the first ten seconds (sampled every 5 s; the
  laptop's memory compression made a few samples read lower); recycling replaced processes on schedule. Recycling
  after 1000 requests with a jitter of 100 restarted all three processes within 4 seconds of one another every half
  minute at 80 requests a second, the slowest 1% then at 6 s: hence 5000 and 2500. (`preload_app` came after these
  runs, from the chaos run's finding; it was not measured here.)
- **SIGTERM:** a request 2 s into a 10-second Razorpay call when gunicorn got SIGTERM ended with its 503 after 11.1 s,
  then the process and the master exited (gunicorn's graceful 30 s). A Celery worker (a live Redis, the threads pool)
  given SIGTERM 3 s into a refund whose Razorpay call took 10 s logged "Warm shutdown", let the try finish ("retry:
  Retry in 56s"), then exited: the retry waited in the queue for the next worker, nothing was left unacknowledged.
- **Two processes, one session:** a session signed in on one gunicorn (allauth.headless) answered `/api/v1/me/` on
  another sharing the database and the cache.

To run it again: the commands at the top of `scripts/loadtest.py`, with `DATABASE_URL`, `CACHE_URL`, a closed port as
`CELERY_BROKER_URL`, `SMS_BACKEND=msg91` (and `MSG91_AUTHKEY`, `MSG91_TEMPLATE_OTP`), `RAZORPAY_KEY_ID` and `_SECRET`,
`INTERNAL_API_TOKEN`, `SOLUTIONS_REQUIRE_LOGIN=0` and a large `SMS_DAILY_CAP`; `collectstatic` first (with `DEBUG=0`
the static files' manifest is needed).

## Settings for operators

Environment variables (each also in DEPLOYMENT.md section 13):

| Variable | Default | What it does; when to change it |
|---|---|---|
| `WEB_CONCURRENCY` | `2` (the chart sets 3) | gunicorn processes: about 2 × the CPUs + 1. More processes, more memory (about 120 MB each) and database connections |
| `GUNICORN_THREADS` | `8` | requests at once per process; half of them may wait on providers (the bulkhead). More threads: more database connections (one each) |
| `GUNICORN_TIMEOUT` | `60` | a process whose main loop is silent this long is killed (with threads, not a request's limit) |
| `GUNICORN_GRACEFUL_TIMEOUT` | `30` | after SIGTERM, the requests in progress may finish; keep the stop grace above it (compose 40 s, the chart 70 s) |
| `GUNICORN_KEEPALIVE` | `5` | seconds an idle connection from the proxy stays open |
| `GUNICORN_MAX_REQUESTS`, `GUNICORN_MAX_REQUESTS_JITTER` | `5000`, `2500` | a process is replaced after this many requests, each after a number of its own; lower only if a process's memory grows |
| `GUNICORN_WORKER_CONNECTIONS` | `1000` | connections a process takes at once; a cap starves a proxy's kept-alive connections (the load test) |
| `GUNICORN_BIND` | `0.0.0.0:8000` | where gunicorn listens |
| `GUNICORN_CMD_ARGS` | none | gunicorn's own: more arguments, which win over `gunicorn.conf.py` |
| `DB_CONNECT_TIMEOUT` | `5` | seconds to connect to PostgreSQL |
| `DB_STATEMENT_TIMEOUT` | `15` in gunicorn, `600` in Celery, `0` (none) in `manage.py` | seconds a statement may run before PostgreSQL cancels it; raise for the web only if a page needs it (it should not) |
| `DB_IDLE_IN_TRANSACTION_TIMEOUT` | `60`, `600`, `0` | seconds a transaction may sit idle (a stuck thread holding row locks) |
| `CONN_MAX_AGE` | `60` | seconds a database connection is kept between requests (existing) |
| `CELERY_WORKER_MAX_TASKS_PER_CHILD` | `200` | a Celery process is replaced after this many tasks |
| `CELERY_WORKER_MAX_MEMORY_PER_CHILD` | `307200` (KiB, 300 MB) | … or once it holds this much (WeasyPrint grows by about 1 MB an invoice); keep the worker's memory limit above the main process (about 160 MB) plus concurrency × this |
| `SLOW_REQUEST_SECONDS` | `2` | a request slower than this is logged as a warning |
| `LOG_JSON` | `1` with `DEBUG=0` | also gunicorn's own lines (`0`: text) |

Fixed in the code (change them there, with their tests):

| Value | Where |
|---|---|
| Razorpay 3 s to connect, 10 s per read; no SDK retries | `shop/payments.py` `TIMEOUT` |
| MSG91 3 s to connect, 10 s per read or write; 3 retries in the task | `ops/sms.py` |
| boto3 (buckets, SES) 3 s to connect, 20 s per read (SES 10 s), three tries in standard mode; anymail's HTTP backends (3, 10) | `settings.py`, the resilience block |
| Firebase 20 s | `learn/tasks.py` |
| Shiprocket and ERPNext 5 s and 20 s (`INTEGRATIONS_CONNECT_TIMEOUT`, `INTEGRATIONS_READ_TIMEOUT`), the quote 3 s | settings (existing) |
| The cache's Redis: 1 s per call, then 5 s of misses after a failure | `REDIS_CACHE_OPTIONS`, `examleaf/cache.py` |
| The queue's Redis: 2 s per call, one publish retry | `CELERY_BROKER_TRANSPORT_OPTIONS`, `CELERY_TASK_PUBLISH_RETRY_POLICY` |
| The providers' share: half a process's threads | `examleaf/bulkhead.py` |
| Celery: acks late, prefetch 1, 270/300 s, PDFs 60/90, long jobs 1500/1800, clips 3500/3600, visibility timeout 7200 s, results 7 days | settings, `examleaf/celery.py` |
| A search: five words of 50 characters; a page 200; a product's reviews 200 | `api/filters.py`, `api/pagination.py`, `api/shop.py` |
| Bodies 1 MB, files over 2.5 MB to disk, 10 files, 1000 fields | settings (existing) |

## The pooler and the connections

The statement limits travel as libpq's startup `options`: they apply where Django connects straight to PostgreSQL
(compose, the chart without its pooler, the migrations' init container). **Through PgBouncer in transaction mode**
(values-ha.yaml's CloudNativePG Pooler) startup options are refused or dropped and a `SET` would pass to the next
client of the server connection, so Django sends none there (it knows the pooler by its URL's
`disable_server_side_cursors`, which transaction pooling needs anyway). The limits then belong to the pooler: its
`query_timeout` and `idle_transaction_timeout` (`postgres.pooler.parameters`; one value for every client, so the
workers' 600 s), or, for the web's tighter 15 s, database roles of their own for the web and the workers with the
limits set on each (`ALTER ROLE examleaf_web SET statement_timeout = '15s'`; PgBouncer pools by role, so each
role's server connections keep its settings).

Connections: one per gunicorn thread and Celery process, kept up to `CONN_MAX_AGE`: web pods × `WEB_CONCURRENCY` ×
`GUNICORN_THREADS` + every worker's concurrency + beat + the jobs. Straight to PostgreSQL, the chart's autoscaler at
its maximum (4 × 3 × 8 = 96, plus about 5) passes the default `max_connections` of 100: raise it
(`postgres.parameters`) or use the pooler, which holds 25 server connections per pooler pod.

## What the Kubernetes chart must change

For the packaging agent (`deploy/kubernetes/examleaf-platform`):

1. **Liveness: `httpGet /health/live/`** with the same `Host` and `X-Forwarded-Proto: https` headers as the readiness
   probe, `periodSeconds: 20`, `timeoutSeconds: 5`, `failureThreshold: 3`, instead of `tcpSocket` (gunicorn's main
   thread accepts connections even when every worker thread is stuck). It reads neither the database nor Redis.
2. **Readiness**: the chart moved it to a static file; `/health/web/` now checks only the database (`SELECT 1`) and
   the migrations, no cache and no storage, results kept 20 s per process: the chart can switch back to it to take a
   pod whose own path to the database is broken out of traffic (with the pooler, a failover then shows as unready
   pods after 30 s, which the static file avoids: the chart's choice). The CronJob smoke test keeps `/health/`.
3. **`web.gunicornArgs`** can be emptied: `gunicorn.conf.py` sets the worker class, threads and timeout (the image's
   command runs it, with `preload_app`); if kept, its values must agree with the file (a test checks `--worker-class`,
   `--threads`, `--timeout`); `--no-control-socket` is in the file too. The chart's appended `--graceful-timeout 60`
   wins over the file's 30, which is fine with its grace of preStop + 60 + 5. web.yaml's comment on the image's
   command (`gunicorn examleaf.wsgi --bind … --max-requests 1000 …`) is now `gunicorn --config gunicorn.conf.py
   examleaf.wsgi`.
4. **The new variables** in `config` (all optional, defaults above): `GUNICORN_THREADS`, `GUNICORN_TIMEOUT`,
   `GUNICORN_GRACEFUL_TIMEOUT`, `GUNICORN_KEEPALIVE`, `GUNICORN_MAX_REQUESTS`, `GUNICORN_MAX_REQUESTS_JITTER`,
   `DB_CONNECT_TIMEOUT`, `DB_STATEMENT_TIMEOUT`, `DB_IDLE_IN_TRANSACTION_TIMEOUT`, `CELERY_WORKER_MAX_TASKS_PER_CHILD`,
   `CELERY_WORKER_MAX_MEMORY_PER_CHILD`, `SLOW_REQUEST_SECONDS`. The media worker's own environment needs none (its
   defaults are the Celery role's).
5. **Grace periods**: as the chart has them now (web: preStop 10 s + graceful 60 s + 5; the worker 330 s over the
   300 s hard limit; the media worker 3630 s over a clip's 3600 s) they let every task finish on a warm shutdown. A
   pod killed anyway leaves its task to Redis's visibility timeout (two hours, above them all).
6. **Memory**: the worker's 768Mi limit holds the main process (about 160 MB) and two processes up to the 300 MB
   recycling threshold; keep it at least that if `concurrency` or `CELERY_WORKER_MAX_MEMORY_PER_CHILD` grows.
7. **PostgreSQL's `max_connections`** before the web autoscaler's maximum (previous section).
8. **The PgBouncer Pooler** (values-ha.yaml): Django sends it no statement limits; set `query_timeout` and
   `idle_transaction_timeout` in `postgres.pooler.parameters` (600 s, the workers'), or roles of their own for the web
   and the workers with the limits on each (previous section).
9. The image sets `XDG_CACHE_HOME=/tmp/.cache` (fontconfig's cache, on the `/tmp` emptyDir): nothing to do.

## Deferred

| What | Why not now |
|---|---|
| An `Idempotency-Key` header for checkout | the cart's lock makes a cash-on-delivery checkout sent twice place one order; an online one sent twice makes a second order awaiting payment, which charges nothing and expires after two days. Worth it when the app ships (its retries) |
| The frontend forwarding `X-Request-ID` and a timeout on its server-side fetches | the frontend's code: each of its calls to Django gets a new request id, and only its health check has a timeout (2 s) |
| A sweep for panel jobs left "running" by a lost worker | past the soft limit a job now ends failed; one whose worker died (a pod killed, out of memory) stays "running" until staff look: a change to the staff app's job lifecycle, for its owner |
| Inline retries with eager tasks | without a broker (development) a task's autoretry runs again at once inside the request (an SMS: up to 4 × 13 s); production always has a broker, and the broker-down fallback calls the task once |
| An upstream response timeout in Caddy or Traefik | every call Django makes is bounded now; a proxy timeout would answer 504 while the work goes on |
| The audit chain's head row lock | every audited event takes one row's lock until its transaction commits (the chain needs the order); no audited transaction calls a provider while it holds it. A ceiling at many audited writes a second |
| The Razorpay SDK's `print()` on a timeout | "Request timed out." on stdout, not JSON: the SDK's own |
| The Markdown renderer's cache | per process, 20,000 texts at most (a few tens of MB); a shared cache when the content grows |
| `preload_app` under load | added after the load test (the chaos run's finding); its precondition is tested, the recycling gap not measured again here |
| The web's 15 s statement limit behind the pooler | needs the chart's roles of their own (web, workers); until then the pooler's single `query_timeout` |
| A task that kills its process: the worker without a database | the bound needs the result backend (django-db), which every worker has; a worker given no database would loop as before |
