export const topics = [
  { id: "t1", name: "Thermodynamics", subtopics: 6, coverage: 82, questions: 34, trend: "up" as const },
  { id: "t2", name: "Fluid Mechanics", subtopics: 5, coverage: 64, questions: 21, trend: "up" as const },
  { id: "t3", name: "Electromagnetism", subtopics: 8, coverage: 91, questions: 47, trend: "flat" as const },
  { id: "t4", name: "Semiconductor Physics", subtopics: 4, coverage: 28, questions: 6, trend: "down" as const },
  { id: "t5", name: "Digital Logic Design", subtopics: 7, coverage: 55, questions: 18, trend: "flat" as const },
  { id: "t6", name: "Control Systems", subtopics: 5, coverage: 12, questions: 2, trend: "down" as const },
  { id: "t7", name: "Signal Processing", subtopics: 6, coverage: 47, questions: 14, trend: "up" as const },
  { id: "t8", name: "Data Structures", subtopics: 9, coverage: 88, questions: 52, trend: "up" as const },
];

export const neglectedTopics = topics.filter((t) => t.coverage < 40);

export type Difficulty = "Easy" | "Medium" | "Hard";
export type Bloom =
  | "Remember"
  | "Understand"
  | "Apply"
  | "Analyze"
  | "Evaluate"
  | "Create";

export interface Question {
  id: string;
  text: string;
  topic: string;
  difficulty: Difficulty;
  marks: number;
  bloom: Bloom;
  createdAt: string;
  similarity: number;
}

export const questions: Question[] = [
  {
    id: "q1",
    text: "Derive the expression for entropy change in an isothermal reversible process for an ideal gas.",
    topic: "Thermodynamics",
    difficulty: "Hard",
    marks: 10,
    bloom: "Analyze",
    createdAt: "2026-07-28",
    similarity: 12,
  },
  {
    id: "q2",
    text: "State and explain Bernoulli's principle with a real-world application.",
    topic: "Fluid Mechanics",
    difficulty: "Medium",
    marks: 5,
    bloom: "Understand",
    createdAt: "2026-07-30",
    similarity: 8,
  },
  {
    id: "q3",
    text: "Calculate the electric field due to a uniformly charged infinite sheet using Gauss's law.",
    topic: "Electromagnetism",
    difficulty: "Medium",
    marks: 8,
    bloom: "Apply",
    createdAt: "2026-08-01",
    similarity: 34,
  },
  {
    id: "q4",
    text: "Compare the working principle of NPN and PNP transistors in switching applications.",
    topic: "Semiconductor Physics",
    difficulty: "Easy",
    marks: 4,
    bloom: "Understand",
    createdAt: "2026-08-02",
    similarity: 5,
  },
  {
    id: "q5",
    text: "Design a 4-bit synchronous binary counter using JK flip-flops and explain its timing diagram.",
    topic: "Digital Logic Design",
    difficulty: "Hard",
    marks: 10,
    bloom: "Create",
    createdAt: "2026-08-02",
    similarity: 19,
  },
  {
    id: "q6",
    text: "Define Bloom's cognitive levels and identify which level this question falls under: 'List Newton's laws of motion.'",
    topic: "Control Systems",
    difficulty: "Easy",
    marks: 2,
    bloom: "Remember",
    createdAt: "2026-08-03",
    similarity: 41,
  },
  {
    id: "q7",
    text: "Evaluate the stability of a closed-loop control system using the Routh-Hurwitz criterion for a given characteristic equation.",
    topic: "Control Systems",
    difficulty: "Hard",
    marks: 10,
    bloom: "Evaluate",
    createdAt: "2026-08-03",
    similarity: 3,
  },
  {
    id: "q8",
    text: "Explain the Nyquist sampling theorem and its significance in digital signal processing.",
    topic: "Signal Processing",
    difficulty: "Medium",
    marks: 6,
    bloom: "Understand",
    createdAt: "2026-08-04",
    similarity: 15,
  },
  {
    id: "q9",
    text: "Implement a balanced binary search tree insertion algorithm and analyze its time complexity.",
    topic: "Data Structures",
    difficulty: "Hard",
    marks: 10,
    bloom: "Create",
    createdAt: "2026-08-04",
    similarity: 22,
  },
  {
    id: "q10",
    text: "Differentiate between stack and queue data structures with suitable examples.",
    topic: "Data Structures",
    difficulty: "Easy",
    marks: 3,
    bloom: "Understand",
    createdAt: "2026-07-25",
    similarity: 9,
  },
];

export const uploadedDocuments = [
  {
    id: "d1",
    name: "Semester_7_Syllabus_2026.pdf",
    type: "Syllabus",
    size: "1.2 MB",
    status: "Processed" as const,
    uploadedAt: "2026-07-20",
    topicsExtracted: 42,
  },
  {
    id: "d2",
    name: "Unit3_Thermodynamics_Notes.docx",
    type: "Class Notes",
    size: "3.4 MB",
    status: "Processed" as const,
    uploadedAt: "2026-07-25",
    topicsExtracted: 18,
  },
  {
    id: "d3",
    name: "QP_2023_MidSem.pdf",
    type: "Question Paper",
    size: "820 KB",
    status: "Processed" as const,
    uploadedAt: "2026-07-27",
    topicsExtracted: 26,
  },
  {
    id: "d4",
    name: "QP_2024_EndSem.pdf",
    type: "Question Paper",
    size: "910 KB",
    status: "Processed" as const,
    uploadedAt: "2026-07-27",
    topicsExtracted: 31,
  },
  {
    id: "d5",
    name: "Unit6_ControlSystems_Notes.pdf",
    type: "Class Notes",
    size: "2.1 MB",
    status: "Processing" as const,
    uploadedAt: "2026-08-04",
    topicsExtracted: 0,
  },
  {
    id: "d6",
    name: "Unit8_SignalProcessing_Draft.docx",
    type: "Class Notes",
    size: "1.8 MB",
    status: "Failed" as const,
    uploadedAt: "2026-08-04",
    topicsExtracted: 0,
  },
];

export const recentActivity = [
  { id: "a1", label: "Generated 3 questions on Fluid Mechanics", time: "12 min ago", type: "generate" as const },
  { id: "a2", label: "Uploaded Unit6_ControlSystems_Notes.pdf", time: "1 hr ago", type: "upload" as const },
  { id: "a3", label: "Exported Mid-Sem Exam Paper as PDF", time: "3 hrs ago", type: "export" as const },
  { id: "a4", label: "Flagged duplicate question in Data Structures", time: "5 hrs ago", type: "flag" as const },
  { id: "a5", label: "Created exam blueprint 'End-Sem 2026'", time: "Yesterday", type: "create" as const },
];

export const examBlueprints = [
  {
    id: "e1",
    name: "Mid-Semester Exam — Aug 2026",
    totalMarks: 50,
    duration: 90,
    status: "Draft" as const,
    questionCount: 12,
    updatedAt: "2026-08-04",
  },
  {
    id: "e2",
    name: "End-Semester Exam — Nov 2026",
    totalMarks: 100,
    duration: 180,
    status: "In Review" as const,
    questionCount: 24,
    updatedAt: "2026-08-02",
  },
  {
    id: "e3",
    name: "Unit Test 3 — Thermodynamics",
    totalMarks: 25,
    duration: 45,
    status: "Exported" as const,
    questionCount: 6,
    updatedAt: "2026-07-29",
  },
];
