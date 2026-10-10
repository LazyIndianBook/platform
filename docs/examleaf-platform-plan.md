# ExamLeaf — product and platform plan

![Component](assets/badges/component-platform.svg) ![Status](assets/badges/status-plan.svg) ![For the owner](assets/badges/audience-owner.svg)

The product and platform plan of 8 October 2026: the evidence behind ExamLeaf's first products, the product line and the
roadmap, the platform, the costs and risks, and what to do next, in order. It is for the founder and whoever plans the
next product; it is kept as written, and the [Changelog](../examleaf-web/CHANGELOG.md) records what has been built
since.

*8 October 2026. Written from three verified research runs (archived in `docs/research/`), the printed books already produced, and the platform being built in `examleaf-web/`. Where the evidence stops and my own judgement begins, the text says so.*

## 1. Summary, and what I think

ExamLeaf's first products are right: exam-pattern practice papers in three tiers, built on the Board's own pattern. The learning research is unusually clear that this kind of practice works — regular practice testing raises achievement by about half a standard deviation across 222 classroom studies, the effect is larger in high school, it is larger when the practice matches the real exam's format, and it is larger still when students get corrective feedback. Those three conditions are exactly what the ExamLeaf books provide, so the core product has strong evidence behind it.

The five new ideas sort into three groups:

| Idea | Evidence says | My recommendation |
|---|---|---|
| Sealed papers | Precedent exists (Educart seals 2 of 15 papers as "pre-board" sets; Korea's EBS sells envelope mock exams every year). The seal itself is untested; the research rewards exam-pattern fidelity and feedback, not stakes or packaging. Printing cost, bookshop browsing and returns were not verified. | Do it in a limited form: seal the last two or three papers of each book as a loose "pre-board pack" with blank answer sheets, keep the rest browsable. Get printer and bookseller quotes first. Spend the real effort on the exam-pattern fidelity we already have. |
| Solutions behind QR + registration | Three problems: it weakens the feedback that drives the practice benefit (worst for weak students); from about 13 May 2027 it makes ExamLeaf a fiduciary of children's data needing identity-checked parental consent with no publisher exemption; in rural Assam most Class 10 students use a parent's phone and only about half can complete a simple web task. | Change the design: print a compact answer key in every book; make the full step-by-step solutions reachable from the QR code **without login**; keep accounts **optional** (for saving records, the AI checker and purchases) and, for under-18s, held by the parent. The platform supports this with one setting (section 4). |
| 15-minute revision videos | Engagement in course logs falls after about 6 minutes whatever the video length; one small experiment says chapter navigation matters more than length; the Assam market leader (PhysicsWallah) draws its audience with 2–12 hour live sessions, while older Assam-medium channels teach in 14–19 minute videos. Untested bet either way. | Pilot before scaling: build each chapter as 2–3 segments of about 6 minutes with a chapter menu and built-in questions linked to the book's papers, publish on YouTube (the digital task rural teenagers complete most often), measure completion and question attempts for a few chapters, then decide on three languages. |
| Question banks and guidebooks for other boards | This run produced no verified claims on market sizes, SCERT/NCERT adoption, copyright or distribution. | Keep the pipeline that produced the Assam books (it is board-agnostic: a spec, a format file, chapter work orders, writers, checkers, readers) and research each board before writing. Class 10 Assam is the natural next step because the distribution network and the brand are already there. |
| AI answer-sheet checker | Reading handwritten Assamese is unproven (best published figure 71.6 % word accuracy); every generative reader silently corrects student mistakes; AI cost is small (about ₹5.5 per paper) but teacher review costs more. | Build it as a practice-only, two-stage pipeline with a visible transcript and a teacher review queue, behind an accuracy gate measured on our own papers. Full design and cost model: `docs/examleaf-ai-checker-design.md`. |

If I had to choose one thing from this research to act on, it is the solutions decision. Registration-gated solutions are the one idea the evidence argues against from three directions at once, and the DPDP deadline makes it urgent: accounts created for the February–March 2027 examinations will still be held when the duties start in May 2027.

## 2. The evidence behind the recommendations

### 2.1 Sealed papers
- Educart's 2026-27 CBSE Class 10 books contain 15 sample papers of which two are "sealed pre-board paper sets with answer sheets" — loose inserts with red seal tabs and blank OMR-style writing sheets, according to buyer photographs (confidence high).
- South Korea's state broadcaster EBS has sold an "envelope mock exam" for the national entrance test every year since at least 2024, at roughly ₹550–750 per subject; private publishers copy the format (high).
- Practice testing: g ≈ 0.50 over 222 studies and 48,478 students; g = 0.66 in high school; repeated testing beats a single test (high). Matching the practice format to the final exam raises the effect from 0.40 to 0.53 (medium). Stakes do not matter (high-stake 0.44 vs low-stake 0.48, not significant), and nothing in the literature tests seals, tear-outs or timed full-length mocks (medium).
- Not verified in this run: cost per copy of perforation, gummed edges, shrink-wrap or sticker seals; the effect on bookshop browsing and returns; binding strength. Ask two printers and three booksellers before the next print run.

### 2.2 Solutions behind QR and registration
- Feedback: the testing effect is 0.54 with corrective feedback against 0.37 without; for students scoring 50 % or below the effect without feedback was close to nil in one meta-analysis (medium). Anything that stops a weak student from seeing the solution removes the part of practice that matters most for them.
- The DPDP Rules 2025 (G.S.R. 846(E), 13 November 2025) bring the children's provisions into force about **13 May 2027**: verifiable parental consent before any processing of an under-18's data, with the fiduciary obliged to check that the consenting adult is identifiable (identity details already held, voluntarily provided details, or a DigiLocker-type token — no OTP or self-declaration route is listed). The exemptions cover healthcare, educational institutions (for their own teaching), creches and school transport; publishers and ed-tech are not named. Section 9(3) bars tracking, behavioural monitoring and targeted advertising directed at children, and parental consent cannot lift that (high).
- Access: in rural Assam 91 % of households have a smartphone but only about 12 % of 14–16-year-olds own one (girls 11 %, boys 19 %); at 17–18 ownership is 43–66 % depending on the measure. Only about half of 14–16-year-olds could both produce a connected phone and complete a web search; 21–42 % had ever filled in an online form (high).
- Competitors: Oswaal gates a minority of titles with a scratch code plus login tied to the purchased copy, and its live system captures the browser's location — a design out of step with the DPDP regime. No verified evidence on how Arihant, Educart, MTG, S. Chand or Xam Idea deliver digital solutions (high for Oswaal, gap for the rest).
- Copying risk: open solutions will be copied; no evidence was found that this hurts sales, and solutions that are free anyway lose little.

### 2.3 Revision videos
- In 6.9 million edX viewing sessions, students watched a median of about 6 minutes per session whatever the length; the share attempting the follow-up problem fell from 56 % for 0–3 minute videos to 31 % for 12–40 minutes. Adult, self-motivated learners; engagement, not learning (high).
- A 22-person experiment found a chapter menu inside one long video raised learning gain (7.4 vs 5.3) while cutting it into a series did not; length itself was never varied (low).
- PhysicsWallah's NCERT Wallah channel teaches chapters in "One Shot" videos of 1 h 45 min to 4 h 54 min; PW Assam HS Science (opened March 2026) runs 60 live one-shots (median 2 h 05 min) and 11–12 hour marathons, which out-draw its compressed 25–40 minute chapter videos 3 to 9 times; its short clips are strategy and important-question talks. Older Assam-medium channels teach in 14–19 minute videos (high for PW, unvoted for the others).
- Not verified: production cost and AI-dubbing quality for Assamese, Bengali and Hindi.

### 2.4 Question banks and other boards
No claims survived verification. The first run (29 September) established the Assam HS 2026-27 syllabus position and the NCERT titles; nothing yet on West Bengal, Bihar, Odisha or Uttar Pradesh. Treat as open research.

### 2.5 AI answer-sheet checker
Covered by its own run and design document. The key numbers: handwritten Assamese 71.6 % word accuracy at best; Hindi/Bengali prose 3–7 % word error on clean pages; only Sarvam Vision and Google's models can read Assamese at all; silent correction accounts for 63–79 % of reader errors and 88–95 % on formulas; AI cost about ₹5.5 per 12-page paper (₹2.7 in batch); teacher review of six answers costs about ₹15.

## 3. Product line and roadmap

| When | Product | Notes |
|---|---|---|
| Now (ready) | Class 12 Science sample papers, Assam board: Physics, Chemistry, Mathematics, Biology — 30 papers each, with a separate Solutions book | PDFs built; printing needs ISBN, price, higher-resolution covers, the sealed pre-board pack decision and the answer-key decision |
| Next print run | Compact answer key printed at the back of each Sample Papers book | keeps feedback immediate; the Solutions book remains the full product. Measured on our files: a one-line answer exists for 97 % of Mathematics questions and 64 % of Physics questions, but only 31 % of Chemistry and 23 % of Biology questions (theory answers have no one-line form). For those two subjects print the marking-scheme summary (the first step of each solution) instead of a bare key, or point to the open web solutions. |
| Next | Class 10 Assam (SEBA) sample papers in the same three tiers | reuse the pipeline; research the SEBA pattern and syllabus first |
| Then | Question banks (chapter-wise, from the same bank of 5,883 questions plus new ones) and guidebooks | the question bank data model already exists in the platform |
| Pilot | Revision videos: 3–4 chapters, segmented, with built-in questions, on YouTube | decide on scale and languages after measuring |
| Later | AI checker, practice only, behind the accuracy gate | design document ready |
| Later | Other state boards | one board at a time, research first |

## 4. The platform (examleaf-web)

What exists today, in production-grade form: Django 6.1; accounts with django-allauth (email login, verification, password reset), parental-consent fields and consent records, roles (STUDENT, TEACHER, CONTENT_EDITOR, SALES, SUPPORT, ADMIN), teacher access requests, DPDP data export and 7-day-grace account deletion; content models with the 120 papers and 5,883 solutions imported; the QR landing page `/s/<CODE>/` and the solutions pages; students' own records of attempts; legal pages editable in the admin; a branded admin with a dashboard; production settings (PostgreSQL, Redis, Celery, Sentry, JSON logs, health checks, CSP, HSTS); Docker/Caddy stack, CI, deployment and runbook documents. Being added now: the shop (catalogue, cart, checkout, Razorpay payments and webhooks, GST invoices, shipments, refunds, admin order management) and the REST API v1 (JWT and session auth, catalogue, gated solutions, attempts, profile, OpenAPI docs) for the mobile app.

Decisions this plan asks for, and how the platform supports each:
1. **Open solutions.** A single setting (`SOLUTIONS_REQUIRE_LOGIN`) decides whether `/s/<CODE>/` shows the solutions to everyone or asks for an account. The evidence says open; the setting defaults to the founder's current choice until the decision is taken. Either way the QR code points at our own domain, so reprints never need new codes.
2. **Optional, parent-held accounts.** Accounts stay available for saving records, purchases and the AI checker. For under-18s the parent is the consenting party; the consent record stores the privacy-text version. Before May 2027 the consent flow must be upgraded to an identity-checked method (DigiLocker or equivalent) or accounts for under-18s must be closed; this is a legal and product decision to take by early 2027 with a lawyer.
3. **No tracking.** The platform loads no third-party scripts except KaTeX, carries no analytics or advertising, and the login log keeps failures only. Keep it that way; section 9(3) forbids behavioural tracking of children regardless of consent.
4. **Roles that can grow.** Teachers (verified by staff) can later see linked students' attempts and review AI-checked answers; content editors edit questions and marking schemes in the admin; sales handles orders and shipments; support sees users and attempts read-only.

## 5. Costs that matter

| Item | Figure | Source |
|---|---|---|
| AI grading per 12-page paper | ₹5.5 real time, ₹2.7 batch, ₹8.4 with re-reads | checker research, cost model |
| AI grading per student per year (20 papers) | ₹55–170 | same |
| Teacher review of 6 answers per paper at ₹300/hour | about ₹15 | same |
| Reading pages with Sarvam Digitise | ₹0.50 per page, ₹6 per paper | Sarvam price list, 8 Oct 2026 |
| Google Document AI OCR | ₹1.74 per paper | Google price list |
| Translation of comments through Sarvam | ₹15–25 per paper (3,000–5,000 characters) | Sarvam price list |
| Sealing papers, printing, binding | not verified — get quotes | — |
| Video production and dubbing in three languages | not verified — pilot first | — |

Hosting for the platform at launch scale (one VPS with PostgreSQL, Redis and the web/worker containers, plus object storage and email) is a few thousand rupees a month; the Docker stack is written for that shape, and the runbook covers backups and restore.

## 6. Risks the founder may not have considered

1. Registration as a marketing channel is largely blocked for under-18s by section 9(3), and the industry body IAMAI itself said verifiable children's consent is hard to build quickly.
2. Phone-gated features reach girls least (11 % ownership against 19 % for boys at 14–16).
3. Withholding solutions weakens the book most for weak students, the main buyers of a practice book.
4. Copying Oswaal's gate would also copy its location capture and its under-13-only privacy policy.
5. A well-funded incumbent, PhysicsWallah, entered Assam HS in March 2026 with free English/Assamese revision; ExamLeaf's edge is the printed, Board-faithful paper and the marking-scheme solutions, not video volume.
6. For the AI checker: silent correction of students' mistakes, model retirements every few weeks, unsafe default routing on OpenRouter, price cliffs at prompt-size tiers, and unmeasured accuracy for Assamese, diagrams and chemistry.
7. Student data collected for the 2027 examinations will still be held when the DPDP duties start in May 2027.

## 7. What to do next, in order

1. Decide the solutions model (open solutions plus printed answer key, accounts optional) and set the platform switch accordingly.
2. Get printer quotes for a sealed pre-board pack and bookseller views on sealed books; decide the pack before the print run.
3. Fill the imprint page (ISBN, price), request print-resolution covers, print.
4. Deploy the platform (Docker stack, Razorpay live keys after the policy pages are complete, email provider, backups), with the QR codes pointing at the live domain; print the codes into the books with `book.py --qr-base`.
5. Pilot two or three segmented revision videos on YouTube with built-in questions; measure.
6. Before February 2027, take legal advice on DPDP for accounts and for the AI checker's data flows; plan the identity-checked consent upgrade or the closure of under-18 accounts by May 2027.
7. Collect 100–200 teacher-marked, phone-photographed answer papers per subject and language for the AI checker's accuracy gate; run the head-to-head reader test; only then build the checker's user-facing part.
8. Start the Class 10 Assam research and pipeline.

## 8. Sources and archive

- `docs/research/2026-09-29-assam-hs-syllabus-and-market/` — syllabus, pattern, books, competitors (first run).
- `docs/research/2026-10-08-examleaf-platform-ideas/` — sealed papers, QR-gated solutions, videos (107 agents; 121 claims extracted, 25 verified, 23 confirmed, 2 refuted).
- `docs/research/2026-10-08-ai-answer-checker/` — OCR, grading models, costs, data residency (105 agents; 115 claims extracted).
- `docs/examleaf-ai-checker-design.md` — the checker's design and cost model.
- Each archive folder holds the report, the findings as data, the sources, every extracted claim with its votes, and the raw agent journal.
