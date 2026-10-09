# Sources: RBAC, admin security, audit, Indian data-protection law, user and staff management

All fetched 2026-10-09 (curl or WebFetch; PDFs read as text). Numbers match the [n] citations in research-rbac-security.md.
"Primary" means the official text or the maintainer's own documentation or source code. Where only a secondary source was
reachable, the note says so.

## India: law, rules, government

| # | Source | URL | Quality note |
|---|---|---|---|
| 1 | Digital Personal Data Protection Act, 2023 (Act 22 of 2023), Gazette copy | https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf | Primary. Read ss. 2, 6–17, 33 and the Schedule (penalties). |
| 2 | Digital Personal Data Protection Rules, 2025, G.S.R. 846(E), 13 Nov 2025 | https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf | Primary, the full English text: rr. 1–23 and Schedules 1–7. Digitally signed 14 Nov 2025. |
| 3 | PIB, "Government notifies DPDP Rules…", 14 Nov 2025 (PRID 2190014) | https://www.pib.gov.in/PressReleasePage.aspx?PRID=2190014 | Primary (government press release). Summary only. Read with curl because WebFetch got 403. |
| 4 | PIB backgrounder "DPDP Rules, 2025 Notified", 17 Nov 2025 | https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/nov/doc20251117695301.pdf | Primary (government). Plain-language summary, 90-day response, penalties; links to [1] and [2]. |
| 5 | PIB, Lok Sabha reply on start-ups and the DPDP Act, 3 Dec 2025 (PRID 2198217) | https://www.pib.gov.in/PressReleasePage.aspx?PRID=2198217 | Primary, but it gives no detail: a "simplified framework" is mentioned and no s.17(3) notification is cited. |
| 6 | dpdpa.com, "DPDPA 2023 enforcement timeline" (Act commencement, G.S.R. 843(E)) | https://www.dpdpa.com/dpdpa_enforcement_timeline.html | Secondary. Quotes the commencement notification. The official copy of G.S.R. 843(E) was not retrieved. |
| 7 | S.S. Rana & Co. (via Chambers), "MeitY plans to cut short DPDP compliance timeline…", 23 Feb 2026 | https://chambers.com/articles/meity-plans-to-cut-short-dpdp-compliance-timeline-and-notify-cross-border-restrictions-for-sdfs | Secondary (law firm). The 23 Jan 2026 stakeholder proposal (18 to 12 months, mainly for SDFs). A proposal, not notified. |
| 8 | LiveLaw, "India's Data Protection Board: Established In Law, Absent In Fact", 1 Aug 2026 | https://www.livelaw.in/articles/india-data-protection-board-established-law-543751 | Secondary (legal news). As of Aug 2026 the Board has no Chairperson or Members; no amendment notified. |
| 9 | Hogan Lovells, "India's DPDP Act 2023 brought into force", 17 Nov 2025 | https://www.hlc.com/en/publications/indias-digital-personal-data-protection-act-2023-brought-into-force- | Secondary (law firm). States that the SPDI Rules 2011 stay in force until the phase-in ends. |
| 10 | CERT-In Directions under s.70B(6) IT Act, No. 20(3)/2022-CERT-In, 28 Apr 2022 | https://www.cert-in.org.in/PDF/CERT-In_Directions_70B_28.04.2022.pdf | Primary. 6-hour reporting, 180-day logs, NTP, point of contact, Annexure I incident types. |
| 11 | CERT-In FAQs on the Cyber Security Directions, May 2022 | https://www.cert-in.org.in/PDF/FAQs_on_CyberSecurityDirections_May2022.pdf | Primary (official clarifications): Q30 partial reports, Q35 logs may sit outside India, Q37 which logs, Q40–43 NTP. |
| 12 | IT (Reasonable Security Practices… and SPDI) Rules, 2011 (Gazette text, PRS copy) | https://prsindia.org/files/bills_acts/bills_parliament/2011/IT_Rules_2011.pdf | Primary text (a PRS-hosted copy of the gazette). r.3 SPDI incl. passwords; r.5(9) grievance officer, one month; r.8 security practices. |
| 13 | IT (Intermediary Guidelines and Digital Media Ethics Code) Rules, 2021, as updated 6.4.2023 (MeitY) | https://www.meity.gov.in/static/uploads/2024/02/Information-Technology-Intermediary-Guidelines-and-Digital-Media-Ethics-Code-Rules-2021-updated-06.04.2023-.pdf | Primary (consolidated by MeitY). r.3(1)(g),(h) 180-day retention; r.3(2) 24 h / 15 days / 72 h. Later 2025–26 amendments were not reviewed. |
| 14 | Consumer Protection (E-Commerce) Rules, 2020, G.S.R. 462(E), 23 Jul 2020 (Gazette text, PRS copy) | https://prsindia.org/files/bills_acts/bills_parliament/2021/Consumer%20Protection%20(E-Commerce)%20Rules,%202020.pdf | Primary text. r.4: grievance officer, 48 h / one month, no pre-ticked consent, refunds. The official consumeraffairs.nic.in link timed out. |
| 15 | CGST Act, 2017 (CBIC consolidated, updated 30.09.2020), s.36 | https://cbic-gst.gov.in/pdf/CGST-Act-Updated-30092020.pdf | Primary (CBIC). Records kept 72 months from the annual-return due date, plus the appeal proviso. |
| 16 | CGST Rules, 2017 (CBIC, amended up to 1.6.2021), r.56(8) | https://cbic-gst.gov.in/pdf/01062021-CGST-Rules-2017-Part-A-Rules.pdf | Primary (CBIC). No overwriting; electronic records keep a log of every entry edited or deleted. |
| 17 | Companies Act 2013 s.128 and Companies (Accounts) Rules 2014 r.3 (ca2013.com compilation, "valid as on" Aug 2026) | https://ca2013.com/128-books-of-account-etc-to-be-kept-by-company/ | Secondary compilation of the statute. s.128(5): 8 financial years; r.3(1) audit-trail proviso; r.3(5) backups on servers in India (the page says "periodic"; check whether the 2022 amendment made it "daily"). |
| 18 | Taxmann, "Challenges in implementation… accounting software with audit trail", 10 May 2023 (updated 3 Jan 2024) | https://www.taxmann.com/post/blog/challenges-in-implementation-and-application-of-accounting-software-with-audit-trail/ | Secondary. Effective date 1 Apr 2023; r.11(g) auditor reporting. The official MCA PDF was not reachable. |

## Payments

| # | Source | URL | Quality note |
|---|---|---|---|
| 19 | PCI SSC blog, "FAQ clarifies new SAQ A eligibility criteria for e-commerce merchants" (FAQ 1588), 28 Feb 2025 | https://blog.pcisecuritystandards.org/faq-clarifies-new-saq-a-eligibility-criteria-for-e-commerce-merchants | Primary (standards body). The criterion applies to embedded forms (iframes), not redirects; two ways to meet it. The SAQ A PDF itself (gated) was not read. |
| 20 | Razorpay, Security: shared responsibility model | https://razorpay.com/docs/security/shared-responsibility-model.md | Primary (vendor docs). Razorpay is PCI DSS L1; the merchant protects the key secret; IP allowlisting is mentioned for RazorpayX payouts. |
| 21 | Razorpay, Webhooks: validate and test | https://razorpay.com/docs/webhooks/validate-test/ | Primary (vendor docs). X-Razorpay-Signature HMAC-SHA256 over the raw body; x-razorpay-event-id for duplicates; out-of-order delivery; old secret for retries. |

## Standards and guidance

| # | Source | URL | Quality note |
|---|---|---|---|
| 22 | NIST CSRC, Role Based Access Control project | https://csrc.nist.gov/projects/role-based-access-control | Primary (NIST; the project page says it is archived). INCITS 359-2004/2012; "Adding Attributes to RBAC". |
| 23 | NIST CSRC, RBAC FAQ | https://csrc.nist.gov/projects/role-based-access-control/faqs | Primary. Core RBAC, Hierarchical RBAC, SSD and DSD components; access granted "only if" role requirements are met, so constraints can be added. |
| 24 | Sandhu, Ferraiolo, Kuhn, "The NIST model for RBAC: towards a unified standard", 26 Jul 2000 (publication page) | https://csrc.nist.gov/pubs/conference/2000/07/26/nist-model-for-rbac-towards-a-unified-standard/final | Primary abstract (flat, hierarchical, constrained, symmetric). The PDF download failed. |
| 25 | NIST SP 800-162, Guide to ABAC (Jan 2014, updated 2 Aug 2019) | https://csrc.nist.gov/pubs/sp/800/162/upd2/final | Primary. Definition of ABAC including environment conditions. |
| 26 | NIST SP 800-53 Rev. 5 control catalog (OSCAL JSON, release 5.2.0, modified 2026-05-11) | https://raw.githubusercontent.com/usnistgov/oscal-content/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json | Primary (NIST machine-readable catalog). Statements extracted for AC-2, AC-2(2)(3)(4)(13), AC-5, AC-6(5)(7)(9)(10), AC-7, AC-12, AT-2, AU-2/3/6/9/9(2)(3)(4)/10/11, CM-3/5, CP-9/9(1), IA-2(1)(2), IA-5(1), PS-4/5/6. |
| 27 | NIST SP 800-63B-4, Authentication and Authenticator Management (final, Aug 2025) | https://pages.nist.gov/800-63-4/sp800-63b.html | Primary. AAL2/AAL3 timeouts, password rules, phishing resistance, syncable authenticators, rate limits. |
| 28 | OWASP ASVS 5.0.0 (May 2025), chapters V2, V3, V6, V7, V8, V13, V14, V16 | https://github.com/OWASP/ASVS/tree/master/5.0/en | Primary (OWASP source repo, raw markdown). Requirement IDs and levels are cited as `ASVS x.y.z (Ln)`. |
| 29 | OWASP Top 10:2025 (A01, A03, A07, A09 read in full; intro list) | https://github.com/OWASP/Top10/tree/master/2025/docs/en (site: https://owasp.org/Top10/2025/) | Primary (OWASP repo, master branch). |
| 30 | OWASP API Security Top 10 2023 | https://owasp.org/API-Security/editions/2023/en/0x11-t10/ (read from github.com/OWASP/API-Security) | Primary. BOLA, BOPLA, BFLA, resource consumption, sensitive business flows. |
| 31 | OWASP Authorization Cheat Sheet | https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html | Primary (OWASP; read from the GitHub markdown). |
| 32 | OWASP Session Management Cheat Sheet | https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html | Primary. Idle 2–5 min (high value) / 15–30 min; absolute 4–8 h; `__Host-` cookies. |
| 33 | OWASP Logging Cheat Sheet | https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html | Primary. Events to log, attributes (when/where/who/what), data to exclude, protection. |
| 34 | OWASP Logging Vocabulary Cheat Sheet | https://cheatsheetseries.owasp.org/cheatsheets/Logging_Vocabulary_Cheat_Sheet.html | Primary. Event names (authn_*, authz_*, user_*, sensitive_*, privilege_*). |
| 35 | OWASP Multifactor Authentication Cheat Sheet | https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html | Primary. Resetting and changing MFA factors. |
| 36 | OWASP Secrets Management Cheat Sheet | https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html | Primary. Secrets lifecycle, auditing, break-glass, backup and restore tests. |
| 37 | OWASP Transaction Authorization Cheat Sheet | https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html | Primary. What You See Is What You Sign, server-side enforcement, unique short-lived authorisations. |
| 38 | CISA, "Implementing Phishing-Resistant MFA" fact sheet, Oct 2022 | https://www.cisa.gov/sites/default/files/publications/fact-sheet-implementing-phishing-resistant-mfa-508c.pdf | Primary (US government). "The only widely available phishing-resistant authentication is FIDO/WebAuthn." |
| 39 | Microsoft Learn, "Manage emergency access accounts in Microsoft Entra ID" | https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/security-emergency-access | Vendor guidance, used as an industry break-glass pattern: two or more accounts, phishing-resistant keys, alert on every use, check at least every 90 days. |

## Frameworks and libraries (ExamLeaf stack)

| # | Source | URL | Quality note |
|---|---|---|---|
| 40 | Django 6.0 docs, Customizing authentication: handling object permissions | https://docs.djangoproject.com/en/6.0/topics/auth/customizing/ | Primary. "No implementation for it in the core" for object permissions. |
| 41 | Django 6.0 docs, Using the authentication system: permission caching | https://docs.djangoproject.com/en/6.0/topics/auth/default/ | Primary. |
| 42 | Django 6.0 docs, Sessions (`set_expiry`, `SESSION_SAVE_EVERY_REQUEST`, `cycle_key`) | https://docs.djangoproject.com/en/6.0/topics/http/sessions/ | Primary. |
| 43 | Django 6.0 docs, Content Security Policy (`SECURE_CSP`, report-only) | https://docs.djangoproject.com/en/6.0/ref/csp/ | Primary. |
| 44 | Django 6.1 release notes | https://docs.djangoproject.com/en/dev/releases/6.1/ | Primary. `Permission.user_perm_str`; PBKDF2 at 1.5M iterations. |
| 45 | Django REST framework, Permissions | https://www.django-rest-framework.org/api-guide/permissions/ | Primary. Object permissions are not applied to lists or creates; DjangoModelPermissions needs a view permission added for GET. |
| 46 | django-allauth docs, Account configuration | https://docs.allauth.org/en/latest/account/configuration.html | Primary. `ACCOUNT_REAUTHENTICATION_TIMEOUT` (300 s), `ACCOUNT_EMAIL_NOTIFICATIONS`. |
| 47 | django-allauth docs, MFA configuration | https://docs.allauth.org/en/latest/mfa/configuration.html | Primary. `MFA_TRUST_ENABLED` (14-day trust cookie), recovery codes. |
| 48 | django-allauth 65.19.7 source, installed in examleaf-web/.venv: `account/internal/flows/reauthentication.py`, `mfa/stages.py`, `headless/base/views.py`, `headless/base/response.py`, `usersessions/models.py`, `headless/spec/doc/openapi.yaml` | (local) | Primary (the code ExamLeaf runs). Behaviour of `did_recently_authenticate`, the MFA stage after every login method, the headless reauthentication 401 and endpoints, `UserSession.end()`. |
| 49 | django-simple-history docs, Common issues (bulk and queryset updates) | https://django-simple-history.readthedocs.io/en/latest/common_issues.html | Primary. |
| 50 | django-axes docs, Configuration | https://django-axes.readthedocs.io/en/latest/4_configuration.html | Primary, but the text only partly rendered (tables missing). |
| 51 | django-hijack docs, Customization (permission check, signals) | https://django-hijack.readthedocs.io/en/stable/customization/ | Primary. |
| 52 | PyPI JSON metadata: django-guardian 3.5.0 (2026-09-12), rules 3.5 (2024-09-02), django-hijack 3.7.9, django-auditlog 3.4.1, djangorestframework-api-key 3.1.0, django-pghistory 3.9.2, django-waffle 5.0.0, pip-audit 2.10.1 | https://pypi.org/pypi/{name}/json | Primary metadata. Django classifiers: none lists 6.1; guardian, hijack and pghistory list 6.0. |
| 53 | djangorestframework-simplejwt 5.5.1 source (`settings.py`, `authentication.py`) and Django 6.1.2 source (`contrib/auth/backends.py`), both installed in examleaf-web/.venv | (local) | Primary (the code ExamLeaf runs). simplejwt: `CHECK_USER_IS_ACTIVE` True, `CHECK_REVOKE_TOKEN` False by default. Django: `ModelBackend.user_can_authenticate` rejects `is_active=False`. |
| 54 | Google Identity, OpenID Connect (`hd` and `sub` claims) | https://developers.google.com/identity/openid-connect/openid-connect | Primary. Check the ID token's `hd`; `sub` is the identifier, not `email`. |
| 55 | Next.js docs, Authentication guide (shows 16.4.0 as the latest) | https://nextjs.org/docs/app/guides/authentication | Primary. Optimistic checks in Proxy versus secure checks in a Data Access Layer; Server Actions and Route Handlers are public endpoints. |
| 56 | GitHub advisory GHSA-f82v-jwr5-mffw / CVE-2025-29927, Next.js middleware authorization bypass, 21 Mar 2025 | https://github.com/vercel/next.js/security/advisories/GHSA-f82v-jwr5-mffw | Primary (read via the GitHub advisories API). |
| 57 | PostgreSQL docs, Privileges (current) | https://www.postgresql.org/docs/current/ddl-priv.html | Primary. An owner can always re-grant; the right to modify or destroy belongs to the owner. |
| 58 | Cloudflare R2 docs, Bucket locks | https://developers.cloudflare.com/r2/buckets/bucket-locks/ | Primary. Prevent deletion or overwrite for a period or indefinitely. |
| 59 | Caddy docs, Request matchers (`remote_ip`, `client_ip`) | https://caddyserver.com/docs/caddyfile/matchers | Primary. |
| 60 | Google Workspace Admin Help, Email sender guidelines | https://support.google.com/a/answer/81126 | Primary (provider policy). SPF, DKIM, DMARC; spam rate under 0.3%; one-click unsubscribe for 5,000+ messages a day. |
| 61 | Sentry docs, Server-side data scrubbing | https://docs.sentry.io/security-legal-pii/scrubbing/ | Primary; read only for the overview. |
| 62 | ExamLeaf repository (examleaf-web, branch design/answer-script): `accounts/roles.py`, `accounts/models.py`, `examleaf/middleware.py`, `examleaf/settings.py`, `examleaf/api_settings.py`, `Caddyfile`, `docker-compose.yml`, `RUNBOOK.md`, `README.md` | (local) | Primary for the current state. Read 2026-10-09; nothing changed. |

## Not reached, or only through search snippets (claims marked in the text)

- The official copy of the Act's commencement notification G.S.R. 843(E): only via [6].
- Any MeitY amendment to the DPDP Rules after Nov 2025: none found ([7], [8]). The web-search budget ran out before a last gazette check.
- PCI DSS v4.0.1 SAQ A (gated PDF), PCI DSS req. 7.2.4 (six-monthly access review): not read and not cited.
- TRAI TCCCPR 2018 (SMS DLT): the official PDF did not download. DLT is referred to only through the repo's own RUNBOOK.
- MCA notifications on the audit trail (24 Mar 2021, deferral 31 Mar 2022): via [17] and [18] only.
