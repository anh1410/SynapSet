import { useEffect, useState } from "react";
import {
  FileStack,
  Clock,
  Plus,
  Trash2,
  AlertTriangle,
  Save,
  Sparkles,
  RefreshCw,
  Lock,
  CalendarClock,
  KeyRound,
  LayoutTemplate,
  Wand2,
  CheckCircle2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { PatternCompliancePanel } from "@/components/PatternCompliancePanel";
import {
  BLOOM_LEVELS,
  BLOOM_LABELS,
  CONSTRAINT_LABELS,
  SKILL_LABELS,
  assembleFromPattern,
  checkAgainstPattern,
  effectiveSkill,
  listPatterns,
  type ComplianceReport,
  type ExamPattern,
  QUESTION_TYPE_LABELS,
  QUESTION_TYPE_ORDER,
  createExam,
  fetchGraph,
  fetchQuestions,
  generateQuestions,
  getExam,
  updateExam,
  type BloomLevel,
  type GraphNode,
  type Question,
  type QuestionType,
} from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { cn } from "@/lib/utils";

interface BuilderRow {
  rowId: string;
  status: "pending" | "generating" | "generated" | "error";
  topicId: string;
  questionType: QuestionType;
  bloomLevel: BloomLevel;
  marks: number;
  question?: Question;
  error?: string;
}

let rowIdCounter = 0;
const newRowId = () => `row-${Date.now()}-${++rowIdCounter}`;

function makeRow(topics: GraphNode[]): BuilderRow {
  return {
    rowId: newRowId(),
    status: "pending",
    topicId: topics[0]?.id ?? "",
    questionType: "short_answer",
    bloomLevel: 2,
    marks: 5,
  };
}

/** ISO timestamp -> value for a <input type="datetime-local">, in the
 *  browser's local time (slicing the ISO string would show UTC as local). */
function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function rowFromQuestion(q: Question): BuilderRow {
  return {
    rowId: q.id,
    status: "generated",
    topicId: q.topic_ids[0] ?? "",
    questionType: q.question_type,
    bloomLevel: q.bloom_level,
    marks: q.marks,
    question: q,
  };
}

export function ExamBuilderPage({
  seedQuestionIds,
  editExamId,
  initialPatternId = null,
  onSaved,
}: {
  seedQuestionIds: string[];
  editExamId: string | null;
  initialPatternId?: string | null;
  onSaved: (examId: string) => void;
}) {
  const { activeSubjectId } = useAuth();
  const [topics, setTopics] = useState<GraphNode[]>([]);
  const [examId, setExamId] = useState<string | null>(editExamId);
  const [examName, setExamName] = useState(`Weekly Quiz — ${new Date().toLocaleDateString()}`);
  const [duration, setDuration] = useState(30);
  const [goLiveAt, setGoLiveAt] = useState("");
  const [closesAt, setClosesAt] = useState("");
  const [password, setPassword] = useState("");
  const [rows, setRows] = useState<BuilderRow[]>([]);
  const [generatingAll, setGeneratingAll] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [showAnswerKey, setShowAnswerKey] = useState(false);
  const [patterns, setPatterns] = useState<ExamPattern[]>([]);
  const [patternId, setPatternId] = useState<string | null>(initialPatternId);
  const [report, setReport] = useState<ComplianceReport | null>(null);
  const [assembling, setAssembling] = useState(false);
  const [generateMissing, setGenerateMissing] = useState(false);
  const [assembleNote, setAssembleNote] = useState<{ ok: boolean; lines: string[] } | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const pattern = patterns.find((p) => p.id === patternId) ?? null;

  useEffect(() => {
    if (!activeSubjectId) return;
    listPatterns(activeSubjectId).then(setPatterns);
  }, [activeSubjectId]);

  // A pattern chosen for a brand-new exam supplies its name and duration.
  useEffect(() => {
    if (!pattern || examId) return;
    setExamName(`${pattern.exam_type} — ${pattern.name}`);
    setDuration(pattern.duration_minutes);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pattern?.id]);

  useEffect(() => {
    if (!activeSubjectId) return;
    fetchGraph(activeSubjectId).then((g) => setTopics(g.nodes));
  }, [activeSubjectId]);

  useEffect(() => {
    if (loaded || !activeSubjectId) return;

    if (editExamId) {
      getExam(editExamId).then(({ exam, questions }) => {
        setExamId(exam.id);
        setExamName(exam.name);
        setDuration(exam.duration_minutes ?? 30);
        setGoLiveAt(toLocalInput(exam.go_live_at));
        setClosesAt(toLocalInput(exam.closes_at));
        setPassword(exam.password ?? "");
        setPatternId(exam.pattern_id);
        setRows(questions.map(rowFromQuestion));
        setLoaded(true);
      });
      return;
    }

    if (seedQuestionIds.length > 0) {
      fetchQuestions(activeSubjectId).then((all) => {
        const byId = new Map(all.map((q) => [q.id, q]));
        setRows(
          seedQuestionIds
            .map((id) => byId.get(id))
            .filter((q): q is Question => Boolean(q))
            .map(rowFromQuestion)
        );
        setLoaded(true);
      });
      return;
    }

    setLoaded(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editExamId, seedQuestionIds, loaded, activeSubjectId]);

  useEffect(() => {
    if (loaded && !editExamId && !initialPatternId && seedQuestionIds.length === 0 && rows.length === 0 && topics.length > 0) {
      setRows([makeRow(topics)]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded, topics]);

  const topicName = (id: string) => topics.find((t) => t.id === id)?.name ?? id;

  const addRow = () => setRows((r) => [...r, makeRow(topics)]);
  const removeRow = (rowId: string) => setRows((r) => r.filter((row) => row.rowId !== rowId));
  const updateRow = <K extends keyof BuilderRow>(rowId: string, key: K, value: BuilderRow[K]) =>
    setRows((r) => r.map((row) => (row.rowId === rowId ? { ...row, [key]: value } : row)));

  const generateRow = async (rowId: string) => {
    const row = rows.find((r) => r.rowId === rowId);
    if (!row || !row.topicId || !activeSubjectId) return;
    updateRow(rowId, "status", "generating");
    try {
      const { results } = await generateQuestions({
        subject_id: activeSubjectId,
        topic: topicName(row.topicId),
        num_questions: 1,
        bloom_level: row.bloomLevel,
        marks: row.marks,
        question_type: row.questionType,
        check_duplicates: true,
        save_to_bank: true,
      });
      if (results.length === 0) {
        setRows((r) => r.map((x) => (x.rowId === rowId ? { ...x, status: "error", error: "No question returned" } : x)));
        return;
      }
      setRows((r) => r.map((x) => (x.rowId === rowId ? { ...x, status: "generated", question: results[0].question } : x)));
    } catch (e) {
      setRows((r) =>
        r.map((x) => (x.rowId === rowId ? { ...x, status: "error", error: e instanceof Error ? e.message : "Generation failed" } : x))
      );
    }
  };

  const generateAll = async () => {
    setGeneratingAll(true);
    const pending = rows.filter((r) => r.status === "pending" || r.status === "error");
    for (const row of pending) {
      await generateRow(row.rowId);
    }
    setGeneratingAll(false);
  };

  const generatedRows = rows.filter((r) => r.status === "generated" && r.question);
  const totalMarks = generatedRows.reduce((s, r) => s + (r.question?.marks ?? 0), 0);
  const selectedIdsKey = generatedRows.map((r) => r.question!.id).join(",");

  // Live compliance check against the chosen pattern (same rules the assembler uses).
  useEffect(() => {
    if (!patternId) {
      setReport(null);
      return;
    }
    const ids = selectedIdsKey ? selectedIdsKey.split(",") : [];
    const t = setTimeout(() => {
      checkAgainstPattern(patternId, ids).then(setReport).catch(() => setReport(null));
    }, 250);
    return () => clearTimeout(t);
  }, [patternId, selectedIdsKey]);

  const sectionOf = (questionId: string) => report?.sections.find((s) => s.question_ids.includes(questionId))?.name;

  const handleAssemble = async () => {
    if (!patternId || !activeSubjectId) return;
    setAssembling(true);
    setAssembleNote(null);
    try {
      const { assembly, generated } = await assembleFromPattern(patternId, generateMissing);
      const bank = await fetchQuestions(activeSubjectId);
      const byId = new Map(bank.map((q) => [q.id, q]));
      const picked = assembly.question_ids.map((id) => byId.get(id)).filter((q): q is Question => Boolean(q));
      setRows(picked.map(rowFromQuestion));

      const lines: string[] = [];
      if (assembly.satisfied) {
        lines.push(`Assembled ${picked.length} questions meeting every pattern constraint.`);
      } else {
        lines.push(
          `The question bank can't satisfy this pattern yet (blocked by ${assembly.blocking.map((b) => CONSTRAINT_LABELS[b]).join(", ")}). ` +
            `This draft relaxes ${assembly.relaxed.map((b) => CONSTRAINT_LABELS[b]).join(", ")}.`
        );
      }
      if (generated.length) {
        const made = generated.filter((g) => g.question_id).length;
        lines.push(`Generated ${made} new question${made === 1 ? "" : "s"} into the bank for short sections.`);
        generated
          .filter((g) => g.skipped_reason)
          .forEach((g) => lines.push(`${g.request.section} (${g.request.topic_name}): ${g.skipped_reason}`));
      } else if (!assembly.satisfied && !generateMissing && assembly.blocking.includes("sections")) {
        lines.push("Tick “Generate missing questions” to have the AI write questions for the short sections.");
      }
      setAssembleNote({ ok: assembly.satisfied, lines });
    } catch (e) {
      setAssembleNote({ ok: false, lines: [e instanceof Error ? e.message : "Assembly failed"] });
    } finally {
      setAssembling(false);
    }
  };
  const anyError = rows.some((r) => r.status === "error");
  const anyPending = rows.some((r) => r.status === "pending");

  // Mirrors the server rule (Exam._closes_after_go_live) so the teacher sees it before saving.
  const scheduleError =
    closesAt && !goLiveAt
      ? "Set a go-live time before setting a closing time."
      : closesAt && goLiveAt && new Date(closesAt) <= new Date(goLiveAt)
        ? "Closing time must be after the go-live time."
        : null;

  const handleSave = async () => {
    if (generatedRows.length === 0 || !activeSubjectId) return;
    if (scheduleError) {
      setSaveError(scheduleError);
      return;
    }
    setSaving(true);
    setSaveError(null);
    const typeInfo = { exam_type: pattern ? pattern.exam_type : ("QUIZ" as const), pattern_id: pattern ? pattern.id : null };
    try {
      const question_ids = generatedRows.map((r) => r.question!.id);
      const scheduleUpdate = {
        go_live_at: goLiveAt ? new Date(goLiveAt).toISOString() : null,
        closes_at: closesAt ? new Date(closesAt).toISOString() : null,
        password: password.trim() || null,
      };

      let savedId = examId;
      if (savedId) {
        await updateExam(savedId, {
          name: examName,
          question_ids,
          total_marks: totalMarks,
          duration_minutes: duration,
          ...typeInfo,
          ...scheduleUpdate,
        });
      } else {
        const exam = await createExam({
          subject_id: activeSubjectId,
          name: examName,
          question_ids,
          total_marks: totalMarks,
          duration_minutes: duration,
          ...typeInfo,
        });
        savedId = exam.id;
        if (scheduleUpdate.go_live_at || scheduleUpdate.closes_at || scheduleUpdate.password) {
          await updateExam(savedId, scheduleUpdate);
        }
      }
      onSaved(savedId);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Couldn't save the exam");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-1 h-fit lg:sticky lg:top-20">
        <CardHeader>
          <div className="flex items-center gap-2">
            <FileStack className="h-4 w-4 text-primary" />
            <CardTitle>Exam Builder</CardTitle>
          </div>
          <CardDescription>
            Add questions one at a time, or pick an MSE/SEE pattern and let the assembler fill it from your question bank
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2 rounded-lg border border-border p-3">
            <p className="flex items-center gap-1.5 text-[11px] font-semibold text-foreground">
              <LayoutTemplate className="h-3.5 w-3.5" /> Exam pattern
            </p>
            <Select
              value={patternId ?? ""}
              onChange={(e) => {
                setPatternId(e.target.value || null);
                setAssembleNote(null);
              }}
              aria-label="Exam pattern"
            >
              <option value="">None — free-form quiz</option>
              {patterns.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.exam_type} · {p.name} ({p.total_marks} marks)
                </option>
              ))}
            </Select>
            {patterns.length === 0 && <p className="text-[11px] text-muted-foreground">Create MSE/SEE patterns under Exam Patterns.</p>}
            {pattern && (
              <>
                <label className="flex items-start gap-2 text-[11px] text-muted-foreground">
                  <Checkbox checked={generateMissing} onCheckedChange={setGenerateMissing} className="mt-0.5" />
                  <span>Generate missing questions with AI when the bank can't fill a section (Graph-RAG, saved to the bank)</span>
                </label>
                <Button size="sm" className="w-full" onClick={handleAssemble} disabled={assembling}>
                  <Wand2 className="h-3.5 w-3.5" />
                  {assembling ? (generateMissing ? "Assembling & generating..." : "Assembling...") : "Auto-assemble from pattern"}
                </Button>
                {rows.length > 0 && !assembling && <p className="text-[11px] text-muted-foreground">Replaces the current question list.</p>}
              </>
            )}
            {assembleNote && (
              <div className={cn("space-y-1 rounded-md p-2 text-[11px] text-foreground", assembleNote.ok ? "bg-success/[0.06]" : "bg-warning/[0.06]")}>
                {assembleNote.lines.map((line, i) => (
                  <p key={i} className={cn(i === 0 && "flex items-start gap-1 font-medium")}>
                    {i === 0 &&
                      (assembleNote.ok ? (
                        <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-success" />
                      ) : (
                        <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-warning" />
                      ))}
                    {line}
                  </p>
                ))}
              </div>
            )}
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-foreground">{pattern ? "Exam Name" : "Quiz Name"}</label>
            <Input value={examName} onChange={(e) => setExamName(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-xs font-medium text-foreground">
              <Clock className="h-3.5 w-3.5" /> Duration (min)
            </label>
            <Input value={duration} onChange={(e) => setDuration(Number(e.target.value))} type="number" />
            <p className="text-[11px] text-muted-foreground">
              Each student's timer starts when they begin and is enforced by the server.
            </p>
          </div>

          <div className="space-y-3 rounded-lg border border-border p-3">
            <p className="flex items-center gap-1.5 text-[11px] font-semibold text-foreground">
              <CalendarClock className="h-3.5 w-3.5" /> Schedule (optional now)
            </p>
            {/* Stacks in the narrow builder column on large screens, side by side on tablets. */}
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-1 2xl:grid-cols-2">
              <div className="space-y-1">
                <label className="text-[11px] font-medium text-muted-foreground">Go live at</label>
                <Input type="datetime-local" value={goLiveAt} onChange={(e) => setGoLiveAt(e.target.value)} />
              </div>
              <div className="space-y-1">
                <label className="text-[11px] font-medium text-muted-foreground">Closes at (optional)</label>
                <Input
                  type="datetime-local"
                  value={closesAt}
                  min={goLiveAt || undefined}
                  onChange={(e) => setClosesAt(e.target.value)}
                  aria-invalid={Boolean(scheduleError)}
                />
              </div>
            </div>
            {scheduleError ? (
              <p className="flex items-center gap-1.5 text-[11px] text-destructive">
                <AlertTriangle className="h-3 w-3" /> {scheduleError}
              </p>
            ) : (
              <p className="text-[11px] text-muted-foreground">
                {closesAt
                  ? "No new attempts after the closing time; students already in progress must finish by then."
                  : "Without a closing time the exam stays open until you close it."}
              </p>
            )}
            <div className="space-y-1">
              <label className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
                <Lock className="h-3 w-3" /> Access password
              </label>
              <Input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Students enter this to start the quiz"
              />
            </div>
          </div>

          <div className="space-y-3">
            {rows.map((row, idx) => (
              <div key={row.rowId} className="space-y-2 rounded-lg border border-border p-3">
                <div className="flex items-center justify-between">
                  <label className="text-[11px] font-semibold text-foreground">Question {idx + 1}</label>
                  <button className="text-muted-foreground hover:text-destructive" onClick={() => removeRow(row.rowId)}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>

                {row.status === "generated" && row.question ? (
                  <div className="space-y-1.5">
                    <p className="line-clamp-2 text-xs text-foreground">{row.question.text}</p>
                    <div className="flex flex-wrap gap-1.5">
                      <Badge variant="outline">{QUESTION_TYPE_LABELS[row.question.question_type]}</Badge>
                      <Badge variant="outline">{row.question.marks} marks</Badge>
                      <Badge variant="accent">{BLOOM_LABELS[row.question.bloom_level]}</Badge>
                    </div>
                    <Button variant="ghost" size="sm" onClick={() => generateRow(row.rowId)}>
                      <RefreshCw className="h-3.5 w-3.5" /> Regenerate
                    </Button>
                  </div>
                ) : (
                  <>
                    <Select
                      value={row.topicId}
                      onChange={(e) => updateRow(row.rowId, "topicId", e.target.value)}
                      disabled={topics.length === 0}
                    >
                      {topics.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name}
                        </option>
                      ))}
                    </Select>
                    <div className="grid grid-cols-2 gap-2">
                      <Select
                        value={row.questionType}
                        onChange={(e) => updateRow(row.rowId, "questionType", e.target.value as QuestionType)}
                      >
                        {QUESTION_TYPE_ORDER.map((qt) => (
                          <option key={qt} value={qt}>
                            {QUESTION_TYPE_LABELS[qt]}
                          </option>
                        ))}
                      </Select>
                      <Select
                        value={row.bloomLevel}
                        onChange={(e) => updateRow(row.rowId, "bloomLevel", Number(e.target.value) as BloomLevel)}
                      >
                        {BLOOM_LEVELS.map((b) => (
                          <option key={b} value={b}>
                            {BLOOM_LABELS[b]}
                          </option>
                        ))}
                      </Select>
                    </div>
                    <Input
                      type="number"
                      min={1}
                      value={row.marks}
                      onChange={(e) => updateRow(row.rowId, "marks", Math.max(1, Number(e.target.value)))}
                      placeholder="Marks"
                    />
                    {row.status === "error" && (
                      <p className="flex items-center gap-1.5 text-[11px] text-destructive">
                        <AlertTriangle className="h-3 w-3" /> {row.error}
                      </p>
                    )}
                    <Button
                      size="sm"
                      variant="outline"
                      className="w-full"
                      onClick={() => generateRow(row.rowId)}
                      disabled={row.status === "generating" || !row.topicId}
                    >
                      <Sparkles className="h-3.5 w-3.5" /> {row.status === "generating" ? "Generating..." : "Generate"}
                    </Button>
                  </>
                )}
              </div>
            ))}
          </div>

          <Button variant="outline" size="sm" className="w-full" onClick={addRow} disabled={topics.length === 0}>
            <Plus className="h-3.5 w-3.5" /> Add Question
          </Button>

          {topics.length === 0 && <p className="text-xs text-muted-foreground">Upload material first to see topics here.</p>}

          <div className="rounded-lg border border-border bg-secondary/40 p-3 text-xs">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Ready</span>
              <span className="font-medium text-foreground">
                {generatedRows.length} of {rows.length} question{rows.length !== 1 && "s"} · {totalMarks} marks
              </span>
            </div>
          </div>

          {anyPending && (
            <Button variant="secondary" className="w-full" onClick={generateAll} disabled={generatingAll}>
              <Sparkles className="h-4 w-4" /> {generatingAll ? "Generating..." : "Generate All Pending"}
            </Button>
          )}

          {saveError && <p className="text-xs text-destructive">{saveError}</p>}
          <Button className="w-full" onClick={handleSave} disabled={saving || generatedRows.length === 0}>
            <Save className="h-4 w-4" /> {saving ? "Saving..." : examId ? "Save Changes" : pattern ? `Save ${pattern.exam_type}` : "Save Quiz"}
          </Button>
        </CardContent>
      </Card>

      <div className="space-y-4 lg:col-span-2">
        {pattern && report && <PatternCompliancePanel pattern={pattern} report={report} />}
        {generatedRows.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-16 text-center">
              <FileStack className="h-8 w-8 text-muted-foreground" />
              <p className="mt-3 text-sm font-medium text-foreground">No questions yet</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {pattern ? "Click “Auto-assemble from pattern”, or add questions manually" : 'Add a question, configure it, and click "Generate"'}
              </p>
            </CardContent>
          </Card>
        ) : (
          <>
            <Card className={cn(anyError ? "border-warning/30 bg-warning/[0.03]" : "border-success/30 bg-success/[0.03]")}>
              <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {generatedRows.length} question{generatedRows.length !== 1 && "s"} ready · {totalMarks} marks · {duration} min
                  </p>
                  {goLiveAt && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      Scheduled to go live {new Date(goLiveAt).toLocaleString()}
                      {closesAt && !scheduleError && ` · closes ${new Date(closesAt).toLocaleString()}`}
                      {password && " · password protected"}
                    </p>
                  )}
                </div>
                <Button variant="outline" size="sm" onClick={() => setShowAnswerKey((v) => !v)}>
                  <KeyRound className="h-3.5 w-3.5" /> {showAnswerKey ? "Hide Answer Key" : "Show Answer Key"}
                </Button>
              </CardContent>
            </Card>

            {generatedRows.map((row, idx) => {
              const q = row.question!;
              return (
                <Card key={row.rowId}>
                  <CardContent className="space-y-2 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-sm text-foreground">
                        {idx + 1}. {q.text}
                      </p>
                    </div>
                    {q.question_type === "code_fix" && q.starter_code && (
                      <pre className="overflow-x-auto rounded-md bg-slate-900 p-3 text-xs text-slate-100">
                        <code>{q.starter_code}</code>
                      </pre>
                    )}
                    {(q.question_type === "mcq" || q.question_type === "fill_in_blank") && q.options && (
                      <ul className="space-y-0.5 text-xs text-muted-foreground">
                        {q.options.map((opt, oi) => (
                          <li
                            key={oi}
                            className={cn(showAnswerKey && opt === q.correct_answer && "font-medium text-success")}
                          >
                            {String.fromCharCode(97 + oi)}) {opt}
                          </li>
                        ))}
                      </ul>
                    )}
                    {showAnswerKey && q.correct_answer && (
                      <div className="rounded-md border border-success/30 bg-success/[0.04] p-2.5">
                        <p className="text-[11px] font-semibold text-success">
                          {q.question_type === "code_fix" ? "Reference Solution" : "Answer"}
                        </p>
                        {q.question_type === "code_fix" ? (
                          <pre className="mt-1 overflow-x-auto rounded-md bg-slate-900 p-3 text-xs text-slate-100">
                            <code>{q.correct_answer}</code>
                          </pre>
                        ) : (
                          <p className="mt-0.5 whitespace-pre-wrap text-xs text-foreground">{q.correct_answer}</p>
                        )}
                      </div>
                    )}
                    <div className="flex flex-wrap gap-1.5">
                      {pattern &&
                        (sectionOf(q.id) ? <Badge variant="default">{sectionOf(q.id)}</Badge> : <Badge variant="warning">No section fits</Badge>)}
                      <Badge variant="outline">{QUESTION_TYPE_LABELS[q.question_type]}</Badge>
                      <Badge variant="outline">{SKILL_LABELS[effectiveSkill(q)]}</Badge>
                      <Badge variant="outline">{topicName(row.topicId)}</Badge>
                      <Badge variant="outline">{q.marks} marks</Badge>
                      <Badge variant="accent">{BLOOM_LABELS[q.bloom_level]}</Badge>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}
