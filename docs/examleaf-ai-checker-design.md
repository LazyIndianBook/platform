# ExamLeaf AI answer-sheet checker — design and cost model

*Written 8 October 2026 from the research run archived in `docs/research/2026-10-08-ai-answer-checker/` (105 agents, 53 sources, 115 claims verified by three-vote adversarial review). Prices and model names are a snapshot of 7–8 October 2026 and change weekly; the design is written so that models can be swapped without rework.*

## 1. What the checker does

A student photographs the pages of a hand-written answer to one of our sample papers with a phone. The app returns, within minutes, a word-for-word transcript of what was written, an estimated mark per question against our marking scheme (the same step tables that the Solutions book and the website use), a short comment per question in the student's language, and a confidence level. Answers the system is unsure of go to a teacher's review queue; the student can appeal any mark.

**Practice only.** Marks are labelled as estimates. Nothing the checker produces counts for anything beyond the student's own practice. This is a product decision forced by the evidence below, not a temporary limitation.

## 2. What the evidence says (short version)

| Question | Finding | Confidence |
|---|---|---|
| Can machines read handwritten Assamese? | Never measured on exam sheets. The best published figure is 71.6 % word accuracy (Gemini 3.1 Pro) on word-block images; a recogniser trained for the job reaches about 85 % on word crops. Treat Assamese reading as unproven until we test it ourselves. | medium |
| Hindi and Bengali handwriting? | 3–7 % word error on clean prose pages with Sarvam OCR or Gemini Flash; 17–25 % on another benchmark. Rankings do not carry over between datasets. | medium |
| Which commercial OCR APIs can we use? | Only Sarvam Vision and Google (Gemini, Cloud Vision, Document AI) are realistic for Assamese, Bengali and Hindi. AWS Textract and Azure cannot read Assamese or Bengali. Google Document AI handwriting covers Bengali and Hindi but does not list Assamese. | high |
| Do the Chinese OCR specialists help? | No. On handwriting benchmarks (Chinese, English, maths) DeepSeek-OCR, PaddleOCR-VL, MinerU and dots.ocr score below general vision models such as Qwen3-VL and Gemini. There is no Indic evidence for them at all. | medium |
| Handwritten maths? | Poor for every model tested: about 55 % character error on long multi-line working. | medium |
| The biggest hidden danger | Generative readers silently *correct* what the student wrote: 63–79 % of their errors are of this kind, 88–95 % on formulas. A transcript can turn a wrong answer into a right one before marking. | high |
| Cheapest capable grading models on OpenRouter | GLM-5.3-Flash ($0.15/$0.50 per million tokens; $0.06/$0.20 in batch; intelligence index 41.8). Claude Haiku 5.5 and GPT-6 Luna cost the same ($0.10/$0.50); Gemini 3.8 Flash is dearer ($0.75/$3.75). "Chinese means cheaper" no longer holds. No model has verified evidence on exam grading or on Assamese. | high |
| Data protection on OpenRouter | Default routing can send children's answer sheets to providers that store prompts or train on them. We must set `zdr: true`, `data_collection: "deny"` and an explicit provider allow-list. The cheapest Qwen Flash models have no zero-retention endpoint. OpenRouter cannot keep data in India. | high |
| Cost | About ₹5.5 per 12-page paper for the recommended two-stage pipeline (₹2.7 in batch, ₹8.4 with 20 % of pages re-read by a stronger model). Teacher review of six answers at ₹300/hour costs about ₹15 per paper, more than all the AI. | low (model-based) |

Full findings, with the numbers behind each cell and the claims that failed verification, are in `docs/research/2026-10-08-ai-answer-checker/report.md`.

## 3. Architecture: two stages, transcript first

```
phone photos ──► page pre-processing ──► STAGE 1: reader ──► transcript (per question, [?] for unreadable)
 (12 pages)       (deskew, crop, order)    Gemini 3.8 Flash          │ shown to the student beside the page image
                                            ↓ low confidence         ▼
                                           Gemini 3.1 Pro        STAGE 2: grader ──► marks, comments, confidence per question
                                           (re-read)             GLM-5.3-Flash (or Gemini 3.8 Flash / Claude Haiku 5.5)
                                                                     │ marking scheme from our Solution table
                                                                     ▼
                                                       confidence gate ──► teacher review queue ──► final estimate
                                                                               (low confidence, diagrams, chemical equations, appeals)
```

Why two stages rather than grading straight from the image:
- the silent-correction problem can only be caught when the transcript is visible; the student or a teacher can flag "I did not write that";
- the reader and the grader can be replaced independently when models expire (Gemini 2.5 and most Qwen3-VL listings expire this month);
- it costs only a few rupees more per paper.

Reader prompt rules (these are what the evidence says matters): transcribe word for word; keep the student's mistakes; write `[?]` for unreadable text instead of guessing; never add steps; split the output by question label; keep the Assamese letters ৰ and ৱ (readers trained on Bengali substitute র and ব, and then marking-scheme keywords do not match).

Grader prompt rules: grade only what is in the transcript; apply the step table literally and award the marks the table awards; give a confidence of low when the transcript contains `[?]` in the answer, when a diagram or chemical equation carries marks, or when the answer is far from every accepted alternative; write the comment in the language the student chose (the grader writes Assamese, Bengali or Hindi directly; translation through Sarvam would cost ₹15–25 per paper more).

## 4. Model choices and fallbacks

| Role | First choice | Why | Fallbacks |
|---|---|---|---|
| Reader (all pages) | Gemini 3.8 Flash, `media_resolution: high` (1,120 tokens per page) | near the top on every handwriting test in the research; Gemini 2.5 Flash was the most faithful transcriber in the "When VLMs fix students" study | Sarvam Vision 2.1 Digitise (Indian vendor, ₹0.50/page, handwriting accuracy unpublished); self-hosted Bodhan IndicOCR (0.8B, gated licence) |
| Reader (re-read of low-confidence pages) | Gemini 3.1 Pro | best measured reader of handwritten Assamese (71.6 %), preview model | none needed; skip re-read if unavailable |
| Grader | GLM-5.3-Flash through OpenRouter, reasoning effort set explicitly to *low* or *medium* (its default is maximum and bills about 47K reasoning tokens per task) | best-value Chinese model with 29 zero-retention endpoints and a batch price | Gemini 3.8 Flash; Claude Haiku 5.5; GPT-6 Luna — all in the same price band; choose by agreement with teachers' marks, not by index score |
| Avoid | DeepSeek's own endpoint (trains on data); Qwen3.7/3.8-Flash (no zero-retention endpoint; price tier jumps above 32K tokens); Kimi K3 ($15 per million output tokens); Gemini 2.5 and Qwen3-VL listings (expiring); Textract and Azure (no Assamese or Bengali); Chinese OCR specialists for Indic scripts (no evidence, weaker on handwriting) | | |

Pin exact model versions in settings. Keep a fixed test set and re-run the accuracy gate (section 6) whenever a model is swapped.

## 5. Routing and data protection

- **Route:** OpenRouter with `zdr: true`, `data_collection: "deny"`, an explicit `provider.order` allow-list (for GLM-5.3-Flash: Z.AI, DeepInfra, Together or Fireworks; for Gemini: Google), and account-wide ZDR switched on. These settings can only tighten routing, never loosen it.
- **What ZDR does not give:** data residency in India. OpenRouter's in-region routing covers only the EU and US. If legal advice requires the data to stay in India, the India-resident options are Google Vertex AI or Document AI in `asia-south1` (Mumbai), Sarvam's API directly, or self-hosting open weights (IndicOCR, Qwen3-VL) on an Indian GPU cloud (E2E Networks, Yotta, AWS or Google Mumbai) — self-hosting costs were not established and need a separate estimate.
- **DPDP Act 2023:** most of our students are under 18. The Act requires verifiable parental consent before processing a child's data and lets the government restrict transfers to named countries; its Rules were notified in late 2025 and come into force in phases. The platform already records parental consent (`accounts.ConsentRecord`). Before launch: extend the privacy notice to name AI processing of handwriting by named processors abroad, record a separate consent event for it, and have a lawyer confirm the wording and the transfer position. Students' sheets may be used to fine-tune models only if the consent covers it.
- **Retention:** keep page images and transcripts only as long as the student keeps the attempt; the Phase-1 account deletion must purge uploads; never log image bytes.

## 6. Accuracy gate before launch (and before every model swap)

1. Collect 100–200 papers per subject and language, photographed by students on their own phones, marked by experienced Assam board examiners, with teacher-checked transcripts of at least 50 pages per language.
2. Measure the reader: character and word error rate per language; the rate of silent corrections (compare transcript with the ground truth on exactly the words the student got wrong); the handling of ৰ/ৱ, crossed-out work, diagrams and chemical equations. Run Gemini 3.8 Flash, Gemini 3.1 Pro, Sarvam Vision 2.1 and IndicOCR head to head.
3. Measure the grader on teacher-checked transcripts: exact agreement, agreement within one mark, quadratic weighted kappa, leniency (mean signed difference) and bias by language and question type. Try grading straight from the image as a control.
4. Release only if, on the held-out set, within-one-mark agreement is at least 85 % for 1–3 mark questions and the mean signed difference is within ±0.3 marks; everything below the gate goes to teacher review by default.
5. Publish the gate results to teachers in the admin and keep the test set frozen (pin the Sarvam benchmark commit `84ce7ce` if it is reused).

## 7. Cost model

Assumptions (from the research; real costs may be two to three times higher or lower): 12 pages per paper; marking scheme about 4,000 tokens plus 1,000 of instructions; transcript about 10,000 tokens (Indic scripts use many tokens per word); 1,120 image tokens per page on Gemini; 3,000 visible output tokens plus 0 / 10K / 40K reasoning tokens for low / medium / high effort; ₹96.7 per US dollar.

| Pipeline | Per paper (real time) | Per paper (batch) |
|---|---|---|
| Reader Gemini 3.8 Flash + grader GLM-5.3-Flash, medium reasoning (recommended) | ₹5.5 | ₹2.7 |
| Same, with 20 % of pages re-read by Gemini 3.1 Pro | ₹8.4 | about ₹5 |
| Single step, Gemini 3.8 Flash reads and grades from the images, low / medium / high reasoning | ₹2.4 / ₹6.1 / ₹16.9 | ₹1.2 / ₹3.0 / ₹8.5 |
| Single step, GLM-5.3-Flash from the images | ₹0.5 / ₹1.0 / ₹2.4 | ₹0.2 / ₹0.4 / ₹1.0 |
| Single step, Gemini 3.1 Pro | ₹7 / ₹19 / ₹53 | — |
| Reader only: Sarvam Digitise / Google Document AI / Gemini 3.8 Flash | ₹6.0 / ₹1.7 / ₹4.6 | — |
| Teacher review, 6 of 30 answers at 30 s each, ₹300 per hour | about ₹15 | — |

Per student per year, at 20 papers: ₹55–₹170 of AI cost with the recommended pipeline. Pricing the feature: a ₹299 annual add-on covers the AI cost with margin only if teacher review is capped (for example two reviewed papers per month) or paid separately.

Cost traps found in the research: prompt-size tiers bill the whole request at the higher rate (12 Gemini pages plus a 5K prompt is 35.7K tokens, past Qwen's 32K line, 3.4 times the price); GLM-5.3-Flash's default reasoning effort is maximum; some providers charge by time of day; Sarvam Digitise allows 10 pages per job and 10 requests per minute (about 300 papers per hour per account) — exam-season peaks need batch mode or enterprise limits.

## 8. What to build in the platform (Phase 5)

- `aichecker` app: `AnswerSheetUpload` (exists as a placeholder) → `Page` (image, order, pre-processing status), `Transcript` (per question, model, confidence, flags), `Grading` (per question: marks, comment, confidence, model, prompt version), `ReviewTask` (teacher queue, SLA, outcome), `Appeal`. Every row records the model version and prompt version used.
- Provider adapters behind one interface: `OpenRouterProvider` (zdr, deny, allow-list, exact model ids, batch mode), `GeminiDirectProvider` (Vertex `asia-south1` for the India-resident option), `SarvamProvider`. Settings-driven; no provider hard-coded in views.
- Celery pipeline with retries and idempotency keys; a daily budget cap per student and per day in rupees; a kill switch.
- Teacher review UI (role TEACHER verified by staff; CONTENT_EDITOR can edit marking schemes); student UI showing the page image beside the locked transcript, marks as estimates, a confidence badge, and an appeal button.
- Evaluation command: runs the accuracy gate on the frozen test set and writes a report that must pass before the feature flag can be enabled in production.
- REST endpoints under `/api/v1/checker/` for the mobile app (upload, status, result, appeal), following the API conventions of Phase 3.

## 9. Risks the founder may not have considered

1. **Silent correction inflates marks** — the single biggest technical risk; mitigated only by a visible, locked transcript and teacher sampling.
2. **Model churn** — 32 OpenRouter listings expire within weeks of this writing; accuracy measured one month may not hold the next.
3. **Unsafe default routing** — without `zdr`/`deny` settings, children's handwriting reaches providers that store or train on it.
4. **Price cliffs and runaway reasoning** — tier jumps and default maximum reasoning can multiply the bill.
5. **Unmeasured Assamese, diagrams and chemistry** — every published figure is a stand-in for our real input.
6. **Vendor benchmarks** — the Indic figures come from vendors and have been rewritten; the only numbers to trust are our own.
7. **Throughput at exam season** — per-account rate limits; plan batch processing and a queue with expected-time messaging.
8. **Gaming** — if transcripts were editable and marks counted for anything, students could type what they did not write; lock the transcript and show the image.
9. **Licensing** — Bodhan IndicOCR is under a custom gated licence, not an open-source one; check commercial terms before self-hosting.
10. **Trust** — teachers and boards have not been asked; frame the feature as a practice aid, publish the gate results, and never present marks as official.

## 10. Open questions to answer with our own data

- Character and word error rates, and silent-correction rates, of the candidate readers on 100–200 of our own Assamese, Bengali and Hindi pages.
- Agreement of each grader with Assam board examiners by question type, language and tier; image-direct grading versus transcript-first.
- The exact DPDP requirements for processing minors' handwriting abroad, and the per-paper cost of the India-resident options.
- What existing AI checkers (Indian startups, Gradescope-style tools, board pilots) report, and what boards and teachers' bodies have said.
