# Package P14: Security review of Phase B's authorization (model: Claude Opus 5.5)

Ports: Django 8122 if you need a server (you should not). Read COMMON.md sections 1 to 4 and 7 first. Your worktree
is a checkout of the `phase-b` integration branch with every Phase B module merged. Plan section 9.2's security exit
criteria are the deliverable: "an access-log event for every person lookup and every view of a child's record; reveal
and export throttles; step-up on every money, role, key and export action, each with a test; a review of the
authorization tests against OWASP API1, API3 and API5." Research: `research-rbac-security.md` 1.1, 1.4, 1.5, 1.7,
1.9, 2.4, 2.5, 4.3, 5; `staff/README.md` in full; `staff/tests/test_matrix.py`; every `staff_api.py`,
`privacy_api.py`, `customers_api.py`, `system_api.py`, `support/api.py`, `integrations/api.py`, `ops/staff_api.py`,
`insights/staff_api.py` and the public endpoints Phase B added (`api/` for returns, reports, tickets, nominee,
config, pages' versions, the webhooks under `/api/hooks/`).

Review, then fix, then test. For every finding: fix it in the code, add the test that fails without the fix, and
record it in `docs/security/phase-b-authorization-review.md` (what was checked, how, what was found, what changed).

1. **API1, broken object-level authorization**: for every endpoint with an object in its path (every `{id}`,
   `{number}`, `{slug}`, `{code}`, `{label}`), a test that a member of staff whose scope does not reach the object
   (a CONTENT_EDITOR of another subject, a PACKER on a pending order, a SUPPORT member on a record that `scoped()`
   excludes) gets 404 and not the object, and that a customer-facing endpoint never answers another customer's
   object (returns, tickets, the nominee, `me/…`). Write the test as one parametrised table like the matrix
   (`staff/tests/test_objects.py`) over every endpoint that takes an object, with a factory per object kind; every
   endpoint of Phase B appears in it (assert the table covers every object path the URL walk finds, as
   `test_every_endpoint_names_a_catalogued_permission…` does).
2. **API3, excessive data exposure and mass assignment**: every serializer explicit (no `fields = "__all__"`; a
   test that walks every serializer class under the staff and public APIs), no personal field answered where the
   plan says masked (emails, phones, addresses, dates of birth, parents' contacts: a test that the list and record
   answers of every customer-related endpoint contain no raw email or phone of the fixture unless revealed), write
   serializers that refuse unknown fields where the record is sensitive (`is_staff`, `is_superuser`, roles, limits,
   `livemode`, numbers, hashes: a test that a PATCH with such a field is refused or ignored and audited), secrets
   never answered (credentials, tokens, keys: masked everywhere including audit `changes` and the mock).
3. **API5, broken function-level authorization**: the matrix covers every endpoint (assert the URL walk and the
   matrix tables agree: no endpoint outside the tables); every GET names a `view_` permission; the API-key path
   (`ApiKeyAuthentication`) refused on human-only actions (`self.human()`) and tested; `ADMIN_HOSTS` 404 for every
   new prefix (a test over the walk); the public endpoints Phase B added have throttles, Turnstile where the plan
   says, CSRF on session-authenticated ones, and no staff data.
4. **Step-up**: every money, role, key, export, erasure, void, cancel-document and credential action answers
   `reauthentication_required` to a session authenticated an hour ago and succeeds to a fresh one: a parametrised
   test over the catalogue's high and critical permissions crossed with the endpoints that name them (derive the
   list from the catalogue and the URL walk, so a new high action without the step fails the test).
5. **Throttles**: reveals, exports, bulk actions, customer searches, code lookups, the public report and ticket
   endpoints, each answering 429 at its limit in a test, with the limits sensible (`REST_FRAMEWORK` rates) and
   documented.
6. **The access log**: every lookup of a person (`q` on users, orders, tickets, entitlements, the command palette's
   search endpoint if there is one) writes `customer.lookup` with a hash, and every view of a child's record (the
   customer record, its timeline, a minor's order, ticket, learner page) writes `sensitive_read` with `child: true`:
   one parametrised test over those endpoints.
7. **Audit completeness**: every state-changing endpoint of Phase B writes an audit event with the target and no
   personal data in `details` (a test that walks the matrix's POST/PUT/PATCH/DELETE rows as an OWNER with a valid
   body where one is simple, and asserts an event per success; where a body is not simple, list the endpoint in a
   table of hand-written cases).
8. **The approval paths**: each new `approvals.Action` has a test that the maker cannot approve, the checker needs
   the payload's hash, execution re-checks preconditions, and an expired request refuses.
9. **Webhooks and inbound endpoints**: constant-time comparisons (`hmac.compare_digest`), the previous token
   accepted only within its overlap, replayed events deduplicated, oversized bodies refused (Caddy's limit and a
   Django check), no exception leaking into the answer.
10. **Headers**: `no-store` on every staff answer (a walk), the CSP and `frame-ancestors` unchanged, `noindex` on
    the new public pages of the site (`/account/requests/`), the console's new pages private.

Fix what you find with the smallest correct change in the shared place (the base class, the helper), never per
endpoint when a base fix covers all. Keep the whole backend suite green (SQLite), ruff clean, migrations clean. Commit
per finding with the `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` trailer. Your report: the findings
table (severity, endpoint, what, the fix, the test), the counts of the new parametrised tests, and what you judged
acceptable and why.
