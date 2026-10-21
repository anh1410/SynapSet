/**
 * "Add your own question" (Question Bank). The teacher writes the question -
 * any type, including coding ones - and the AI classifies it: Bloom's level
 * with a reason, topics and course outcomes from this subject's knowledge
 * graph, question type and marks; difficulty, skill and near-duplicates come
 * from the local models. Coding questions also get their reference solution
 * test-run and can take AI-suggested test cases (expected outputs computed by
 * running the reference solution). Everything stays editable before saving.
 */
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Loader2, Plus, Save, Sparkles, Trash2, Wand2, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import {
  ApiError,
  BLOOM_LABELS,
  BLOOM_LEVELS,
  QUESTION_TYPE_LABELS,
  QUESTION_TYPE_ORDER,
  SKILL_LABELS,
  analyzeQuestion,
  difficultyBucket,
  effectiveSkill,
  isCodingType,
  saveQuestion,
  type BloomLevel,
  type CodeTestCase,
  type GraphNode,
  type Question,
  type QuestionAnalysis,
  type QuestionDraftInput,
  type QuestionType,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const textareaClass =
  "w-full rounded-lg border border-input bg-white px-3 py-2 text-sm shadow-subtle placeholder:text-muted-foreground " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:border-primary";
const codeClass = cn(textareaClass, "font-mono text-[12.5px] leading-5");

/** crypto.randomUUID only exists in secure contexts (https / localhost). */
function newQuestionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const hex = Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-foreground">{label}</label>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

interface Props {
  open: boolean;
  onClose: () => void;
  subjectId: string;
  topics: GraphNode[];
  outcomes: GraphNode[];
  bank: Question[];
  onSaved: (question: Question) => void;
}

export function ManualQuestionDialog({ open, onClose, subjectId, topics, outcomes, bank, onSaved }: Props) {
  // ---- what the teacher writes ----
  const [type, setType] = useState<QuestionType | "auto">("auto");
  const [scenario, setScenario] = useState(false);
  const [text, setText] = useState("");
  const [options, setOptions] = useState<string[]>(["", "", "", ""]);
  const [correctIndex, setCorrectIndex] = useState<number | null>(null);
  const [answer, setAnswer] = useState("");
  const [starter, setStarter] = useState("");
  const [solution, setSolution] = useState("");
  const [tests, setTests] = useState<CodeTestCase[]>([{ input: "", expected_output: "" }]);
  const [marks, setMarks] = useState("");

  // ---- AI result (editable) ----
  const [analysis, setAnalysis] = useState<QuestionAnalysis | null>(null);
  // The reference solution + test cases the last check actually ran (or that
  // came verified from the AI suggestions). Saving a coding question needs
  // the current code to match it, so an unchecked solution can't slip in.
  const [checkedCode, setCheckedCode] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [finalType, setFinalType] = useState<QuestionType>("short_answer");
  const [bloom, setBloom] = useState<BloomLevel>(2);
  const [topicIds, setTopicIds] = useState<string[]>([]);
  const [coIds, setCoIds] = useState<string[]>([]);
  const [finalMarks, setFinalMarks] = useState(1);

  const [busy, setBusy] = useState<"analyse" | "save" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setType("auto");
    setScenario(false);
    setText("");
    setOptions(["", "", "", ""]);
    setCorrectIndex(null);
    setAnswer("");
    setStarter("");
    setSolution("");
    setTests([{ input: "", expected_output: "" }]);
    setMarks("");
    setAnalysis(null);
    setStale(false);
    setCheckedCode(null);
    setError(null);
  };

  useEffect(() => {
    if (open) reset();
  }, [open]);

  // Any edit after analysing means the classification may be out of date.
  const touch = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    if (analysis) setStale(true);
  };

  // The type the form is showing fields for: the teacher's choice, else what the AI picked.
  const shownType: QuestionType | "auto" = type !== "auto" ? type : analysis ? finalType : "auto";
  const objective = shownType === "mcq" || shownType === "fill_in_blank";
  const coding = shownType !== "auto" && isCodingType(shownType);

  const cleanTests = tests.filter((t) => t.input.trim() || t.expected_output.trim());
  const cleanOptions = options.map((o) => o.trim()).filter(Boolean);
  const codeKey = JSON.stringify([solution, cleanTests]);

  const draft = (): QuestionDraftInput => ({
    text: text.trim(),
    question_type: type === "auto" ? null : type,
    options: objective ? cleanOptions : null,
    correct_answer: coding
      ? solution || null
      : objective
        ? correctIndex != null
          ? options[correctIndex]?.trim() || null
          : null
        : answer.trim() || null,
    code_language: coding ? "python" : null,
    starter_code: coding ? starter || null : null,
    test_cases: coding && cleanTests.length ? cleanTests : null,
    marks: marks ? Math.max(1, Number(marks)) : null,
    scenario_based: shownType === "code_write" && scenario,
  });

  const analyse = async () => {
    if (!text.trim()) return setError("Write the question first.");
    if (objective && cleanOptions.length < 2) return setError("Add at least two answer options.");
    setBusy("analyse");
    setError(null);
    try {
      const result = await analyzeQuestion(subjectId, draft());
      setAnalysis(result);
      setStale(false);
      setCheckedCode(codeKey);
      setFinalType(result.question_type);
      setBloom(result.bloom_level);
      setTopicIds(result.topic_ids);
      setCoIds(result.co_ids);
      setFinalMarks(result.suggested_marks);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't analyse the question. Check your connection.");
    } finally {
      setBusy(null);
    }
  };

  // What's still missing before the question can be auto-graded / saved.
  const saveProblem = useMemo(() => {
    if (!analysis) return "Analyse the question first.";
    const t = finalType;
    if (t === "mcq" || t === "fill_in_blank") {
      if (cleanOptions.length < 2) return "Add at least two answer options.";
      if (new Set(cleanOptions.map((o) => o.toLowerCase())).size !== cleanOptions.length) return "Two options are the same - make each option different.";
      if (correctIndex == null || !options[correctIndex]?.trim()) return "Mark the correct option (it can't be blank).";
    }
    if (t === "numerical") {
      if (!answer.trim()) return "Enter the numeric answer.";
      if (!Number.isFinite(Number(answer.trim().replace(/,/g, "")))) return "The answer to a numerical question must be a number.";
    }
    if (isCodingType(t)) {
      if (t === "code_fix" && !starter.trim()) return "Add the code the student has to fix.";
      if (t === "code_fix" && starter.trim() === solution.trim()) return "The code to fix is identical to the reference solution.";
      if (!solution.trim()) return "Add a reference solution.";
      if (!cleanTests.length) return "Add at least one test case (used to auto-grade).";
      if (checkedCode !== codeKey) return "You changed the code or test cases - re-analyse to check the reference solution against them.";
      const check = analysis.code_check;
      if (check && check.passed < check.total)
        return `Your reference solution fails ${check.total - check.passed} of ${check.total} test case(s) - fix the solution or the expected outputs.`;
    }
    return null;
  }, [analysis, finalType, cleanOptions, options, correctIndex, answer, starter, solution, cleanTests.length, checkedCode, codeKey]);

  const save = async () => {
    if (!analysis || saveProblem) return;
    const d = draft();
    const question: Question = {
      id: newQuestionId(),
      text: d.text,
      question_type: finalType,
      marks: Math.max(1, finalMarks),
      bloom_level: bloom,
      topic_ids: topicIds,
      co_ids: coIds,
      unit: null,
      options: finalType === "mcq" || finalType === "fill_in_blank" ? cleanOptions : null,
      correct_answer: isCodingType(finalType)
        ? solution
        : finalType === "mcq" || finalType === "fill_in_blank"
          ? options[correctIndex!].trim()
          : answer.trim() || null,
      code_language: isCodingType(finalType) ? "python" : null,
      starter_code: isCodingType(finalType) ? starter || null : null,
      test_cases: isCodingType(finalType) ? cleanTests : null,
      scenario_based: finalType === "code_write" && scenario,
      origin: "manual",
      // Difficulty depends on these; if the teacher changed them, the server rescores on save.
      difficulty_score:
        bloom === analysis.bloom_level && finalMarks === analysis.suggested_marks && finalType === analysis.question_type &&
        JSON.stringify([...topicIds].sort()) === JSON.stringify([...analysis.topic_ids].sort())
          ? analysis.difficulty.score
          : null,
      embedding_id: null,
      is_duplicate_of: null,
      skill_category: null,
      source_document: null,
      created_at: new Date().toISOString(),
    };
    setBusy("save");
    setError(null);
    try {
      onSaved(await saveQuestion(subjectId, question));
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't save the question.");
    } finally {
      setBusy(null);
    }
  };

  const addSuggestedTests = () => {
    if (!analysis) return;
    const kept = tests.filter((t) => t.input.trim() || t.expected_output.trim());
    const seen = new Set(kept.map((t) => t.input));
    const next = [...kept, ...analysis.suggested_test_cases.filter((t) => !seen.has(t.input))];
    setTests(next);
    // These outputs came from running the current solution, so they're already
    // checked - as long as the code and existing tests were checked too.
    if (checkedCode === codeKey) setCheckedCode(JSON.stringify([solution, next]));
  };

  // Escape / backdrop click shouldn't silently throw away a half-written question.
  const requestClose = () => {
    if (busy) return;
    if (text.trim() && !window.confirm("Discard this question?")) return;
    onClose();
  };

  const toggle = (list: string[], id: string) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
  const bankText = (id: string) => bank.find((q) => q.id === id)?.text ?? id;
  const bucket = analysis ? difficultyBucket(analysis.difficulty.score) : null;

  return (
    <Dialog open={open} onClose={requestClose} title="Add your own question" description="Write it yourself - the AI works out the Bloom's level, topics and the rest." className="max-w-3xl">
      <div className="space-y-5">
        {/* ---------------- 1. the question ---------------- */}
        <section className="space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_120px]">
            <Field label="Question type">
              <Select value={type} onChange={(e) => touch(setType)(e.target.value as QuestionType | "auto")}>
                <option value="auto">Let the AI decide</option>
                {QUESTION_TYPE_ORDER.map((t) => (
                  <option key={t} value={t}>
                    {QUESTION_TYPE_LABELS[t]}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Marks">
              <Input type="number" min={1} value={marks} onChange={(e) => touch(setMarks)(e.target.value)} placeholder="AI suggests" />
            </Field>
          </div>

          {shownType === "code_write" && (
            <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Coding question style">
              {[
                { v: false, label: "Write the full program", hint: "A direct programming task" },
                { v: true, label: "Interview / scenario problem", hint: "A real-world, company-interview style problem" },
              ].map((o) => (
                <button
                  key={String(o.v)}
                  type="button"
                  role="radio"
                  aria-checked={scenario === o.v}
                  onClick={() => touch(setScenario)(o.v)}
                  className={cn(
                    "flex-1 rounded-lg border px-3 py-2 text-left text-xs transition-colors",
                    scenario === o.v ? "border-primary bg-primary/5" : "border-border hover:bg-secondary/50"
                  )}
                >
                  <span className="block font-medium text-foreground">{o.label}</span>
                  <span className="text-muted-foreground">{o.hint}</span>
                </button>
              ))}
            </div>
          )}

          <Field
            label="Question"
            hint={
              shownType === "code_write"
                ? "Describe the task, the input format, the output format and an example."
                : shownType === "fill_in_blank"
                  ? 'Mark the blank with "_____".'
                  : undefined
            }
          >
            <textarea
              rows={shownType === "code_write" ? 7 : 4}
              className={textareaClass}
              value={text}
              onChange={(e) => touch(setText)(e.target.value)}
              placeholder={
                scenario && shownType === "code_write"
                  ? "e.g. A food-delivery app keeps pending orders in a queue. Write a program that reads n orders and prints them in the order they will be dispatched...\n\nInput format: ...\nOutput format: ...\nExample: ..."
                  : "Type the question exactly as students will see it"
              }
            />
          </Field>

          {objective && (
            <Field label="Options" hint="Select the correct option.">
              <div className="space-y-2">
                {options.map((opt, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="correct-option"
                      className="h-4 w-4 accent-primary"
                      checked={correctIndex === i}
                      onChange={() => touch(setCorrectIndex)(i)}
                      aria-label={`Option ${i + 1} is correct`}
                    />
                    <Input
                      value={opt}
                      onChange={(e) => touch(setOptions)(options.map((o, j) => (j === i ? e.target.value : o)))}
                      placeholder={`Option ${String.fromCharCode(65 + i)}`}
                    />
                    {options.length > 2 && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 shrink-0"
                        aria-label="Remove option"
                        onClick={() => {
                          touch(setOptions)(options.filter((_, j) => j !== i));
                          if (correctIndex === i) setCorrectIndex(null);
                          else if (correctIndex != null && correctIndex > i) setCorrectIndex(correctIndex - 1);
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                ))}
                {options.length < 6 && (
                  <Button variant="ghost" size="sm" onClick={() => touch(setOptions)([...options, ""])}>
                    <Plus className="h-3.5 w-3.5" /> Add option
                  </Button>
                )}
              </div>
            </Field>
          )}

          {(shownType === "auto" || shownType === "numerical" || shownType === "short_answer" || shownType === "long_answer") && (
            <Field
              label={shownType === "numerical" ? "Answer" : "Model answer / key points (optional)"}
              hint={shownType === "numerical" ? "Graded by exact match." : "Shown in the answer key to help with manual grading."}
            >
              {shownType === "numerical" ? (
                <Input value={answer} onChange={(e) => touch(setAnswer)(e.target.value)} className="max-w-xs" />
              ) : (
                <textarea rows={3} className={textareaClass} value={answer} onChange={(e) => touch(setAnswer)(e.target.value)} />
              )}
            </Field>
          )}

          {coding && (
            <div className="space-y-3 rounded-lg border border-border p-3">
              <p className="text-[11px] font-semibold text-foreground">Code (Python) · auto-graded by running hidden test cases</p>
              <Field
                label={shownType === "code_fix" ? "Code the student has to fix" : "Starter template (optional)"}
                hint={shownType === "code_fix" ? "The buggy or incomplete program students start from." : "Usually left empty - students write everything."}
              >
                <textarea rows={shownType === "code_fix" ? 6 : 3} spellCheck={false} className={codeClass} value={starter} onChange={(e) => touch(setStarter)(e.target.value)} />
              </Field>
              <Field label="Reference solution" hint="A correct program. It reads input() and prints the answer - it is run against the test cases.">
                <textarea rows={6} spellCheck={false} className={codeClass} value={solution} onChange={(e) => touch(setSolution)(e.target.value)} />
              </Field>
              <Field label="Test cases" hint="Hidden from students. Input is exactly what the program reads, one value per line.">
                <div className="space-y-2">
                  {tests.map((t, i) => (
                    <div key={i} className="grid grid-cols-[1fr_1fr_auto] items-start gap-2">
                      <textarea
                        rows={2}
                        spellCheck={false}
                        className={codeClass}
                        placeholder="Input"
                        value={t.input}
                        onChange={(e) => touch(setTests)(tests.map((x, j) => (j === i ? { ...x, input: e.target.value } : x)))}
                      />
                      <textarea
                        rows={2}
                        spellCheck={false}
                        className={codeClass}
                        placeholder="Expected output"
                        value={t.expected_output}
                        onChange={(e) => touch(setTests)(tests.map((x, j) => (j === i ? { ...x, expected_output: e.target.value } : x)))}
                      />
                      <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="Remove test case" onClick={() => touch(setTests)(tests.filter((_, j) => j !== i))}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  ))}
                  <Button variant="ghost" size="sm" onClick={() => touch(setTests)([...tests, { input: "", expected_output: "" }])}>
                    <Plus className="h-3.5 w-3.5" /> Add test case
                  </Button>
                </div>
              </Field>
            </div>
          )}

          <Button onClick={() => void analyse()} disabled={busy !== null || !text.trim()} variant={analysis && !stale ? "outline" : "primary"}>
            {busy === "analyse" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            {analysis ? (stale ? "Re-analyse with AI" : "Analyse again") : "Analyse with AI"}
          </Button>
        </section>

        {/* ---------------- 2. AI classification (editable) ---------------- */}
        {analysis && (
          <section className="space-y-3 rounded-lg border border-primary/20 bg-primary/[0.03] p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
                <Wand2 className="h-4 w-4 text-primary" /> {analysis.method === "ai" ? "AI classification" : "Classification (keyword rules)"}
              </p>
              <p className="text-[11px] text-muted-foreground">Adjust anything before saving.</p>
            </div>
            {analysis.note && (
              <p className="flex items-start gap-1.5 rounded-md bg-warning/10 px-2.5 py-1.5 text-xs text-warning">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {analysis.note}
              </p>
            )}
            {stale && (
              <p className="flex items-center gap-1.5 text-xs text-warning">
                <AlertTriangle className="h-3.5 w-3.5" /> You changed the question - re-analyse to refresh these suggestions.
              </p>
            )}

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <Field label="Bloom's level">
                <Select value={bloom} onChange={(e) => setBloom(Number(e.target.value) as BloomLevel)}>
                  {BLOOM_LEVELS.map((b) => (
                    <option key={b} value={b}>
                      {b}. {BLOOM_LABELS[b]}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Question type">
                <Select value={finalType} onChange={(e) => setFinalType(e.target.value as QuestionType)} disabled={type !== "auto"}>
                  {QUESTION_TYPE_ORDER.map((t) => (
                    <option key={t} value={t}>
                      {QUESTION_TYPE_LABELS[t]}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Marks">
                <Input type="number" min={1} value={finalMarks} onChange={(e) => setFinalMarks(Math.max(1, Number(e.target.value)))} />
              </Field>
            </div>
            <p className="text-xs italic text-muted-foreground">Why: {analysis.bloom_rationale}</p>

            <Field label="Topics" hint={topics.length ? "From this subject's knowledge graph." : "No topics yet - upload course material first."}>
              <div className="flex flex-wrap gap-1.5">
                {topics.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setTopicIds(toggle(topicIds, t.id))}
                    aria-pressed={topicIds.includes(t.id)}
                    className={cn(
                      "rounded-full border px-2.5 py-0.5 text-xs transition-colors",
                      topicIds.includes(t.id) ? "border-primary bg-primary text-primary-foreground" : "border-border bg-white text-foreground hover:bg-secondary"
                    )}
                  >
                    {t.name}
                  </button>
                ))}
              </div>
            </Field>

            {outcomes.length > 0 && (
              <Field label="Course outcomes">
                <div className="flex flex-wrap gap-1.5">
                  {outcomes.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      title={c.description}
                      onClick={() => setCoIds(toggle(coIds, c.name))}
                      aria-pressed={coIds.includes(c.name)}
                      className={cn(
                        "rounded-full border px-2.5 py-0.5 text-xs transition-colors",
                        coIds.includes(c.name) ? "border-primary bg-primary text-primary-foreground" : "border-border bg-white text-foreground hover:bg-secondary"
                      )}
                    >
                      {c.name}
                    </button>
                  ))}
                </div>
              </Field>
            )}

            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="text-muted-foreground">Difficulty</span>
              <Badge variant={bucket === "Easy" ? "success" : bucket === "Hard" ? "destructive" : "warning"}>
                {bucket} · {analysis.difficulty.score.toFixed(1)}/10
              </Badge>
              <span className="ml-2 text-muted-foreground">Skill</span>
              <Badge variant="outline">{SKILL_LABELS[effectiveSkill({ question_type: finalType, bloom_level: bloom, skill_category: null })]}</Badge>
              {finalType === "code_write" && scenario && <Badge variant="default">Interview scenario</Badge>}
            </div>

            {analysis.duplicate_matches.length > 0 && (
              <div className="rounded-md border border-warning/30 bg-warning/[0.06] p-2.5 text-xs">
                <p className="flex items-center gap-1.5 font-medium text-warning">
                  <AlertTriangle className="h-3.5 w-3.5" /> Similar question{analysis.duplicate_matches.length > 1 && "s"} already in the bank
                </p>
                <ul className="mt-1 space-y-0.5 text-foreground">
                  {analysis.duplicate_matches.slice(0, 3).map((m) => (
                    <li key={m.existing_question_id} className="line-clamp-1">
                      {Math.round(m.final_score * 100)}% · {bankText(m.existing_question_id)}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {isCodingType(finalType) && analysis.code_check && (
              <div className={cn("rounded-md p-2.5 text-xs", analysis.code_check.passed === analysis.code_check.total ? "bg-success/[0.07]" : "bg-destructive/[0.06]")}>
                <p className="flex items-center gap-1.5 font-medium text-foreground">
                  {analysis.code_check.passed === analysis.code_check.total ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                  ) : (
                    <XCircle className="h-3.5 w-3.5 text-destructive" />
                  )}
                  Reference solution passes {analysis.code_check.passed} of {analysis.code_check.total} test cases
                </p>
                {analysis.code_check.results
                  .filter((r) => !r.passed)
                  .map((r, i) => (
                    <p key={i} className="mt-1 font-mono text-[11px] text-muted-foreground">
                      input {JSON.stringify(r.input)} → expected {JSON.stringify(r.expected_output)}, got{" "}
                      {r.error ? r.error : JSON.stringify(r.actual_output)}
                    </p>
                  ))}
              </div>
            )}

            {isCodingType(finalType) && analysis.suggested_test_cases.length > 0 && (
              <div className="rounded-md border border-border bg-white p-2.5 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-medium text-foreground">AI-suggested test cases (outputs from running your solution)</p>
                  <Button size="sm" variant="outline" onClick={addSuggestedTests}>
                    <Plus className="h-3.5 w-3.5" /> Add these
                  </Button>
                </div>
                <ul className="mt-1.5 space-y-0.5 font-mono text-[11px] text-muted-foreground">
                  {analysis.suggested_test_cases.map((t, i) => (
                    <li key={i}>
                      {JSON.stringify(t.input)} → {JSON.stringify(t.expected_output)}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        )}

        {error && (
          <p className="flex items-center gap-1.5 text-xs text-destructive" role="alert">
            <AlertTriangle className="h-3.5 w-3.5" /> {error}
          </p>
        )}

        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border pt-3">
          {analysis && saveProblem && <p className="mr-auto text-xs text-muted-foreground">{saveProblem}</p>}
          <Button variant="outline" onClick={requestClose}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={busy !== null || Boolean(saveProblem)}>
            {busy === "save" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save to question bank
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
