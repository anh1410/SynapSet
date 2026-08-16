import { useEffect, useMemo, useState } from "react";
import { FileStack, Wand2, Clock, Hash, PieChart, ListChecks, Plus, Minus, AlertTriangle, Save, Sparkles } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  BLOOM_LEVELS,
  BLOOM_LABELS,
  createBlueprint,
  difficultyBucket,
  fetchGraph,
  fetchQuestions,
  generateQuestions,
  optimizePaper,
  type BloomLevel,
  type GraphNode,
  type Question,
  type QuestionType,
} from "@/lib/api";

const bloomColors: Record<BloomLevel, string> = {
  1: "bg-slate-400",
  2: "bg-sky-400",
  3: "bg-primary",
  4: "bg-warning",
  5: "bg-orange-400",
  6: "bg-destructive",
};

const defaultBloomMix: Record<BloomLevel, number> = { 1: 10, 2: 25, 3: 30, 4: 20, 5: 10, 6: 5 };

// Question format per Bloom level for auto-generated candidates (marks are
// computed separately, see pickMarksAndCount, so the total is actually
// reachable rather than a fixed per-level value that may never sum to target).
const questionTypeForBloom: Record<BloomLevel, QuestionType> = {
  1: "mcq",
  2: "short_answer",
  3: "short_answer",
  4: "short_answer",
  5: "long_answer",
  6: "long_answer",
};

// The optimizer requires candidate marks to sum to EXACTLY total_marks, so pick
// a per-question marks value that evenly divides the target within [minCount,
// maxCount] questions — that guarantees the generated batch alone can hit the
// total exactly, rather than hoping a random mix of marks happens to work.
function pickMarksAndCount(totalMarks: number, minCount: number, maxCount: number) {
  const MARKS_OPTIONS = [10, 8, 6, 5, 4, 2, 1];
  for (const marks of MARKS_OPTIONS) {
    const count = totalMarks / marks;
    if (Number.isInteger(count) && count >= minCount && count <= maxCount) {
      return { marks, count };
    }
  }
  const count = Math.min(maxCount, Math.max(minCount, Math.round(totalMarks / 5)));
  return { marks: 5, count };
}

export function ExamBuilderPage({
  seedQuestionIds,
  onSaved,
}: {
  seedQuestionIds: string[];
  onSaved: (blueprintId: string) => void;
}) {
  const [topics, setTopics] = useState<GraphNode[]>([]);
  const [allQuestions, setAllQuestions] = useState<Question[]>([]);
  const [selectedTopics, setSelectedTopics] = useState<string[]>([]);
  const [paperName, setPaperName] = useState(`Exam Paper — ${new Date().toLocaleDateString()}`);
  const [totalMarks, setTotalMarks] = useState(50);
  const [duration, setDuration] = useState(90);
  const [bloomMix, setBloomMix] = useState<Record<BloomLevel, number>>(defaultBloomMix);

  const [selected, setSelected] = useState<Question[] | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [generateNew, setGenerateNew] = useState(true);
  const [progress, setProgress] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const isSeeded = seedQuestionIds.length > 0;

  useEffect(() => {
    fetchGraph().then((g) => setTopics(g.nodes));
    fetchQuestions().then(setAllQuestions);
  }, []);

  useEffect(() => {
    if (!isSeeded && topics.length > 0 && selectedTopics.length === 0) {
      setSelectedTopics(topics.slice(0, 5).map((t) => t.id));
    }
  }, [topics, isSeeded, selectedTopics.length]);

  const toggleTopic = (id: string) =>
    setSelectedTopics((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const adjustBloom = (level: BloomLevel, delta: number) =>
    setBloomMix((m) => ({ ...m, [level]: Math.max(0, Math.min(100, m[level] + delta)) }));

  const candidatePool = useMemo(() => {
    if (isSeeded) return allQuestions.filter((q) => seedQuestionIds.includes(q.id));
    return allQuestions.filter((q) => q.topic_ids.some((t) => selectedTopics.includes(t)));
  }, [allQuestions, isSeeded, seedQuestionIds, selectedTopics]);

  const bloomSum = BLOOM_LEVELS.reduce((s, b) => s + bloomMix[b], 0);

  const activeBloomLevels = BLOOM_LEVELS.filter((b) => bloomMix[b] > 0);
  const MAX_GENERATED = 20;

  const generateCandidatesForTopics = async (
    topicIds: string[]
  ): Promise<{ generated: Question[]; failures: number }> => {
    const topicNames = topicIds
      .map((id) => topics.find((t) => t.id === id)?.name)
      .filter((name): name is string => Boolean(name));
    if (topicNames.length === 0) return { generated: [], failures: 0 };

    const levels = activeBloomLevels.length > 0 ? activeBloomLevels : ([2] as BloomLevel[]);

    // Pick a marks-per-question value that evenly divides total_marks, so the
    // generated batch alone can sum to exactly the target (the optimizer
    // requires an exact match, not just "close enough").
    const { marks: marksPerQuestion, count: jobCount } = pickMarksAndCount(
      totalMarks,
      topicNames.length,
      MAX_GENERATED
    );

    // Cycle topic-major then Bloom-level-major so every topic is covered at
    // every active level before repeating.
    const jobs = Array.from({ length: jobCount }, (_, i) => ({
      topicName: topicNames[i % topicNames.length],
      bloom: levels[Math.floor(i / topicNames.length) % levels.length],
    }));

    const generated: Question[] = [];
    let failures = 0;
    for (let i = 0; i < jobs.length; i++) {
      const { topicName, bloom } = jobs[i];
      setProgress(`Generating question ${i + 1} of ${jobs.length}...`);
      try {
        const { results } = await generateQuestions({
          topic: topicName,
          num_questions: 1,
          bloom_level: bloom,
          marks: marksPerQuestion,
          question_type: questionTypeForBloom[bloom],
          check_duplicates: false,
          save_to_bank: true,
        });
        if (results[0]) generated.push(results[0].question);
        else failures++;
      } catch {
        failures++;
      }
    }
    setProgress(null);
    return { generated, failures };
  };

  const runOptimize = async () => {
    setRunning(true);
    setStatus(null);
    setSelected(null);
    setErrorMessage(null);
    try {
      let pool = candidatePool;
      if (!isSeeded && generateNew && selectedTopics.length > 0) {
        const { generated: newQuestions, failures } = await generateCandidatesForTopics(selectedTopics);
        if (newQuestions.length > 0) {
          setAllQuestions((prev) => [...prev, ...newQuestions]);
          pool = [...pool, ...newQuestions];
        }
        if (failures > 0 && newQuestions.length === 0) {
          setStatus("ERROR");
          setErrorMessage(
            `Question generation failed for all ${failures} attempt${failures !== 1 ? "s" : ""}. The Gemini API may be rate-limited or out of quota — wait a bit and try again, or uncheck "Generate new questions" to build from the existing bank only.`
          );
          return;
        }
      }

      if (pool.length === 0) {
        setStatus("ERROR");
        setErrorMessage("No candidate questions available. Select topics with existing questions, or enable generation.");
        return;
      }

      const weights: Partial<Record<BloomLevel, number>> = {};
      BLOOM_LEVELS.forEach((b) => {
        if (bloomMix[b] > 0) weights[b] = bloomMix[b] / (bloomSum || 1);
      });
      const candidateIds = pool.map((q) => q.id);
      const result = await optimizePaper({ total_marks: totalMarks, bloom_distribution: { weights } }, candidateIds);
      setStatus(result.status);
      if (result.status === "OPTIMAL" || result.status === "FEASIBLE") {
        setSelected(result.selected);
      }
    } catch (e) {
      setStatus("ERROR");
      setErrorMessage(e instanceof Error ? e.message : "Unknown error");
      setSelected(null);
    } finally {
      setRunning(false);
    }
  };

  const handleSave = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      const blueprint = await createBlueprint({
        name: paperName,
        total_marks: totalMarks,
        duration_minutes: duration,
        question_ids: selected.map((q) => q.id),
      });
      onSaved(blueprint.id);
    } finally {
      setSaving(false);
    }
  };

  const actualMarks = selected?.reduce((s, q) => s + q.marks, 0) ?? 0;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-1 h-fit lg:sticky lg:top-20">
        <CardHeader>
          <div className="flex items-center gap-2">
            <FileStack className="h-4 w-4 text-primary" />
            <CardTitle>Paper Requirements</CardTitle>
          </div>
          <CardDescription>Define constraints for automatic question selection</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-foreground">Paper Name</label>
            <Input value={paperName} onChange={(e) => setPaperName(e.target.value)} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                <Hash className="h-3.5 w-3.5" /> Total Marks
              </label>
              <Input value={totalMarks} onChange={(e) => setTotalMarks(Number(e.target.value))} type="number" />
            </div>
            <div className="space-y-1.5">
              <label className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                <Clock className="h-3.5 w-3.5" /> Duration (min)
              </label>
              <Input value={duration} onChange={(e) => setDuration(Number(e.target.value))} type="number" />
            </div>
          </div>

          <div className="space-y-2.5">
            <label className="flex items-center gap-1.5 text-xs font-medium text-foreground">
              <PieChart className="h-3.5 w-3.5" /> Bloom's Level Mix
            </label>
            {BLOOM_LEVELS.map((b) => (
              <div key={b} className="flex items-center gap-3">
                <span className="w-20 shrink-0 text-xs text-muted-foreground">{BLOOM_LABELS[b]}</span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary">
                  <div
                    className={`h-full rounded-full ${bloomColors[b]}`}
                    style={{ width: `${bloomSum ? (bloomMix[b] / bloomSum) * 100 : 0}%` }}
                  />
                </div>
                <div className="flex items-center gap-1">
                  <button className="rounded p-0.5 text-muted-foreground hover:bg-secondary" onClick={() => adjustBloom(b, -5)}>
                    <Minus className="h-3 w-3" />
                  </button>
                  <span className="w-9 text-right text-xs font-medium text-foreground">
                    {bloomSum ? Math.round((bloomMix[b] / bloomSum) * 100) : 0}%
                  </span>
                  <button className="rounded p-0.5 text-muted-foreground hover:bg-secondary" onClick={() => adjustBloom(b, 5)}>
                    <Plus className="h-3 w-3" />
                  </button>
                </div>
              </div>
            ))}
          </div>

          {isSeeded ? (
            <div className="rounded-lg border border-primary/20 bg-accent p-3 text-xs text-accent-foreground">
              Optimizing over {seedQuestionIds.length} question{seedQuestionIds.length !== 1 && "s"} selected from the
              Question Bank.
            </div>
          ) : (
            <div className="space-y-2">
              <label className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                <ListChecks className="h-3.5 w-3.5" /> Topic Coverage
              </label>
              <div className="max-h-48 space-y-1 overflow-y-auto rounded-lg border border-border p-2 scrollbar-thin">
                {topics.map((t) => (
                  <label
                    key={t.id}
                    className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-xs transition-colors duration-150 hover:bg-secondary/60"
                  >
                    <Checkbox checked={selectedTopics.includes(t.id)} onCheckedChange={() => toggleTopic(t.id)} />
                    <span className="flex-1 text-foreground">{t.name}</span>
                    <span className="text-muted-foreground">{t.question_count} avail.</span>
                  </label>
                ))}
              </div>
              <label className="flex cursor-pointer items-center gap-2 rounded-md px-1 py-1 text-xs text-foreground">
                <Checkbox checked={generateNew} onCheckedChange={setGenerateNew} />
                <Sparkles className="h-3.5 w-3.5 text-primary" />
                Generate new questions for these topics before building
              </label>
            </div>
          )}

          <Button
            className="w-full"
            onClick={runOptimize}
            disabled={
              running ||
              (isSeeded ? candidatePool.length === 0 : selectedTopics.length === 0 && !generateNew)
            }
          >
            <Wand2 className="h-4 w-4" /> {progress ?? (running ? "Optimizing..." : "Auto-generate Paper")}
          </Button>
          {!isSeeded && selectedTopics.length === 0 && (
            <p className="text-xs text-muted-foreground">Select at least one topic.</p>
          )}
          {isSeeded && candidatePool.length === 0 && (
            <p className="text-xs text-muted-foreground">No questions available for the current selection.</p>
          )}
        </CardContent>
      </Card>

      <div className="space-y-4 lg:col-span-2">
        {status === null ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-16 text-center">
              <FileStack className="h-8 w-8 text-muted-foreground" />
              <p className="mt-3 text-sm font-medium text-foreground">No paper generated yet</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Set your requirements and click "Auto-generate Paper" to preview
              </p>
            </CardContent>
          </Card>
        ) : status === "INFEASIBLE" || status === "ERROR" || !selected ? (
          <Card className="border-destructive/30 bg-destructive/[0.03]">
            <CardContent className="flex flex-col items-center justify-center gap-2 py-16 text-center">
              <AlertTriangle className="h-8 w-8 text-destructive" />
              <p className="text-sm font-medium text-foreground">
                {status === "INFEASIBLE" ? "No paper satisfies these constraints" : "Something went wrong"}
              </p>
              <p className="max-w-sm text-xs text-muted-foreground">
                {status === "INFEASIBLE"
                  ? "Try lowering total marks, widening the Bloom mix, or including more topics — there aren't enough matching questions in the bank."
                  : errorMessage ?? "The request failed. Try again."}
              </p>
            </CardContent>
          </Card>
        ) : (
          <>
            <Card className="border-success/30 bg-success/[0.03]">
              <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div>
                  <p className="text-sm font-medium text-foreground">Constraints satisfied ({status})</p>
                  <p className="text-xs text-muted-foreground">
                    {actualMarks} marks · {duration} min · {selected.length} questions · No repeated questions
                  </p>
                </div>
                <Button size="sm" onClick={handleSave} disabled={saving}>
                  <Save className="h-3.5 w-3.5" /> {saving ? "Saving..." : "Save Paper"}
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Selected Questions</CardTitle>
                <CardDescription>Best combination matching your constraints</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {selected.map((q, i) => {
                  const bucket = difficultyBucket(q.difficulty_score);
                  return (
                    <div
                      key={q.id}
                      className="flex items-start gap-3 rounded-lg border border-border bg-white p-3.5 transition-all duration-200 hover:border-primary/30"
                    >
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
