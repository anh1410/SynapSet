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
export const DIFFICULTY_LEVELS: Difficulty[] = ["Easy", "Medium", "Hard"];

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

// ---------- Exams (weekly quizzes) ----------

export type ExamStatus = "draft" | "scheduled" | "closed";
export type ExamBucket = "draft" | "upcoming" | "live" | "closed";

export interface Exam {
  id: string;
  teacher_id: string;
  name: string;
  question_ids: string[];
  total_marks: number;
  duration_minutes: number | null;
  go_live_at: string | null;
  password: string | null;
  status: ExamStatus;
  bucket: ExamBucket;
  created_at: string;
  updated_at: string;
}

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
      message = typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail ?? parsed);
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

export function fetchGraph() {
  return apiFetch<GraphResponse>("/graph");
}

export function fetchDocuments() {
  return apiFetch<UploadedDocument[]>("/graph/documents");
}

export function deleteDocument(id: string) {
  return apiFetch<{ deleted: string }>(`/graph/documents/${id}`, { method: "DELETE" });
}

export interface IngestResult {
  document: UploadedDocument;
  retrieval_chunks_indexed: number;
  extraction_chunks_processed: number;
  graph_nodes: number;
  graph_edges: number;
}

export function ingestDocument(file: File, category: DocumentCategory, courseOutcomes?: string) {
  const form = new FormData();
  form.append("file", file);
  form.append("category", category);
  if (courseOutcomes) form.append("course_outcomes", courseOutcomes);
  return apiFetch<IngestResult>("/graph/ingest", { method: "POST", body: form });
}

export interface DedupeTopicsResult {
  merged_groups: number;
  nodes_removed: number;
  questions_updated: number;
}

export function dedupeTopics() {
  return apiFetch<DedupeTopicsResult>("/graph/dedupe-topics", { method: "POST" });
}

// ---------- Questions ----------

export interface GenerateQuestionsParams {
  topic: string;
  num_questions: number;
  bloom_level: BloomLevel;
  marks: number;
  question_type: QuestionType;
  target_difficulty?: Difficulty;
  check_duplicates?: boolean;
  save_to_bank?: boolean;
}

export function generateQuestions(params: GenerateQuestionsParams) {
  return apiFetch<{ results: GeneratedQuestionResult[] }>("/questions/generate", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export function fetchQuestions() {
  return apiFetch<Question[]>("/questions");
}

export function saveQuestion(question: Question) {
  return apiFetch<Question>("/questions", { method: "POST", body: JSON.stringify(question) });
}

export function deleteQuestion(id: string) {
  return apiFetch<{ deleted: string }>(`/questions/${id}`, { method: "DELETE" });
}

export function checkDuplicates(question: Question, threshold = 0.75) {
  return apiFetch<{ matches: DuplicateMatch[] }>("/questions/check-duplicates", {
    method: "POST",
    body: JSON.stringify({ question, threshold }),
  });
}

// ---------- Exams ----------

export function createExam(data: { name: string; question_ids?: string[]; total_marks?: number; duration_minutes?: number | null }) {
  return apiFetch<Exam>("/exams", { method: "POST", body: JSON.stringify(data) });
}

export function listExams() {
  return apiFetch<Exam[]>("/exams");
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
    password: string | null;
    status: ExamStatus;
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
