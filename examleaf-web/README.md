# ExamLeaf web

The website behind the ExamLeaf Sample Papers books. The solutions are not printed in the books: every paper carries a
QR code that opens `/s/<CODE>/` (e.g. `/s/PHY-E01/`), where a registered student reads the full marking-scheme
solutions for free and can save the marks scored. Now: Class 12, Assam board (ASSEB), Physics, Chemistry,
Mathematics and Biology, 30 papers each (E01–E10 Easy, M01–M10 Medium, H01–H10 Hard).

Django 6.1 · Python 3.14 · server-rendered templates · one hand-written CSS file (`static/css/site.css`), no build step ·
KaTeX from jsDelivr for the `$…$` maths · no trackers, analytics or ads.

## Set up and run (development)

```sh
cd examleaf-web
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env                      # DEBUG=1, SQLite, console email
.venv/bin/python manage.py migrate
.venv/bin/python manage.py import_papers --all
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver      # http://localhost:8000 · admin at /admin/
```

In development the verification code and password-reset emails are printed in the runserver console.
The debug toolbar is on when `DEBUG=1` (not during tests).

## Importing the papers

```sh
.venv/bin/python manage.py import_papers --root "/Users/chinmoybhuyan/Desktop/Personal/Book/Class 12" --subject physics
.venv/bin/python manage.py import_papers --all          # --root defaults to the folder above examleaf-web (BOOK_ROOT)
```

The command creates the board ASSEB (Assam), Class 12, the subject and its book, and reads
`production/<subject>/papers_md/<CODE>-<T><NN>.md` and `-solutions.md` with `parse_paper`, `parse_solutions` and
`split_marks` from `production/build/book.py` (imported by path, not copied). Question labels are derived from the
paper's structure the way the solutions file names them: `9`, `1(a)`, `9 OR`, `B9(a)`/`Z3 OR` (Biology's Botany and
Zoology parts), and the plain numbered sections of Mathematics papers 08–10. A lettered line under a numbered
question that is not a group heading is a sub-part of that question (Chemistry table questions). Chapter and textbook
section tags come from the work orders (`production/<subject>/orders/ch*.md`).

It reports, per subject, papers, questions, solutions matched, tags, created/updated/unchanged records, and lists every
solution label it could not match and every question without a solution (it exits with an error if there are any).
Re-running it changes only what changed in the Markdown, so the edit history stays meaningful.
Current result: 30 papers per subject; Physics 1650, Chemistry 1260, Mathematics 1383, Biology 1590 questions,
every one with its solution and tags; 0 unmatched.

## QR codes

- `/qr/<CODE>.png` — the QR image for a paper; it encodes `SITE_URL + /s/<CODE>/`.
- `.venv/bin/python manage.py export_qr --out qr/` — all papers as `<CODE>.png` and `<CODE>.svg` (37 mm square in the SVG).

Set `SITE_URL` to the real domain before exporting codes for print: `export_qr` refuses to write codes for `localhost`
or a plain-http address (a printed book cannot be corrected), unless you pass `--force` for a test run.
`/s/phy-e01/` redirects to `/s/PHY-E01/`.

## Pages

| URL | Page |
|---|---|
| `/` | the four books |
| `/books/<slug>/` | a book's 30 papers by tier (`physics-2027`, `chemistry-2027`, `mathematics-2027`, `biology-2027`) |
| `/s/<CODE>/` | QR landing page: register / log in (returning here via `next`) for visitors, the solutions for students |
| `/account/signup/` (`/account/register/` redirects), `/account/login/`, `/account/logout/`, `/account/password/change/`, `/account/password/reset/` | django-allauth |
| `/account/record/` | My record: attempts, filter by subject and tier, average per tier; add from a solutions page, edit from here |
| `/privacy/`, `/about/`, `/sitemap.xml`, `/admin/` | |

Registration asks for full name, email, password, class, board, district (optional) and date of birth, and a consent
box (agreement to the privacy notice, linked beside it) that everyone must tick; its time is stored in `consent_at`.
Under 18 it also requires a parent's or guardian's name and phone or email, and the parent ticks the box; for adults no
parent data is asked, validated or kept. The email address is confirmed with a code typed on the same page, then the
student lands back on the paper whose QR code was scanned. The consent is self-declared: nothing verifies that the
person who ticked it is the parent (see the notes under Production).

## Tests

```sh
.venv/bin/python manage.py test              # 33 tests, about 30 s (imports all four subjects once)
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
```

They cover the import of the four subjects (30 papers each, every solution matched, re-import changes nothing), the QR
landing redirect, the gated solutions page and log-in returning to it (and never to another site), the QR image and
the QR export guard, registration (under 18: missing parent details, bad parent contact, consent → emailed code → back
on the paper; adults: consent required, no parent data kept), the Markdown renderer (HTML and attribute break-out in
content, maths left for KaTeX), query counts of the solutions and My record pages, the Content-Security-Policy and
private caching of the paper page, axes (lock-out after 10 failures, no log of good logins) and recording attempts.

## Production

Set environment variables (see `.env.example`): `DEBUG=0`, `SECRET_KEY`, `ALLOWED_HOSTS`, `SITE_URL`
(https), `DATABASE_URL` (e.g. `postgres://…`; psycopg is installed), `EMAIL_BACKEND` plus `ANYMAIL_*` for the email
provider (django-anymail, e.g. `anymail.backends.brevo.EmailBackend` and `ANYMAIL_BREVO_API_KEY`),
`DEFAULT_FROM_EMAIL`, `PROXY_COUNT` behind a load balancer (without it the site sees plain http behind the proxy and
the HTTPS redirect loops), and `CACHE_URL` (e.g. Redis) when running several workers so that rate limits are shared.
With `DEBUG=0` the session and CSRF cookies are `Secure`, `SECURE_SSL_REDIRECT` is on and HSTS is sent for a year
(`SECURE_SSL_REDIRECT=0` / `SECURE_HSTS_SECONDS=…` change that; `SECURE_HSTS_INCLUDE_SUBDOMAINS` and `SECURE_HSTS_PRELOAD`
stay off until you are sure of every subdomain, which is why `check --deploy` still prints W005 and W021).
A Content-Security-Policy allows scripts, styles and fonts only from the site and from the KaTeX folder on jsDelivr
(`KATEX_CDN` in `settings.py`; change it together with `templates/solutions.html`); in development it is report-only and
the browser console lists violations. django-axes keeps only failed log-ins (address and browser, needed for the 15-minute
lock-out); run `python manage.py axes_reset` from a daily cron job so that they do not pile up.

```sh
python manage.py migrate && python manage.py collectstatic --noinput && python manage.py import_papers --all
gunicorn examleaf.wsgi
```

Static files are served by WhiteNoise (hashed and compressed). Upload size is not limited anywhere yet because no
student upload exists; Django keeps the first 2.5 MB in memory, and the answer-sheet upload view must add a size check
(and the reverse proxy a body limit) when it is built. Uploaded files (answer-sheet photos, later) go to
`media/`, which is deliberately not served publicly; set `MEDIA_BUCKET` (and `MEDIA_ENDPOINT_URL`, `pip install
boto3`) to keep them in a private S3-compatible bucket through django-storages.

## Data model

- `accounts.User` — email login; full name, phone (optional), class (10/12), board, district, date of birth,
  parent's name and contact (under 18 only), `consent_at`; created/modified.
- `content` — `Board` → `ClassLevel` → `Subject` (PHY/CHE/MAT/BIO) → `Book` → `Paper` (code, tier E/M/H, number,
  marks, time, `header_json` with the instruction lines and allotment tables, `is_published`) → `Question` (order,
  label, part and group headings, `text_md`, `options_json`, `marks_text`, `is_alternative`, `table_md`, tags) →
  `Solution` (`body_md`, the solution block as written: step table, Final answer, Also accepted, Diagram expected).
  The Markdown is stored and rendered at display time by the `markdown` template filter (markdown-it-py, cached).
  Book, Paper, Question and Solution keep a full edit history (django-simple-history).
- `practice.Attempt` — a student's marks, time and notes for a paper. `practice.AnswerSheetUpload` — photo, status
  (pending/processing/checked/failed) and `result_json`; model and admin only, no checking logic yet.

## Planned extensions (not built)

- **Question banks**: questions already carry chapter and section tags; a bank is a filtered list of `Question`s
  (by subject, chapter tag, marks), and new bank-only questions can live in papers that are not published.
- **15-minute revision videos**: a `Video` model linked to a subject and chapter tag, shown on the book page and
  next to tagged questions.
- **AI checking of photographed answer sheets**: an upload view creating `AnswerSheetUpload`, a background worker that
  reads the photo, compares each answer with the `Solution` step table and writes marks per step to `result_json`,
  and a result page; the status field already models the queue.
- **Class 10 and other boards**: new `Board`/`ClassLevel`/`Subject`/`Book` rows; the importer takes the board from
  its arguments once a second board exists.

## Libraries

| Library | Purpose |
|---|---|
| Django 6.1 | the framework: ORM, admin, auth, forms, generic views, messages, sitemaps, password validators, security middleware |
| django-environ | settings from environment variables / `.env`: `DATABASE_URL`, `CACHE_URL`, lists and booleans |
| whitenoise | serves static files, hashed and compressed, in production |
| gunicorn | WSGI server for production |
| psycopg[binary] | PostgreSQL driver (production database) |
| django-allauth | registration, email login, email verification by code, password change and reset, built-in rate limits |
| django-axes (with django-ipware) | records failed logins and locks an account for 15 minutes after 10 failures from one address |
| django-anymail | sends email through a transactional email provider in production (console backend in development) |
| django-model-utils | `TimeStampedModel` (created/modified) and `StatusModel` for the answer-sheet status |
| django-simple-history | audit trail of edits to books, papers, questions and solutions (admin History button) |
| django-taggit | chapter and textbook-section tags on questions |
| django-widget-tweaks | template-level attributes for the My record filter form |
| django-phonenumber-field (phonenumberslite) | phone field and validation of Indian numbers (region IN) for the parent's contact |
| django-import-export | CSV export of users and attempts from the admin |
| django-filter | the subject/tier filter on My record |
| django-qr-code (segno) | generates the QR images (PNG for `/qr/<code>.png`, PNG and SVG for `export_qr`) |
| django-storages | optional private S3-compatible storage for uploaded answer sheets (local files by default) |
| django-debug-toolbar | development only, when `DEBUG=1` |
| markdown-it-py | Markdown (with tables) to HTML for questions and solutions |
| Pillow | image support for the answer-sheet `ImageField` |
| KaTeX 0.19 (jsDelivr CDN, with SRI) | renders the `$…$` maths in the browser |

django-crispy-forms was considered but has no plain-CSS template pack (only Bootstrap/Tailwind/Bulma add-ons);
forms are rendered by Django's own form templates and allauth's elements instead.
