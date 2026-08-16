import { useEffect, useMemo, useState } from "react";
import {
  FileStack,
  Wand2,
  Clock,
  Plus,
  Minus,
  Trash2,
  AlertTriangle,
  Save,
  Sparkles,
  RefreshCw,
  X,
  ShieldAlert,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  BLOOM_LEVELS,
  BLOOM_LABELS,
  QUESTION_TYPE_LABELS,
  createBlueprint,
  difficultyBucket,
  fetchGraph,
  fetchQuestions,
  generateQuestions,
  optimizePaper,
  type BloomLevel,
  type GeneratedQuestionResult,
  type GraphNode,
  type Question,
  type QuestionType,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const bloomColors: Record<BloomLevel, string> = {
  1: "bg-slate-400",
  2: "bg-sky-400",
  3: "bg-primary",
  4: "bg-warning",
  5: "bg-orange-400",
  6: "bg-destructive",
};

const defaultBloomMix: Record<BloomLevel, number> = { 1: 10, 2: 25, 3: 30, 4: 20, 5: 10, 6: 5 };

const questionTypes: QuestionType[] = ["short_answer", "long_answer", "mcq", "numerical"];

interface TopicRow {
  rowId: string;
  topicId: string;
  count: number;
  questionType: QuestionType;
  bloomLevel: BloomLevel;
  marks: number;
}

interface RowResult {
  rowId: string;
  results: GeneratedQuestionResult[];
  error: string | null;
}

let rowIdCounter = 0;
const newRowId = () => `row-${++rowIdCounter}`;

export function ExamBuilderPage({
  seedQuestionIds,
  onSaved,
}: {
  seedQuestionIds: string[];
  onSaved: (blueprintId: string) => void;
}) {
  const [topics, setTopics] = useState<GraphNode[]>([]);
  const [allQuestions, setAllQuestions] = useState<Question[]>([]);
  const [paperName, setPaperName] = useState(`Exam Paper — ${new Date().toLocaleDateString()}`);
  const [duration, setDuration] = useState(90);

  const isSeeded = seedQuestionIds.length > 0;

  useEffect(() => {
    fetchGraph().then((g) => setTopics(g.nodes));
    fetchQuestions().then(setAllQuestions);
  }, []);

  // ---------- Seeded mode (from Bank selection): unchanged CP-SAT flow over a fixed pool ----------
  const [seededBloomMix, setSeededBloomMix] = useState<Record<BloomLevel, number>>(defaultBloomMix);
  const [seededTotalMarks, setSeededTotalMarks] = useState(50);
  const [seededSelected, setSeededSelected] = useState<Question[] | null>(null);
  const [seededStatus, setSeededStatus] = useState<string | null>(null);
  const [seededRunning, setSeededRunning] = useState(false);
  const [seededError, setSeededError] = useState<string | null>(null);

  const candidatePool = useMemo(
    () => allQuestions.filter((q) => seedQuestionIds.includes(q.id)),
    [allQuestions, seedQuestionIds]
  );
  const seededBloomSum = BLOOM_LEVELS.reduce((s, b) => s + seededBloomMix[b], 0);
  const adjustSeededBloom = (level: BloomLevel, delta: number) =>
    setSeededBloomMix((m) => ({ ...m, [level]: Math.max(0, Math.min(100, m[level] + delta)) }));

  const runSeededOptimize = async () => {
    setSeededRunning(true);
    setSeededStatus(null);
    setSeededSelected(null);
    setSeededError(null);
    try {
      const weights: Partial<Record<BloomLevel, number>> = {};
      BLOOM_LEVELS.forEach((b) => {
        if (seededBloomMix[b] > 0) weights[b] = seededBloomMix[b] / (seededBloomSum || 1);
      });
      const result = await optimizePaper(
        { total_marks: seededTotalMarks, bloom_distribution: { weights } },
        candidatePool.map((q) => q.id)
      );
      setSeededStatus(result.status);
      if (result.status === "OPTIMAL" || result.status === "FEASIBLE") setSeededSelected(result.selected);
    } catch (e) {
      setSeededStatus("ERROR");
      setSeededError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setSeededRunning(false);
    }
  };

  const seededActualMarks = seededSelected?.reduce((s, q) => s + q.marks, 0) ?? 0;

  const handleSaveSeeded = async () => {
    if (!seededSelected) return;
    const blueprint = await createBlueprint({
      name: paperName,
      total_marks: seededTotalMarks,
      duration_minutes: duration,
      question_ids: seededSelected.map((q) => q.id),
    });
    onSaved(blueprint.id);
  };

  // ---------- Topic-spec mode: explicit per-topic count/type/bloom/marks, no solver needed ----------
  const [rows, setRows] = useState<TopicRow[]>([]);
  const [rowResults, setRowResults] = useState<RowResult[]>([]);
  const [excludedIds, setExcludedIds] = useState<Set<string>>(new Set());
  const [generating, setGenerating] = useState(false);
  const [regeneratingRow, setRegeneratingRow] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [hasGenerated, setHasGenerated] = useState(false);

  useEffect(() => {
    if (!isSeeded && topics.length > 0 && rows.length === 0) {
      setRows([
        { rowId: newRowId(), topicId: topics[0].id, count: 3, questionType: "short_answer", bloomLevel: 2, marks: 5 },
      ]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topics, isSeeded]);

  const addRow = () =>
    setRows((r) => [
      ...r,
      {
        rowId: newRowId(),
        topicId: topics[0]?.id ?? "",
        count: 3,
        questionType: "short_answer",
        bloomLevel: 2,
        marks: 5,
      },
    ]);

  const removeRow = (rowId: string) => setRows((r) => r.filter((row) => row.rowId !== rowId));

  const updateRow = <K extends keyof TopicRow>(rowId: string, key: K, value: TopicRow[K]) =>
    setRows((r) => r.map((row) => (row.rowId === rowId ? { ...row, [key]: value } : row)));

  const topicName = (id: string) => topics.find((t) => t.id === id)?.name ?? id;

  const plannedQuestions = rows.reduce((s, r) => s + r.count, 0);
  const plannedMarks = rows.reduce((s, r) => s + r.count * r.marks, 0);

  const runRow = async (row: TopicRow): Promise<RowResult> => {
    try {
      const { results } = await generateQuestions({
        topic: topicName(row.topicId),
        num_questions: row.count,
        bloom_level: row.bloomLevel,
        marks: row.marks,
        question_type: row.questionType,
        check_duplicates: true,
        save_to_bank: true,
      });
      return { rowId: row.rowId, results, error: results.length === 0 ? "No questions returned" : null };
    } catch (e) {
      return { rowId: row.rowId, results: [], error: e instanceof Error ? e.message : "Generation failed" };
    }
  };

  const generatePaper = async () => {
    setGenerating(true);
    setRowResults([]);
    setExcludedIds(new Set());
    const results: RowResult[] = [];
    for (const row of rows) {
      results.push(await runRow(row));
      setRowResults([...results]);
    }
    setHasGenerated(true);
    setGenerating(false);
  };

  const regenerateRow = async (rowId: string) => {
    const row = rows.find((r) => r.rowId === rowId);
    if (!row) return;
    setRegeneratingRow(rowId);
    const fresh = await runRow(row);
    setRowResults((prev) => prev.map((r) => (r.rowId === rowId ? fresh : r)));
    setRegeneratingRow(null);
  };

  const toggleExcluded = (questionId: string) =>
    setExcludedIds((prev) => {
      const next = new Set(prev);
      if (next.has(questionId)) next.delete(questionId);
      else next.add(questionId);
      return next;
    });

  const finalQuestions = rowResults.flatMap((r) => r.results.map((res) => res.question)).filter((q) => !excludedIds.has(q.id));
  const finalMarks = finalQuestions.reduce((s, q) => s + q.marks, 0);
  const anyRowError = rowResults.some((r) => r.error);

  const handleSaveTopicPlan = async () => {
    if (finalQuestions.length === 0) return;
    setSaving(true);
    try {
      const blueprint = await createBlueprint({
        name: paperName,
        total_marks: finalMarks,
        duration_minutes: duration,
        question_ids: finalQuestions.map((q) => q.id),
      });
      onSaved(blueprint.id);
    } finally {
      setSaving(false);
    }
  };

  // ============================== RENDER ==============================

  if (isSeeded) {
    return (
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1 h-fit lg:sticky lg:top-20">
          <CardHeader>
            <div className="flex items-center gap-2">
              <FileStack className="h-4 w-4 text-primary" />
              <CardTitle>Paper Requirements</CardTitle>
            </div>
            <CardDescription>Select the best combination from your chosen questions</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-foreground">Paper Name</label>
              <Input value={paperName} onChange={(e) => setPaperName(e.target.value)} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground"># Total Marks</label>
                <Input value={seededTotalMarks} onChange={(e) => setSeededTotalMarks(Number(e.target.value))} type="number" />
              </div>
              <div className="space-y-1.5">
                <label className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                  <Clock className="h-3.5 w-3.5" /> Duration (min)
                </label>
                <Input value={duration} onChange={(e) => setDuration(Number(e.target.value))} type="number" />
              </div>
            </div>
            <div className="space-y-2.5">
              <label className="text-xs font-medium text-foreground">Bloom's Level Mix</label>
              {BLOOM_LEVELS.map((b) => (
                <div key={b} className="flex items-center gap-3">
                  <span className="w-20 shrink-0 text-xs text-muted-foreground">{BLOOM_LABELS[b]}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary">
                    <div
                      className={`h-full rounded-full ${bloomColors[b]}`}
                      style={{ width: `${seededBloomSum ? (seededBloomMix[b] / seededBloomSum) * 100 : 0}%` }}
                    />
                  </div>
                  <div className="flex items-center gap-1">
                    <button className="rounded p-0.5 text-muted-foreground hover:bg-secondary" onClick={() => adjustSeededBloom(b, -5)}>
                      <Minus className="h-3 w-3" />
                    </button>
                    <span className="w-9 text-right text-xs font-medium text-foreground">
                      {seededBloomSum ? Math.round((seededBloomMix[b] / seededBloomSum) * 100) : 0}%
                    </span>
                    <button className="rounded p-0.5 text-muted-foreground hover:bg-secondary" onClick={() => adjustSeededBloom(b, 5)}>
                      <Plus className="h-3 w-3" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
            <div className="rounded-lg border border-primary/20 bg-accent p-3 text-xs text-accent-foreground">
              Optimizing over {seedQuestionIds.length} question{seedQuestionIds.length !== 1 && "s"} selected from the
              Question Bank.
            </div>
            <Button className="w-full" onClick={runSeededOptimize} disabled={seededRunning || candidatePool.length === 0}>
              <Wand2 className="h-4 w-4" /> {seededRunning ? "Optimizing..." : "Auto-generate Paper"}
            </Button>
          </CardContent>
        </Card>

        <div className="space-y-4 lg:col-span-2">
          {seededStatus === null ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-16 text-center">
                <FileStack className="h-8 w-8 text-muted-foreground" />
                <p className="mt-3 text-sm font-medium text-foreground">No paper generated yet</p>
                <p className="mt-1 text-xs text-muted-foreground">Set your requirements and click "Auto-generate Paper"</p>
              </CardContent>
            </Card>
          ) : seededStatus === "INFEASIBLE" || seededStatus === "ERROR" || !seededSelected ? (
            <Card className="border-destructive/30 bg-destructive/[0.03]">
              <CardContent className="flex flex-col items-center justify-center gap-2 py-16 text-center">
                <AlertTriangle className="h-8 w-8 text-destructive" />
                <p className="text-sm font-medium text-foreground">
                  {seededStatus === "INFEASIBLE" ? "No paper satisfies these constraints" : "Something went wrong"}
                </p>
                <p className="max-w-sm text-xs text-muted-foreground">
                  {seededStatus === "INFEASIBLE"
                    ? "Try lowering total marks or widening the Bloom mix — the selected questions can't satisfy this exactly."
                    : seededError ?? "The request failed. Try again."}
                </p>
              </CardContent>
            </Card>
          ) : (
            <>
              <Card className="border-success/30 bg-success/[0.03]">
                <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
                  <div>
                    <p className="text-sm font-medium text-foreground">Constraints satisfied ({seededStatus})</p>
                    <p className="text-xs text-muted-foreground">
                      {seededActualMarks} marks · {duration} min · {seededSelected.length} questions
                    </p>
                  </div>
                  <Button size="sm" onClick={handleSaveSeeded}>
                    <Save className="h-3.5 w-3.5" /> Save Paper
                  </Button>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Selected Questions</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {seededSelected.map((q, i) => {
                    const bucket = difficultyBucket(q.difficulty_score);
                    return (
                      <div key={q.id} className="flex items-start gap-3 rounded-lg border border-border bg-white p-3.5">
                        <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-secondary text-[11px] font-semibold text-muted-foreground">
                          {i + 1}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm text-foreground">{q.text}</p>
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            <Badge variant="accent">{BLOOM_LABELS[q.bloom_level]}</Badge>
                            <Badge variant={bucket === "Hard" ? "destructive" : bucket === "Medium" ? "warning" : "success"}>
                              {bucket}
                            </Badge>
                            <Badge variant="outline">{q.marks} marks</Badge>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </CardContent>
              </Card>
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-1 h-fit lg:sticky lg:top-20">
        <CardHeader>
          <div className="flex items-center gap-2">
            <FileStack className="h-4 w-4 text-primary" />
            <CardTitle>Question Plan</CardTitle>
          </div>
          <CardDescription>Choose exactly how many questions of each type/level to pull from each topic</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-foreground">Paper Name</label>
            <Input value={paperName} onChange={(e) => setPaperName(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-xs font-medium text-foreground">
              <Clock className="h-3.5 w-3.5" /> Duration (min)
            </label>
            <Input value={duration} onChange={(e) => setDuration(Number(e.target.value))} type="number" />
          </div>

          <div className="space-y-3">
            {rows.map((row) => (
              <div key={row.rowId} className="space-y-2 rounded-lg border border-border p-3">
                <div className="flex items-center justify-between">
                  <label className="text-[11px] font-medium text-muted-foreground">Topic</label>
                  <button className="text-muted-foreground hover:text-destructive" onClick={() => removeRow(row.rowId)}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
                <Select value={row.topicId} onChange={(e) => updateRow(row.rowId, "topicId", e.target.value)}>
                  {topics.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </Select>

                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <label className="text-[11px] font-medium text-muted-foreground">Questions</label>
                    <Input
                      type="number"
                      min={1}
                      value={row.count}
                      onChange={(e) => updateRow(row.rowId, "count", Math.max(1, Number(e.target.value)))}
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-[11px] font-medium text-muted-foreground">Marks each</label>
                    <Input
                      type="number"
                      min={1}
                      value={row.marks}
                      onChange={(e) => updateRow(row.rowId, "marks", Math.max(1, Number(e.target.value)))}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <label className="text-[11px] font-medium text-muted-foreground">Type</label>
                    <Select value={row.questionType} onChange={(e) => updateRow(row.rowId, "questionType", e.target.value as QuestionType)}>
                      {questionTypes.map((qt) => (
                        <option key={qt} value={qt}>
                          {QUESTION_TYPE_LABELS[qt]}
                        </option>
                      ))}
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <label className="text-[11px] font-medium text-muted-foreground">Bloom Level</label>
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
                </div>

                <p className="text-[11px] text-muted-foreground">
                  = {row.count} question{row.count !== 1 && "s"} · {row.count * row.marks} marks
                </p>
              </div>
            ))}
          </div>

          <Button variant="outline" size="sm" className="w-full" onClick={addRow} disabled={topics.length === 0}>
            <Plus className="h-3.5 w-3.5" /> Add Topic
          </Button>

          {topics.length === 0 && <p className="text-xs text-muted-foreground">Upload material first to see topics here.</p>}

          <div className="rounded-lg border border-border bg-secondary/40 p-3 text-xs">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Planned</span>
              <span className="font-medium text-foreground">
                {plannedQuestions} question{plannedQuestions !== 1 && "s"} · {plannedMarks} marks
              </span>
            </div>
          </div>

          <Button className="w-full" onClick={generatePaper} disabled={generating || rows.length === 0}>
            <Sparkles className="h-4 w-4" /> {generating ? "Generating..." : "Generate Paper"}
          </Button>
        </CardContent>
      </Card>

      <div className="space-y-4 lg:col-span-2">
        {!hasGenerated ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-16 text-center">
              <FileStack className="h-8 w-8 text-muted-foreground" />
              <p className="mt-3 text-sm font-medium text-foreground">No paper generated yet</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Add topics to your plan and click "Generate Paper" to preview
              </p>
            </CardContent>
          </Card>
        ) : (
          <>
            <Card className={cn(anyRowError ? "border-warning/30 bg-warning/[0.03]" : "border-success/30 bg-success/[0.03]")}>
              <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {anyRowError ? "Generated with some issues" : "Paper generated"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {finalMarks} marks · {duration} min · {finalQuestions.length} question{finalQuestions.length !== 1 && "s"}
                    {excludedIds.size > 0 && ` · ${excludedIds.size} excluded`}
                  </p>
                </div>
                <Button size="sm" onClick={handleSaveTopicPlan} disabled={saving || finalQuestions.length === 0}>
                  <Save className="h-3.5 w-3.5" /> {saving ? "Saving..." : "Save Paper"}
                </Button>
              </CardContent>
            </Card>

            {rowResults.map((rr) => {
              const row = rows.find((r) => r.rowId === rr.rowId);
              if (!row) return null;
              return (
                <Card key={rr.rowId}>
                  <CardHeader className="flex-row items-center justify-between space-y-0">
                    <div>
                      <CardTitle>{topicName(row.topicId)}</CardTitle>
                      <CardDescription>
                        {BLOOM_LABELS[row.bloomLevel]} · {QUESTION_TYPE_LABELS[row.questionType]} · {row.marks} marks each
                      </CardDescription>
                    </div>
                    <Button variant="ghost" size="sm" onClick={() => regenerateRow(rr.rowId)} disabled={regeneratingRow === rr.rowId}>
                      <RefreshCw className={cn("h-3.5 w-3.5", regeneratingRow === rr.rowId && "animate-spin")} /> Regenerate
                    </Button>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {rr.error && (
                      <p className="flex items-center gap-1.5 text-xs text-destructive">
                        <AlertTriangle className="h-3.5 w-3.5" /> {rr.error}
                      </p>
                    )}
                    {rr.results.map((res) => {
                      const excluded = excludedIds.has(res.question.id);
                      const bestMatch = res.duplicate_matches[0];
                      const isDuplicate = Boolean(bestMatch?.is_duplicate);
                      return (
                        <div
                          key={res.question.id}
                          className={cn(
                            "flex items-start gap-3 rounded-lg border p-3.5",
                            excluded ? "border-border bg-secondary/30 opacity-50" : isDuplicate ? "border-warning/40 bg-warning/[0.03]" : "border-border bg-white"
                          )}
                        >
                          <Checkbox checked={!excluded} onCheckedChange={() => toggleExcluded(res.question.id)} />
                          <div className="min-w-0 flex-1">
                            <p className="text-sm text-foreground">{res.question.text}</p>
                            <div className="mt-2 flex flex-wrap gap-1.5">
                              <Badge variant="outline">{res.question.marks} marks</Badge>
                              {isDuplicate && (
                                <Badge variant="warning">
                                  <ShieldAlert className="h-3 w-3" /> {Math.round(bestMatch.final_score * 100)}% similar to existing
                                </Badge>
                              )}
                            </div>
                          </div>
                          <button
                            className="text-muted-foreground hover:text-destructive"
                            onClick={() => toggleExcluded(res.question.id)}
                            title={excluded ? "Include" : "Exclude"}
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      );
                    })}
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
