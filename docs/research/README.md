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
| `2026-10-08-examleaf-platform-ideas/` | Sealed sample papers, QR-gated free solutions, 15-minute revision videos, question banks for state boards, AI answer-sheet checking — evidence and recommendations | the ExamLeaf platform plan (`docs/examleaf-platform-plan.md`) |
| `2026-10-08-ai-answer-checker/` | OCR for handwritten Assamese/Bengali/Hindi/English with maths, grading models on OpenRouter and elsewhere, costs per paper, data residency, existing products | the AI checker design and cost model in the platform plan |

The web pages and PDFs cited by the first run are saved under `docs/web/` (index: `docs/web/SOURCES.md`); official board documents under `docs/assam/`.
