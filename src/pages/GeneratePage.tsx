import { useEffect, useState } from "react";
import { Sparkles, RefreshCw, Save, ShieldCheck, ShieldAlert, Check, AlertCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import {
  BLOOM_LEVELS,
  BLOOM_LABELS,
  QUESTION_TYPE_LABELS,
  difficultyBucket,
  fetchGraph,
  generateQuestions,
  saveQuestion,
  type BloomLevel,
  type GeneratedQuestionResult,
  type GraphNode,
  type QuestionType,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const questionTypes: QuestionType[] = ["short_answer", "long_answer", "mcq", "numerical"];
const marksOptions = [1, 2, 4, 5, 6, 8, 10];
const countOptions = [1, 3, 5, 10];

export function GeneratePage() {
  const [topics, setTopics] = useState<GraphNode[]>([]);
  const [topic, setTopic] = useState("");
  const [bloomLevel, setBloomLevel] = useState<BloomLevel>(2);
  const [marks, setMarks] = useState(5);
  const [questionType, setQuestionType] = useState<QuestionType>("short_answer");
  const [numQuestions, setNumQuestions] = useState(3);

  const [results, setResults] = useState<GeneratedQuestionResult[]>([]);
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set());
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasGenerated, setHasGenerated] = useState(false);

  useEffect(() => {
    fetchGraph().then((g) => {
      setTopics(g.nodes);
      if (g.nodes.length > 0) setTopic(g.nodes[0].name);
    });
  }, []);

  const runGenerate = async () => {
    if (!topic) return;
    setGenerating(true);
    setError(null);
    try {
      const { results } = await generateQuestions({
        topic,
        num_questions: numQuestions,
        bloom_level: bloomLevel,
        marks,
        question_type: questionType,
        check_duplicates: true,
        save_to_bank: false,
      });
      setResults(results);
      setHasGenerated(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Generation failed");
    } finally {
      setGenerating(false);
    }
  };

  const regenerateOne = async (index: number) => {
    setError(null);
    try {
      const { results: fresh } = await generateQuestions({
        topic,
        num_questions: 1,
        bloom_level: bloomLevel,
        marks,
        question_type: questionType,
        check_duplicates: true,
        save_to_bank: false,
      });
      if (fresh[0]) {
        setResults((prev) => prev.map((r, i) => (i === index ? fresh[0] : r)));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Regeneration failed");
    }
  };

  const handleSave = async (result: GeneratedQuestionResult) => {
    try {
      await saveQuestion(result.question);
      setSavedIds((prev) => new Set(prev).add(result.question.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    }
  };

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-1 h-fit lg:sticky lg:top-20">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <CardTitle>Question Parameters</CardTitle>
          </div>
          <CardDescription>Generation is grounded strictly in your uploaded content</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-foreground">Topic</label>
            {topics.length === 0 ? (
              <p className="text-xs text-muted-foreground">Upload material first to see topics here.</p>
            ) : (
              <Select value={topic} onChange={(e) => setTopic(e.target.value)}>
                {topics.map((t) => (
                  <option key={t.id} value={t.name}>
                    {t.name}
                  </option>
                ))}
              </Select>
            )}
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-foreground">Question Type</label>
            <Select value={questionType} onChange={(e) => setQuestionType(e.target.value as QuestionType)}>
              {questionTypes.map((qt) => (
                <option key={qt} value={qt}>
                  {QUESTION_TYPE_LABELS[qt]}
                </option>
              ))}
            </Select>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-foreground">Marks</label>
            <Select value={marks} onChange={(e) => setMarks(Number(e.target.value))}>
              {marksOptions.map((m) => (
                <option key={m} value={m}>
                  {m} marks
                </option>
              ))}
            </Select>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-foreground">Bloom's Cognitive Level</label>
            <Select value={bloomLevel} onChange={(e) => setBloomLevel(Number(e.target.value) as BloomLevel)}>
              {BLOOM_LEVELS.map((b) => (
                <option key={b} value={b}>
                  {BLOOM_LABELS[b]}
                </option>
              ))}
            </Select>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-foreground">Number of Questions</label>
            <Select value={numQuestions} onChange={(e) => setNumQuestions(Number(e.target.value))}>
              {countOptions.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
          </div>

          <Button className="w-full" onClick={runGenerate} disabled={!topic || generating}>
            <Sparkles className="h-4 w-4" /> {generating ? "Generating..." : "Generate Questions"}
          </Button>

          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
              <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
              {error}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="space-y-4 lg:col-span-2">
        {!hasGenerated ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-16 text-center">
              <Sparkles className="h-8 w-8 text-muted-foreground" />
              <p className="mt-3 text-sm font-medium text-foreground">No questions generated yet</p>
              <p className="mt-1 text-xs text-muted-foreground">Set your parameters and generate to see results here</p>
            </CardContent>
          </Card>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Generated <span className="font-medium text-foreground">{results.length} question{results.length !== 1 && "s"}</span> for{" "}
                <span className="font-medium text-foreground">{topic}</span>
              </p>
            </div>

            {results.map((r, i) => {
              const bestMatch = r.duplicate_matches[0];
              const isDuplicate = Boolean(bestMatch?.is_duplicate);
              const isSaved = savedIds.has(r.question.id);
              const bucket = difficultyBucket(r.difficulty.score);
              return (
                <Card key={r.question.id} className={cn(isDuplicate && "border-warning/40 bg-warning/[0.03]")}>
                  <CardContent className="p-5">
                    <p className="text-sm leading-relaxed text-foreground">{r.question.text}</p>

                    {r.question.question_type === "mcq" && r.question.options && (
                      <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                        {r.question.options.map((opt, oi) => (
                          <li key={oi} className={cn(opt === r.question.correct_answer && "font-medium text-success")}>
                            {String.fromCharCode(97 + oi)}) {opt}
                          </li>
                        ))}
                      </ul>
                    )}

                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <Badge variant="secondary">{r.question.marks} marks</Badge>
                      <Badge variant="accent">{BLOOM_LABELS[r.question.bloom_level]}</Badge>
                      <Badge variant={bucket === "Hard" ? "destructive" : bucket === "Medium" ? "warning" : "success"}>
                        Difficulty: {r.difficulty.score.toFixed(1)}/10 ({bucket})
                      </Badge>
                      {bestMatch && (
                        <Badge variant={isDuplicate ? "warning" : "success"}>
                          {isDuplicate ? <ShieldAlert className="h-3 w-3" /> : <ShieldCheck className="h-3 w-3" />}
                          {Math.round(bestMatch.final_score * 100)}% similar to existing
                        </Badge>
                      )}
                    </div>

                    {isDuplicate && (
                      <p className="mt-2 text-xs text-warning">
                        This question closely resembles one already in your bank. Review before saving.
                      </p>
                    )}

                    <div className="mt-4 flex items-center gap-2">
                      <Button
                        size="sm"
                        variant={isDuplicate ? "secondary" : "primary"}
                        disabled={isSaved}
                        onClick={() => handleSave(r)}
                      >
                        {isSaved ? <Check className="h-3.5 w-3.5" /> : <Save className="h-3.5 w-3.5" />}
                        {isSaved ? "Saved" : "Save to bank"}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => regenerateOne(i)}>
                        <RefreshCw className="h-3.5 w-3.5" /> Regenerate
                      </Button>
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
