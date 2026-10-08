# ExamLeaf platform

The website, API and revision course of ExamLeaf LLP (published by Bhaben Bhuyan): free worked solutions behind the QR code printed on every sample paper, student accounts, the book shop with Razorpay and cash on delivery, GST invoices, the app-based revision course, the staff admin, and the REST API for the mobile app. The books themselves (questions, solutions, printed PDFs) live in the companion repository `LazyIndianBook/Class-12-Assam`; the website imports their papers.

| Path | What it holds |
|---|---|
| `examleaf-web/` | the Django 6.1 backend: REST API v1 (`/api/v1/`, OpenAPI at `/api/docs/`), allauth headless sign-in (`/_allauth/`), the admin, Razorpay and Anymail webhooks, media, QR PNGs, the staff clip player, emails and PDFs, Celery workers, Docker compose with PostgreSQL, Redis, Caddy; see its `README.md`, `DEPLOYMENT.md`, `RUNBOOK.md`, `API.md`, `CHANGELOG.md`, `SECURITY_REVIEW*.md` |
| `examleaf-frontend/` | the Next.js 16 frontend (TypeScript, App Router, Tailwind 4, restyled shadcn components, typed OpenAPI client, allauth headless client): public pages, the shop, checkout and orders, sign-in and account, the revision course page and learning dashboard; see its `README.md` |
| `docs/design/` | the redesign: resources brief, direction and component vocabulary, component spec, token layer, motion language, coverage matrix, parity map, Lighthouse and accessibility audits, before/after screenshots |
| `docs/examleaf-platform-plan.md`, `docs/examleaf-ai-checker-design.md`, `docs/examleaf-phase5-plan.md`, `docs/examleaf-phase6-plan.md`, `docs/examleaf-frontend-architecture.md`, `docs/examleaf-phase8-nextjs-plan.md` | the plans and decisions, each with a Status section filled by the builders |
| `docs/research/` | the archived research runs behind the plans (platform ideas, AI answer checker, production features), indexed in `docs/research/README.md` |
| `.github/workflows/ci.yml` | on every push: ruff and tests on PostgreSQL, the Docker image build and smoke test, a dependency audit, and the frontend's lint, types, unit tests, build and Playwright journeys |

## Running it locally
Backend: `cd examleaf-web && python3.14 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python manage.py migrate && .venv/bin/python manage.py import_papers --all --source ../../Class\ 12/production && .venv/bin/python manage.py seed_shop --stock 100`, then `SITE_URL=http://localhost:3000 CSRF_TRUSTED_ORIGINS=http://localhost:3000 USE_X_FORWARDED_HOST=1 .venv/bin/python manage.py runserver 8100` (check `import_papers --help` for the source option it expects). Frontend: `cd examleaf-frontend && npm ci && npm run dev` with the variables from its `.env.example`. Tests: `examleaf-web/.venv/bin/python -m pytest` and `cd examleaf-frontend && npm test && npm run test:e2e`.

## Deployment
One machine with Docker compose (`examleaf-web/docker-compose.yml`): PostgreSQL 17, two Redis instances, the Django web service, Celery worker, beat and media worker, the Next.js frontend, Caddy with automatic TLS routing the Django prefixes to the backend and every other path to the frontend. `examleaf-web/DEPLOYMENT.md` lists every setting and the accounts to open (Razorpay, MSG91 with DLT, Amazon SES, Google OAuth, Cloudflare R2, Firebase, Turnstile); `RUNBOOK.md` the operating procedures.

Repository created on 8 October 2026 by splitting the platform paths, with their history, out of `LazyIndianBook/Class-12-Assam`.
