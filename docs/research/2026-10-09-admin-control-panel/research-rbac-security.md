# ExamLeaf Admin Control Panel: RBAC, admin security, audit, Indian data-protection law, user and staff management

Research input for the plan. Sources were read on 2026-10-09.

- `[n]` is a citation; the numbers are listed in `sources-rbac-security.md`.
- `ASVS x.y.z (Ln)` is an OWASP ASVS 5.0.0 requirement and its level [28].
- "Repo" means examleaf-web as read today [62].
- Thresholds such as ₹ caps and row counts are placeholders for the owner to set.

## 0. Key findings

1. **The DPDP timeline is fixed in the gazette.** The DPDP Rules are G.S.R. 846(E), gazette dated 13 Nov 2025 (PIB gives 14 Nov) [2][3]. Their commencement is in three steps [2 r.1]:
   - Rules 1, 2 and 17–21 (the Board) are in force now.
   - Rule 4 (consent managers) starts about 13 Nov 2026.
   - Rules 3 and 5–16, 22–23 start about 13 May 2027. They cover notice, security, breach, retention, children, rights, SDFs and cross-border transfer.

   The Act's core sections 3–17 also start at 18 months, under G.S.R. 843(E); that split comes from a secondary source [6]. Until then IT Act s.43A and the SPDI Rules 2011 apply [9][12].

   Two points are uncertain. MeitY's proposal of 23 Jan 2026 to shorten the window to 12 months, mainly for SDFs, has not been notified as far as I could find [7][8]. The Board still had no Chairperson or Members on 1 Aug 2026 [8]. Plan for 13 May 2027, but build so the date could be met earlier.
2. **CERT-In's 2022 Directions are in force today** [10][11]. They require four things:
   - report listed incidents within 6 hours;
   - keep 180 days of ICT logs, rolling;
   - sync clocks to NIC/NPL NTP servers;
   - name a point of contact.

   The repo keeps far less [62]: Docker logs of 10 MB × 5 per service, webhook records for 7 days, the SMS log for 90 days, and device rows only until the night after the session ends. That is already short of the 180 days for logs. From May 2027 it is also short of the DPDP minimum of 1 year for logs and processing records (r.6(1)(e), r.8(3)) [2].
3. **Parental consent needs an age check by May 2027.** Rule 10 requires checking that the consenting parent is an identifiable adult [2 r.10]. The check can use reliable identity and age details already held, details the parent gives voluntarily, or a virtual token from an authorised entity (DigiLocker is named). The repo's email or SMS link proves only that someone controls the inbox, not that they are an adult; RUNBOOK already notes this limit [62].
4. **Children's data is the largest legal risk.** s.9(3) bans tracking or behavioural monitoring of children and targeted advertising directed at them [1]. The exemption for an "educational institution" (tracking for its educational activities) may or may not cover a publisher with a revision course [2 Sch.4]; that is a question for counsel. The panel should at least:
   - flag under-18 accounts;
   - keep them out of marketing segments;
   - log staff access to their records.
5. **Every personal data breach must be reported; there is no harm threshold.** Each affected person must be told without delay. The Board must be told without delay, with a detailed report within 72 hours [2 r.7]. CERT-In must be told within 6 hours [10]. Penalties go up to ₹250 crore for failed security safeguards and ₹200 crore each for a missed breach notice or a breach of the children's rules [1 Schedule].
6. **Authorization is enforced in Django on every staff API call** (ASVS 8.3.1 (L1)) [28]. Next.js receives a permission manifest only to draw the UI. Next.js Proxy (middleware) is never the gate: CVE-2025-29927 let requests skip auth checks that lived only in middleware [55][56].
7. **The authorization model has five parts:**
   - **Role:** a Django Group, defined in code as `accounts/roles.py` does today.
   - **Permission:** model permissions plus custom action permissions.
   - **Scope:** which objects, such as a subject, a school or an order state.
   - **Limit:** a ₹ cap or a row cap.
   - **Condition:** recent re-authentication, an approval, or an IP or time window.

   Django core has no object-permission implementation [40], and DRF does not apply object permissions to lists [45]. So one scoping helper must filter every staff queryset.
8. **High-risk actions are maker-checker**, meaning a second person approves. The approval is bound to the exact payload (ASVS 2.3.5 (L3), NIST AC-5, Transaction Authorization Cheat Sheet) [28][26][37]. This covers:
   - refunds above the maker's cap;
   - payouts and changes to a payee's bank account;
   - price or discount changes beyond a threshold;
   - deletion or erasure started by staff;
   - grants of privileged roles;
   - bulk operations;
   - large exports of personal data.
9. **Staff login.** MFA is already mandatory [62]. Add:
   - passkeys for owner, admin and finance (NIST AAL2 must offer a phishing-resistant option) [27][38];
   - an idle timeout (today there is only the 8-hour absolute limit);
   - step-up re-authentication through allauth's headless 401 flow [48];
   - a separate admin hostname, optionally with an IP allowlist or VPN [28 3.5.4][59].
10. **Audit needs its own log.** Add a dedicated append-only AuditLog covering reads, exports, logins and approvals, hash-chained and exported daily to a locked R2 bucket [58]. Keep simple_history for record timelines, but it misses bulk and queryset updates and its rows can be deleted [49]. In PostgreSQL the table owner can always re-grant itself rights, so the app's role must not own the audit table [57].
11. **Retention.** If ExamLeaf is a company, financial records are kept for 8 financial years (Companies Act s.128(5)), which is longer than GST's 72 months (CGST s.36) [17][15]. Their edit log is kept as long (CGST r.56(8)) [16]. Security logs must be kept at least 180 days now and at least 1 year from May 2027 [10][2].

## 1. RBAC design

### 1.1 Model and vocabulary

The NIST RBAC reference model has four parts [23]:
- **Core RBAC:** users, roles, permissions, user–role and permission–role assignment, and role activation within a session.
- **Hierarchical RBAC:** roles inherit from other roles.
- **Static Separation of Duty (SSD):** limits on which roles one user may hold.
- **Dynamic Separation of Duty (DSD):** limits on roles active together in one session or transaction.

The 2000 NIST model names four cumulative levels: flat, hierarchical, constrained and symmetric [24]. NIST grants access "only if" the role requirements are met, so further constraints, such as a relationship to the object, can be layered on top [23]. ABAC (attribute-based access control) adds attributes of the subject, the object and the environment (time, location), checked against a policy [25]; NIST has written on "adding attributes to RBAC" [22]. OWASP prefers ABAC or ReBAC (relationship-based) over pure RBAC for applications, to avoid "role explosion" [31].

An ExamLeaf decision is "allow" only if all of these hold:
- the role grants the permission (function level, ASVS 8.2.1 (L1));
- the object is in the user's scope (data level, against broken object-level authorization (BOLA): ASVS 8.2.2 (L1), OWASP API1:2023) [28][30];
- the role may see or change the field (field level, against broken object-property authorization: ASVS 8.2.3 (L2), API3:2023);
- the limits hold (₹ cap, row cap), and so do the conditions (recent re-authentication, an existing approval, an optional IP or time window); conditions must be documented (ASVS 8.1.3 and 8.1.4 (L3));
- otherwise the request is denied. Default is deny, every request is checked, and errors fail closed (OWASP A01:2025, Authorization Cheat Sheet) [29][31].

| Term | Meaning | ExamLeaf example | Where it lives |
|---|---|---|---|
| Role | A bundle for one job | Support, Packer | `accounts/roles.py` ROLES (exists) → Django Group |
| Permission | An operation on a resource type | `shop.view_order`, `shop.approve_refund` | Django Permission (default model perms + `Meta.permissions`) |
| Scope | Which instances | subject ∈ {Physics}; order status ∈ {paid, packing}; school = 42 | new `StaffScope` rows, or a role-level rule |
| Limit | A numeric bound | refund ≤ ₹2,000 without approval; export ≤ 500 rows | `ROLE_LIMITS` next to ROLES; per-user override if ever needed |
| Condition | A contextual check | re-auth within 5 min; approval exists; office IP; 08:00–20:00 IST | policy code, documented (ASVS 8.1.3) |

### 1.2 Hierarchy, SSD and DSD for a small team

- **Hierarchy.** Django groups are flat, so compose roles in code, as the repo already does by building ROLES from shared lists. Keep the tree shallow: Owner ⊃ Admin ⊃ functional roles, and Auditor = every `view_*` permission except revealing personal data. Deep hierarchies make SSD inconsistent [23].
- **SSD**, checked when a role is assigned (in `sync_roles` and in the role-grant endpoint):
  - Finance (records offline payments, refunds) ✕ Packer (marks orders shipped). This prevents one person marking an order paid and shipping it.
  - Auditor ✕ any role that can write.
  - Marketing (creates coupons) ✕ the person who approves discounts above the threshold.
- **DSD**, checked per transaction:
  - the approver of a change request is not its maker;
  - the reviewer who publishes a paper is not its last editor;
  - nobody approves a change to their own account or roles.

  See NIST AC-5 ("define system access authorizations to support separation of duties") [26] and ASVS 2.3.5 (L3) [28].
- **Small teams.** When no second person is available, allow an owner-only override. It needs a reason, sends an alert and is reviewed afterwards (§1.6). Do not allow silent self-approval.

### 1.3 Role templates

These build on the repo's existing STUDENT, TEACHER, CONTENT_EDITOR, SALES, SUPPORT and ADMIN.

| Role | Purpose | Key permissions | Scope | Limits / conditions | Notes |
|---|---|---|---|---|---|
| OWNER (founder) | Final authority | everything: grants ADMIN and FINANCE roles, approves as a last resort, exports the audit log, uses break-glass | all | passkey; idle 15 min | ideally 2 people; the superuser flag only on the break-glass account |
| ADMIN | Operations lead | today's ADMIN: everything except the SUPERUSER_ONLY apps [62]; proposes role grants, which the owner approves | all | passkey; idle 15 min | cannot approve own requests |
| FINANCE (accountant) | Money and tax | view orders, payments, invoices, credit notes; approve and run refunds; record offline payments; reconcile Razorpay; export GSTR-1; prepare payouts (maker) | all orders | refund cap; payouts always two-person; passkey | SSD with PACKER |
| CONTENT_EDITOR (editor/author) | Write content | content CRUD (book, paper, question, solution) and learn content | by subject, board and class | publishing needs a REVIEWER (if that step is turned on) | the existing role gains scopes |
| REVIEWER | Check and publish content | view content in scope; `content.publish_*`; comment | by subject | DSD: not the last editor | new role |
| SUPPORT | Help customers | view accounts (masked); reveal contact (logged); verify teachers; resend verification; unlock axes; start a password reset; end sessions; handle data requests; `learn.entitlement` (exists); request refunds (maker) | all customers | reveal rate limit; refund requests up to a cap | today's SUPPORT, without raw personal data by default |
| PACKER (warehouse) | Fulfilment | view orders that are paid, packing or shipped: items, ship-to name, address, phone; mark packed or shipped; add tracking | by order status | optional shift window and warehouse IP; idle 15 min | no email, payments or history; split out of today's SALES |
| SALES (school/B2B) | School orders, quotations | quote requests, school and phone orders, payment links | all | discount cap | today's SALES without refunds or shipping |
| MARKETING | Campaigns | coupons and offers (approval above the discount threshold); newsletters; review moderation; aggregate analytics | consented adults only | no exports of individuals; no targeting of under-18s (s.9(3)) [1] | |
| AUDITOR (read-only) | Review | every `view_*`; view and export the audit log | all | time-bound (`expires_at`); no revealing personal data; no writes | SSD with every role that writes |
| TEACHER_PARTNER (external) | A school's own data | own school's orders, book codes and pupils' entitlements | school = own (a relationship) | not `is_staff`; uses the website, not the panel | ReBAC, per OWASP [31] |
| SERVICE (integration) | Machine access | for example `orders:read`, `shipments:write`, `invoices:read` | as scoped | API key with an expiry; optional IP allowlist | never a human, never logs in to the panel (§2.6) |

### 1.4 Permission naming and grouping for the UI

- **Machine names.** Keep Django's `app_label.codename`; Django 6.1's `Permission.user_perm_str` returns exactly this string [44].
- **Action permissions.** Add the verbs that add/change/delete/view do not cover in `Meta.permissions`: `refund_order`, `approve_refund`, `record_offline_payment`, `publish_paper`, `reveal_contact`, `suspend_user`, `reset_user_mfa`, `impersonate_user`, `export_personal_data`, `assign_role`, `approve_role_change`, `view_auditlog`, `export_auditlog`, `manage_api_keys`, `replay_webhook`, `toggle_maintenance`, `break_glass`.
- **A permission catalogue in code**, next to ROLES. It gives each permission:
  - a UI label ("Approve refunds");
  - an area: Orders, Payments & refunds, Customers, Content, Catalogue, Marketing, Staff & roles, Audit, Settings, Operations;
  - a risk level: low, medium, high or critical;
  - what it triggers: re-authentication, approval, alert.

  The risk level then drives behaviour the same way everywhere, instead of each view deciding for itself.
- **Limits are attributes, not permission strings.** "Refund orders" plus `limits.refund_inr = 2000` displays as "Refund orders — up to ₹2,000 without approval". The same goes for discount %, export rows and bulk rows.
- **DRF pitfall.** `DjangoModelPermissions` lets any authenticated user make GET requests unless `perms_map` adds `view_*` [45]. Staff viewsets must require `view_*` for GET.

### 1.5 Approvals (maker-checker)

| Action | Maker | Checker | Rule |
|---|---|---|---|
| Refund above the maker's cap | Support / Finance | Finance / Owner | the approver is not the maker |
| Payout to authors or affiliates; new or changed payee bank account | Finance | Owner | always two-person; a bank-detail change has a cooling period and the payee is told |
| Price change above X% or below cost; coupon or offer above Y% | Catalogue / Marketing | Finance / Owner | |
| Deletion or erasure started by staff; account merge | Support | Admin | show a dry-run preview first |
| Granting or removing a privileged role | Admin | Owner | no self-grant |
| Bulk operations above N rows; personal-data exports above N rows; any export of children's data | anyone | Admin / Owner | |
| Resetting MFA on a staff account | Admin | Owner | identity proofing (§5) |

How it works:
- **A `ChangeRequest` model.** Fields:
  - action, and target (content type + id);
  - the payload as JSON, plus `payload_sha256`;
  - amount, maker, reason;
  - status: pending → approved / rejected / expired → executed / failed;
  - approvals: user, decision, comment, time;
  - `expires_at` (for example 24 h), the execution result, and an idempotency key.

  The repo already uses django-fsm-2 for its Order and Payment state machines; reuse it here [62].
- **What You See Is What You Sign.** The checker sees and approves the exact stored payload, and the server executes that stored payload, not a new one from the client. It first re-checks the preconditions (for example, that the order has not already been refunded). Each approval works once and expires [37]. The whole operation succeeds or rolls back (ASVS 2.3.3 (L2)) [28].
- Approving and executing both need a recent re-authentication (§2.3). Every state change is an AuditLog event.
- Standards: ASVS 2.3.5 (L3), "high-value business logic flows require multi-user approval" [28]; NIST AC-5 [26].

### 1.6 Break-glass (emergency access)

This follows NIST AC-2(2) (emergency accounts are disabled automatically), Microsoft's emergency-access guidance, and OWASP's advice to log every break-glass use [26][39][33].
- **The accounts.** One or two emergency accounts sit outside Google SSO, so they still work if Workspace is down. Each has a FIDO2 security key and a backup key, both kept offline. They are not used day to day, and they are the only superuser accounts.
- **Using one:**
  - a reason must be given;
  - the owner and the admins are alerted at once by email and SMS;
  - the elevated session is time-boxed, for example to 2 hours;
  - every action is logged with `break_glass=true`;
  - the use is reviewed within 24 hours.
- **Just-in-time elevation for ordinary staff.** A staff member requests a temporary role and gives a reason; the owner approves; `expires_at` removes the role automatically (AC-2(2)).
- **Testing.** Test the accounts every quarter; Microsoft says at least every 90 days [39]. Include the list of people who can use them in the access review.

### 1.7 Expressing permissions to the Next.js frontend

- **The manifest.** `GET /api/staff/session` (sent with `no-store`) returns:
  - the user, and their roles with expiry;
  - `permissions`: a sorted list of `app.codename` strings from `user.get_all_permissions()`;
  - scopes, limits and flags;
  - `reauth_valid_until`, `idle_timeout_s`, `absolute_expires_at`;
  - a `manifest_version` hash.

  Keep it in memory (React context), not in localStorage (ASVS 14.3.3 (L2)) [28].
- **UI only.** The UI uses the manifest only to hide or disable things, with a tooltip such as "Needs: Refund approver". Django authorizes every API call again (ASVS 8.3.1 (L1)) [28]. Refetch the manifest after any 403 or when `manifest_version` changes.
- **Next.js:**
  - use Proxy (Next 16's name for middleware) only for optimistic redirects based on the cookie;
  - do the real checks in a Data Access Layer;
  - treat Server Actions and Route Handlers as public endpoints that must check for themselves [55].

  CVE-2025-29927 let an `x-middleware-subrequest` header skip auth done in middleware. It was fixed in 15.2.3 and earlier branches, and Next 16 includes the fix [56]. Strip that header at Caddy anyway.
- **No "god token" backend-for-frontend.** The Next.js server forwards the staff member's own session to Django. It never holds an elevated service credential (ASVS 8.3.3 (L3): access is based on the originating subject) [28].
- **Role removal is immediate.** It takes effect on the next request: session auth reloads the user, and Django caches permissions only on that user object [41]. The app's JWTs carry no permissions [62]. This meets ASVS 8.3.2 (L3).

### 1.8 Showing what a role can do

- **Role catalogue page**, read-only: roles are code and are reviewed in pull requests, and the repo's `bootstrap_roles` undoes edits made in the admin [62]. For each role it shows:
  - capabilities grouped by area, with plain labels and risk badges;
  - limits and scopes;
  - SSD conflicts;
  - member count.
- **User → "Access" tab:**
  - roles, with who granted them, when, and the expiry;
  - scopes and limits;
  - the effective permission list, with the last use of each (from the AuditLog);
  - pending requests.
- **"Who can…?" lookup:** pick a permission and see the users who have it. This feeds the access reviews.
- **Role-change preview:** shows the permissions gained and lost and the required approver; an SSD conflict blocks submission.
- **Unused-permission report:** permissions not used in 90 days, per user (AC-6(7)) [26].

### 1.9 Django implementation map (minimal)

- **Keep:** `auth.Group`, `auth.Permission`, `accounts/roles.py` as the single source of truth, and `sync_roles` (all exist) [62].
- **Add:**
  - custom `Meta.permissions` for the action verbs;
  - `ROLE_LIMITS`, `SOD_CONFLICTS` and the permission catalogue (labels, risk) in code;
  - a `StaffScope(user, kind, value, granted_by, expires_at)` model;
  - one auth backend whose `has_perm(user, perm, obj)` is True only if the user has the model permission and `obj` is in scope. Django asks every backend, and ModelBackend answers False for objects [40];
  - one `scoped(queryset, user, perm)` helper used by `get_queryset` in every staff viewset, because DRF applies object permissions neither to lists nor to creates [45];
  - a serializer per role, for field-level access.
- **Libraries.** Neither candidate lists Django 6.1 support [52]:
  - django-guardian 3.5.0 stores per-object rows in the database and lists Django up to 6.0. It fits grants on "this specific book" but not rules like "all Physics", and it adds a row per assignment.
  - `rules` 3.5 uses predicates with no database and fits scope rules, but its last release was in 2024 and it is one more dependency.

  Recommendation: no new dependency. About 50 lines (the backend and the helper) plus tests. Revisit django-rules if the predicates multiply.
- **Tests.** One table-driven test per role × endpoint × method; OWASP asks for unit and integration tests of authorization logic [31]. Extend the repo's existing `accounts/test_roles.py`.

## 2. Staff account security

### 2.1 Authentication

- **MFA is already mandatory for staff** (`StaffMFAMiddleware`: TOTP, passkey or recovery codes) [62]. See NIST IA-2(1), MFA for privileged accounts [26], and ASVS 6.3.3 (L2) [28].
- **Phishing resistance.** NIST 800-63B-4 says AAL2 verifiers SHALL offer a phishing-resistant option, and OTPs, look-up codes and out-of-band codes are not phishing-resistant [27]. CISA: "the only widely available phishing-resistant authentication is FIDO/WebAuthn" [38]. So:
  - require a passkey or security key for OWNER, ADMIN and FINANCE;
  - accept TOTP for other roles;
  - syncable passkeys are fine at AAL2 but not at AAL3 [27].
- **Passkey-only sign-in is stronger than password + TOTP.** After a passwordless passkey login allauth skips its MFA stage, because the passkey is itself multi-factor [48 mfa/stages.py]. Today staff "cannot log in with a passkey alone" (RUNBOOK) [62]; consider allowing it.
- **Keep `MFA_TRUST_ENABLED` False for staff** (the default). It issues a 14-day cookie that skips MFA [47][48]. NIST: "remember my browser" cookies SHALL NOT replace authentication, except for AAL2 re-authentication after idle time [27].
- **Login by emailed code.** allauth still runs the MFA stage for users with TOTP or WebAuthn [48], so a staff code login is mailbox + second factor. ASVS 6.3.6 (L3) says email should not be an authentication factor [28]. The simplest fix is to refuse login-by-code for `is_staff` users in the adapter.
- **Recovery codes.** allauth's default is 10 codes of 8 digits [47]. Staff keep them offline, and regenerating them cancels the old ones (RUNBOOK) [62]. Consider `MFA_RECOVERY_CODES_SHOW_ONCE=True` for staff [48].
- **Google Workspace SSO for staff** (optional, but it centralizes offboarding). Use allauth's Google provider, which the repo already configures with PKCE [62]:
  - grant staff status only to a social account whose ID token has `hd` equal to the company domain; the `hd` request parameter is only a UI hint;
  - link accounts by `sub`, never by email [54];
  - this follows ASVS 6.8.1 (L2) (no identity spoofing across identity providers) and 6.8.4 (L2) [28].

  allauth runs its MFA stage after a social login too, so ExamLeaf's MFA stays on top of Workspace 2-step verification [48].
- **allauth quirk.** `did_recently_authenticate()` returns True for a user who has no usable password and no MFA, such as a social-only user [48]. That is harmless while every staff member must have MFA. Add a test that a staff account without an authenticator cannot pass the re-authentication gate.

### 2.2 Passwords

NIST 800-63B-4 [27], with the matching ASVS 6.2.x [28]:

| Rule | NIST | ExamLeaf today [62] | Action |
|---|---|---|---|
| Minimum length when the password is the only factor | SHALL ≥ 15 | 10 | decide for students: usability versus NIST (NIST is US guidance, not Indian law) |
| Minimum length with MFA | SHALL ≥ 8 | 10 | fine for staff |
| Maximum length | SHOULD allow ≥ 64 | check the form's limit | allow 64+ (ASVS 6.2.9 (L2)) |
| Composition rules | SHALL NOT | none | keep |
| Periodic rotation | SHALL NOT, but force a change on evidence of compromise | none | keep; the panel's "force reset" covers compromise |
| Blocklist (common, breached, context words) | SHALL | Pwned Passwords | add context words such as examleaf and product names (ASVS 6.1.2, 6.2.11 (L2)) |
| Hints, security questions | SHALL NOT | none | keep |
| Throttling | at most 100 consecutive failures per authenticator | axes: 10 per 15 min | keep; alert on staff lockouts |

Django 6.1 raised PBKDF2 to 1.5 M iterations [44], which is fine.

### 2.3 Sessions and re-authentication

| | NIST AAL2 [27] | NIST AAL3 [27] | OWASP CS [32] | ExamLeaf proposal |
|---|---|---|---|---|
| Absolute (overall) | SHOULD ≤ 24 h | SHALL ≤ 12 h | 4–8 h for office use | 8 h (exists) |
| Idle | SHOULD ≤ 1 h | SHOULD ≤ 15 min | 2–5 min for high-value apps; 15–30 min for low risk | 15 min for Owner, Admin, Finance, Packer; 30 min for others (none today) |
| Step-up | n/a | n/a | n/a | allauth re-auth window of 300 s (default) [46] |

- **Idle timeout.** Add a staff-only middleware that stores `last_activity` in the session and logs the user out once the idle limit passes. Django has no built-in idle timeout: `set_expiry(seconds)` is an inactivity expiry, and `SESSION_SAVE_EVERY_REQUEST` is global [42]. Document the chosen values (ASVS 7.1.1, 7.3.1, 7.3.2 (L2)) [28].
- **Step-up for sensitive actions** (ASVS 7.5.1 (L2), 7.5.3 (L3)) [28]:
  1. A DRF permission class calls allauth's `did_recently_authenticate(request)`.
  2. If that fails, it returns allauth's `ReauthenticationResponse(request)`: an HTTP 401 with `flows: [reauthenticate, mfa_reauthenticate]`.
  3. Next.js shows a modal and posts to `/_allauth/browser/v1/auth/reauthenticate` (password), `/auth/2fa/reauthenticate` (TOTP or recovery code) or `/auth/webauthn/reauthenticate` (passkey).
  4. Next.js retries the original request [48].

  Two notes. The public module `allauth.account.reauthentication` is deprecated and the function lives in `allauth.account.internal` [48], so pin allauth and cover this with a test. allauth's `AccountMiddleware` turns an uncaught `ReauthenticationRequired` into a redirect, so catch it in the DRF layer [48].
- **Actions that need step-up:**
  - role or scope changes; resetting someone else's MFA;
  - refunds, payouts and approvals;
  - revealing personal data (once per window); personal-data exports;
  - impersonation;
  - creating or rotating API keys; changing webhook secrets;
  - deletion or erasure;
  - maintenance mode; feature flags that touch payments or consent;
  - break-glass.
- **Device list and remote logout.** allauth.usersessions is on, with activity tracking. It stores the IP, user agent, created and last-seen times, and `UserSession.end()` deletes the session [48][62]. The panel needs:
  - a device list per user;
  - "end this session" and "end all sessions" (ASVS 7.4.5 (L2));
  - an offer to end other sessions after a factor change (ASVS 7.4.3 (L2)) [28].
- **Deactivation.** Django's ModelBackend refuses sessions of inactive users (`user_can_authenticate` checks `is_active`, per the installed Django 6.1.2 source [53]). simplejwt refuses inactive users by default (`CHECK_USER_IS_ACTIVE`), and refresh tokens can be blacklisted because the blacklist app is installed [53][62]. This meets ASVS 7.4.2 (L1) [28]. Consider `CHECK_REVOKE_TOKEN=True`, so a password change voids existing access tokens [53].
- **Concurrent sessions.** Document how many are allowed (ASVS 7.1.2 (L2)), for example two browsers per staff member, and alert above that.

### 2.4 Network, host and browser hardening

- **A separate hostname for the panel**, for example `admin.examleaf.in` (ASVS 3.5.4 (L2)) [28]. Then an XSS on the public site cannot ride a staff session.
  - Caddy routes `/api/staff/*` and `/_allauth/*` on that host to Django. The panel stays same-origin, so no CORS is needed, and allauth's browser client requires same-origin anyway [62 settings].
  - Django answers 404 for staff endpoints on any other host.
  - Retire Django admin (`/admin/`), or restrict it to the admin host and superusers. Today `/admin/*` is public on the main host [62 Caddyfile].
- **IP allowlist or VPN.** Use Caddy's `client_ip` or `remote_ip` matchers on the admin host, for the warehouse IP, the office IP or the VPN's exit address [59]. ASVS 8.4.2 (L3) says network location must not be the only factor [28]; this is an extra layer on top of MFA.
- **Headers:**
  - HSTS of at least 1 year, including subdomains (ASVS 3.4.1 (L1)); the repo's `SECURE_HSTS_INCLUDE_SUBDOMAINS` defaults to False [62];
  - a CSP with `frame-ancestors 'none'` and a report endpoint (ASVS 3.4.3, 3.4.6, 3.4.7) [28][43];
  - `Cache-Control: no-store` on staff API responses (ASVS 14.3.2 (L2));
  - `X-Robots-Tag: noindex`, a Referrer-Policy and COOP.
- **Cookies.** Set `Secure` and `HttpOnly`, and use the `__Host-` prefix for the session cookie (ASVS 3.3.1, 3.3.3; OWASP) [28][32]. Choose SameSite by purpose (ASVS 3.3.2): the public host needs Lax for returns from Google OAuth and Razorpay; the admin host can use Strict.
- **CSRF.** DRF's session authentication enforces Django CSRF. State changes only via POST, PUT, PATCH or DELETE (ASVS 3.5.3 (L1)), and `CSRF_TRUSTED_ORIGINS` lists exact origins.
- **Obscurity and detection.** A hidden admin URL is not a security control; the separate host, the allowlist and MFA are. A honeytoken (a fake admin login or a decoy API key that alerts when used) is cheap detection (OWASP A09:2025) [29].

### 2.5 Rate limiting, lockout, abuse

- **axes** locks a (username, IP) pair for 15 minutes after 10 failures (exists) [62][50]. NIST's upper bound is 100 [27]. ASVS 6.1.1 (L1) asks to document this and to prevent malicious lockouts [28]. Alert the owner when a staff account is locked, using axes's `user_locked_out` signal.
- **Per-staff throttles** with DRF `ScopedRateThrottle` on reveals, exports, bulk actions and customer searches. Going over the limit blocks the action and sends an alert (OWASP API4 and API6:2023; ASVS 2.4.1 (L2)) [30][28].

### 2.6 Secrets, API tokens, service accounts

- **Secrets** stay in `.env` (repo), with rotation procedures in RUNBOOK [62]. ASVS 13.3.1 (L2) prefers a secrets manager; 13.1.4 and 13.3.4 (L3) want a rotation schedule [28]. OWASP adds: audit who used what and when, set expiries, revoke [36]. The panel shows metadata only (name, purpose, owner, where used, last rotated, due date), never values.
- **Integration keys**, for example for a shipping aggregator, an accounting sync, the uptime monitor or a school SIS:
  - one key per integration, high-entropy and shown once;
  - stored as a SHA-256 hash with a visible prefix;
  - scopes, `expires_at` (at most 12 months) and an optional IP allowlist;
  - `last_used_at` and last IP;
  - two overlapping keys during rotation;
  - a human sponsor, and revocation.

  This follows ASVS 13.2.1 (L2) (individual service accounts or short-term tokens) and 7.2.2 (L1) (no static API secrets for user sessions) [28]. Log `authn_token_created`, `authn_token_revoked` and `authn_token_reuse` [34]. djangorestframework-api-key 3.1.0 does this but lists Django only up to 5.2 [52]; a small model of our own is just as short.
- **Service accounts** never log in to the panel and never get `is_staff`.

### 2.7 Impersonation ("log in as customer")

- **Prefer "view as" over a real session swap**: a read-only view of the customer's pages, rendered from the staff session with their data. Students are minors, so full impersonation of an under-18 account should need the owner's approval and a recorded reason, or not exist at all.
- **If full impersonation exists:**
  - it needs the permission `accounts.impersonate_user`;
  - staff and superusers can never be targets; django-hijack's `superusers_and_staff` rule stops staff hijacking staff [51];
  - it needs re-authentication, a reason and a ticket id, and is time-boxed to 15 minutes;
  - a banner shows throughout;
  - these actions are blocked: password, email, MFA, consent, payment, address and deletion;
  - every request is audited with `actor=staff` and `on_behalf_of=user`, plus start and end events (hijack has `hijack_started` and `hijack_ended` signals) [51];
  - the user is told, for transparency.

  django-hijack swaps Django sessions and allows only superusers by default [51]. With the headless Next.js frontend, a narrower custom flow is simpler.

### 2.8 Login alerts and notifications

- **After credential changes.** allauth's `ACCOUNT_EMAIL_NOTIFICATIONS` (on in the repo) emails password and email changes, with IP and user agent [46][62]. See ASVS 6.3.7 (L3).
- **Suspicious attempts** (ASVS 6.3.5 (L3)) [28]. Email the staff member:
  - on a login from a new IP and user-agent pair (compare with their UserSession history);
  - on a login after more than 30 days dormant;
  - on MFA failures.

  Send the owner a digest of staff logins outside usual hours.

### 2.9 Offboarding checklist

Record each step in the panel, with who did it and when. This follows NIST PS-4 (disable access within a set time, revoke authenticators and credentials, retrieve property, keep access to their information), PS-5 for transfers, and AC-2(k) (change shared credentials when someone leaves) [26], plus ASVS 7.4.2 (L1) [28].
1. Deactivate (`is_active=False`) so their sessions stop. End their UserSessions and blacklist their outstanding JWT refresh tokens [48][53].
2. Remove their roles and scopes; the old values stay in the AuditLog. Cancel any just-in-time grants. Reassign their pending change requests, support tickets and data requests.
3. Close their external accounts:
   - suspend Google Workspace;
   - remove them from the Razorpay dashboard, MSG91, AWS/SES, Cloudflare (R2), Sentry, GitHub and the domain registrar;
   - remove their server SSH keys and password-manager shares.
4. Revoke the API keys they own and move integration sponsorship to someone else.
5. Rotate the shared secrets they could read, following RUNBOOK [62]: anything in `.env` if they had server access, the webhook secrets, `HEALTH_CHECK_TOKEN`.
6. Collect their security keys, and remind them of confidentiality on exit.
7. The owner reviews an activity report of their last 90 days: exports, reveals, refunds.

Timing: for an involuntary exit, before the conversation ends; for a voluntary one, by the end of the last day.

### 2.10 OWASP mapping for the panel

| Item | Requirement |
|---|---|
| Top 10:2025 A01 Broken Access Control | deny by default; check server-side; enforce record ownership; log failures and alert; rate-limit; test authorization [29] |
| A02 Security Misconfiguration | DEBUG off (ASVS 13.4.2); no exposed docs or monitoring (13.4.5) [28][29] |
| A03 Software Supply Chain Failures | dependency monitoring (§7) [29] |
| A07 Authentication Failures | §2.1–2.3 [29] |
| A09 Security Logging & Alerting Failures | append-only audit tables, alerting, honeytokens [29] |
| A10 Mishandling of Exceptional Conditions | fail closed and roll back (ASVS 16.5.3) [28][29] |
| API1, API3, API5 (2023) | object-, property- and function-level authorization on every staff endpoint [30] |
| API4, API6 (2023) | throttle exports, reveals, bulk operations and refunds [30] |
| ASVS V6, V7, V8, V16 | as cited inline [28] |

## 3. Audit and accountability

### 3.1 What to log

Event names follow OWASP's Logging Cheat Sheet ("always log") and Logging Vocabulary [33][34], and NIST AU-2, AC-2(4) and AC-6(9) [26].
- **Authentication:**
  - `authn_login_success`, `authn_login_fail`, `authn_login_lock`;
  - MFA success and failure; re-authentication;
  - password and MFA changes, whether by the user or started by staff;
  - `session_created`, `session_expired`, `session_logout`, `session_ended_by_staff`;
  - `authn_token_created`, `authn_token_revoked`.
- **Authorization:**
  - `authz_fail`: every 403 on staff APIs;
  - `authz_change`: role, scope or limit granted or removed, from → to;
  - `authz_admin`: break-glass and just-in-time elevation.
- **Users:** `user_created`, `user_updated`, `user_archived`, `user_deleted`; suspend and unsuspend; unlock; merge; email change by staff; MFA reset; password reset started; impersonation start and end.
- **Sensitive data:**
  - `sensitive_read`: revealing personal data, opening a child's profile or timeline, downloading an export;
  - `sensitive_update`, `sensitive_delete`;
  - data exports, with the filter, row count and purpose.
- **DPDP:**
  - consent given or withdrawn (`ConsentRecord` exists [62]);
  - parental verification;
  - rights requests: received, verified, answered, closed;
  - erasure executed or held;
  - breach-register entries.
- **Money:**
  - refunds: requested, approved, executed, failed;
  - offline payments recorded;
  - invoices and credit notes issued;
  - price, coupon and offer changes;
  - payouts and payee changes.
- **Configuration and operations:**
  - feature flags, maintenance mode, settings;
  - secret rotations (metadata only), API keys;
  - webhook replays and signature failures;
  - job retries and cancellations;
  - backups and restore tests, deploys.
- **ChangeRequest** transitions.

**Fields for each event**, from NIST AU-3 (type, when, where, source, outcome, identity) [26] and OWASP's when/where/who/what [33]:
- `id`; `ts` in UTC with milliseconds (ASVS 16.2.2 (L2));
- `actor_id`, `actor_type` (staff, user, service or system), a snapshot of `actor_roles`, and `on_behalf_of`;
- `action`, `target_type`, `target_id`, and `target_label` (no personal data);
- `outcome` (success, denied or failed), `reason`, `change_request_id`;
- `request_id`: Caddy's `X-Request-ID`, already carried by django-guid [62];
- `ip`, `user_agent` (truncated), `session_hash`;
- `changes` as {field: [before, after]}, with personal data and secrets masked or replaced by a hash;
- `prev_hash` and `hash`.

**Never log** passwords, tokens, session ids (hash them), card data or full personal-data values (OWASP "data to exclude"; ASVS 16.2.5 (L2)) [33][28]. Encode values against log injection (ASVS 16.4.1 (L2)).

### 3.2 simple_history vs a dedicated AuditLog

| | django-simple-history (in the repo on Order, Payment, OrderNote, Review) | AuditLog (to add) |
|---|---|---|
| Unit | a row snapshot each time one model is saved | one event per action, of any kind |
| Covers | model changes, with `history_user`, change reason and diffs; the customer's status timeline (repo) | logins, reads, reveals, exports, permission failures, approvals, configuration, actions on no model |
| Misses | bulk_create, bulk_update and queryset.update, unless the `*_with_history` utilities are used [49]; reads; failures | field snapshots (it links to the history row instead) |
| Integrity | an ordinary table whose rows can be deleted (the repo deletes history rows on erasure [62]) | append-only, hash chain, copy kept off-site |
| Use | "what did this order look like on 3 May"; restore | "who did what, from where, why, and who approved it" |

Keep both, and have AuditLog rows reference the history row id where one exists. Django admin's `LogEntry` remains for the legacy admin only.

### 3.3 Tamper evidence

- **Append-only.** PostgreSQL owners can always re-grant themselves privileges, and the right to modify or drop a table comes with owning it [57]. So:
  - preferably, run the app as a role that does not own the audit table: migrations run as the owner role, and the runtime role gets `SELECT` and `INSERT` only;
  - at minimum, add a `BEFORE UPDATE OR DELETE OR TRUNCATE` trigger that raises an error. Removing the trigger is DDL and visible, but detection still relies on the next two layers.

  OWASP A09:2025 names append-only tables [29]. NIST AU-9 asks to protect audit data and alert, and AU-9(4) to restrict audit management to a subset of privileged users [26]. See also ASVS 16.4.2 (L2) [28].
- **Hash chain.** Each row stores `hash = SHA-256(prev_hash || canonical_json(row))`, written under one lock. (A single global writer lock is fine at ExamLeaf's volume; shard by day if it ever contends.) A nightly job verifies the chain and alerts if it breaks (AU-9 b; AU-9(3), cryptographic integrity) [26].
- **Off-site copy.** Each day, export the new rows as JSONL, with the chain head, to an R2 bucket that has a bucket-lock retention rule, so nothing can be deleted or overwritten for that period [58]. Only the export job holds the credentials (AU-9(2), separate system; ASVS 16.4.3 (L2)) [26][28].
- **Time.** Clocks are NTP-synced. CERT-In wants NIC/NPL servers or traceable sources, and its FAQ accepts cloud-native time [10][11].

### 3.4 Retention matrix

| Record | Minimum | Source |
|---|---|---|
| Invoices, credit notes, payments, refunds, orders (books of account and vouchers) | GST: 72 months from the due date of that year's annual return, plus 1 year after any appeal or proceeding ends [15]. If a company: 8 financial years (s.128(5)) [17]. Use 8 financial years; the repo already purges orders after 8 years [62] | [15][17] |
| Edit log of those entries | as long as the records. Electronic records need "a log of every entry edited or deleted" [16]. Companies using accounting software need an audit trail that cannot be disabled, from FY 2023-24 [17][18] | [16][17][18] |
| ICT and security logs (Caddy access, app, auth, admin actions) | 180 days rolling, in force now [10]. The FAQ allows storage outside India if logs are produced on demand within a reasonable time [11] | [10][11] |
| Logs and personal data needed for security investigations | 1 year (r.6(1)(e)), from 13 May 2027 | [2] |
| Personal data, traffic data and logs of each processing (order confirmation, payment and delivery events; SMS and email sends; webhook events) | at least 1 year from the processing, even after the account is deleted (r.8(3) and its e-book illustration); then erase, unless another law needs longer | [2] |
| Registration data, if ExamLeaf is an intermediary (for example for user reviews) | 180 days after the account is cancelled; removed content preserved for 180 days | [13 r.3(1)(g),(h)] |
| Consent records | while processing relies on them, plus the limitation period: ExamLeaf must prove notice and consent (s.6(10)). The 7-year rule in Schedule 1 applies to consent managers only | [1][2 Sch.1] |
| Staff-action AuditLog | proposal: 2 years (DPDP needs at least 1); money-related events 8 financial years | derived |
| Backups | short rotation (30 days exists [62]) so erased data does not linger. If the platform holds the books of account, backups go on servers in India (r.3(5) proviso says "periodic"; a 2022 amendment may have made it "daily", verify) | [17] |

**Repo settings that conflict** [62]:
- Docker logs of 50 MB per service;
- Celery results and webhook records kept 7 days;
- the SMS log kept 90 days;
- device rows purged nightly.

These fall short of 180 days for logs now (CERT-In), and of r.8(3) from May 2027. Keep minimal metadata for the full period, and trim payloads (for example webhook bodies) early.

### 3.5 Search, export, access to logs

- **Filters:** actor, action, target type and id, outcome, date range, request id, IP. Saved views, for example "all refunds > ₹5,000 this month" or "all reveals by X".
- **Access:** AUDITOR and OWNER only (AU-9(4)) [26]. Reading or exporting the audit log is itself audited; OWASP says all access to logs should be recorded [33].
- **Export:** CSV or JSONL, generated asynchronously, with an expiring link. Include the chain hashes so a copy can be verified.
- **Review:** a weekly skim of high-risk events (AU-6) [26].

### 3.6 Alerts

Send these to the owner at once by email or SMS; everything else goes into a daily digest [29][26]:
- grants of privileged roles or scopes; a new staff account; an MFA reset on a staff account;
- break-glass use; the start of an impersonation;
- a refund or payout above the threshold;
- any export of children's personal data, or of more than N rows;
- a break in the audit chain, or a failed export job;
- a staff lockout;
- a spike in `authz_fail` or in webhook signature failures;
- maintenance mode turned on;
- no backup for more than 26 hours.

### 3.7 Approval records

The ChangeRequest row (§1.5) is the approval record. It holds the maker, the reason, the hash of the exact payload, the approver or approvers, comments, timestamps and the execution outcome, and the AuditLog links to it (ASVS 2.3.5 (L3)) [28]. For configuration changes, CM-3 asks to review, approve, document and keep records [26].

## 4. Indian data protection: requirements and panel features

### 4.1 Status (as of 2026-10-09)

| Item | Status | Source |
|---|---|---|
| DPDP Act 2023 | Enacted 11 Aug 2023. In force since 13 Nov 2025: s.1(2), 2, 18–26, 35, 38–43, 44(1),(3). After 1 year: s.6(9), 27(1)(d). After 18 months: the core ss.3–17, plus 27–34, 36–37 and 44(2) | [1][4][6] (the commencement split comes from a secondary source) |
| DPDP Rules 2025, G.S.R. 846(E) | Gazette 13 Nov 2025, signed 14 Nov. In force now: rr.1, 2, 17–21. From about 13 Nov 2026: r.4. From about 13 May 2027: rr.3, 5–16, 22–23 | [2][3][4] |
| Shortening to 12 months | MeitY stakeholder proposal of 23 Jan 2026, mainly for SDFs; not notified as far as found | [7][8] |
| Data Protection Board | Established, but no Chairperson or Members as of 1 Aug 2026 | [8] |
| Start-up exemptions, s.17(3) | The Government may exempt notified Data Fiduciaries, including start-ups, from s.5, 8(3), 8(7), 10 and 11. No notification found | [1][5] |
| SPDI Rules 2011 + IT Act s.43A | Apply until s.44(2) commences with the 18-month phase | [9][12] |
| CERT-In Directions 2022 | In force since 27 Jun 2022 (60 days after issue) | [10][11] |

### 4.2 DPDP obligations → panel features

| Obligation | Source | Panel feature |
|---|---|---|
| A standalone, itemised notice: the personal data, the purposes, the goods or services enabled, and links to withdraw consent, exercise rights and complain to the Board | r.3 [2] | A notice-versions table (text, version, effective date); every ConsentRecord stores its version (exists [62]) |
| Withdrawal as easy as giving consent; stop processing within a reasonable time and make processors stop | s.6(4),(6) [1] | A consent ledger per purpose (account, marketing, SMS updates and so on); withdrawal events; "cease" tasks for processors |
| Prove notice and consent in proceedings | s.6(10) [1] | Append-only consent ledger: version, method, time, IP hash (exists), and a reference to the parental evidence |
| Consent managers | s.6(7)–(9); r.4 from Nov 2026 [1][2] | Optional, later: accept consent artefacts that come from a consent manager |
| Reasonable security safeguards: encryption, masking or tokens; access control; access logs with monitoring and review; backups; 1-year log retention; processor contracts | s.8(5); r.6 [1][2] | Personal data masked by default, with logged reveals; RBAC; AuditLog; backups panel; a processor register with contract dates |
| Erase when consent is withdrawn or the purpose is served, unless a law requires retention; make processors erase too | s.8(7) [1] | Deletion workflow with legal holds and processor tasks (§4.5) |
| Keep processing logs and personal data for at least 1 year | r.8(3) [2] | A retention-schedule engine; erasure skips held categories until their expiry |
| Publish the DPO or contact person, and quote them in every rights response | s.8(9); r.9 [1][2] | Response templates add the contact block automatically |
| A grievance mechanism; respond within 90 days. Data Principals must use it before going to the Board | s.8(10), s.13; r.14(3) [1][2] | A requests queue with due dates, SLA timers and escalation |
| Access: a summary of the data and its processing, and who else (Data Fiduciaries, processors) it was shared with | s.11 [1] | The export (`export_user_data` exists [62]) plus a recipients list attached automatically from the processor register |
| Correction, completion, updating, erasure | s.12 [1] | Correction tasks with history; erasure requests |
| Nomination, for death or incapacity | s.14; r.14(4) [1][2] | A nominee record (name, contact, relation), verified when a claim is made; today RUNBOOK keeps it in the mailbox [62] |
| Publish how to make requests and which identifiers are needed | r.14(1) [2] | A settings page for the published text |
| Breach intimation | s.8(6); r.7 [1][2] | Breach register (§4.4) |
| Children: verifiable parental consent; no harmful processing; no tracking, behavioural monitoring or targeted ads | s.9; r.10, r.12, Sch.4 [1][2] | §4.3 |
| Cross-border transfer: allowed unless the Government restricts it (notified countries; conditions on access by foreign States) | s.16; r.15 [1][2] | The processor register records each processor's country or region, so a switch is quick |
| SDF duties: DPO in India, independent auditor, yearly DPIA and audit, algorithmic due diligence, localisation of specified data | s.10; r.13 [1][2] | Not expected for ExamLeaf, but watch the notifications: "volume and sensitivity" of data is a listed factor, and children's data may count |
| Penalties: ₹250 cr security; ₹200 cr breach notice; ₹200 cr children; ₹150 cr SDF; ₹50 cr anything else; ₹10,000 for breaches of Data Principal duties | Schedule [1] | n/a |
| Employee data: a legitimate use "for the purposes of employment", so no consent is needed, but the safeguards still apply | s.7(i) [1] | Keep staff HR fields minimal and restricted |
| Third Schedule: erase after 3 years of inactivity | r.8(1),(2) [2] | Applies only to e-commerce entities with at least 2 crore users (and to gaming and social media), so not ExamLeaf; s.8(7) still applies |

### 4.3 Children (under 18)

- **Definitions.** s.2(f): a child is anyone under 18. s.2(j): for a child, the Data Principal includes the parent or lawful guardian [1].
- **Rule 10.** Before processing any of a child's data, obtain the parent's verifiable consent and check that the parent is an identifiable adult [2]. The check can use:
  - (a) reliable identity and age details already held; or
  - (b) details the parent gives voluntarily, or a virtual token mapped to them from an authorised entity, including through a DigiLocker service provider.

  The rule has four illustrations, covering whether the child or the parent starts and whether the parent is already registered [2].
- **Panel states per child account:**
  - `age_band`, from the date of birth;
  - consent state: none, declared, pending, verified, withdrawn or expired;
  - method: declared tick, email link, SMS link, an existing verified adult account, a DigiLocker token, or manual by staff with evidence;
  - `verified_at` and `verified_by`;
  - an evidence reference (not the document image) and the notice version.

  The repo already has `ConsentRecord(by_parent, method, verified_at, notice_version)` and the modes declared and verified [62]. Add the identity and age step before 13 May 2027.
- **Fourth Schedule exemptions from s.9(1) and 9(3)** [2]:
  - Part A lists classes, including an "educational institution" (tracking or behavioural monitoring for its educational activities, or for the children's safety).
  - Part B lists purposes, including "creation of a user account for communicating by email" (limited to email), keeping harmful content or ads away from a child, and confirming that a user is not a child (r.10 due diligence).

  Whether ExamLeaf counts as "an institution of learning that imparts education" is for counsel.
- **Until counsel advises:**
  - keep under-18 accounts out of marketing segments, ad audiences, lookalike exports and A/B experiments;
  - do no behavioural profiling beyond what the learning feature needs;
  - log every time staff open a child's record (`sensitive_read`).

### 4.4 Breach register and incident clock

- **What counts.** Any unauthorised processing, or accidental disclosure, acquisition, sharing, use, alteration, destruction or loss of access, that compromises confidentiality, integrity or availability [1 s.2(u)]. So ransomware, or an outage that blocks access to personal data, counts.
- **Telling each affected person** [2 r.7(1)]: without delay, through their account or registered contact, with:
  - the nature, extent and timing;
  - the likely consequences;
  - the mitigation taken;
  - steps they can take;
  - a contact person.
- **Telling the Board** [2 r.7(2)]:
  - without delay: a description (nature, extent, timing, location, impact);
  - within 72 hours, or longer if the Board agrees to a written request: updated details, the facts and reasons, the mitigation, findings on who caused it, the remedial measures, and a report on the notices sent to people.
- **Telling CERT-In:** within 6 hours of noticing, for the Annexure I types (which include data breach, data leak, unauthorised access, attacks on e-commerce applications and malicious code), to incident@cert-in.org.in. Partial information is allowed at first [10][11 Q30].
- **Panel: an `Incident` record** with:
  - detected_at, noticed_by, the Annexure I type, the systems and data categories involved, the people affected (and whether any are children);
  - the CERT-In report time and reference; the Board's initial and detailed report times; any extension request;
  - the template sent to people, and how many were sent;
  - actions, root cause, closure;
  - deadline timers (6 hours, 72 hours) counted from detection;
  - links to the related AuditLog events.
- Keep the CERT-In point of contact (Annexure II) and the DPDP contact (r.9) in settings [10][2].

### 4.5 Erasure workflow with holds

- **Self-service** "Delete my account" exists, with a 7-day grace period and anonymisation [62].
- **Staff-side:**
  1. A request comes in, and the requester's identity is verified.
  2. A dry-run report shows what will be erased, what is held, why, and until when.
  3. If staff started it, it is approved.
  4. It is executed.
  5. Processor tasks follow: Sentry events, email-provider logs, R2 media, analytics [1 s.8(7)(b)].
  6. A confirmation goes out with the contact block [2 r.9].
- **Holds:**
  - tax and books: 8 financial years or 72 months [15][17];
  - one year of processing logs under r.8(3) [2];
  - open disputes, chargebacks or legal claims (s.17(1)(a) exempts processing needed to enforce a legal claim) [1];
  - the intermediary 180-day rule, if it applies [13];
  - for erasure involving a child, confirmation from the parent.
- **Backups** age out through rotation. Never restore erased users from a backup: keep a record of erasures and re-apply it after any restore.

### 4.6 Grievance and complaint timelines

Use one queue, with the strictest clock that applies:

| Regime | Who | Timeline | Source |
|---|---|---|---|
| DPDP (from May 2027) | rights requests and grievances | respond within 90 days | [2 r.14(3)] |
| SPDI Rules (until May 2027) | a grievance officer, with name and contact on the website | redress within one month | [12 r.5(9)] |
| E-Commerce Rules 2020 | a grievance officer, with name, contact and designation on the platform | acknowledge within 48 h; redress within one month | [14 r.4(4),(5)] |
| IT Rules 2021 (only if an intermediary, for example for user reviews) | a grievance officer | acknowledge within 24 h; resolve within 15 days; some removal requests within 72 h | [13 r.3(2)] |

The E-Commerce Rules also require [14]:
- the legal name, HQ address, and customer-care and grievance contacts shown on the platform;
- a nodal person of contact who lives in India (r.4(1));
- purchase consent only by an explicit, affirmative action, with no pre-ticked boxes (r.4(9));
- refunds within a reasonable time, as the RBI prescribes (r.4(10)).

### 4.7 CERT-In obligations as panel and ops items

- **6-hour incident reporting** (§4.4) [10].
- **Logs** of all ICT systems, kept securely for 180 days rolling, covering successful and failed events [10][11 Q37].
- **Clock sync** by NTP to samay1.nic.in, samay2.nic.in, time.nplindia.org or a traceable source; cloud-native time is accepted [11 Q40–43]. The repo's DEPLOYMENT.md does not mention this [62].
- **A point of contact** registered with CERT-In [10 Annex II].

### 4.8 PCI DSS with Razorpay

- Razorpay is PCI DSS Level 1. Card data must not reach ExamLeaf's servers; if it did, ExamLeaf would need its own PCI DSS certification. Protect the key secret [20].
- Razorpay Standard Checkout is an embedded form, so the revised SAQ A eligibility criterion applies: ExamLeaf must confirm the site is not susceptible to script attacks [19]. There are two ways:
  - use techniques like PCI DSS 6.4.3 and 11.6.1 on the page that embeds checkout: a script inventory, integrity checks and change detection; or
  - get written confirmation from Razorpay that its solution protects the page.

  The criterion does not apply to redirects [19].
- **Panel implications:**
  - never show or store card data: only Razorpay ids, the method, and the last 4 digits if Razorpay returns them;
  - deployments that change the checkout page's scripts or CSP go through change control (CM-3) [26];
  - a daily check of the checkout page's script hashes alerts on any change.

### 4.9 Repo vs law: gaps to plan for

1. Log retention is below CERT-In's 180 days (Docker keeps 50 MB per service). This applies today [10][62].
2. Processing-log retention is below r.8(3)'s one year: webhook records 7 days, SMS log 90 days, device rows purged nightly, Celery results 7 days. Fix by 13 May 2027 [2][62].
3. Parental verification does not meet r.10. Fix by 13 May 2027 [2][62].
4. The NTP time source is not documented, and neither the CERT-In point of contact nor the 6-hour procedure is in RUNBOOK (it does cover the Board's 72 hours) [10][62].
5. There is no breach register, rights-request queue or processor register in the system; today these are shell commands in RUNBOOK [62].
6. There is no append-only log of staff actions, only admin LogEntry and simple_history [62].

## 5. User management (admin side)

**Account types:**
- student, often under 18;
- parent, linked through consent;
- teacher (`TeacherProfile` verification exists);
- school (TEACHER_PARTNER or a school admin);
- guest buyer.

**Verification badges:**
- email verified (allauth `EmailAddress`);
- phone verified (`login_phone_verified`);
- age band;
- parental consent state and method;
- teacher verification;
- MFA on;
- status: active, suspended, locked by axes, pending deletion, erased.

**Actions.** Each one has a permission, and may need step-up re-authentication, an approval and a user notification; each writes an AuditLog event.

| Action | Permission | Re-auth | Approval | Notify | Rules |
|---|---|---|---|---|---|
| View (contact masked; no date of birth by default) | `accounts.view_user` | no | no | no | show the minimum data (ASVS 14.2.6 (L3)) [28] |
| Reveal contact, date of birth or parent contact | `accounts.reveal_contact` | yes | no | no | reason required; throttled; logged as `sensitive_read` |
| Suspend / reactivate | `accounts.suspend_user` | yes | no | yes | `is_active=False` ends sessions (ASVS 7.4.2) |
| Unlock (axes) | `accounts.unlock_user` | no | no | no | `axes_reset_username` (RUNBOOK) [62] |
| Reset 2FA | `accounts.reset_user_mfa` | yes | if the target is staff: owner | yes | prove identity as strongly as at enrolment (ASVS 6.4.4 (L2)); OWASP MFA reset methods [28][35]; today this is a RUNBOOK shell step [62] |
| Force password reset | `accounts.initiate_password_reset` | no | no | yes | staff never set or see a password (ASVS 6.4.6 (L3)); the reset must not bypass MFA (6.4.3 (L2)); offer "end all sessions" |
| Change email | `accounts.change_user_email` | yes | no | old and new address | a code goes to the new address; allauth notifies the old one [46] |
| Merge duplicates | `accounts.merge_users` | yes | yes | yes | dry-run diff first; move orders, consents and entitlements; keep an id map; irreversible |
| View as / impersonate | `accounts.impersonate_user` | yes | for child accounts: owner | yes | §2.7 |
| End sessions / devices | `accounts.end_user_sessions` | no | no | optional | usersessions plus JWT blacklist [48][53] |
| Export personal data (access request) | `accounts.export_personal_data` | yes | no | sent only to a verified address | the JSON export exists [62] |
| Delete / erase | `accounts.delete_user` | yes | if staff started it: yes | yes | holds as in §4.5 |
| Verify teacher | `accounts.change_teacherprofile` | no | no | yes | record the type of evidence, not the document |
| Verify parental consent by hand | `accounts.verify_parental_consent` | yes | no | the parent | record the method and an evidence reference (r.10) [2] |
| Notes | `accounts.add_note` | no | no | no | notes are personal data: they go into access exports; no health or other sensitive details; keep edit history |

- **Bulk operations:**
  - run asynchronously, with progress and a cancel button;
  - show a dry-run count first;
  - cap rows per role, and need approval above N;
  - write one AuditLog event per row plus one for the batch;
  - never bulk-delete children's data without approval.
- **Segments** are built only from consented purposes, and under-18s are excluded from marketing (s.9(3)) [1]. Segment definitions are versioned.
- **Activity timeline:**
  - logins, failures and MFA events;
  - devices;
  - orders, payments and refunds;
  - consents and data requests;
  - support notes;
  - staff actions on the account (AuditLog with `target=user`).

  Opening a child's timeline counts as a `sensitive_read`.
- **DPDP queue.** Each request records:
  - its type: access, correction, erasure, grievance, nomination or consent withdrawal;
  - the channel, the identifiers (r.14(1)(b)) and the identity check;
  - a due date, the earliest of the clocks that apply (§4.6);
  - the assignee and any holds;
  - the response, with the r.9 contact, proof that it was sent, and the closure reason.
- **Exports of any personal data:**
  - need an `*.export_*` permission (the repo already gates import-export by permission [62]) and re-authentication;
  - are generated asynchronously, behind a link that expires in 24 hours;
  - go only to the staff member who asked;
  - carry a watermark (who, when) inside the file;
  - have row caps, and alert above a threshold;
  - write an AuditLog event with the filter and the count. OWASP counts data export as higher-risk functionality [33].

## 6. Staff management

- **Invitations.** The owner or an admin invites an email address (the company domain or an allowlist), with the role chosen in advance; privileged roles need approval. The link is signed, works once and expires after 72 hours. At first login, the person must enrol MFA (exists) and acknowledge the policies before any page opens.
- **Onboarding.** Staff acknowledge these policies:
  - acceptable use;
  - protection of children's data;
  - confidentiality;
  - incident reporting, including "tell the owner at once", because of the 6-hour CERT-In clock.

  Store each acknowledgement as (user, policy, version, time), and ask again when a policy changes. NIST PS-6 wants access agreements signed before access and re-signed after updates; AT-2 wants training at the start and periodically [26].
- **Role changes** go: request → diff preview → SSD check → approval → effective, optionally with an `expires_at`. AC-2(e) asks for approval to create accounts and AC-2(c) for prerequisites to join a role [26].
- **Transfers.** When someone's duties change, review and confirm they still need their access (PS-5) [26].
- **Offboarding:** the checklist in §2.9.
- **Activity reports**, per staff member: logins, actions by type, exports, reveals, refunds approved, failed authorization. Outliers are flagged.
- **Per-staff rate limits:** §2.5.
- **Packer shifts** (optional). Allowed hours per packer, as an ABAC condition documented under ASVS 8.1.3 (L3) [28]. Outside those hours, either deny or allow with an alert. Keep shift notes minimal.
- **Quarterly access reviews.** Generate a list of users × roles × scopes × last login × last use of each permission. The reviewer marks each line keep, modify or revoke, and the decisions go through the role-change flow. Also:
  - flag or disable dormant staff accounts, for example after 45 days (AC-2(3));
  - check the break-glass list (Microsoft: every 90 days) [26][39].

  See AC-2(j) and AC-6(7) [26].
- **Least-privilege report:** permissions unused for 90 days, per user and per role (AC-6(7)) [26].
- **Emergency contacts:** name, relation and phone only, visible to the owner. This is a legitimate use for employment (s.7(i)) [1].
- **API keys per integration:** as in §2.6, reviewed during the access review.

## 7. Operational security in the panel

| Area | Show / do | Source |
|---|---|---|
| Backups | the last successful backup (time, size, checksum, whether encrypted with age, location); alert if older than 26 h; retention (`BACKUP_KEEP_DAYS` = 30); the last restore test (date, who, result, duration); an immutable copy in a locked R2 bucket, against ransomware | CP-9, CP-9(1) [26]; backups in r.6(1)(d) [2]; OWASP restore tests [36]; [58][62] |
| Secrets rotation | the inventory from RUNBOOK (SECRET_KEY, JWT key, provider keys, webhook secrets, health token): owner, last rotated, next due; never values | ASVS 13.1.4, 13.3.4 [28]; [36][62] |
| Dependencies | the last pip-audit (2.10.1) and npm audit runs; open advisories by severity; an SLA, for example 7 days for critical. No CI configuration was found in the repo | A03:2025 [29]; [52] |
| Uptime and status | the external monitor on `/health/` with `X-Health-Token` (exists); history; current incidents | [62] |
| Errors | Sentry, with personal data scrubbed (`send_default_pii=False` exists): counts and links, no raw payloads in the panel | [61][62] |
| Feature flags | key, state, audience (staff, all, a segment), owner, notes; history and AuditLog; flags touching payments, auth or consent need approval | CM-3, CM-5 [26] |
| Maintenance mode | owner or admin only; a reason; a banner; expires automatically; the admin host stays reachable; audited | CM-3 [26] |
| Config view (masked) | environment, DEBUG (must be False), security headers, CSP, allowed hosts, versions (staff only), and which secrets are set with a fingerprint (the first 4 hex digits of a SHA-256); never values | ASVS 13.4.2, 13.4.6 [28] |
| Job queues | Celery queues, active and failed tasks; retry or cancel with audit. Periodic tasks stay superuser-only: the repo treats running any task with any arguments as a privilege | [62] |
| Webhooks | events (type, received, signature valid, processed, attempts, error); replay from the stored payload, idempotent on `x-razorpay-event-id`; tolerate out-of-order delivery; after a secret rotation, use the old secret for retried older events; alert on signature failures | [21][62] |
| Email | sent, delivered, bounced and complaints (anymail); the suppression list (exists); SPF, DKIM and DMARC status; a Postmaster spam rate under 0.3%; one-click unsubscribe for marketing | [60][62] |
| SMS | SmsLog status per kind of message, DLT template ids (RUNBOOK), failure reasons, OTP volumes | [62] |
| Abuse controls | throttle hits by endpoint; axes lockouts (with unlock); Turnstile failures; blocklists (email domains, phone numbers, IPs and CIDRs) with a reason, an expiry and audit | API4, API6 [30]; [62] |
| Logs | a log inventory: what is logged, where, for how long, and who can read it | ASVS 16.1.1 (L2) [28] |

## 8. Questions for the owner and counsel

1. Is ExamLeaf a company, so that the Companies Act's 8-year books and audit-trail rule apply? Are the books kept in this platform, or in Tally or Zoho? [17][18]
2. Does the revision course make ExamLeaf an "educational institution" for the Fourth Schedule tracking exemption? If not, which learning analytics on under-18s does s.9(3) allow? [1][2]
3. Which Rule 10 method for parents: a DigiLocker token, the parent's own account holding reliable identity and age details, or both? [2]
4. Do user reviews make ExamLeaf an intermediary for that content, bringing in the IT Rules timelines? [13]
5. Should staff sign in through Google Workspace SSO? If so, on which domain?
6. The thresholds: refund cap per role, discount %, export rows, bulk rows, idle timeouts.
7. Where will logs be kept for 180 days and for 1 year (a log service, or R2 with lifecycle rules), and in which region? [10][11]
