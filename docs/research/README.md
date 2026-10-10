# Research archive

![Status](../assets/badges/status-archive.svg) ![For the owner](../assets/badges/audience-owner.svg) ![For developers](../assets/badges/audience-developers.svg)

The research runs behind the plans, each kept in its own folder named by date and topic so that it can be re-read
later without the chat history. It is for whoever revisits a plan's choice and wants the evidence; the reports are
archives and stay as they were written.

Each folder holds:

- `report.md` — the synthesised report: summary, findings with confidence, evidence and sources, caveats, open questions.
- `findings.json` — the same report as data (findings, refuted and unverified claims, sources, run statistics).
- `sources.md` — every web source fetched, with its quality rating and the angle that found it.
- `claims.jsonl` — every claim extracted from the sources with the verifiers' votes (where the run's journal is available).
- `journal.jsonl` — the raw agent log of the run (search, fetch, verify, synthesis), for audit.

| Folder | Question | Used for |
|---|---|---|
| `2026-10-08-examleaf-platform-ideas/` | Sealed sample papers, QR-gated free solutions, 15-minute revision videos (ideas 4 and 5 produced no surviving claims in this run) — 107 agents, 121 claims extracted, 23 confirmed | the ExamLeaf platform plan (`docs/examleaf-platform-plan.md`) |
| `2026-10-08-ai-answer-checker/` | OCR for handwritten Assamese/Bengali/Hindi/English with maths, grading models on OpenRouter and elsewhere, costs per paper, data residency — 105 agents, 115 claims extracted | `docs/examleaf-ai-checker-design.md` and the platform plan |
| `2026-10-08-production-features/` | Library and provider verification for the production features of the website: allauth phone OTP, login by code, passkeys and Google; Indian SMS providers and TRAI DLT; Cloudflare R2 vs S3 Mumbai; django-pictures; Amazon SES through Anymail with a suppression list; Shiprocket/Delhivery vs tracking links; the PIN-code directory; PWA; SEO structured data — one Sonnet researcher, settings run in a scratch project (report.md only; no claim journal) | `docs/examleaf-phase5-plan.md` |
| `2026-10-09-admin-control-panel/` | Everything the Admin Control Panel needs, one report per area (no claim journal; each report cites a numbered `sources-*.md`): `inventory.md` (what the backend already does for staff), `research-lms-crm-cms.md` (learning, content, CRM and marketing, support, analytics, admin UX; 221 items, 449 sources), `research-rbac-security.md` (RBAC, approvals, audit, sessions, DPDP and CERT-In duties, user and staff management), `research-commerce-gst.md` (orders, inventory, accounting, invoicing and GST after the 22 Sep 2025 rate changes, consumer and publisher law; 91 sources), `research-b2b-predictive.md` (distributors, schools, teachers, predictive analytics under the DPDP children's rules; 83 sources), `research-integrations.md` (Shiprocket, Delhivery and India Post; Razorpay, WhatsApp and SMS, SES, Google sign-in, Tally and Zoho, GST APIs, DigiLocker, the PIN directory, Sentry, R2, analytics; how Stripe, Shopify, Zapier, Svix build integration pages; 315 sources), `research-erpnext.md` (ERPNext v16: versions, why it needs MariaDB and not PostgreSQL, the Helm chart and frappe_docker, India Compliance and the other apps, the sync design, operations, security, costs; 127 sources) | `docs/examleaf-admin-control-panel-plan.md` |

## What each run produced

- [2026-10-08-examleaf-platform-ideas](2026-10-08-examleaf-platform-ideas/report.md): the report with its data,
  [sources](2026-10-08-examleaf-platform-ideas/sources.md), claims and journal; 23 of its 121 claims confirmed, behind
  the platform plan.
- [2026-10-08-ai-answer-checker](2026-10-08-ai-answer-checker/report.md): the report with its data,
  [sources](2026-10-08-ai-answer-checker/sources.md), claims and journal; the evidence of the checker's design and
  cost model.
- [2026-10-08-production-features](2026-10-08-production-features/report.md): one report and nothing else, the
  library and provider checks behind the Phase 5 plan.
- [2026-10-09-admin-control-panel](2026-10-09-admin-control-panel/inventory.md): the inventory of what the backend did
  for staff and six reports, each with its numbered sources
  ([learning, content, CRM](2026-10-09-admin-control-panel/research-lms-crm-cms.md),
  [roles and security](2026-10-09-admin-control-panel/research-rbac-security.md),
  [commerce and GST](2026-10-09-admin-control-panel/research-commerce-gst.md),
  [B2B and predictions](2026-10-09-admin-control-panel/research-b2b-predictive.md),
  [integrations](2026-10-09-admin-control-panel/research-integrations.md),
  [ERPNext](2026-10-09-admin-control-panel/research-erpnext.md)); the Admin Control Panel's plan.

## Elsewhere

The syllabus and market research for the Assam Class 12 books lives in the books repository (LazyIndianBook/Class-12-Assam, `docs/research/2026-09-29-assam-hs-syllabus-and-market/`). Export a workflow run with `python3 docs/research/research_export.py <workflow transcript dir> <folder> --question "…"`.

The design research for the website redesign (ui-ux-pro-max, shadcn/ui, ThreeUI, Aceternity, animmasterlib, designprompts, design.dev, superdesign) is in `docs/design/resources-brief.md`; the decided direction and component vocabulary in `docs/design/direction.md`.

## Related documents

- [The platform plan](../examleaf-platform-plan.md): written from the first two runs and the books' syllabus
  research.
- [The AI answer checker](../examleaf-ai-checker-design.md): its design and cost model, from the second.
- [The Phase 5 plan](../examleaf-phase5-plan.md): from the production features run.
- [The panel's plan](../examleaf-admin-control-panel-plan.md): from the Admin Control Panel run.
- [The design resources brief](../design/resources-brief.md): the redesign's research.
