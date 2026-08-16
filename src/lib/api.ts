const BASE = "/api/v1";

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

export type QuestionType = "mcq" | "short_answer" | "long_answer" | "numerical";

export const QUESTION_TYPE_LABELS: Record<QuestionType, string> = {
  mcq: "Multiple Choice",
  short_answer: "Short Answer",
  long_answer: "Long Answer",
  numerical: "Numerical",
};

// ---------- Core resources ----------

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

export type BlueprintStatus = "draft" | "exported";

export interface PaperBlueprint {
  id: string;
  name: string;
  total_marks: number;
  duration_minutes: number | null;
  question_ids: string[];
  status: BlueprintStatus;
  created_at: string;
  updated_at: string;
}

export interface BloomDistribution {
  weights: Partial<Record<BloomLevel, number>>;
}

export interface PaperConstraints {
  total_marks: number;
  bloom_distribution: BloomDistribution;
  co_coverage?: Record<string, number>;
  unit_marks?: Record<string, number>;
  num_questions?: number | null;
  allowed_question_types?: QuestionType[] | null;
}

// ---------- fetch helpers ----------

class ApiError extends Error {}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const isFormData = options.body instanceof FormData;
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: isFormData ? options.headers : { "Content-Type": "application/json", ...options.headers },
  });
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

async function downloadFromResponse(res: Response, fallbackName: string) {
  if (!res.ok) {
    const text = await res.text();
    throw new ApiError(text || `${res.status} ${res.statusText}`);
  }
  const blob = await res.blob();
  const disposition = res.headers.get("content-disposition");
  const match = disposition?.match(/filename="?([^"]+)"?/);
  const filename = match?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
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

// ---------- Paper: optimize & export ----------

export function optimizePaper(constraints: PaperConstraints, questionIds?: string[]) {
  return apiFetch<{ status: string; selected: Question[] }>("/paper/optimize", {
    method: "POST",
    body: JSON.stringify({ constraints, question_ids: questionIds }),
  });
}

export async function exportPaperAdhoc(title: string, questions: Question[], format: "pdf" | "docx") {
  const res = await fetch(`${BASE}/paper/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, questions, format }),
  });
  await downloadFromResponse(res, `${title}.${format}`);
}

export function createBlueprint(data: {
  name: string;
  total_marks: number;
  duration_minutes?: number;
  question_ids: string[];
}) {
  return apiFetch<PaperBlueprint>("/paper/blueprints", { method: "POST", body: JSON.stringify(data) });
}

export function listBlueprints() {
  return apiFetch<PaperBlueprint[]>("/paper/blueprints");
}

export function getBlueprint(id: string) {
  return apiFetch<{ blueprint: PaperBlueprint; questions: Question[] }>(`/paper/blueprints/${id}`);
}

export function updateBlueprint(
  id: string,
  data: Partial<{
    name: string;
    total_marks: number;
    duration_minutes: number;
    question_ids: string[];
    status: BlueprintStatus;
  }>
) {
  return apiFetch<PaperBlueprint>(`/paper/blueprints/${id}`, { method: "PATCH", body: JSON.stringify(data) });
}

export function deleteBlueprint(id: string) {
  return apiFetch<{ deleted: string }>(`/paper/blueprints/${id}`, { method: "DELETE" });
}

export async function exportBlueprint(id: string, name: string, format: "pdf" | "docx") {
  const res = await fetch(`${BASE}/paper/blueprints/${id}/export?format=${format}`);
  await downloadFromResponse(res, `${name}.${format}`);
}

// ---------- Display helpers ----------

export type DifficultyBucket = "Easy" | "Medium" | "Hard";

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

export { ApiError };
