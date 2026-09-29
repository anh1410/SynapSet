# SynapSet — Development Context (handoff)

_Last updated: 2026-09-29 · Branch: `stavina-student-dashboard` (on top of `stavina-student-features` @ `8ed50df`)_

SynapSet is an assessment platform: teachers upload course material, a
knowledge graph + vector index is built from it, questions are generated with Graph-RAG
(Gemini), papers are assembled against MSE/SEE patterns with a constraint solver, exams are
scheduled and taken by students (public exam page at `/take/<examId>`, see §9; student
accounts + dashboard at `/student`, see §10 — all in the same Vite app), graded (auto + manual),
and analysed.

This file is the single source of context for continuing development. Read it fully before changing code.

---

## 1. Current state at a glance

| Area | Status |
|---|---|
| Teacher interface | Feature-complete for this phase (see §7) |
| Student exam interface | **Complete for this phase** (see §9): lobby, timed attempts, autosave/resume, submit, receipt |
| Student dashboard | **MVP complete** (see §10): student accounts, join codes/enrolment, exam list with own status, resume, results |
| Backend tests | 209 passed, 2 skipped, 2 deselected (Gemini-backed, opt-in) |
| Frontend | `tsc -b --noEmit` clean, `vite build` succeeds |
| Git | `main` (`9c95791`) → `stavina-teacher-features` (`2ea19b7`) → `stavina-student-features` (`8ed50df`) → `stavina-student-dashboard` (dashboard milestone). All pushed; each branch builds on the previous one. Nothing merged into `main`. |

Branch commits (newest first):
- _(stavina-student-dashboard)_ Add student dashboard and enrollment
- `8ed50df` _(stavina-student-features)_ Add student exam interface and attempt workflow
- `2ea19b7` Add SynapSet developer handoff document
- `76be0e5` Paper review/editing, blueprint & CO analysis, bank intelligence, Graph-RAG evidence, assessment analytics, topic risk, PDF export, attempt autosave
- `0cee599` Exam closing times, server-side attempts & duration enforcement, timing API
- `eb627e2` Exam patterns (MSE/SEE), pattern-based assembly, manual grading, student performance analytics
- `9c95791` = `main` (original project)

---

## 2. Running locally (Windows, Git Bash)

Prereqs already on the dev machine: Python **3.12** (`py -3.12`), Node, **Microsoft C++ Build Tools** ("Desktop development with C++" — needed to compile `chroma-hnswlib`), `.venv/`, `node_modules/`, `.env`.

```bash
# Terminal 1 — backend (port 8000). Run from repo root (it reads .env from CWD).
.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
```bash
# Terminal 2 — frontend (port 5173, proxies /api -> 8000)
npm run dev
```
Open http://localhost:5173 (teacher app). Students either open `http://localhost:5173/take/<examId>` (teachers get it from Exams → "Copy student link") or sign in at `http://localhost:5173/student` and join a subject with the join code shown on the teacher's Overview page.

**Do not use `--reload`**: on this Windows setup WatchFiles hangs after the first change. Restart the backend manually after backend edits. Frontend hot-reloads.

### Fresh setup — dependency pins are broken
`requirements.txt` has **conflicting pins** and a plain install fails:
`chromadb==0.5.5` needs numpy<2 but `shap==0.52.0` needs numpy>=2; `xgboost==3.4.1` writes models `shap 0.49.1` can't read; `google-genai==0.7.0` builds a response schema Gemini rejects (400). Working set:

```bash
py -3.12 -m venv .venv
grep -vE '^(shap|xgboost|google-genai)==' requirements.txt > req-local.txt
.venv/Scripts/python -m pip install -r req-local.txt "shap==0.49.1" "numpy==1.26.4" "xgboost==3.0.5" "google-genai==1.30.0"
rm req-local.txt
npm install
```
`.env` (gitignored, repo root) needs at least `GOOGLE_API_KEY=...`. Optional: `EMBEDDING_MODEL` (default `gemini-embedding-001`), `GENERATION_MODEL` (default `gemini-flash-lite-latest`). Many entries in `.env.example` are stale/unused.

**Open TODO:** fix `requirements.txt` with the four versions above (+ document Build Tools) — not done yet.

Checks:
```bash
.venv/Scripts/python -m pytest -q          # full suite (~2 min; excludes -m llm)
.venv/Scripts/python -m pytest -q -m llm   # real Gemini tests (uses quota)
npx tsc -b --noEmit
npm run build                              # then rm -rf dist tsconfig.tsbuildinfo
```

---

## 3. Architecture

```
React (Vite, TS, Tailwind, no router/chart libs)  --/api proxy-->  FastAPI (app/main.py)
  src/pages/*  ->  src/lib/api.ts                                   app/api/*       HTTP routers
                                                                    app/services/*  business logic
                                                                    app/core/*      stores, config, clients
                                                                    app/schemas/*   Pydantic models
Storage (all under data/, gitignored):
  JSON files  teachers, students, subjects, exams, submissions, attempts, exam_patterns (global, filtered by owner)
  per subject question_banks/{sid}.json, documents/{sid}.json, graphs/{sid}.gpickle (NetworkX)
  ChromaDB    data/chroma, one collection per subject "subject_{sid}"
External      Gemini (embeddings, topic extraction, question generation, pattern import)
Local models  sentence-transformers all-MiniLM-L6-v2 (duplicates), XGBoost+SHAP (difficulty)
```
- Every store is `@lru_cache`'d, loaded into memory, rewritten whole on save → **single process only**; don't hand-edit `data/` while the backend runs (it will overwrite you). Stop the backend first.
- Multi-tenancy: JWT teacher auth (`app/api/deps.py: get_current_teacher`), `require_subject(subject_id, teacher)` returns 404 for subjects the teacher doesn't own. Every teacher endpoint is subject/owner-scoped; tests cover cross-teacher isolation.
- Student exam endpoints (`app/api/submissions.py`) are public, gated by the exam password + attempt id. The frontend calls them through a separate `studentFetch` (no teacher token, 401 ≠ logout) — see §9.
- Student accounts (`app/api/student_portal.py`) use the same JWT secret with a **`role` claim** (`teacher`|`student`); `decode_access_token(token, role)` rejects the wrong role, so a student token never passes `get_current_teacher` and vice versa. Tokens without a role claim (issued before this) are teacher tokens — see §10.
- Time: always `app.core.clock.utcnow()` (called as `clock.utcnow()` so tests can monkeypatch it).
- Neo4j config exists but is unused (NetworkX only).

---

## 4. Module map

### Backend `app/`
| File | Role |
|---|---|
| `api/auth.py`, `subjects.py` | teacher signup/login/me; subject CRUD + join code (get/rotate) + enrolled students |
| `api/student_portal.py` | student accounts (signup/login/me), join/leave subjects, my exams (with own status), my results |
| `api/deps.py` | `get_current_teacher`, `get_current_student`, `get_optional_student` (public exam start), `require_subject` |
| `core/security.py` | bcrypt; role-aware JWT (`create_access_token(id, role)`, `decode_access_token(token, role)`) |
| `core/student_store.py`, `schemas/student.py` | `Student` (roll number unique via `student_key`, `subject_ids` = enrolments), `StudentPublic` |
| `api/graph.py` | ingest document → chunks (Chroma) + topic/relation extraction (graph) + PageRank; documents; `GET /graph` with coverage stats (`is_course_outcome` flag) ; dedupe topics |
| `api/questions.py` | generate (Graph-RAG), CRUD, duplicates, per-question grade, **usage**, **evidence** |
| `api/exams.py` | exam CRUD (schedule, closes_at, pattern link), submissions list, manual grading, attempts list; blocks question changes once submissions exist |
| `api/paper_review.py` | blueprint, replacement candidates, regenerate, marks edit, PDF export |
| `api/patterns.py` | pattern CRUD, presets, document import, assemble (+gap fill, avoid-recent), compliance check |
| `api/submissions.py` | **student-facing**: timing, verify-password, start/resume, attempt status, autosave, submit (returns a trimmed `SubmissionReceipt`) |
| `schemas/public_exam.py` | student-safe views: `PublicQuestion`, `PublicExam`, `ExamTiming`, `AttemptResponse`, `SaveAnswersResult`, `SubmissionReceipt` |
| `api/analytics.py` | class overview, student detail, per-exam analytics, topic risk, grading scale |
| `core/config.py` | `Settings` (pydantic-settings, `.env`) incl. thresholds (§6.8) |
| `core/*_store.py` | JSON/pickle stores; `graph_store.course_outcome_node_ids()` |
| `core/clock.py` | `utcnow()` |
| `services/question_generation.py` | Graph-RAG prompt (retrieved chunks + graph relations), structured Gemini output, code_fix self-check, records `provenance` |
| `services/entity_extraction.py`, `document_extraction.py`, `vector_indexing.py`, `topic_dedup.py`, `document_cleanup.py` | ingestion pipeline |
| `services/difficulty_scoring.py` | XGBoost (bootstrapped on synthetic labels) + SHAP, score 1–10 |
| `services/duplicate_detection.py` | 0.5 semantic + 0.3 topic Jaccard + 0.2 structural; ≥0.75 = duplicate |
| `services/pattern_assembly.py` | MILP assembler (scipy HiGHS), compliance report, gap-fill planner |
| `services/pattern_import.py` | Gemini → draft pattern from a scheme document |
| `services/blueprint.py` | blueprint view over the compliance report |
| `services/paper_review.py` | constraints, reuse finder, replacement candidates |
| `services/question_usage.py` | usage history from exams/submissions |
| `services/evidence.py` | provenance / reconstructed evidence + graph context |
| `services/exam_attempts.py` | grade & record submission, attempt status, lazy finalisation |
| `services/grading.py`, `code_sandbox.py` | auto-grading; best-effort Python sandbox (AST allowlist + subprocess timeout) |
| `services/performance_analytics.py` | class/student/assessment analytics, grades, topic risk |
| `services/pdf_writer.py`, `paper_export.py` | dependency-free PDF writer; paper/answer key/blueprint layouts |

### Frontend `src/`
- `App.tsx` — path `/take/<examId>` → `StudentApp` (exam page, no teacher auth); `/student` → `StudentPortal` (student dashboard); otherwise the teacher app: state-based "router" (`Page` union), auth gate → first-subject gate → shell.
- `lib/api.ts` — **all** types + API calls (mirror backend schemas). Teacher calls use `apiFetch` (Bearer token, 401 → session expired); student calls use `studentFetch`. `ApiError` carries `status`. `lib/AuthContext.tsx`, `lib/session.ts` (sessionStorage token + active subject).
- Student interface: `pages/student/*`, `lib/studentSession.ts`, `lib/useServerCountdown.ts`, `lib/useAttemptAutosave.ts`, `components/AutosaveStatus.tsx` (see §9).
- Student dashboard: `pages/student/StudentPortal.tsx`, `lib/studentAccount.ts`; teacher-side `components/StudentAccessCard.tsx` on Overview (see §10).
- Pages: `OverviewPage`, `UploadPage`, `AnalysisPage`, `BankPage`, `PatternsPage`, `ExamBuilderPage`, `ExamsPage`, `PaperReviewPage`, `ExamResultsPage`, `AnswerKeyPage`, `PerformancePage`, `AuthPage`.
- Components: `Sidebar`, `Topbar`, `SubjectSwitcher`, `PatternEditor`, `PatternCompliancePanel`, `BlueprintView`, `EvidenceDialog`, `charts.tsx` (hand-rolled SVG/CSS charts, table-view toggle), `AutosaveStatus`; `ui/` primitives (incl. minimal `dialog.tsx`).
- `lib/mock-data.ts` is dead code.

---

## 5. API reference (`/api/v1`, teacher endpoints need `Authorization: Bearer <jwt>`)

```
auth       POST /auth/signup · POST /auth/login · GET /auth/me
subjects   GET|POST /subjects · DELETE /subjects/{id}
           GET /subjects/{id}/join-code · POST /subjects/{id}/join-code/rotate · GET /subjects/{id}/students
graph      POST /graph/ingest (multipart: subject_id, file, category, course_outcomes?)
           GET /graph/documents?subject_id · DELETE /graph/documents/{id}?subject_id
           GET /graph?subject_id · POST /graph/dedupe-topics?subject_id
questions  POST /questions/generate · POST /questions/check-duplicates
           GET|POST /questions?subject_id · DELETE /questions/{id}?subject_id · POST /questions/{id}/grade
           GET /questions/usage?subject_id · GET /questions/{id}/evidence?subject_id
patterns   GET /patterns/presets · GET|POST /patterns · GET|PUT|DELETE /patterns/{id}
           POST /patterns/import (multipart) · POST /patterns/{id}/assemble · POST /patterns/{id}/check
exams      GET|POST /exams · GET|PATCH|DELETE /exams/{id}
           GET /exams/{id}/submissions · PATCH /exams/{id}/submissions/{sid}/answers/{qid} (manual grade)
           GET /exams/{id}/attempts (teacher view of attempt progress)
review     POST /exams/{id}/blueprint · POST /exams/{id}/review/candidates|regenerate|marks
           GET /exams/{id}/export/{paper|answer-key|blueprint}?tz_offset=<JS getTimezoneOffset()>
analytics  GET /analytics/overview?subject_id[&exam_type] · GET /analytics/students/{key}?subject_id
           GET /analytics/exams/{exam_id} · GET /analytics/topic-risk?subject_id · GET /analytics/grading-scale
student    (public) GET /exams/{id}/timing · POST /exams/{id}/verify-password · POST /exams/{id}/start
           GET /exams/{id}/attempts/{attempt_id} · PUT /exams/{id}/attempts/{attempt_id}/answers
           POST /exams/{id}/submit  (-> SubmissionReceipt, see §9.6)
           /start optionally takes a student Bearer token (links the attempt, §10.5)
student    (student token) POST /student/auth/signup · POST /student/auth/login · GET /student/auth/me
 portal    GET /student/subjects · POST /student/subjects/join {code} · DELETE /student/subjects/{id}
           GET /student/exams · GET /student/results
GET /health
```
Review endpoints take the **draft** paper: `{question_ids?, marks_overrides?: {qid: marks}, target_id?}`.

---

## 6. Domain rules (the non-obvious parts)

### 6.1 Questions
Types: `mcq, fill_in_blank, short_answer, long_answer, numerical, code_fix`. Auto-gradable: mcq, fill_in_blank, numerical (case-insensitive exact match), code_fix (sandbox vs hidden test cases, partial marks by tests passed). short/long need manual grading.
- `skill_category` (conceptual/reasoning/coding) is **derived**: code_fix → coding; Bloom ≥ Apply → reasoning; else conceptual. Optional per-question override (Bank page). `app/schemas/skill.py` + mirrored `effectiveSkill` in `api.ts`.
- `difficulty_bucket`: ≤4 easy, ≤7 medium, else hard (unscored = medium). Same thresholds front and back.
- `provenance` (generated questions): requested topic, retrieved chunks (+relevance), graph relations, model, time. `derived_from`: copy made when marks were edited for one paper.

### 6.2 Patterns (MSE/SEE)
`ExamPatternFields`: sections (count × marks, allowed types, allowed Bloom levels), Bloom/difficulty distributions (% of marks), **units = groups of knowledge-graph topic ids** (+% of marks), CO requirements (`min_questions` and/or `min_percent` of marks), `tolerance_percent`. Validation: sections sum to total_marks; distributions sum to 100±1; no duplicate keys. Sources: presets, form, or Gemini document import (draft → teacher review). Stored per subject+teacher.

### 6.3 Assembly (`pattern_assembly.py`)
MILP (scipy `milp`/HiGHS — replaces the old removed CP-SAT; no ortools dependency). One binary per eligible (question, section) pair; exact section counts; Bloom/difficulty/unit mark bands (target ± tolerance); CO minimums; objective = maximise distinct topics, small penalty for reuse. If infeasible: identifies blocking constraint families and returns a best-effort draft. `evaluate_selection` = same rules for a hand-picked list (compliance checks, blueprint). Gap filling: planner adds costed "virtual" questions to the same MILP to decide the *minimal* set to generate, then generates via Graph-RAG, pins marks/Bloom/unit/topic, dedupes, saves, re-solves. `avoid_recent_days` excludes recently used questions.

### 6.4 Course-outcome graph nodes
Topic extraction adds CO nodes (targets of `MAPS_TO`). They are **not topics**: excluded from generation topic pools, analytics topic breakdowns, topic risk, blueprint topic rows, graph coverage/neglected, and frontend topic pickers (`topicNodes()` in `api.ts`). Helper: `core/graph_store.course_outcome_node_ids(graph)`.

### 6.5 Exams, scheduling, attempts
- `status` draft|scheduled|closed; computed `bucket` draft|upcoming|live|closed; `closed_by` teacher|schedule. Setting `go_live_at` moves draft→scheduled. Optional `closes_at` (must be > go_live) auto-closes. `exam_type` QUIZ|MSE|SEE, optional `pattern_id`.
- Attempts: `POST /start` creates/resumes **one attempt per student per exam** (student key = normalised roll number, else name). `started_at` is server time only. Deadline = min(start + duration frozen at start, closes_at). Submissions/autosaves refused after deadline + `submission_grace_seconds` (30). Timed exams require an attempt; untimed exams keep the legacy verify-password→submit flow.
- Autosave: `PUT .../answers {answers, seq}` merges into `attempt.saved_answers`; `seq ≤ last applied` is ignored (stale retries). Submit uses saved answers overlaid with request answers.
- **Lazy finalisation** (`exam_attempts.finalize_ended_attempts`): attempts that timed out or whose exam was manually closed, and have saved answers, become `auto_submitted` submissions stamped at the deadline. Runs whenever the exam's attempts/submissions/analytics are read (no scheduler). Late actions on such attempts return 403 "your saved answers were submitted automatically".
- Papers with submissions are locked (PATCH of `question_ids` → 409; review ops → 409).

### 6.6 Grading & analytics
- Manual grading PATCH sets `manually_graded`, recomputes totals; `fully_auto_graded` means "nothing pending".
- Submissions snapshot question metadata (bloom, topics, skill, difficulty, test-case counts, answer text) so analytics survive bank edits.
- Latest attempt per (student, exam) is used. **Ungraded answers are pending, never counted as zero.**
- Grade scale (10-point): O≥90, A+≥80, A≥70, B+≥60, B≥50, C≥45, P≥40, F<40. Bands: strong ≥75, developing ≥50, needs_support <50, insufficient if < `MIN_EVIDENCE`=2 graded answers.
- Assessment analytics: per-question stats need ≥ `question_min_responses` (5); predicted-vs-actual difficulty (Spearman) needs ≥ `calibration_min_questions` (4) such questions — else "Not enough data".
- Topic risk: coverage risk (< `topic_min_questions`=3 bank questions) vs performance risk (< `topic_risk_percent`=50% with ≥2 answers), reported separately.

### 6.7 Review / regeneration
Edits are draft-only until Save (marks too, via `marks_overrides`); the UI diffs draft vs saved blueprint and requires confirmation to save a non-compliant paper. Regenerate: reuse a bank question meeting all constraints (0 Gemini calls) → else generate (≤2 calls: retry for difficulty band or if result rephrases the original). Marks edit on save: in place if unshared, else copy (`derived_from`).

### 6.8 Configurable thresholds (`Settings`, overridable in `.env`)
`submission_grace_seconds=30, recent_use_days=30, frequent_use_count=3, question_min_responses=5, calibration_min_questions=4, topic_min_questions=3, topic_risk_percent=50`.

---

## 7. Teacher UI (sidebar pages)
Overview (incl. the **Student join code** card, §10.7) · Upload Materials · Topic Analysis · Question Bank (usage history + filters, skill override, source/evidence) · Exam Patterns (templates, form, document import) · Exam Builder (free-form rows or pattern auto-assemble with AI gap-fill + avoid-recent; live compliance; schedule go-live/closes-at/password) · Exams (Live/Upcoming/Drafts/Closed, schedule line, auto-refresh; Review & export, Results, Answer Key, Close) · Paper Review (sections, reorder/remove/replace/regenerate/marks/source, impact diff, blueprint tab, PDF exports) · Results (answers, test cases, manual grading, auto-submitted badge, in-progress/timed-out counts) · Student Performance (Class overview incl. topic risk, Assessment, Individual student; exam-type filter; table view for every chart).

---

## 8. Testing conventions
- `tests/conftest.py`: `api_client` fixture = TestClient with **isolated tmp storage** (all store paths via env vars + `cache_clear()`), a signed-up teacher and one subject (`api_client.subject_id`). `clock` fixture = `FakeClock` (starts `T0 = 2026-10-01 09:00 UTC`, `.advance(...)`) patched into `app.core.clock.utcnow`.
- `tests/factories.py`: `q(...)`, `seed`, `seed_graph`, `make_exam`, `small_pattern`, `submit`, `other_teacher_headers`, `provenance`.
- Mock Gemini by monkeypatching the name **where it's used** (e.g. `app.api.paper_review.generate_questions`, `app.services.question_generation.get_genai_client`, `app.services.evidence.query_similar_chunks`).
- New stores must be added to conftest env vars + `cached_fns` (the student store is: `STUDENT_STORE_PATH`). New settings/paths → `.gitignore` if they create data files (`students.json` is ignored).
- The `api_client` fixture sends the teacher token on every request. Student-side tests override it per request: `headers={"Authorization": ""}` = anonymous, or `{"Authorization": "Bearer <student token>"}`.
- Every feature has isolation tests (other teacher → 404).

---

## 9. Student interface (completed milestone)
Branch `stavina-student-features` (branched from `stavina-teacher-features`). The exam page needs **no account**: identity = name + optional roll number (normalised into `student_key`, §6.5); access = the link + the exam password. (Signed-in students reach the same page from their dashboard with their account identity — §10.)

### 9.1 Frontend architecture
- Same Vite app, no router library. `App.tsx` checks `window.location.pathname` for `/take/<examId>` **before** the teacher `AuthProvider`, and renders `StudentApp` — the student UI never touches teacher auth state.
- Student API calls live in `lib/api.ts` ("Student API" section) and go through `studentFetch`: never sends the teacher's Bearer token and treats 401 ("Incorrect password") as an ordinary `ApiError` (the teacher `apiFetch` clears the session on 401 — using it for student calls would log out a teacher in the same browser).
- `ApiError.status` is used to map server refusals to screens (`studentFlow.ts: endedFromError`).
- Styling reuses the teacher `ui/` primitives (Card, Button, Input, Badge, Dialog, Progress); mobile-first (single column, sticky header; navigator above questions on small screens, sticky sidebar on `lg`).

### 9.2 Pages / components (`src/pages/student/`)
| File | Role |
|---|---|
| `StudentApp.tsx` | Screen state machine (`StudentView`): loading → lobby / exam / receipt / ended / not_found / error. Lobby (upcoming countdown that auto-refreshes into live; closed; start form: name, roll number, password). Resume on mount. Ended screens. |
| `StudentExam.tsx` | Exam taking: sticky header (exam, student, `AutosaveStatus`, timer turning amber ≤5 min / red ≤1 min, Submit), question list, navigator (answered count + progress + jump buttons), submit confirmation dialog listing unanswered questions, time-up auto-submit, periodic resync, `beforeunload` warning while saves are pending. |
| `QuestionCard.tsx` | One control per type: mcq → radios; fill_in_blank → radios if it has options, else text; numerical → text input (`inputMode=decimal`, not `type=number`, so the exact string is kept); short/long → textarea; code_fix → monospace textarea pre-filled with `starter_code`, Tab inserts 4 spaces, "Reset to starter code". `isAnswered`: non-blank and (code) differs from starter code. |
| `SubmissionReceiptView.tsx` | Receipt (§9.6). |
| `studentFlow.ts` | `StudentView` union, `endedFromError`, `viewForAttempt`. |
| `lib/studentSession.ts` | sessionStorage: `synapset_student_attempt:<examId>` = {attemptId, identity incl. password}; `synapset_student_receipt:<examId>`. Separate from teacher keys. |
| `lib/useServerCountdown.ts` | Countdown from a server-computed `*_seconds` value, anchored to `performance.now()`; `formatClock`. |
| `lib/useAttemptAutosave.ts`, `components/AutosaveStatus.tsx` | Autosave (pre-existing, now used). |
| Teacher `ExamsPage.tsx` | "Copy student link" on live/upcoming exams → `${origin}/take/<examId>`; falls back to `window.prompt` if the clipboard API is blocked. |

### 9.3 Student API flow
1. Lobby: `GET /exams/{id}/timing` (404 → "Exam not found"; drafts are 404 too).
2. Start: `POST /exams/{id}/start {password, student_name, student_identifier}` → `AttemptResponse` (timing, attempt {id, deadline, remaining_seconds, expired, submitted}, exam with `PublicQuestion`s, `saved_answers`, `save_seq`). 401 → "Incorrect exam password". Identity + attempt id stored in sessionStorage.
3. Autosave: `PUT /exams/{id}/attempts/{aid}/answers {answers, seq}` via `useAttemptAutosave`.
4. Resync (every 60 s, on tab visible, on `online`): `GET /exams/{id}/attempts/{aid}` — updates the timer; detects submitted/expired/closed.
5. Submit: `POST /exams/{id}/submit {password, student_name, student_identifier, attempt_id, answers}` — sends **all** current answers (server overlays them on the autosaved ones). The password is re-checked by the server, which is why it's kept in sessionStorage during the attempt.

### 9.4 Attempt lifecycle & server-side timing
- One attempt per student per exam; `started_at` = server clock; deadline = min(start + duration frozen at start, `closes_at`) (§6.5). The client never sends times.
- The UI countdown uses `remaining_seconds` from the latest server response anchored to the monotonic clock, so a wrong/changed device clock can't move it; resync corrects drift.
- At 0: the client submits once (`timeRanOut`) — within the server's 30 s grace. If that fails (offline), lazy finalisation later submits the autosaved answers; the page learns via resync.
- Teacher closes the exam → next resync sees the attempt submitted (finalised from saved answers) → "Your answers were submitted" screen. With nothing saved → "This exam is closed".
- Screens for server refusals: 409 already submitted → "Exam submitted"; 403 auto-submitted → "Your answers were submitted"; 403 time up → "Time is up"; 403 closed → "This exam is closed"; 403 not live yet → back to lobby.

### 9.5 Autosave / resume
- Every edit → local state + `autosave.update(qid, value)`; debounced batch PUTs with increasing `seq` (stale retries ignored server-side); offline → backoff retry, "Connection lost" status; 403/409 → autosave stops ("ended").
- Refresh: `StudentApp` reads the stored attempt and calls `/start` again with the same identity → same attempt, same deadline, `saved_answers` restored, autosave seeded with `save_seq`. On another device/tab the student re-enters the same name + roll number (same result).
- On any end (receipt/ended/not found) the stored attempt — including the password — is cleared; only the receipt is kept so a refresh still shows it.

### 9.6 Submission receipt
`POST /submit` returns `SubmissionReceipt` (not the graded `Submission`):
`submission_id, exam_id, student_name, student_identifier, attempt_id, auto_submitted, started_at, submitted_at, auto_graded_marks, auto_graded_max_marks, pending_review_marks, pending_review_count, total_max_marks, answers[{question_id, status: auto_graded|pending_review}]`.
UI: "Score so far **X / Y** + N marks pending teacher review", paper total, per-question "Auto-graded" / "Pending teacher review" badges. Pending marks are never shown as zero. No per-question marks or correctness. The teacher results API (`GET /exams/{id}/submissions`) is unchanged and still returns the full graded submission.

### 9.7 Student security / data-exposure rules
- Questions during an attempt (`PublicQuestion`): no `correct_answer`, `test_cases`, `difficulty_score`, `topic_ids`, `co_ids`, `provenance`, `skill_category`; exam password never returned. (`bloom_level` is still included — not displayed.)
- Receipt: no correctness, grading `detail`, per-answer marks, test-case counts, answer text, feedback or question metadata. Tests: `tests/test_submission_receipt.py` (forbidden-key scan over the whole JSON, incl. `/start` and attempt status).
- Student calls never carry the teacher token; a student 401 can't end a teacher session.
- Attempt ids are unguessable UUIDs and act as the attempt token.

### 9.8 Verification done for this milestone
Backend suite (numbers in §1), `tsc`, `vite build`, and browser E2E against an **isolated** backend (port 8001, all store paths pointed at a scratch dir via the env vars in §8, so `data/` is never touched): upcoming → live transition, closed & unknown exam, wrong password (teacher session preserved), all six question types, autosave, refresh/resume (answers + timer), submit confirmation + receipt, 409 on re-entry, time-up auto-submit, teacher close mid-attempt, teacher Exams/Results pages, Copy student link, 375 px layout.

---

## 10. Student dashboard (completed MVP)
Branch `stavina-student-dashboard` (branched from `stavina-student-features` @ `8ed50df`). Decisions taken: student **accounts + subject join codes**; results show the **final score only once fully graded**; `/take` links **stay public**.

### 10.1 Student accounts & authentication (`api/student_portal.py`, `core/student_store.py`, `schemas/student.py`)
- `Student {id, email, name, roll_number, password_hash (bcrypt), subject_ids, created_at}`; stored in `data/students.json` (`STUDENT_STORE_PATH`, gitignored). `StudentPublic` never includes the hash.
- Signup requires name, roll number, email, password ≥ 8 chars. Email unique (case-insensitive). **Roll number unique** — compared via `student_key(name, roll)` (normalised case/whitespace) because it is the student's identity on exams.
- Login by email; `GET /student/auth/me`. Tokens: `create_access_token(student.id, role="student")`, same secret/expiry as teachers.
- Frontend session: `lib/studentAccount.ts`, sessionStorage keys `synapset_student_token` / `synapset_student_profile` (separate from teacher `synapset_token`). A 401 from any dashboard call signs the student out.

### 10.2 Role separation
- `decode_access_token(token, role)` checks the `role` claim (missing claim = teacher). `get_current_teacher` → role teacher; `get_current_student` → role student. Wrong role → 401.
- `get_optional_student` (used by `POST /exams/{id}/start`): no token → anonymous; **valid teacher token → anonymous** (the old behaviour, and what the teacher-authenticated test client relies on); anything else must be a valid student token (else 401 "Invalid or expired student session", so an expired dashboard session fails loudly instead of silently starting an unlinked attempt).
- The frontend `studentFetch(path, options, studentToken?)` sends only the student token, never the teacher's.

### 10.3 Subject join codes & enrolment
- `Subject.join_code`: 7 chars from an unambiguous alphabet (no 0/O/1/I/L), unique. Assigned on subject creation; older subjects get one lazily on `GET /subjects/{id}/join-code` (so opening Overview writes it to `subjects.json`). `POST .../join-code/rotate` replaces it — the old code stops working, existing enrolments stay. `GET /subjects/{id}/students` lists enrolled students. All teacher-scoped via `require_subject` (other teacher → 404).
- Students: `POST /student/subjects/join {code}` (case/space/dash tolerant, idempotent; bad code → 404), `GET /student/subjects` (name + teacher name), `DELETE /student/subjects/{id}` (leave). Enrolment = `Student.subject_ids`; subjects a teacher deleted are skipped.

### 10.4 `/student` dashboard (`pages/student/StudentPortal.tsx`)
- Not signed in → login/sign-up page (link to the teacher app). Signed in → header (name, roll, refresh, sign out); "My subjects" chips (leave with confirm) + join-code input; sections **Live now**, **Upcoming** (live countdown via `useServerCountdown`), **Results**, **Past exams**; empty states. Refreshes every 30 s and when the tab becomes visible. Mobile-friendly (no horizontal scroll at 375 px).
- `GET /student/exams` → `{server_time, exams: StudentExamRow[]}` for joined subjects, **never drafts**, no questions / password (only `password_required`) / answer keys. Row: name, subject, type, marks, question count, duration, state (upcoming/live/closed), go-live/closes, `opens_in_seconds`/`closes_in_seconds`, and **`my_status`**:
  `not_started` · `in_progress` (+ `remaining_seconds`) · `submitted` · `auto_submitted` · `not_submitted` (started, ended with nothing saved) · `missed` (closed, never started). Status comes from the attempt for the student's `student_key`; `finalize_ended_attempts` runs first (same lazy finalisation as elsewhere).
- Live + not started → **Start exam**; live + in progress → **Resume · mm:ss left**. Both open `/take/<examId>`.

### 10.5 Dashboard-started attempts (linking to the account)
- On `/take/<examId>`, `StudentApp` reads the student session: the lobby shows "Signed in as <name> · <roll>" instead of name/roll inputs (password still required) and the header gets a "My dashboard" link. `startAttempt(examId, identity, token)` sends the student token (also on resume after refresh).
- Server (`start_attempt`): with a student token the identity is the **account's** name + roll number (request values ignored) and the new attempt gets `Attempt.student_id`. An existing unlinked attempt for that roll number (started via the plain link) is **claimed** when resumed from the dashboard; an attempt linked to a different account → 403. `grade_and_record` copies `student_id` onto the `Submission` (also for lazy auto-submission).
- Expired student session on start → the lobby clears it and falls back to the anonymous form with a message.

### 10.6 Student results (`GET /student/results`)
- Only submissions with `Submission.student_id == me` (newest first). A submission made through the plain link under the student's roll number is **not** shown (can't be verified as theirs); the exam row still says "Submitted".
- Row: exam/subject/type, submitted_at, auto_submitted, `status` graded|pending_review, `graded_marks/graded_max_marks`, `pending_review_marks/count`, `total_max_marks`; **only when fully graded**: `final_marks`, `final_percent`, `grade` + `grade_label` (10-point scale, §6.6). Never per-question marks, correctness, feedback, answer text or answer key.
- UI: pending → "X / Y so far + N marks pending teacher review"; graded → "15 / 16 · 93.8% · O".

### 10.7 Teacher side
- Overview → **Student join code** card (`components/StudentAccessCard.tsx`): code, copy (copies the portal URL + code), "N students joined", **New code** (rotate, with confirm).
- Teacher login page links to `/student`. Teacher results/analytics are unchanged (submissions just carry an extra `student_id`).

### 10.8 `/take/<examId>` stays public
Nothing about the exam-link flow changed for anonymous students (no token → exactly as §9). The dashboard is an additional way in.

### 10.9 Tests & verification
- `tests/test_student_portal.py` (19 tests): signup/login/me, validation, duplicate email/roll, bad login; tokens not interchangeable (student→teacher endpoints and teacher→student endpoints = 401); teacher token on `/start` treated as anonymous; invalid student token → 401; join code generate/rotate/other-teacher 404; join/leave/idempotent/rotated code; enrolled list; exams only from joined subjects, never drafts, no password/questions leak; other teacher's subject isolation; `my_status` through start/in-progress/submitted, auto_submitted, not_submitted, missed; account identity overrides request identity; link attempt claimed on dashboard resume; results pending → final + grade after manual grading, forbidden-key scan; unlinked link submissions not shown; teacher results API unchanged.
- Browser E2E on an isolated instance (ports 8001/5180, all store paths incl. `STUDENT_STORE_PATH` in a scratch dir): sign-up, wrong/lowercase join code, dashboard sections + countdown, start from dashboard ("Signed in as"), leave mid-exam → "In progress · Resume mm:ss left", resume with answers + timer restored, submit → receipt → dashboard "so far + pending", teacher grades → "15 / 16 · 93.8% · O", payload leak scan, student token → teacher endpoint 401, teacher Overview join-code card + enrolled count, teacher login link, 375 px layout.

---

## 11. Known limitations / tech debt
- `requirements.txt` pins broken (see §2) — fix pending.
- Single-process JSON stores; no DB, no migrations, no concurrency safety.
- Exam passwords stored/compared in plaintext; `jwt_secret` defaults to a dev value.
- Uploads saved as `data/uploads/{filename}` (not subject-prefixed); same filename across subjects collides.
- Code sandbox is best-effort, not container isolation.
- Difficulty model trained on synthetic heuristic labels; difficulty targets can be hard to hit.
- "Answer any N of M" recorded in section instructions only; online grading grades all questions.
- PDF writer: standard fonts, Latin-1 only (other chars → `?`); layout verified by text extraction, not visually.
- Lazy finalisation (no background scheduler); submission timestamp is the real deadline.
- Ingestion is synchronous inside the request (one Gemini call per ~4000-word chunk).
- Existing Overview/Topic Analysis "coverage" is relative to the best-covered topic (pre-existing semantics).
- `mock-data.ts` dead; `.env.example` stale; stray empty tracked file `git` at repo root (from `main`).

Student exam interface:
- Exam links stay public: anyone with the link + password can start as any name/roll number (one attempt per identity). Only dashboard-started attempts are tied to a verified account.
- The exam password sits in the tab's sessionStorage during an attempt (the server re-checks it on submit); cleared when the exam ends. The receipt stays in sessionStorage for the tab's lifetime (a second student using the same tab would see it).
- `GET /timing` doesn't return the exam name, so the lobby can't show it until the attempt starts.
- `PublicQuestion` still includes `bloom_level`.
- Grading is exact-match for numerical/fill-in-the-blank ("4.0" ≠ "4") — backend rule, not a UI one.
- Code editor is a plain textarea (no syntax highlighting); Tab is captured for indentation (Shift+Tab still leaves the field).
- Time-up submit relies on the tab being open; otherwise lazy finalisation submits autosaved answers when the exam is next read. Browsers throttle timers in hidden tabs, so countdowns / time-up submit can run late while hidden (the page catches up when visible; the server finalises regardless).
- No frontend unit tests; student UI verified by manual browser E2E (§9.8, §10.9).

Student dashboard:
- Roll numbers are claimed first-come: whoever registers a roll number first owns that exam identity (and can resume/claim an unlinked link attempt for it). No roster/verification against a school list, no email verification.
- No password reset / change, no account deletion, no profile editing for students.
- Student session is per tab (sessionStorage); closing the tab signs out.
- Join codes are the only enrolment gate: anyone with the code can join a subject. Teachers can rotate the code but cannot remove an enrolled student.
- Results only for dashboard-linked submissions; exams taken via the plain link aren't shown with a score even under the student's roll number.
- No per-question feedback or answer review for students after grading (by design for now).
- Leaving a subject hides its exams but keeps past results (they belong to the student).
- `GET /student/exams` scans every joined subject's exams and runs lazy finalisation per exam on each call (fine for JSON-store scale; dashboard polls every 30 s).
- Exams are not filtered by enrolment on the public exam endpoints (by design, §10.8).

---

## 12. Working rules for this repo
- Branches: teacher milestone `stavina-teacher-features`, student exam interface `stavina-student-features`, student dashboard `stavina-student-dashboard` (each on top of the previous). **Never** checkout/modify/merge `main`; **never push** unless the user explicitly asks.
- For browser E2E, run a separate backend with the store env vars (§8) pointed at a scratch directory rather than using `data/`.
- Never modify `.env` or print the Gemini key. Never commit `data/`, `.venv/`, `node_modules/`, `dist/`, `.env` (all gitignored — keep it that way).
- Remove any test data created during manual/E2E testing before committing; leave the real teacher accounts untouched (local `data/` holds real teacher accounts alongside any throwaway test account; delete only what your test run created).
- Stage files explicitly (not `git add -A`); commit message ends with the Co-Authored-By line the session provides.
- Line endings are mixed (index LF, `core.autocrlf=true`); patch tooling must tolerate CRLF.
- Run full backend suite + `tsc` + `vite build` before committing; add regression tests for every bug fixed.
