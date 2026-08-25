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
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import {
  BLOOM_LEVELS,
  BLOOM_LABELS,
  DIFFICULTY_LEVELS,
  QUESTION_TYPE_LABELS,
  QUESTION_TYPE_ORDER,
  createExam,
  difficultyBucket,
  fetchGraph,
  fetchQuestions,
  generateQuestions,
  getExam,
  updateExam,
  type BloomLevel,
  type Difficulty,
  type GraphNode,
  type Question,
  type QuestionType,
} from "@/lib/api";
import { cn } from "@/lib/utils";

interface BuilderRow {
  rowId: string;
  status: "pending" | "generating" | "generated" | "error";
  topicId: string;
  questionType: QuestionType;
  bloomLevel: BloomLevel;
  marks: number;
  difficulty: Difficulty;
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
    difficulty: "Medium",
  };
}

export function ExamBuilderPage({
  seedQuestionIds,
  editExamId,
  onSaved,
}: {
  seedQuestionIds: string[];
  editExamId: string | null;
  onSaved: (examId: string) => void;
}) {
  const [topics, setTopics] = useState<GraphNode[]>([]);
  const [examId, setExamId] = useState<string | null>(editExamId);
  const [examName, setExamName] = useState(`Weekly Quiz — ${new Date().toLocaleDateString()}`);
  const [duration, setDuration] = useState(30);
  const [goLiveAt, setGoLiveAt] = useState("");
  const [password, setPassword] = useState("");
  const [rows, setRows] = useState<BuilderRow[]>([]);
  const [generatingAll, setGeneratingAll] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    fetchGraph().then((g) => setTopics(g.nodes));
  }, []);

  useEffect(() => {
    if (loaded) return;

    if (editExamId) {
      getExam(editExamId).then(({ exam, questions }) => {
        setExamId(exam.id);
        setExamName(exam.name);
        setDuration(exam.duration_minutes ?? 30);
        setGoLiveAt(exam.go_live_at ? exam.go_live_at.slice(0, 16) : "");
        setPassword(exam.password ?? "");
        setRows(
          questions.map((q) => ({
            rowId: q.id,
            status: "generated" as const,
            topicId: q.topic_ids[0] ?? "",
            questionType: q.question_type,
            bloomLevel: q.bloom_level,
            marks: q.marks,
            difficulty: difficultyBucket(q.difficulty_score),
            question: q,
          }))
        );
        setLoaded(true);
      });
      return;
    }

    if (seedQuestionIds.length > 0) {
      fetchQuestions().then((all) => {
        const byId = new Map(all.map((q) => [q.id, q]));
        setRows(
          seedQuestionIds
            .map((id) => byId.get(id))
            .filter((q): q is Question => Boolean(q))
            .map((q) => ({
              rowId: q.id,
              status: "generated" as const,
              topicId: q.topic_ids[0] ?? "",
              questionType: q.question_type,
              bloomLevel: q.bloom_level,
              marks: q.marks,
              difficulty: difficultyBucket(q.difficulty_score),
              question: q,
            }))
        );
        setLoaded(true);
      });
      return;
    }

    setLoaded(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editExamId, seedQuestionIds, loaded]);

  useEffect(() => {
    if (loaded && !editExamId && seedQuestionIds.length === 0 && rows.length === 0 && topics.length > 0) {
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
    if (!row || !row.topicId) return;
    updateRow(rowId, "status", "generating");
    try {
      const { results } = await generateQuestions({
        topic: topicName(row.topicId),
        num_questions: 1,
        bloom_level: row.bloomLevel,
        marks: row.marks,
        question_type: row.questionType,
        target_difficulty: row.difficulty,
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
  const anyError = rows.some((r) => r.status === "error");
  const anyPending = rows.some((r) => r.status === "pending");

  const handleSave = async () => {
    if (generatedRows.length === 0) return;
    setSaving(true);
    try {
      const question_ids = generatedRows.map((r) => r.question!.id);
      const scheduleUpdate = {
        go_live_at: goLiveAt ? new Date(goLiveAt).toISOString() : null,
        password: password.trim() || null,
      };

      let savedId = examId;
      if (savedId) {
        await updateExam(savedId, {
          name: examName,
          question_ids,
          total_marks: totalMarks,
          duration_minutes: duration,
          ...scheduleUpdate,
        });
      } else {
        const exam = await createExam({
          name: examName,
          question_ids,
          total_marks: totalMarks,
          duration_minutes: duration,
        });
        savedId = exam.id;
        if (scheduleUpdate.go_live_at || scheduleUpdate.password) {
          await updateExam(savedId, scheduleUpdate);
        }
      }
      onSaved(savedId);
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
          <CardDescription>Add questions one at a time — pick topic, type, Bloom's level, marks, and difficulty for each</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-foreground">Quiz Name</label>
            <Input value={examName} onChange={(e) => setExamName(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-xs font-medium text-foreground">
              <Clock className="h-3.5 w-3.5" /> Duration (min)
            </label>
            <Input value={duration} onChange={(e) => setDuration(Number(e.target.value))} type="number" />
          </div>

          <div className="space-y-3 rounded-lg border border-border p-3">
            <p className="flex items-center gap-1.5 text-[11px] font-semibold text-foreground">
              <CalendarClock className="h-3.5 w-3.5" /> Schedule (optional now)
            </p>
            <div className="space-y-1">
              <label className="text-[11px] font-medium text-muted-foreground">Go live at</label>
              <Input type="datetime-local" value={goLiveAt} onChange={(e) => setGoLiveAt(e.target.value)} />
            </div>
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
                    <div className="grid grid-cols-2 gap-2">
                      <Select
                        value={row.difficulty}
                        onChange={(e) => updateRow(row.rowId, "difficulty", e.target.value as Difficulty)}
                      >
                        {DIFFICULTY_LEVELS.map((d) => (
                          <option key={d} value={d}>
                            {d}
                          </option>
                        ))}
                      </Select>
                      <Input
                        type="number"
                        min={1}
                        value={row.marks}
                        onChange={(e) => updateRow(row.rowId, "marks", Math.max(1, Number(e.target.value)))}
                        placeholder="Marks"
                      />
                    </div>
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

          <Button className="w-full" onClick={handleSave} disabled={saving || generatedRows.length === 0}>
            <Save className="h-4 w-4" /> {saving ? "Saving..." : examId ? "Save Changes" : "Save Quiz"}
          </Button>
        </CardContent>
      </Card>

      <div className="space-y-4 lg:col-span-2">
        {generatedRows.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-16 text-center">
              <FileStack className="h-8 w-8 text-muted-foreground" />
              <p className="mt-3 text-sm font-medium text-foreground">No questions yet</p>
              <p className="mt-1 text-xs text-muted-foreground">Add a question, configure it, and click "Generate"</p>
            </CardContent>
          </Card>
        ) : (
          <>
            <Card className={cn(anyError ? "border-warning/30 bg-warning/[0.03]" : "border-success/30 bg-success/[0.03]")}>
              <CardContent className="p-4">
                <p className="text-sm font-medium text-foreground">
                  {generatedRows.length} question{generatedRows.length !== 1 && "s"} ready · {totalMarks} marks · {duration} min
                </p>
                {goLiveAt && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Scheduled to go live {new Date(goLiveAt).toLocaleString()}
                    {password && " · password protected"}
                  </p>
                )}
              </CardContent>
            </Card>

            {generatedRows.map((row, idx) => {
              const q = row.question!;
              const bucket = difficultyBucket(q.difficulty_score);
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
                          <li key={oi} className={cn(opt === q.correct_answer && "font-medium text-success")}>
                            {String.fromCharCode(97 + oi)}) {opt}
                          </li>
                        ))}
                      </ul>
                    )}
                    <div className="flex flex-wrap gap-1.5">
                      <Badge variant="outline">{QUESTION_TYPE_LABELS[q.question_type]}</Badge>
                      <Badge variant="outline">{topicName(row.topicId)}</Badge>
                      <Badge variant="outline">{q.marks} marks</Badge>
                      <Badge variant="accent">{BLOOM_LABELS[q.bloom_level]}</Badge>
                      <Badge variant={bucket === "Hard" ? "destructive" : bucket === "Medium" ? "warning" : "success"}>
                        {bucket}
                      </Badge>
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
