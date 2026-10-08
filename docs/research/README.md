# Research archive

Every research run is kept in its own folder, named by date and topic, so that it can be re-read later without the chat history. Each folder holds:

- `report.md` — the synthesised report: summary, findings with confidence, evidence and sources, caveats, open questions.
- `findings.json` — the same report as data (findings, refuted and unverified claims, sources, run statistics).
- `sources.md` — every web source fetched, with its quality rating and the angle that found it.
- `claims.jsonl` — every claim extracted from the sources with the verifiers' votes (where the run's journal is available).
- `journal.jsonl` — the raw agent log of the run (search, fetch, verify, synthesis), for audit.

| Folder | Question | Used for |
|---|---|---|
| `2026-09-29-assam-hs-syllabus-and-market/` | Assam HS 2nd Year 2026-27: syllabus changes, exam pattern, NCERT books, previous papers, competitor sample-paper books | the production plan (`PLAN.md`) and the subject specs |
| `2026-10-08-examleaf-platform-ideas/` | Sealed sample papers, QR-gated free solutions, 15-minute revision videos (ideas 4 and 5 produced no surviving claims in this run) — 107 agents, 121 claims extracted, 23 confirmed | the ExamLeaf platform plan (`docs/examleaf-platform-plan.md`) |
| `2026-10-08-ai-answer-checker/` | OCR for handwritten Assamese/Bengali/Hindi/English with maths, grading models on OpenRouter and elsewhere, costs per paper, data residency — 105 agents, 115 claims extracted | `docs/examleaf-ai-checker-design.md` and the platform plan |
| `2026-10-08-production-features/` | Library and provider verification for the production features of the website: allauth phone OTP, login by code, passkeys and Google; Indian SMS providers and TRAI DLT; Cloudflare R2 vs S3 Mumbai; django-pictures; Amazon SES through Anymail with a suppression list; Shiprocket/Delhivery vs tracking links; the PIN-code directory; PWA; SEO structured data — one Sonnet researcher, settings run in a scratch project (report.md only; no claim journal) | `docs/examleaf-phase5-plan.md` |

The web pages and PDFs cited by the first run are saved under `docs/web/` (index: `docs/web/SOURCES.md`); official board documents under `docs/assam/`.

The design research for the website redesign (ui-ux-pro-max, shadcn/ui, ThreeUI, Aceternity, animmasterlib, designprompts, design.dev, superdesign) is in `docs/design/resources-brief.md`; the decided direction and component vocabulary in `docs/design/direction.md`.
