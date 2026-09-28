import { clearSession, getToken, type TeacherPublic } from "@/lib/session";

const BASE = "/api/v1";

export class AuthError extends Error {}

// ---------- Shared enums ----------

export type BloomLevel = 1 | 2 | 3 | 4 | 5 | 6;

export const BLOOM_LEVELS: BloomLevel[] = [1, 2, 3, 4, 5, 6];

export const BLOOM_LABELS: Record<BloomLevel, string> = {
  1: "Remember",
  2: "Understand",
  3: "Apply",
  4: "Analyze",
  5: "Evaluate",
  6: "Create",
};

export type QuestionType = "mcq" | "short_answer" | "long_answer" | "numerical" | "fill_in_blank" | "code_fix";

export const QUESTION_TYPE_LABELS: Record<QuestionType, string> = {
  mcq: "Multiple Choice",
  short_answer: "Short Answer",
  long_answer: "Long Answer",
  numerical: "Numerical",
  fill_in_blank: "Fill in the Blank (Options)",
  code_fix: "Coding (Fix the Code)",
};

export const QUESTION_TYPE_ORDER: QuestionType[] = [
  "mcq",
  "fill_in_blank",
  "short_answer",
  "long_answer",
  "numerical",
  "code_fix",
];

export type Difficulty = "Easy" | "Medium" | "Hard";

export type SkillCategory = "conceptual" | "reasoning" | "coding";

export const SKILL_LABELS: Record<SkillCategory, string> = {
  conceptual: "Conceptual",
  reasoning: "Reasoning",
  coding: "Coding",
};

/** Mirrors app/schemas/skill.py resolve_skill_category. */
export function effectiveSkill(q: Pick<Question, "question_type" | "bloom_level" | "skill_category">): SkillCategory {
  if (q.skill_category) return q.skill_category;
  if (q.question_type === "code_fix") return "coding";
  return q.bloom_level >= 3 ? "reasoning" : "conceptual";
}

// ---------- Core resources ----------

export interface CodeTestCase {
  input: string;
  expected_output: string;
}

export interface Question {
  id: string;
  text: string;
  question_type: QuestionType;
  marks: number;
  bloom_level: BloomLevel;
  topic_ids: string[];
  co_ids: string[];
  unit: number | null;
  options: string[] | null;
  correct_answer: string | null;
  code_language: string | null;
  starter_code: string | null;
  test_cases: CodeTestCase[] | null;
  difficulty_score: number | null;
  embedding_id: string | null;
  is_duplicate_of: string | null;
  skill_category?: SkillCategory | null;
  source_document: string | null;
  created_at: string;
}

export interface DifficultyScore {
  score: number;
  features: Record<string, number>;
  shap_contributions: Record<string, number> | null;
  method: "heuristic" | "model";
}

export interface DuplicateMatch {
  existing_question_id: string;
  semantic_score: number;
  graph_score: number;
  structural_score: number;
  final_score: number;
  is_duplicate: boolean;
}

export interface GeneratedQuestionResult {
  question: Question;
  difficulty: DifficultyScore;
  duplicate_matches: DuplicateMatch[];
}

export interface GraphNode {
  id: string;
  name: string;
  description: string;
  importance_score: number;
  question_count: number;
  coverage_pct: number;
  degree: number;
  neglected: boolean;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation_type: string;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export type DocumentCategory = "syllabus" | "notes" | "papers";
export type DocumentStatus = "processing" | "processed" | "failed";

export interface UploadedDocument {
  id: string;
  filename: string;
  category: DocumentCategory;
  size_bytes: number;
  status: DocumentStatus;
  topics_extracted: number;
  error_message: string | null;
  uploaded_at: string;
}

// ---------- Subjects ----------

export interface Subject {
  id: string;
  teacher_id: string;
  name: string;
  created_at: string;
}

export function listSubjects() {
  return apiFetch<Subject[]>("/subjects");
}

export function createSubject(name: string) {
  return apiFetch<Subject>("/subjects", { method: "POST", body: JSON.stringify({ name }) });
}

export function deleteSubject(id: string) {
  return apiFetch<{ deleted: string }>(`/subjects/${id}`, { method: "DELETE" });
}

// ---------- Exams (weekly quizzes) ----------

export type ExamStatus = "draft" | "scheduled" | "closed";
export type ExamBucket = "draft" | "upcoming" | "live" | "closed";

export interface Exam {
  id: string;
  teacher_id: string;
  subject_id: string;
  name: string;
  question_ids: string[];
  total_marks: number;
  duration_minutes: number | null;
  go_live_at: string | null;
  closes_at: string | null;
  password: string | null;
  status: ExamStatus;
  bucket: ExamBucket;
  closed_by: "teacher" | "schedule" | null;
  exam_type: AssessmentType;
  pattern_id: string | null;
  created_at: string;
  updated_at: string;
}

export type AssessmentType = "QUIZ" | "MSE" | "SEE";

export const ASSESSMENT_TYPE_LABELS: Record<AssessmentType, string> = {
  QUIZ: "Quiz",
  MSE: "MSE",
  SEE: "SEE",
};

// ---------- fetch helpers ----------

export class ApiError extends Error {}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const isFormData = options.body instanceof FormData;
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...authHeaders(),
      ...options.headers,
    },
  });
  if (res.status === 401) {
    clearSession();
    window.dispatchEvent(new Event("synapset:session-expired"));
    throw new AuthError("Session expired, please log in again");
  }
  if (!res.ok) {
    const text = await res.text();
    let message = text;
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed.detail === "string") {
        message = parsed.detail;
      } else if (Array.isArray(parsed.detail)) {
        // FastAPI/pydantic validation errors: keep just the human-readable messages.
        message = parsed.detail
          .map((d: { msg?: string }) => (d.msg ?? "").replace(/^Value error, /, ""))
          .filter(Boolean)
          .join("; ");
      } else {
        message = JSON.stringify(parsed.detail ?? parsed);
      }
    } catch {
      // not json, use raw text
    }
    throw new ApiError(message || `${res.status} ${res.statusText}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ---------- Auth ----------

export interface AuthResponse {
  access_token: string;
  teacher: TeacherPublic;
}

export function signup(email: string, password: string, name: string) {
  return apiFetch<AuthResponse>("/auth/signup", { method: "POST", body: JSON.stringify({ email, password, name }) });
}

export function login(email: string, password: string) {
  return apiFetch<AuthResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
}

export function me() {
  return apiFetch<TeacherPublic>("/auth/me");
}

// ---------- Graph & documents ----------

export function fetchGraph(subjectId: string) {
  return apiFetch<GraphResponse>(`/graph?subject_id=${encodeURIComponent(subjectId)}`);
}

export function fetchDocuments(subjectId: string) {
  return apiFetch<UploadedDocument[]>(`/graph/documents?subject_id=${encodeURIComponent(subjectId)}`);
}

export function deleteDocument(subjectId: string, id: string) {
  return apiFetch<{ deleted: string }>(`/graph/documents/${id}?subject_id=${encodeURIComponent(subjectId)}`, {
    method: "DELETE",
  });
}

export interface IngestResult {
  document: UploadedDocument;
  retrieval_chunks_indexed: number;
  extraction_chunks_processed: number;
  graph_nodes: number;
  graph_edges: number;
}

export function ingestDocument(file: File, category: DocumentCategory, subjectId: string, courseOutcomes?: string) {
  const form = new FormData();
  form.append("file", file);
  form.append("category", category);
  form.append("subject_id", subjectId);
  if (courseOutcomes) form.append("course_outcomes", courseOutcomes);
  return apiFetch<IngestResult>("/graph/ingest", { method: "POST", body: form });
}

export interface DedupeTopicsResult {
  merged_groups: number;
  nodes_removed: number;
  questions_updated: number;
}

export function dedupeTopics(subjectId: string) {
  return apiFetch<DedupeTopicsResult>(`/graph/dedupe-topics?subject_id=${encodeURIComponent(subjectId)}`, {
    method: "POST",
  });
}

// ---------- Questions ----------

export interface GenerateQuestionsParams {
  subject_id: string;
  topic: string;
  num_questions: number;
  bloom_level: BloomLevel;
  marks: number;
  question_type: QuestionType;
  check_duplicates?: boolean;
  save_to_bank?: boolean;
}

export function generateQuestions(params: GenerateQuestionsParams) {
  return apiFetch<{ results: GeneratedQuestionResult[] }>("/questions/generate", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export function fetchQuestions(subjectId: string) {
  return apiFetch<Question[]>(`/questions?subject_id=${encodeURIComponent(subjectId)}`);
}

export function saveQuestion(subjectId: string, question: Question) {
  return apiFetch<Question>(`/questions?subject_id=${encodeURIComponent(subjectId)}`, {
    method: "POST",
    body: JSON.stringify(question),
  });
}

export function deleteQuestion(subjectId: string, id: string) {
  return apiFetch<{ deleted: string }>(`/questions/${id}?subject_id=${encodeURIComponent(subjectId)}`, {
    method: "DELETE",
  });
}

export function checkDuplicates(subjectId: string, question: Question, threshold = 0.75) {
  return apiFetch<{ matches: DuplicateMatch[] }>("/questions/check-duplicates", {
    method: "POST",
    body: JSON.stringify({ subject_id: subjectId, question, threshold }),
  });
}

// ---------- Exams ----------

export function createExam(data: {
  subject_id: string;
  name: string;
  question_ids?: string[];
  total_marks?: number;
  duration_minutes?: number | null;
  exam_type?: AssessmentType;
  pattern_id?: string | null;
}) {
  return apiFetch<Exam>("/exams", { method: "POST", body: JSON.stringify(data) });
}

export function listExams(subjectId: string) {
  return apiFetch<Exam[]>(`/exams?subject_id=${encodeURIComponent(subjectId)}`);
}

export function getExam(id: string) {
  return apiFetch<{ exam: Exam; questions: Question[] }>(`/exams/${id}`);
}

export function updateExam(
  id: string,
  data: Partial<{
    name: string;
    question_ids: string[];
    total_marks: number;
    duration_minutes: number | null;
    go_live_at: string | null;
    closes_at: string | null;
    password: string | null;
    status: ExamStatus;
    exam_type: AssessmentType;
    pattern_id: string | null;
  }>
) {
  return apiFetch<Exam>(`/exams/${id}`, { method: "PATCH", body: JSON.stringify(data) });
}

export function deleteExam(id: string) {
  return apiFetch<{ deleted: string }>(`/exams/${id}`, { method: "DELETE" });
}

// ---------- Submissions (results) ----------

export interface GradedAnswer {
  question_id: string;
  question_type: QuestionType;
  auto_graded: boolean;
  correct: boolean | null;
  marks_awarded: number;
  max_marks: number;
  detail: string;
  answer?: string | null;
  manually_graded?: boolean;
  feedback?: string | null;
  bloom_level?: number | null;
  topic_ids?: string[] | null;
  skill_category?: SkillCategory | null;
  difficulty_score?: number | null;
  test_cases_passed?: number | null;
  test_cases_total?: number | null;
}

export interface Submission {
  id: string;
  exam_id: string;
  student_name: string;
  student_identifier: string | null;
  answers: GradedAnswer[];
  total_marks_awarded: number;
  total_max_marks: number;
  fully_auto_graded: boolean;
  submitted_at: string;
}

export function getExamSubmissions(examId: string) {
  return apiFetch<Submission[]>(`/exams/${examId}/submissions`);
}

export interface AttemptSummary {
  attempt_id: string;
  student_name: string;
  student_identifier: string | null;
  started_at: string;
  deadline: string | null;
  remaining_seconds: number | null;
  expired: boolean;
  submitted: boolean;
  submitted_at: string | null;
}

export function getExamAttempts(examId: string) {
  return apiFetch<AttemptSummary[]>(`/exams/${examId}/attempts`);
}

export function gradeSubmissionAnswer(
  examId: string,
  submissionId: string,
  questionId: string,
  marksAwarded: number,
  feedback?: string
) {
  return apiFetch<Submission>(
    `/exams/${examId}/submissions/${submissionId}/answers/${encodeURIComponent(questionId)}`,
    { method: "PATCH", body: JSON.stringify({ marks_awarded: marksAwarded, feedback: feedback || null }) }
  );
}

// ---------- Question paper patterns ----------

export type PatternExamType = "MSE" | "SEE";
export type DifficultyLevel = "easy" | "medium" | "hard";

export const DIFFICULTY_LEVELS: DifficultyLevel[] = ["easy", "medium", "hard"];

export interface PatternSection {
  name: string;
  instructions: string;
  num_questions: number;
  marks_per_question: number;
  question_types: QuestionType[];
  bloom_levels: BloomLevel[];
}

export interface PatternUnit {
  unit: number;
  name: string;
  topic_ids: string[];
  percent: number;
}

export interface ExamPatternFields {
  name: string;
  exam_type: PatternExamType;
  description: string;
  total_marks: number;
  duration_minutes: number;
  sections: PatternSection[];
  bloom_distribution: { bloom_level: BloomLevel; percent: number }[];
  difficulty_distribution: { difficulty: DifficultyLevel; percent: number }[];
  units: PatternUnit[];
  co_requirements: { co_code: string; min_questions: number }[];
  tolerance_percent: number;
}

export interface ExamPattern extends ExamPatternFields {
  id: string;
  teacher_id: string;
  subject_id: string;
  source_filename: string | null;
  created_at: string;
  updated_at: string;
}

export interface SectionReport {
  name: string;
  required: number;
  marks_per_question: number;
  filled: number;
  question_ids: string[];
  eligible_in_pool: number;
}

export interface DistributionRow {
  key: string;
  label: string;
  target_percent: number | null;
  actual_percent: number;
  actual_marks: number;
  within_tolerance: boolean;
}

export interface ComplianceReport {
  compliant: boolean;
  target_marks: number;
  actual_marks: number;
  sections: SectionReport[];
  bloom: DistributionRow[];
  difficulty: DistributionRow[];
  units: DistributionRow[];
  course_outcomes: { co_code: string; min_questions: number; actual: number; met: boolean }[];
  topics_covered: number;
  unassigned_question_ids: string[];
  issues: string[];
}

export type ConstraintFamily = "sections" | "bloom" | "difficulty" | "units" | "course_outcomes";

export const CONSTRAINT_LABELS: Record<ConstraintFamily, string> = {
  sections: "section slots",
  bloom: "Bloom's distribution",
  difficulty: "difficulty distribution",
  units: "unit distribution",
  course_outcomes: "course-outcome coverage",
};

export interface AssembleResponse {
  assembly: {
    status: "optimal" | "feasible" | "infeasible";
    satisfied: boolean;
    relaxed: ConstraintFamily[];
    blocking: ConstraintFamily[];
    question_ids: string[];
    report: ComplianceReport;
  };
  generated: {
    request: { section: string; topic_name: string; question_type: QuestionType; bloom_level: BloomLevel; marks: number };
    question_id: string | null;
    skipped_reason: string | null;
  }[];
}

export interface PatternImportResult {
  draft: ExamPatternFields;
  warnings: string[];
  source_filename: string;
  valid: boolean;
}

export function listPatternPresets() {
  return apiFetch<ExamPatternFields[]>("/patterns/presets");
}

export function listPatterns(subjectId: string) {
  return apiFetch<ExamPattern[]>(`/patterns?subject_id=${encodeURIComponent(subjectId)}`);
}

export function createPattern(subjectId: string, pattern: ExamPatternFields, sourceFilename?: string | null) {
  return apiFetch<ExamPattern>("/patterns", {
    method: "POST",
    body: JSON.stringify({ ...pattern, subject_id: subjectId, source_filename: sourceFilename ?? null }),
  });
}

export function updatePattern(id: string, pattern: ExamPatternFields) {
  return apiFetch<ExamPattern>(`/patterns/${id}`, { method: "PUT", body: JSON.stringify(pattern) });
}

export function deletePattern(id: string) {
  return apiFetch<{ deleted: string }>(`/patterns/${id}`, { method: "DELETE" });
}

export function importPatternDocument(subjectId: string, file: File, examTypeHint?: PatternExamType) {
  const form = new FormData();
  form.append("subject_id", subjectId);
  form.append("file", file);
  if (examTypeHint) form.append("exam_type_hint", examTypeHint);
  return apiFetch<PatternImportResult>("/patterns/import", { method: "POST", body: form });
}

export function assembleFromPattern(id: string, generateMissing: boolean, maxGenerate = 8) {
  return apiFetch<AssembleResponse>(`/patterns/${id}/assemble`, {
    method: "POST",
    body: JSON.stringify({ generate_missing: generateMissing, max_generate: maxGenerate }),
  });
}

export function checkAgainstPattern(id: string, questionIds: string[]) {
  return apiFetch<ComplianceReport>(`/patterns/${id}/check`, {
    method: "POST",
    body: JSON.stringify({ question_ids: questionIds }),
  });
}

// ---------- Performance analytics ----------

export type Band = "strong" | "developing" | "needs_support" | "insufficient";

export const BAND_LABELS: Record<Band, string> = {
  strong: "Strong",
  developing: "Developing",
  needs_support: "Needs support",
  insufficient: "Not enough data",
};

export interface ScoreStat {
  awarded: number;
  max: number;
  percent: number | null;
  answers: number;
  pending: number;
}

export interface GradeInfo {
  grade: string;
  label: string;
}

export interface BreakdownRow {
  key: string;
  label: string;
  score: ScoreStat;
  band: Band;
}

export interface SkillRow {
  skill: SkillCategory;
  label: string;
  score: ScoreStat;
  band: Band;
}

export interface Breakdowns {
  skills: SkillRow[];
  coding_tests: { passed: number; total: number; percent: number | null } | null;
  bloom: BreakdownRow[];
  topics: BreakdownRow[];
  question_types: BreakdownRow[];
  difficulty: BreakdownRow[];
  strengths: BreakdownRow[];
  weaknesses: BreakdownRow[];
}

export interface TrendPoint {
  exam_id: string;
  name: string;
  date: string;
  percent: number | null;
}

export interface AssessmentRow {
  exam_id: string;
  name: string;
  exam_type: AssessmentType;
  date: string;
  total_marks: number;
  submissions: number;
  average_percent: number | null;
  highest_percent: number | null;
  lowest_percent: number | null;
  pending: number;
}

export interface StudentRow {
  key: string;
  name: string;
  identifier: string | null;
  assessments: number;
  percent: number | null;
  grade: GradeInfo | null;
  band: Band;
  skills: Record<SkillCategory, number | null>;
  trend_delta: number | null;
  pending: number;
  last_submitted_at: string;
}

export interface ClassOverview {
  summary: {
    students: number;
    assessments: number;
    submissions: number;
    average_percent: number | null;
    median_percent: number | null;
    highest_percent: number | null;
    lowest_percent: number | null;
    pass_rate: number | null;
    pending_answers: number;
  };
  grade_distribution: { grade: string; label: string; min_percent: number; count: number }[];
  score_histogram: { start: number; end: number; count: number }[];
  breakdowns: Breakdowns;
  assessments: AssessmentRow[];
  trend: TrendPoint[];
  students: StudentRow[];
}

export interface StudentHistoryRow {
  exam_id: string;
  name: string;
  exam_type: AssessmentType;
  date: string;
  submitted_at: string;
  awarded: number;
  max: number;
  percent: number | null;
  grade: GradeInfo | null;
  class_average_percent: number | null;
  pending: number;
}

export interface StudentDetail {
  key: string;
  name: string;
  identifier: string | null;
  summary: {
    assessments: number;
    percent: number | null;
    grade: GradeInfo | null;
    band: Band;
    rank: number | null;
    class_size: number;
    class_average_percent: number | null;
    pending_answers: number;
  };
  history: StudentHistoryRow[];
  breakdowns: Breakdowns;
  trend: TrendPoint[];
}

function analyticsQuery(subjectId: string, examType?: AssessmentType | null) {
  const params = new URLSearchParams({ subject_id: subjectId });
  if (examType) params.set("exam_type", examType);
  return params.toString();
}

export function fetchClassOverview(subjectId: string, examType?: AssessmentType | null) {
  return apiFetch<ClassOverview>(`/analytics/overview?${analyticsQuery(subjectId, examType)}`);
}

export function fetchStudentDetail(subjectId: string, studentKey: string, examType?: AssessmentType | null) {
  return apiFetch<StudentDetail>(
    `/analytics/students/${encodeURIComponent(studentKey)}?${analyticsQuery(subjectId, examType)}`
  );
}

// ---------- Display helpers ----------

export type DifficultyBucket = Difficulty;

export function difficultyBucket(score: number | null | undefined): DifficultyBucket {
  if (score == null) return "Medium";
  if (score <= 4) return "Easy";
  if (score <= 7) return "Medium";
  return "Hard";
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return `${value.toFixed(1)} ${units[i]}`;
}

export function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} hr${hrs > 1 ? "s" : ""} ago`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days} days ago`;
  return new Date(iso).toLocaleDateString();
}
