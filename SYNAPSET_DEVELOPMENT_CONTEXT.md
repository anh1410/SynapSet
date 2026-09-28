# SynapSet — Development Context (handoff)

_Last updated: 2026-09-28 · Branch: `stavina-teacher-features` · Head: `76be0e5`_

SynapSet is a teacher-facing assessment platform: teachers upload course material, a
knowledge graph + vector index is built from it, questions are generated with Graph-RAG
(Gemini), papers are assembled against MSE/SEE patterns with a constraint solver, exams are
scheduled and taken by students (separate Student app, **not yet built** in this repo), graded
(auto + manual), and analysed.

This file is the single source of context for continuing development. Read it fully before changing code.

---

## 1. Current state at a glance

| Area | Status |
|---|---|
| Teacher interface | Feature-complete for this phase (see §7) |
| Student interface | **Not built.** Backend API + a client autosave hook are ready (see §9) |
| Backend tests | 184 passed, 2 skipped, 2 deselected (Gemini-backed, opt-in) |
| Frontend | `tsc -b --noEmit` clean, `vite build` succeeds |
| Git | `stavina-teacher-features` is 3 commits ahead of `main` (`9c95791`); **never pushed**, no upstream |

Branch commits (newest first):
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
Open http://localhost:5173.

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
  JSON files  teachers, subjects, exams, submissions, attempts, exam_patterns (global, filtered by owner)
  per subject question_banks/{sid}.json, documents/{sid}.json, graphs/{sid}.gpickle (NetworkX)
  ChromaDB    data/chroma, one collection per subject "subject_{sid}"
External      Gemini (embeddings, topic extraction, question generation, pattern import)
Local models  sentence-transformers all-MiniLM-L6-v2 (duplicates), XGBoost+SHAP (difficulty)
```
- Every store is `@lru_cache`'d, loaded into memory, rewritten whole on save → **single process only**; don't hand-edit `data/` while the backend runs (it will overwrite you). Stop the backend first.
- Multi-tenancy: JWT teacher auth (`app/api/deps.py: get_current_teacher`), `require_subject(subject_id, teacher)` returns 404 for subjects the teacher doesn't own. Every teacher endpoint is subject/owner-scoped; tests cover cross-teacher isolation.
- Student endpoints (`app/api/submissions.py`) are public, gated by the exam password + attempt id.
- Time: always `app.core.clock.utcnow()` (called as `clock.utcnow()` so tests can monkeypatch it).
- Neo4j config exists but is unused (NetworkX only).

---

## 4. Module map

### Backend `app/`
| File | Role |
|---|---|
| `api/auth.py`, `subjects.py` | signup/login/me; subject CRUD |
| `api/graph.py` | ingest document → chunks (Chroma) + topic/relation extraction (graph) + PageRank; documents; `GET /graph` with coverage stats (`is_course_outcome` flag) ; dedupe topics |
| `api/questions.py` | generate (Graph-RAG), CRUD, duplicates, per-question grade, **usage**, **evidence** |
| `api/exams.py` | exam CRUD (schedule, closes_at, pattern link), submissions list, manual grading, attempts list; blocks question changes once submissions exist |
| `api/paper_review.py` | blueprint, replacement candidates, regenerate, marks edit, PDF export |
| `api/patterns.py` | pattern CRUD, presets, document import, assemble (+gap fill, avoid-recent), compliance check |
| `api/submissions.py` | **student-facing**: timing, verify-password, start/resume, attempt status, autosave, submit |
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
- `App.tsx` — state-based "router" (`Page` union), auth gate → first-subject gate → shell.
- `lib/api.ts` — **all** types + API calls (mirror backend schemas). `lib/AuthContext.tsx`, `lib/session.ts` (sessionStorage token + active subject).
- Pages: `OverviewPage`, `UploadPage`, `AnalysisPage`, `BankPage`, `PatternsPage`, `ExamBuilderPage`, `ExamsPage`, `PaperReviewPage`, `ExamResultsPage`, `AnswerKeyPage`, `PerformancePage`, `AuthPage`.
- Components: `Sidebar`, `Topbar`, `SubjectSwitcher`, `PatternEditor`, `PatternCompliancePanel`, `BlueprintView`, `EvidenceDialog`, `charts.tsx` (hand-rolled SVG/CSS charts, table-view toggle), `AutosaveStatus`; `ui/` primitives (incl. minimal `dialog.tsx`).
- `lib/useAttemptAutosave.ts` + `components/AutosaveStatus.tsx` — **for the future Student UI; not used by any page**.
- `lib/mock-data.ts` is dead code.

---

## 5. API reference (`/api/v1`, teacher endpoints need `Authorization: Bearer <jwt>`)

```
auth       POST /auth/signup · POST /auth/login · GET /auth/me
subjects   GET|POST /subjects · DELETE /subjects/{id}
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
           POST /exams/{id}/submit
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
Overview · Upload Materials · Topic Analysis · Question Bank (usage history + filters, skill override, source/evidence) · Exam Patterns (templates, form, document import) · Exam Builder (free-form rows or pattern auto-assemble with AI gap-fill + avoid-recent; live compliance; schedule go-live/closes-at/password) · Exams (Live/Upcoming/Drafts/Closed, schedule line, auto-refresh; Review & export, Results, Answer Key, Close) · Paper Review (sections, reorder/remove/replace/regenerate/marks/source, impact diff, blueprint tab, PDF exports) · Results (answers, test cases, manual grading, auto-submitted badge, in-progress/timed-out counts) · Student Performance (Class overview incl. topic risk, Assessment, Individual student; exam-type filter; table view for every chart).

---

## 8. Testing conventions
- `tests/conftest.py`: `api_client` fixture = TestClient with **isolated tmp storage** (all store paths via env vars + `cache_clear()`), a signed-up teacher and one subject (`api_client.subject_id`). `clock` fixture = `FakeClock` (starts `T0 = 2026-10-01 09:00 UTC`, `.advance(...)`) patched into `app.core.clock.utcnow`.
- `tests/factories.py`: `q(...)`, `seed`, `seed_graph`, `make_exam`, `small_pattern`, `submit`, `other_teacher_headers`, `provenance`.
- Mock Gemini by monkeypatching the name **where it's used** (e.g. `app.api.paper_review.generate_questions`, `app.services.question_generation.get_genai_client`, `app.services.evidence.query_similar_chunks`).
- New stores must be added to conftest env vars + `cached_fns`. New settings/paths → `.gitignore` if they create data files.
- Every feature has isolation tests (other teacher → 404).

---

## 9. Next milestone: Student interface
Not started. Build it against the existing public API (§5 "student") — no backend changes should be required for the basic flow:
1. `GET /exams/{id}/timing` → upcoming/live/closed, opens/closes in, duration (show server-time-corrected countdowns).
2. `POST /exams/{id}/start {password, student_name, student_identifier}` → attempt (id, deadline, remaining_seconds), questions (no answer keys), `saved_answers`, `save_seq`.
3. Autosave with `useAttemptAutosave({examId, attemptId, initialSeq: save_seq})` → `update(qid, answer)`; show `<AutosaveStatus/>`.
4. On refresh: call `/start` again (same identity) or `GET /attempts/{attempt_id}` to restore.
5. `POST /submit {attempt_id, answers}`; handle 403 (time up / auto-submitted) and 409 (already submitted).
The Student app may live in a separate project (CORS allows any localhost port in development). Decide whether it shares this repo.

---

## 10. Known limitations / tech debt
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

---

## 11. Working rules for this repo
- Work on `stavina-teacher-features`. **Never** checkout/modify/merge `main`; **never push** unless the user explicitly asks.
- Never modify `.env` or print the Gemini key. Never commit `data/`, `.venv/`, `node_modules/`, `dist/`, `.env` (all gitignored — keep it that way).
- Remove any test data created during manual/E2E testing before committing; leave the real teacher accounts untouched (local `data/` holds real teacher accounts alongside any throwaway test account; delete only what your test run created).
- Stage files explicitly (not `git add -A`); commit message ends with the Co-Authored-By line the session provides.
- Line endings are mixed (index LF, `core.autocrlf=true`); patch tooling must tolerate CRLF.
- Run full backend suite + `tsc` + `vite build` before committing; add regression tests for every bug fixed.
