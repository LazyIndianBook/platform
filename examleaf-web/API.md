# ExamLeaf API (v1)

The REST API behind the ExamLeaf app: the public catalogue (boards, subjects, books, papers), the solutions (for a
signed-in student with a confirmed email address, as on the website), the student's record of attempts, and the
account with its data rights (Download my data, Delete my account). Code: `api/`, settings: `examleaf/api_settings.py`,
URLs: `examleaf/api_urls.py`.

- Base URL: `https://<domain>/api/v1/`. Every path ends with `/`; a path without it answers 404 (no redirect).
- JSON only, both ways (`Content-Type: application/json`); anything else gets 415 (request) or 406 (`Accept`).
- Dates are ISO 8601, times with the Indian offset (`2026-10-15T10:00:00+05:30`); marks are decimal strings (`"52.5"`).
- OpenAPI 3 schema: `/api/schema/` (YAML; `?format=json` for JSON). Swagger UI: `/api/docs/`. Redoc: `/api/redoc/`.
  Both pages are served by the site itself (drf-spectacular-sidecar), so the Content-Security-Policy stays strict.
- `X-Request-ID`: send a UUID and it comes back in the response and in the server's log lines (otherwise the server
  makes one). Quote it when reporting a problem.

## Authentication from the app

The app uses JWT: a short-lived **access** token in every request (`Authorization: Bearer <access>`) and a
long-lived **refresh** token to get new ones. The website's own pages can call the API with their session cookie
instead (with the `X-CSRFToken` header on POST, PUT, PATCH and DELETE).

| Token | Lifetime | Setting |
|---|---|---|
| access | 15 minutes | `JWT_ACCESS_MINUTES` |
| refresh | 30 days | `JWT_REFRESH_DAYS` |

**Sign up** with the same fields and rules as the website's form: class (10 or 12), board (an id from `boards/`),
date of birth, and the consent box (`consent: true`) for everyone; under 18 also a parent's or guardian's name and
phone or email (the parent ticks the consent). The answer carries a `verification_token`; a code (`ABCD-EFGH`) is
emailed. Signing up with an address that already has an account gets the same answer (its owner gets an email), so
nobody can find out who is registered.

```sh
curl -X POST https://examleaf.in/api/v1/auth/registration/ -H 'Content-Type: application/json' -d '{
  "full_name": "Rahul Das", "email": "rahul@example.com",
  "password1": "Brahmaputra-2027", "password2": "Brahmaputra-2027",
  "class_level": 12, "board": 1, "district": "Kamrup", "date_of_birth": "2010-05-14",
  "parent_name": "Anita Das", "parent_contact": "98640 12345", "consent": true}'
# 201 {"detail": "Verification e-mail sent.", "verification_token": "q3k9w0d8m2..."}
# 400 {"parent_name": ["Required for a student under 18."], "parent_contact": ["Required for a student under 18."]}
```

**Confirm the address** with the token and the code. The answer is the same as a log-in: tokens and the profile.
Three wrong codes, or 15 minutes, end the token: then log in again for a new code.

```sh
curl -X POST https://examleaf.in/api/v1/auth/registration/verify-email/ -H 'Content-Type: application/json' \
  -d '{"verification_token": "q3k9w0d8m2...", "code": "ABCD-EFGH"}'
# 200 {"access": "eyJ...", "refresh": "eyJ...", "user": {"id": 7, "email": "rahul@example.com", "roles": ["STUDENT"], ...}}
```

**Log in** with email and password. If the address is not confirmed yet, the answer is
`400 {"detail": "E-mail is not verified.", "verification_token": "..."}` and a new code is emailed (at most one every
three minutes): show the code screen and continue with verify-email.

```sh
curl -X POST https://examleaf.in/api/v1/auth/login/ -H 'Content-Type: application/json' \
  -d '{"email": "rahul@example.com", "password": "Brahmaputra-2027"}'
# 200 {"access": "eyJ...", "refresh": "eyJ...", "user": {...}}
```

**Refresh** when a request answers 401 with `"code": "token_not_valid"` (or a little before the access token runs
out). Every refresh returns a **new refresh token** and the old one stops working: always store the new one, and
send one refresh at a time.

```sh
curl -X POST https://examleaf.in/api/v1/auth/token/refresh/ -H 'Content-Type: application/json' -d '{"refresh": "eyJ..."}'
# 200 {"access": "eyJ...", "refresh": "eyJ..."}      401: log in again
```

**Log out** by sending the refresh token, which is then refused for good; forget both tokens in the app.

```sh
curl -X POST https://examleaf.in/api/v1/auth/logout/ -H 'Content-Type: application/json' -d '{"refresh": "eyJ..."}'
```

**Passwords.** `auth/password/change/` (signed in: `old_password`, `new_password1`, `new_password2`) and a password
reset ends every token of the account, on every device: log in again afterwards. The owner is told by email, as on the
website. `auth/password/reset/` (`email`) always answers 200 and emails a link to the website's "new password" page,
`<SITE_URL>/account/password/reset/key/<uid>-<token>/`; an app that opens such links itself can post `uid`, `token`,
`new_password1` and `new_password2` to `auth/password/reset/confirm/`. When an account deletion is carried out
(seven days after the request), every token of the account ends too.

Log-in, log-out, sign-up, verify-email and password reset ignore the `Authorization` header, so an expired token left
in it does no harm there.

## Endpoints

| Method and path | Who | What |
|---|---|---|
| `POST auth/registration/` | anyone | sign up; emails a code |
| `POST auth/registration/verify-email/` | anyone | the code; returns the tokens |
| `POST auth/login/`, `auth/logout/` | anyone | tokens in, refresh token out |
| `POST auth/token/refresh/`, `auth/token/verify/` | anyone | new tokens; check a token |
| `POST auth/password/reset/`, `auth/password/reset/confirm/` | anyone | forgotten password |
| `POST auth/password/change/` | signed in | new password |
| `GET PUT PATCH me/` | signed in | profile; changeable: `full_name`, `phone`, `class_level`, `board`, `district` |
| `POST me/export/` | signed in | Download my data (`password`): everything kept about the user |
| `POST DELETE me/deletion/` | signed in | Delete my account (`password`), due in 7 days; DELETE cancels |
| `GET boards/`, `subjects/` (`?board=`) | anyone | the boards and subjects |
| `GET books/`, `books/<slug>/` | anyone | books with their papers (`code`, `tier`, `number`, `title`, `is_published`) |
| `GET papers/`, `papers/<code>/` | anyone | paper details: marks, time, instructions, `web_url`, `solutions_url` |
| `GET papers/<code>/solutions/` | signed in, email confirmed | the questions in order, each with its solution |
| `GET qr/<code>/` | anyone | a scanned code (any case) to its paper and `solutions_url` |
| `GET POST attempts/`, `GET PUT PATCH DELETE attempts/<id>/` | signed in, email confirmed | the student's own record |
| `GET health/` | anyone | the same checks as `/health/` (`?format=json`) |

Only published papers appear, as on the website. The email address, date of birth and parent details are read-only
here (the email changes on the website, after a code; the others decide the consent rules). The QR codes in the books
encode `<SITE_URL>/s/<CODE>/`: the app reads the code from the scanned address and asks `qr/<code>/`.

```sh
curl https://examleaf.in/api/v1/books/physics-2027/
curl 'https://examleaf.in/api/v1/papers/?subject=1&tier=H&ordering=number'
curl -H "Authorization: Bearer $ACCESS" https://examleaf.in/api/v1/papers/PHY-E01/solutions/
```

A question of `solutions/` (Markdown with `$…$` maths; `solution.html` is rendered by the site, with the maths left
for KaTeX; `is_alternative` marks the OR choice of the question before it; `number` is what the book prints):

```json
{"order": 17, "label": "2(b)", "number": "2(b)", "part_label": "",
 "group_label": "2. Answer any ten questions from the following as directed : `2×10=20`", "is_alternative": false,
 "text": "Give reason why the potential energy of a system of two positive point charges is always positive.",
 "table": "", "options": [], "marks": "2",
 "solution": {"markdown": "| Step | Marks |\n|---|---|\n| The charges repel each other, ... | 1 |\n...",
              "html": "<div class=\"table-scroll\"><table class=\"steps\">..."}}
```

Attempts: `paper` (code, published papers only), `marks_obtained` (0 to the paper's full marks, halves allowed),
`date` (default today), `time_taken_minutes`, `notes`; the answer adds `subject`, `tier`, `full_marks`, `percent`.
The paper of an attempt cannot change. Filters: `?subject=<id>&tier=E|M|H`.

```sh
curl -X POST https://examleaf.in/api/v1/attempts/ -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"paper": "PHY-E01", "marks_obtained": "52.5", "time_taken_minutes": 170, "notes": "revise optics"}'
curl -X POST https://examleaf.in/api/v1/me/deletion/ -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"password": "Brahmaputra-2027"}'
# 201 {"status": "pending", "requested_at": "...", "due_at": "..."}
```

Teachers cannot see their students' attempts yet: nothing links a student to a teacher (see the TODO in `api/views.py`).

## Lists

Lists are paginated: `{"count": 120, "next": "<url>", "previous": null, "results": [...]}`, 50 a page,
`?page=2`, `?page_size=` up to 200. `?search=` searches books (title, subject) and papers (code, title);
`?ordering=` sorts (`-number` for descending): papers by `code`, `number`, `tier`; books by `id`, `title`; attempts by
`date`, `marks_obtained`, `created`. Filters: papers `?book=<slug>&subject=<id>&tier=`, books `?subject=<id>`,
subjects `?board=<id>`. The catalogue is cached on the server for 15 minutes.

## Errors

DRF's standard format, always JSON:

| Status | Body |
|---|---|
| 400 | the fields' errors: `{"marks_obtained": ["Enter marks from 0 to 70."]}`; others under `non_field_errors` |
| 401 | `{"detail": "Authentication credentials were not provided."}`; a bad or expired token adds `"code": "token_not_valid"` |
| 403 | `{"detail": "Confirm your email address first."}` (or another reason) |
| 404 | `{"detail": "No Paper matches the given query."}`, `{"detail": "Not found."}` |
| 405, 406, 415 | `{"detail": "..."}` |
| 429 | `{"detail": "Request was throttled. Expected available in 38 seconds."}` with a `Retry-After` header |
| 500 | the site's error page; reported to Sentry with the request ID |

## Rate limits

Counted in the cache (Redis in production), per client address for anonymous requests and per user once signed in:

| Scope | Default | Setting |
|---|---|---|
| anonymous | 200 a minute | `API_THROTTLE_ANON` |
| signed in | 600 a minute | `API_THROTTLE_USER` |
| log-in, log-out, sign-up, codes, passwords, data export, deletion | 30 a minute | `API_THROTTLE_AUTH` |

A whole classroom often shares one address: raise the limits rather than lower them. django-axes still locks an
account for 15 minutes after 10 failed log-ins from one address, through the API too.

## CORS

None is needed by the app or the website. A web client on another origin must be listed in `CORS_ALLOWED_ORIGINS`;
only `/api/` answers CORS requests, without cookies (send the access token).

## Versioning

The version is in the path (`/api/v1/`). Within v1, changes only add: new endpoints, new fields in answers, new
optional parameters; clients must ignore fields they do not know. Removing or renaming a field, changing a type or a
meaning, or a new required parameter makes a v2, served beside v1 until the app versions that use v1 are retired (at
least six months, announced in the app). `ALLOWED_VERSIONS` in `examleaf/api_settings.py` lists the versions served.

## Operations

- Refresh tokens and their blacklist are kept in the database; `api.tasks.flush_expired_tokens` (celery beat, 04:30,
  editable in the admin under Periodic tasks) deletes the expired ones.
- The tokens are signed with `SECRET_KEY`: rotating it logs every app out (and every website session).
- Tests: `api/tests.py` (sign-up rules, codes, tokens, gated solutions, attempts, data rights, query counts,
  limits, CORS, schema validity). `manage.py spectacular --validate --fail-on-warn --file schema.yml` checks the schema.
