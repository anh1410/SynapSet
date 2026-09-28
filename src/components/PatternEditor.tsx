import { useState } from "react";
import { AlertTriangle, Plus, Save, Trash2, X } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import {
  BLOOM_LABELS,
  BLOOM_LEVELS,
  DIFFICULTY_LEVELS,
  QUESTION_TYPE_LABELS,
  QUESTION_TYPE_ORDER,
  type BloomLevel,
  type DifficultyLevel,
  type ExamPatternFields,
  type GraphNode,
  type PatternSection,
  type QuestionType,
} from "@/lib/api";
import { cn } from "@/lib/utils";

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "rounded-full border px-2 py-0.5 text-[11px] font-medium transition-colors",
        active ? "border-primary/30 bg-primary/10 text-primary" : "border-border text-muted-foreground hover:text-foreground"
      )}
    >
      {children}
    </button>
  );
}

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="space-y-1">
      <label className="text-[11px] font-medium text-muted-foreground">{label}</label>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

const num = (v: string) => (v === "" ? 0 : Number(v));

function SumHint({ total }: { total: number }) {
  if (total === 0) return <span className="text-[11px] text-muted-foreground">Optional - leave all blank for no constraint</span>;
  const ok = Math.abs(total - 100) <= 1;
  return (
    <span className={cn("text-[11px] font-medium", ok ? "text-success" : "text-destructive")}>
      Total {total}% {ok ? "✓" : "- must add up to 100%"}
    </span>
  );
}

export function PatternEditor({
  initial,
  topics,
  title,
  warnings,
  saving,
  error,
  onSave,
  onCancel,
}: {
  initial: ExamPatternFields;
  topics: GraphNode[];
  title: string;
  warnings?: string[];
  saving: boolean;
  error: string | null;
  onSave: (pattern: ExamPatternFields) => void;
  onCancel: () => void;
}) {
  const [p, setP] = useState<ExamPatternFields>(initial);
  const set = <K extends keyof ExamPatternFields>(key: K, value: ExamPatternFields[K]) => setP((prev) => ({ ...prev, [key]: value }));

  const sectionMarks = p.sections.reduce((s, sec) => s + sec.num_questions * sec.marks_per_question, 0);
  const questionCount = p.sections.reduce((s, sec) => s + sec.num_questions, 0);
  const bloomTotal = p.bloom_distribution.reduce((s, b) => s + b.percent, 0);
  const diffTotal = p.difficulty_distribution.reduce((s, d) => s + d.percent, 0);
  const unitTotal = p.units.reduce((s, u) => s + u.percent, 0);

  const updateSection = (i: number, patch: Partial<PatternSection>) =>
    set("sections", p.sections.map((s, idx) => (idx === i ? { ...s, ...patch } : s)));

  const bloomPercent = (level: BloomLevel) => p.bloom_distribution.find((b) => b.bloom_level === level)?.percent;
  const setBloomPercent = (level: BloomLevel, value: string) => {
    const rest = p.bloom_distribution.filter((b) => b.bloom_level !== level);
    set("bloom_distribution", value === "" ? rest : [...rest, { bloom_level: level, percent: num(value) }].sort((a, b) => a.bloom_level - b.bloom_level));
  };
  const diffPercent = (d: DifficultyLevel) => p.difficulty_distribution.find((x) => x.difficulty === d)?.percent;
  const setDiffPercent = (d: DifficultyLevel, value: string) => {
    const rest = p.difficulty_distribution.filter((x) => x.difficulty !== d);
    set(
      "difficulty_distribution",
      value === "" ? rest : [...rest, { difficulty: d, percent: num(value) }].sort((a, b) => DIFFICULTY_LEVELS.indexOf(a.difficulty) - DIFFICULTY_LEVELS.indexOf(b.difficulty))
    );
  };

  const topicName = (id: string) => topics.find((t) => t.id === id)?.name ?? id;

  const handleSave = () => onSave({ ...p, total_marks: sectionMarks });

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle>{title}</CardTitle>
          <CardDescription className="mt-1">
            {questionCount} question{questionCount === 1 ? "" : "s"} · {sectionMarks} marks · {p.duration_minutes} min
          </CardDescription>
        </div>
        <button onClick={onCancel} className="rounded-md p-1 text-muted-foreground hover:bg-secondary" aria-label="Close editor">
          <X className="h-4 w-4" />
        </button>
      </CardHeader>
      <CardContent className="space-y-6">
        {warnings && warnings.length > 0 && (
          <div className="rounded-lg border border-warning/30 bg-warning/[0.04] p-3">
            <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-warning">
              <AlertTriangle className="h-3.5 w-3.5" /> Review before saving - extracted from the document
            </p>
            <ul className="list-disc space-y-0.5 pl-5 text-[11px] text-foreground">
              {warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        )}

        <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="sm:col-span-2">
            <Field label="Pattern name">
              <Input value={p.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. MSE-1 (Units 1-2)" />
            </Field>
          </div>
          <Field label="Exam type">
            <Select value={p.exam_type} onChange={(e) => set("exam_type", e.target.value as ExamPatternFields["exam_type"])}>
              <option value="MSE">MSE - Mid-Semester</option>
              <option value="SEE">SEE - Semester-End</option>
            </Select>
          </Field>
          <Field label="Duration (min)">
            <Input type="number" min={1} value={p.duration_minutes} onChange={(e) => set("duration_minutes", num(e.target.value))} />
          </Field>
          <div className="sm:col-span-2 lg:col-span-3">
            <Field label="Description">
              <Input value={p.description} onChange={(e) => set("description", e.target.value)} placeholder="Optional notes, e.g. which units this exam covers" />
            </Field>
          </div>
          <Field label="Tolerance (± % of marks)" hint="How far a distribution may drift from target">
            <Input type="number" min={0} max={50} value={p.tolerance_percent} onChange={(e) => set("tolerance_percent", num(e.target.value))} />
          </Field>
        </section>

        {/* Sections */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold text-foreground">Sections</p>
              <p className="text-[11px] text-muted-foreground">Total marks = sum of sections ({sectionMarks})</p>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                set("sections", [
                  ...p.sections,
                  { name: `Part ${String.fromCharCode(65 + p.sections.length)}`, instructions: "", num_questions: 1, marks_per_question: 5, question_types: [], bloom_levels: [] },
                ])
              }
            >
              <Plus className="h-3.5 w-3.5" /> Add section
            </Button>
          </div>
          {p.sections.map((sec, i) => (
            <div key={i} className="space-y-3 rounded-lg border border-border p-3">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-[1fr_110px_110px_110px_auto]">
                <Field label="Name">
                  <Input value={sec.name} onChange={(e) => updateSection(i, { name: e.target.value })} />
                </Field>
                <Field label="Questions">
                  <Input type="number" min={1} value={sec.num_questions} onChange={(e) => updateSection(i, { num_questions: num(e.target.value) })} />
                </Field>
                <Field label="Marks each">
                  <Input type="number" min={1} value={sec.marks_per_question} onChange={(e) => updateSection(i, { marks_per_question: num(e.target.value) })} />
                </Field>
                <Field label="Section marks">
                  <div className="flex h-9 items-center text-sm font-medium text-foreground">{sec.num_questions * sec.marks_per_question}</div>
                </Field>
                <div className="flex items-end justify-end">
                  <button
                    onClick={() => set("sections", p.sections.filter((_, idx) => idx !== i))}
                    disabled={p.sections.length === 1}
                    className="mb-2 text-muted-foreground hover:text-destructive disabled:opacity-30"
                    aria-label={`Remove ${sec.name}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
              <Field label="Allowed question types (none selected = any)">
                <div className="flex flex-wrap gap-1.5">
                  {QUESTION_TYPE_ORDER.map((qt: QuestionType) => (
                    <Chip key={qt} active={sec.question_types.includes(qt)} onClick={() => updateSection(i, { question_types: toggle(sec.question_types, qt) })}>
                      {QUESTION_TYPE_LABELS[qt]}
                    </Chip>
                  ))}
                </div>
              </Field>
              <Field label="Allowed Bloom's levels (none selected = any)">
                <div className="flex flex-wrap gap-1.5">
                  {BLOOM_LEVELS.map((b) => (
                    <Chip key={b} active={sec.bloom_levels.includes(b)} onClick={() => updateSection(i, { bloom_levels: toggle(sec.bloom_levels, b).sort() })}>
                      L{b} {BLOOM_LABELS[b]}
                    </Chip>
                  ))}
                </div>
              </Field>
              <Field label="Instructions">
                <Input value={sec.instructions} onChange={(e) => updateSection(i, { instructions: e.target.value })} placeholder="e.g. Answer all questions" />
              </Field>
            </div>
          ))}
        </section>

        {/* Distributions */}
        <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="space-y-2 rounded-lg border border-border p-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold text-foreground">Bloom's Taxonomy distribution</p>
              <SumHint total={bloomTotal} />
            </div>
            <p className="text-[11px] text-muted-foreground">% of total marks at each level</p>
            <div className="grid grid-cols-3 gap-2">
              {BLOOM_LEVELS.map((b) => (
                <Field key={b} label={`L${b} ${BLOOM_LABELS[b]}`}>
                  <Input type="number" min={0} max={100} placeholder="—" value={bloomPercent(b) ?? ""} onChange={(e) => setBloomPercent(b, e.target.value)} />
                </Field>
              ))}
            </div>
          </div>
          <div className="space-y-2 rounded-lg border border-border p-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold text-foreground">Difficulty distribution</p>
              <SumHint total={diffTotal} />
            </div>
            <p className="text-[11px] text-muted-foreground">% of total marks; uses each question's difficulty score (Easy ≤ 4, Medium ≤ 7, Hard &gt; 7)</p>
            <div className="grid grid-cols-3 gap-2">
              {DIFFICULTY_LEVELS.map((d) => (
                <Field key={d} label={d[0].toUpperCase() + d.slice(1)}>
                  <Input type="number" min={0} max={100} placeholder="—" value={diffPercent(d) ?? ""} onChange={(e) => setDiffPercent(d, e.target.value)} />
                </Field>
              ))}
            </div>
          </div>
        </section>

        {/* Units */}
        <section className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-xs font-semibold text-foreground">Unit / topic distribution</p>
              <p className="text-[11px] text-muted-foreground">
                A unit is a group of knowledge-graph topics. Questions tagged with those topics count toward it; when units are set, only their topics are used.
              </p>
            </div>
            <div className="flex items-center gap-2">
              {p.units.length > 0 && <SumHint total={unitTotal} />}
              <Button
                size="sm"
                variant="outline"
                onClick={() => set("units", [...p.units, { unit: (Math.max(0, ...p.units.map((u) => u.unit)) || 0) + 1, name: "", topic_ids: [], percent: 0 }])}
              >
                <Plus className="h-3.5 w-3.5" /> Add unit
              </Button>
            </div>
          </div>
          {p.units.length > 0 && topics.length === 0 && (
            <p className="text-[11px] text-warning">Upload course material first so there are topics to assign to units.</p>
          )}
          {p.units.map((u, i) => (
            <div key={i} className="space-y-2 rounded-lg border border-border p-3">
              <div className="grid grid-cols-[80px_1fr_110px_auto] gap-2">
                <Field label="Unit #">
                  <Input type="number" min={1} value={u.unit} onChange={(e) => set("units", p.units.map((x, idx) => (idx === i ? { ...x, unit: num(e.target.value) } : x)))} />
                </Field>
                <Field label="Name">
                  <Input value={u.name} placeholder={`Unit ${u.unit}`} onChange={(e) => set("units", p.units.map((x, idx) => (idx === i ? { ...x, name: e.target.value } : x)))} />
                </Field>
                <Field label="% of marks">
                  <Input type="number" min={0} max={100} value={u.percent} onChange={(e) => set("units", p.units.map((x, idx) => (idx === i ? { ...x, percent: num(e.target.value) } : x)))} />
                </Field>
                <div className="flex items-end">
                  <button onClick={() => set("units", p.units.filter((_, idx) => idx !== i))} className="mb-2 text-muted-foreground hover:text-destructive" aria-label="Remove unit">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
              <Field label={`Topics (${u.topic_ids.length} selected)`}>
                <div className="flex max-h-32 flex-wrap gap-1.5 overflow-y-auto scrollbar-thin">
                  {u.topic_ids
                    .filter((id) => !topics.some((t) => t.id === id))
                    .map((id) => (
                      <Chip key={id} active onClick={() => set("units", p.units.map((x, idx) => (idx === i ? { ...x, topic_ids: toggle(x.topic_ids, id) } : x)))}>
                        {topicName(id)} (not in graph)
                      </Chip>
                    ))}
                  {topics.map((t) => (
                    <Chip key={t.id} active={u.topic_ids.includes(t.id)} onClick={() => set("units", p.units.map((x, idx) => (idx === i ? { ...x, topic_ids: toggle(x.topic_ids, t.id) } : x)))}>
                      {t.name}
                    </Chip>
                  ))}
                </div>
              </Field>
            </div>
          ))}
        </section>

        {/* Course outcomes */}
        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold text-foreground">Course-outcome coverage</p>
              <p className="text-[11px] text-muted-foreground">Minimum number of questions tagged with each CO</p>
            </div>
            <Button size="sm" variant="outline" onClick={() => set("co_requirements", [...p.co_requirements, { co_code: `CO${p.co_requirements.length + 1}`, min_questions: 1 }])}>
              <Plus className="h-3.5 w-3.5" /> Add CO
            </Button>
          </div>
          <div className="flex flex-wrap gap-2">
            {p.co_requirements.map((c, i) => (
              <div key={i} className="flex items-center gap-1.5 rounded-lg border border-border p-1.5">
                <Input className="h-7 w-20" value={c.co_code} onChange={(e) => set("co_requirements", p.co_requirements.map((x, idx) => (idx === i ? { ...x, co_code: e.target.value } : x)))} />
                <span className="text-[11px] text-muted-foreground">min</span>
                <Input className="h-7 w-14" type="number" min={1} value={c.min_questions} onChange={(e) => set("co_requirements", p.co_requirements.map((x, idx) => (idx === i ? { ...x, min_questions: num(e.target.value) } : x)))} />
                <button onClick={() => set("co_requirements", p.co_requirements.filter((_, idx) => idx !== i))} className="text-muted-foreground hover:text-destructive" aria-label="Remove CO">
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        </section>

        {error && (
          <p className="flex items-start gap-1.5 rounded-lg border border-destructive/30 bg-destructive/[0.04] p-2.5 text-xs text-destructive">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving || !p.name.trim()}>
            <Save className="h-4 w-4" /> {saving ? "Saving..." : "Save pattern"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
