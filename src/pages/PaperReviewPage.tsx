import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  CheckCircle2,
  Download,
  FileSearch,
  Lock,
  Pencil,
  RefreshCw,
  Replace,
  RotateCcw,
  Save,
  Trash2,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { BlueprintView } from "@/components/BlueprintView";
import { EvidenceDialog } from "@/components/EvidenceDialog";
import {
  ASSESSMENT_TYPE_LABELS,
  BLOOM_LABELS,
  QUESTION_TYPE_LABELS,
  SKILL_LABELS,
  difficultyBucket,
  downloadExport,
  effectiveSkill,
  fetchBlueprint,
  fetchGraph,
  fetchQuestionUsage,
  fetchReplacementCandidates,
  getExam,
  getExamSubmissions,
  regenerateQuestion,
  setQuestionMarks,
  updateExam,
  type Blueprint,
  type Exam,
  type ExportKind,
  type MarksOverrides,
  type Question,
  type QuestionUsage,
  type RegenerateResult,
  type ReplacementCandidate,
  isCodingType,
} from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { cn } from "@/lib/utils";

// ---------- what an edit changed ----------

interface Change {
  text: string;
  worse: boolean;
}

/** Every constraint whose status or value differs between the saved paper and the draft. */
function diffBlueprints(saved: Blueprint, draft: Blueprint): Change[] {
  const out: Change[] = [];
  if (saved.total_marks !== draft.total_marks) {
    const target = draft.target_marks;
    out.push({
      text: `Total marks ${saved.total_marks} → ${draft.total_marks}${target != null ? ` (pattern needs ${target})` : ""}`,
      worse: target != null && draft.total_marks !== target,
    });
  }
  for (const s of draft.sections) {
    const before = saved.sections.find((x) => x.name === s.name);
    if (before && before.filled !== s.filled) {
      out.push({ text: `${s.name}: ${before.filled} → ${s.filled} of ${s.required} filled`, worse: s.filled < s.required });
    }
  }
  const families: [string, keyof Blueprint][] = [
    ["Unit", "units"],
    ["Bloom's", "bloom"],
    ["Difficulty", "difficulty"],
    ["Type", "question_types"],
    ["Skill", "skills"],
  ];
  for (const [label, key] of families) {
    const now = draft[key] as Blueprint["bloom"];
    const was = saved[key] as Blueprint["bloom"];
    const keys = new Set([...now.map((r) => r.key), ...was.map((r) => r.key)]);
    for (const k of keys) {
      const a = was.find((r) => r.key === k);
      const b = now.find((r) => r.key === k);
      const before = a?.actual_percent ?? 0;
      const after = b?.actual_percent ?? 0;
      if (Math.abs(before - after) < 0.05) continue;
      const targeted = (b ?? a)?.target_percent != null;
      const statusFlip = targeted && (a?.within_tolerance ?? true) !== (b?.within_tolerance ?? true);
      if (!targeted && !statusFlip && label !== "Skill" && label !== "Type") continue;
      out.push({
        text: `${label} ${b?.label ?? a?.label}: ${before}% → ${after}%${statusFlip ? (b?.within_tolerance ? " (now within target)" : " (now outside target)") : ""}`,
        worse: statusFlip && !(b?.within_tolerance ?? true),
      });
    }
  }
  for (const c of draft.course_outcomes) {
    const before = saved.course_outcomes.find((x) => x.co_code === c.co_code);
    if (before && (before.actual_percent !== c.actual_percent || before.met !== c.met)) {
      out.push({
        text: `${c.co_code}: ${before.actual_percent}% → ${c.actual_percent}% of marks${before.met !== c.met ? (c.met ? " (now satisfied)" : " (no longer satisfied)") : ""}`,
        worse: before.met && !c.met,
      });
    }
  }
  return out;
}

// ---------- page ----------

export function PaperReviewPage({ examId, onBack }: { examId: string; onBack: () => void }) {
  const { activeSubjectId } = useAuth();
  const [exam, setExam] = useState<Exam | null>(null);
  const [savedIds, setSavedIds] = useState<string[]>([]);
  const [draft, setDraft] = useState<Question[]>([]);
  const [savedBp, setSavedBp] = useState<Blueprint | null>(null);
  const [draftBp, setDraftBp] = useState<Blueprint | null>(null);
  const [topicNames, setTopicNames] = useState<Record<string, string>>({});
  const [usage, setUsage] = useState<Record<string, QuestionUsage>>({});
  const [locked, setLocked] = useState(false);
  const [busy, setBusy] = useState<string | null>(null); // question id with an operation in flight
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmSave, setConfirmSave] = useState(false);
  const [replaceFor, setReplaceFor] = useState<Question | null>(null);
  const [candidates, setCandidates] = useState<ReplacementCandidate[] | null>(null);
  const [regen, setRegen] = useState<{ target: Question; result: RegenerateResult; compliantAfter: boolean | null } | null>(null);
  const [marksEdit, setMarksEdit] = useState<{ id: string; value: string } | null>(null);
  // Marks edits stay in the draft (like every other edit) until Save.
  const [overrides, setOverrides] = useState<MarksOverrides>({});
  // Marks of each question as they are in the bank (i.e. before any unsaved edit).
  const [bankMarks, setBankMarks] = useState<Record<string, number>>({});
  const [evidenceFor, setEvidenceFor] = useState<Question | null>(null);
  const [exporting, setExporting] = useState<ExportKind | null>(null);

  const draftIds = useMemo(() => draft.map((q) => q.id), [draft]);
  const activeOverrides = useMemo(
    () => Object.fromEntries(Object.entries(overrides).filter(([id]) => draftIds.includes(id))),
    [overrides, draftIds]
  );
  const overridesKey = JSON.stringify(activeOverrides);
  const dirty = draftIds.join(",") !== savedIds.join(",") || Object.keys(activeOverrides).length > 0;

  const load = useCallback(async () => {
    const [{ exam: e, questions }, subs] = await Promise.all([getExam(examId), getExamSubmissions(examId)]);
    setExam(e);
    setSavedIds(questions.map((q) => q.id));
    setDraft(questions);
    setOverrides({});
    setBankMarks(Object.fromEntries(questions.map((q) => [q.id, q.marks])));
    setLocked(subs.length > 0);
    const bp = await fetchBlueprint(examId);
    setSavedBp(bp);
    setDraftBp(bp);
  }, [examId]);

  useEffect(() => {
    load().catch((e) => setError(e instanceof Error ? e.message : "Couldn't load the paper"));
  }, [load]);

  useEffect(() => {
    if (!activeSubjectId) return;
    fetchGraph(activeSubjectId).then((g) => setTopicNames(Object.fromEntries(g.nodes.map((n) => [n.id, n.name]))));
    fetchQuestionUsage(activeSubjectId).then((u) => setUsage(u.usage)).catch(() => {});
  }, [activeSubjectId]);

  // Re-run compliance whenever the draft changes.
  useEffect(() => {
    if (!exam) return;
    const t = setTimeout(() => {
      fetchBlueprint(examId, draftIds, activeOverrides)
        .then(setDraftBp)
        .catch((e) => setError(e instanceof Error ? e.message : "Compliance check failed"));
    }, 200);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [examId, exam, draftIds, overridesKey]);

  const changes = useMemo(() => (savedBp && draftBp && dirty ? diffBlueprints(savedBp, draftBp) : []), [savedBp, draftBp, dirty]);
  const membership = useMemo(() => {
    const before = new Set(savedIds);
    const after = new Set(draftIds);
    const added = draftIds.filter((id) => !before.has(id)).length;
    const removed = savedIds.filter((id) => !after.has(id)).length;
    const swapped = Math.min(added, removed);
    const parts = [];
    const remarked = Object.keys(activeOverrides).length;
    if (remarked) parts.push(`marks changed on ${remarked} question${remarked === 1 ? "" : "s"}`);
    if (swapped) parts.push(`${swapped} question${swapped === 1 ? "" : "s"} replaced`);
    if (removed > swapped) parts.push(`${removed - swapped} removed`);
    if (added > swapped) parts.push(`${added - swapped} added`);
    return parts.length ? parts.join(", ") : "Order changed";
  }, [savedIds, draftIds, activeOverrides]);

  const sectionOf = (id: string) => draftBp?.sections.find((s) => s.question_ids.includes(id))?.name ?? null;
  const groups = useMemo(() => {
    if (!draftBp || draftBp.sections.length === 0) return [{ name: null as string | null, questions: draft }];
    const g = draftBp.sections.map((s) => ({ name: s.name as string | null, questions: draft.filter((q) => s.question_ids.includes(q.id)) }));
    const unplaced = draft.filter((q) => !draftBp.sections.some((s) => s.question_ids.includes(q.id)));
    if (unplaced.length) g.push({ name: "Doesn't fit any section", questions: unplaced });
    return g;
  }, [draft, draftBp]);

  // ----- edit operations (all local until Save) -----

  const swap = (oldId: string, q: Question) => setDraft((d) => d.map((x) => (x.id === oldId ? q : x)));

  const move = (id: string, dir: -1 | 1) => {
    const group = groups.find((g) => g.questions.some((q) => q.id === id));
    if (!group) return;
    const idx = group.questions.findIndex((q) => q.id === id);
    const other = group.questions[idx + dir];
    if (!other) return;
    setDraft((d) => {
      const next = [...d];
      const a = next.findIndex((q) => q.id === id);
      const b = next.findIndex((q) => q.id === other.id);
      [next[a], next[b]] = [next[b], next[a]];
      return next;
    });
  };

  const remove = (id: string) => setDraft((d) => d.filter((q) => q.id !== id));

  const openReplace = async (q: Question) => {
    setReplaceFor(q);
    setCandidates(null);
    try {
      setCandidates(await fetchReplacementCandidates(examId, draftIds, q.id, activeOverrides));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load candidates");
      setReplaceFor(null);
    }
  };

  const doRegenerate = async (q: Question, forceNew = false) => {
    setBusy(q.id);
    setError(null);
    try {
      const result = await regenerateQuestion(examId, draftIds, q.id, forceNew, activeOverrides);
      const after = await fetchBlueprint(examId, draftIds.map((id) => (id === q.id ? result.question.id : id)), activeOverrides);
      setRegen({ target: q, result, compliantAfter: after.compliant });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Regeneration failed");
    } finally {
      setBusy(null);
    }
  };

  const applyMarks = async () => {
    if (!marksEdit) return;
    const value = Number(marksEdit.value);
    if (!Number.isInteger(value) || value < 1 || value > 100) {
      setError("Marks must be a whole number from 1 to 100");
      return;
    }
    const id = marksEdit.id;
    const original = savedMarks(id);
    setOverrides((o) => {
      const next = { ...o };
      if (value === original) delete next[id];
      else next[id] = value;
      return next;
    });
    setDraft((d) => d.map((q) => (q.id === id ? { ...q, marks: value } : q)));
    setMarksEdit(null);
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      // Apply marks edits first; the server copies a question rather than
      // changing it when other exams or graded answers depend on it.
      let ids = draftIds;
      for (const [id, marks] of Object.entries(activeOverrides)) {
        const { question } = await setQuestionMarks(examId, ids, id, marks);
        ids = ids.map((x) => (x === id ? question.id : x));
      }
      await updateExam(examId, { question_ids: ids, total_marks: draft.reduce((s, q) => s + q.marks, 0) });
      setConfirmSave(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save the paper");
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    setBankMarks((m) => {
      const next = { ...m };
      for (const q of draft) if (!(q.id in next) && !(q.id in overrides)) next[q.id] = q.marks;
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);
  function savedMarks(id: string) {
    return bankMarks[id] ?? draft.find((q) => q.id === id)?.marks ?? 0;
  }

  const requestSave = () => (draftBp?.compliant === false ? setConfirmSave(true) : save());

  const exportPdf = async (kind: ExportKind) => {
    if (!exam) return;
    setExporting(kind);
    setError(null);
    try {
      await downloadExport(examId, kind, exam.name);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(null);
    }
  };

  if (!exam || !draftBp || !savedBp) {
    return error ? (
      <p className="text-sm text-destructive">{error}</p>
    ) : (
      <div className="space-y-3">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  let number = 0;
  return (
    <div className="space-y-4">
      <button onClick={onBack} className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to Exams
      </button>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex flex-wrap items-center gap-2 text-lg font-semibold text-foreground">
            {exam.name} <Badge variant={exam.exam_type === "QUIZ" ? "secondary" : "default"}>{ASSESSMENT_TYPE_LABELS[exam.exam_type]}</Badge>
          </h1>
          <p className="text-sm text-muted-foreground">Final paper review — edit, check the blueprint, and export.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {(["paper", "answer-key", "blueprint"] as ExportKind[]).map((k) => (
            <Button key={k} size="sm" variant="outline" onClick={() => exportPdf(k)} disabled={exporting !== null || draft.length === 0}>
              <Download className="h-3.5 w-3.5" />
              {exporting === k ? "Preparing..." : k === "paper" ? "Question paper" : k === "answer-key" ? "Answer key" : "Blueprint"} PDF
            </Button>
          ))}
        </div>
      </div>

      {locked && (
        <p className="flex items-center gap-2 rounded-lg border border-border bg-secondary/40 p-3 text-xs text-foreground">
          <Lock className="h-3.5 w-3.5 text-muted-foreground" /> Students have already submitted this exam, so the paper is read-only —
          changing it would make the results no longer match what students answered.
        </p>
      )}
      {dirty && (
        <p className="text-[11px] text-muted-foreground">PDF exports use the saved paper — save your changes first to export them.</p>
      )}
      {error && (
        <p className="flex items-center gap-1.5 rounded-lg border border-destructive/30 bg-destructive/[0.04] p-2.5 text-xs text-destructive">
          <AlertTriangle className="h-3.5 w-3.5" /> {error}
        </p>
      )}

      {/* Save bar with the exact impact of the unsaved edits */}
      {dirty && (
        <Card className={cn(changes.some((c) => c.worse) || draftBp.compliant === false ? "border-warning/40" : "border-primary/30")}>
          <CardContent className="space-y-2 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-medium text-foreground">
                Unsaved changes ({membership.toLowerCase()}) ·{" "}
                {draftBp.compliant === null ? (
                  "free-form quiz"
                ) : draftBp.compliant ? (
                  <span className="text-success">still satisfies the pattern</span>
                ) : (
                  <span className="text-destructive">no longer satisfies the pattern</span>
                )}
              </p>
              <div className="flex gap-2">
                <Button size="sm" variant="ghost" onClick={() => load()}>
                  <RotateCcw className="h-3.5 w-3.5" /> Discard
                </Button>
                <Button size="sm" onClick={requestSave} disabled={saving || draft.length === 0}>
                  <Save className="h-3.5 w-3.5" /> {saving ? "Saving..." : "Save paper"}
                </Button>
              </div>
            </div>
            {changes.length > 0 ? (
              <ul className="space-y-0.5 text-[11px]">
                {changes.map((c) => (
                  <li key={c.text} className={cn("flex items-start gap-1.5", c.worse ? "text-destructive" : "text-muted-foreground")}>
                    {c.worse ? <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" /> : <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-success" />}
                    {c.text}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[11px] text-muted-foreground">{membership} — no constraint affected.</p>
            )}
          </CardContent>
        </Card>
      )}

      <Tabs defaultValue="paper">
        <TabsList>
          <TabsTrigger value="paper">Paper ({draft.length})</TabsTrigger>
          <TabsTrigger value="blueprint">
            Blueprint{" "}
            {draftBp.compliant === false && <AlertTriangle className="ml-1 h-3 w-3 text-destructive" />}
            {draftBp.compliant === true && <CheckCircle2 className="ml-1 h-3 w-3 text-success" />}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="blueprint" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Assessment blueprint</CardTitle>
              <CardDescription>Target vs actual for {dirty ? "the edited (unsaved) paper" : "the saved paper"}</CardDescription>
            </CardHeader>
            <CardContent>
              <BlueprintView blueprint={draftBp} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="paper" className="mt-4 space-y-4">
          {groups.map((group) => (
            <div key={group.name ?? "all"} className="space-y-3">
              {group.name && (
                <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {group.name} · {group.questions.length} question{group.questions.length === 1 ? "" : "s"} ·{" "}
                  {group.questions.reduce((s, q) => s + q.marks, 0)} marks
                </p>
              )}
              {group.questions.map((q, idx) => {
                number += 1;
                const u = usage[q.id];
                const isBusy = busy === q.id;
                return (
                  <Card key={q.id} className={cn(isBusy && "opacity-60")}>
                    <CardContent className="space-y-2 p-4">
                      <div className="flex items-start justify-between gap-3">
                        <p className="whitespace-pre-wrap text-sm text-foreground">
                          <span className="font-semibold">{number}.</span> {q.text}
                        </p>
                        <span className="shrink-0 text-xs font-semibold text-foreground">[{q.marks}]</span>
                      </div>
                      {(q.question_type === "mcq" || q.question_type === "fill_in_blank") && q.options && (
                        <ul className="grid grid-cols-1 gap-0.5 pl-4 text-xs text-muted-foreground sm:grid-cols-2">
                          {q.options.map((o, i) => (
                            <li key={i} className={cn(o === q.correct_answer && "font-medium text-success")}>
                              ({String.fromCharCode(97 + i)}) {o}
                            </li>
                          ))}
                        </ul>
                      )}
                      {isCodingType(q.question_type) && q.starter_code && (
                        <pre className="overflow-x-auto rounded-md bg-slate-900 p-2.5 text-[11px] text-slate-100">
                          <code>{q.starter_code}</code>
                        </pre>
                      )}
                      <div className="flex flex-wrap gap-1.5">
                        {group.name && sectionOf(q.id) && <Badge variant="default">{sectionOf(q.id)}</Badge>}
                        <Badge variant="outline">{QUESTION_TYPE_LABELS[q.question_type]}</Badge>
                        <Badge variant="accent">{BLOOM_LABELS[q.bloom_level]}</Badge>
                        <Badge variant="outline">{difficultyBucket(q.difficulty_score)}</Badge>
                        <Badge variant="outline">{SKILL_LABELS[effectiveSkill(q)]}</Badge>
                        {q.topic_ids.map((t) => (
                          <Badge key={t} variant="outline">
                            {topicNames[t] ?? t}
                          </Badge>
                        ))}
                        {q.co_ids.map((c) => (
                          <Badge key={c} variant="secondary">
                            {c}
                          </Badge>
                        ))}
                        {u && (
                          <Badge variant="outline" title={u.exams.map((x) => x.name).join(", ")}>
                            {u.never_used ? "Never used" : `Used ${u.times_used}×`}
                          </Badge>
                        )}
                        {q.derived_from && <Badge variant="outline">edited copy</Badge>}
                      </div>

                      {marksEdit?.id === q.id ? (
                        <div className="flex items-center gap-2">
                          <Input
                            type="number"
                            min={1}
                            max={100}
                            className="h-7 w-20"
                            value={marksEdit.value}
                            onChange={(e) => setMarksEdit({ id: q.id, value: e.target.value })}
                            aria-label="New marks"
                          />
                          <Button size="sm" className="h-7" onClick={applyMarks} disabled={isBusy}>
                            Apply
                          </Button>
                          <Button size="sm" variant="ghost" className="h-7" onClick={() => setMarksEdit(null)}>
                            Cancel
                          </Button>
                          {draftBp.pattern_id && (
                            <span className="text-[11px] text-muted-foreground">Section slots have fixed marks — this may break the pattern.</span>
                          )}
                        </div>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => move(q.id, -1)} disabled={locked || idx === 0} aria-label="Move up">
                            <ArrowUp className="h-3.5 w-3.5" />
                          </Button>
                          <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => move(q.id, 1)} disabled={locked || idx === group.questions.length - 1} aria-label="Move down">
                            <ArrowDown className="h-3.5 w-3.5" />
                          </Button>
                          <Button size="sm" variant="outline" className="h-7" onClick={() => openReplace(q)} disabled={locked || isBusy}>
                            <Replace className="h-3.5 w-3.5" /> Replace
                          </Button>
                          <Button size="sm" variant="outline" className="h-7" onClick={() => doRegenerate(q)} disabled={locked || isBusy}>
                            <RefreshCw className={cn("h-3.5 w-3.5", isBusy && "animate-spin")} /> {isBusy ? "Working..." : "Regenerate"}
                          </Button>
                          <Button size="sm" variant="outline" className="h-7" onClick={() => setMarksEdit({ id: q.id, value: String(q.marks) })} disabled={locked}>
                            <Pencil className="h-3.5 w-3.5" /> Marks
                          </Button>
                          <Button size="sm" variant="outline" className="h-7" onClick={() => setEvidenceFor(q)}>
                            <FileSearch className="h-3.5 w-3.5" /> Source
                          </Button>
                          <Button size="sm" variant="ghost" className="h-7 text-destructive hover:text-destructive" onClick={() => remove(q.id)} disabled={locked}>
                            <Trash2 className="h-3.5 w-3.5" /> Remove
                          </Button>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          ))}
        </TabsContent>
      </Tabs>

      {/* Replace from bank */}
      <Dialog
        open={replaceFor !== null}
        onClose={() => setReplaceFor(null)}
        title="Replace with a bank question"
        description={replaceFor ? `Replacing: ${replaceFor.text}` : undefined}
      >
        {candidates === null ? (
          <Skeleton className="h-24 w-full" />
        ) : candidates.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No other bank question has the same marks. Use Regenerate to create one.
          </p>
        ) : (
          <ul className="space-y-2">
            {candidates.map((c) => (
              <li key={c.question.id} className="rounded-lg border border-border p-3">
                <p className="text-xs text-foreground">{c.question.text}</p>
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px]">
                  <Badge variant="outline">{QUESTION_TYPE_LABELS[c.question.question_type]}</Badge>
                  <Badge variant="accent">{BLOOM_LABELS[c.question.bloom_level]}</Badge>
                  <Badge variant="outline">{difficultyBucket(c.question.difficulty_score)}</Badge>
                  <span className="text-muted-foreground">
                    Same {c.matches.length ? c.matches.join(", ") : "marks only"} · {c.times_used ? `used ${c.times_used}×` : "never used"}
                  </span>
                </div>
                {c.keeps_compliant === false && (
                  <ul className="mt-1.5 space-y-0.5 text-[11px] text-destructive">
                    {c.new_issues.map((i) => (
                      <li key={i} className="flex items-start gap-1">
                        <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" /> Would break: {i}
                      </li>
                    ))}
                  </ul>
                )}
                <div className="mt-2 flex items-center justify-between">
                  {c.keeps_compliant === true ? (
                    <span className="flex items-center gap-1 text-[11px] font-medium text-success">
                      <CheckCircle2 className="h-3 w-3" /> Keeps the paper compliant
                    </span>
                  ) : (
                    <span />
                  )}
                  <Button
                    size="sm"
                    variant={c.keeps_compliant === false ? "outline" : "primary"}
                    className="h-7"
                    onClick={() => {
                      if (replaceFor) swap(replaceFor.id, c.question);
                      setReplaceFor(null);
                    }}
                  >
                    Use this question
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Dialog>

      {/* Regeneration result */}
      <Dialog
        open={regen !== null}
        onClose={() => setRegen(null)}
        title={regen?.result.source === "reused" ? "Matching question found in the bank" : "Regenerated question"}
        description={regen?.result.note}
      >
        {regen && (
          <div className="space-y-3 text-xs">
            <div className="rounded-lg border border-border p-3">
              <p className="text-foreground">{regen.result.question.text}</p>
              {regen.result.question.options && (
                <ul className="mt-1 pl-4 text-muted-foreground">
                  {regen.result.question.options.map((o, i) => (
                    <li key={i}>
                      ({String.fromCharCode(97 + i)}) {o}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <table className="w-full">
              <thead>
                <tr className="text-left text-[11px] text-muted-foreground">
                  <th className="py-1 font-medium">Constraint</th>
                  <th className="py-1 font-medium">Required</th>
                  <th className="py-1 font-medium">New question</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {regen.result.checks.map((c) => (
                  <tr key={c.name} className="border-t border-border/60">
                    <td className="py-1.5 text-foreground">{c.name}</td>
                    <td className="py-1.5 text-muted-foreground">{c.required}</td>
                    <td className="py-1.5 text-foreground">{c.actual}</td>
                    <td className="py-1.5 text-right">
                      {c.ok ? <CheckCircle2 className="ml-auto h-3.5 w-3.5 text-success" /> : <AlertTriangle className="ml-auto h-3.5 w-3.5 text-destructive" />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {regen.compliantAfter !== null && (
              <p className={cn("font-medium", regen.compliantAfter ? "text-success" : "text-destructive")}>
                {regen.compliantAfter ? "The paper stays compliant with this question." : "The paper would not satisfy the pattern with this question."}
              </p>
            )}
            <div className="flex flex-wrap justify-end gap-2">
              {regen.result.source === "reused" && (
                <Button size="sm" variant="outline" onClick={() => { const t = regen.target; setRegen(null); doRegenerate(t, true); }}>
                  <RefreshCw className="h-3.5 w-3.5" /> Generate a new one instead
                </Button>
              )}
              <Button size="sm" variant="ghost" onClick={() => setRegen(null)}>
                Keep the original
              </Button>
              <Button size="sm" onClick={() => { swap(regen.target.id, regen.result.question); setRegen(null); }}>
                Use this question
              </Button>
            </div>
          </div>
        )}
      </Dialog>

      {/* Save confirmation when the draft breaks the pattern */}
      <Dialog open={confirmSave} onClose={() => setConfirmSave(false)} title="Save a paper that doesn't satisfy its pattern?">
        <div className="space-y-3 text-xs">
          <p className="text-foreground">The edited paper no longer meets these {exam.exam_type} pattern constraints:</p>
          <ul className="space-y-0.5 text-destructive">
            {draftBp.issues.map((i) => (
              <li key={i} className="flex items-start gap-1">
                <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" /> {i}
              </li>
            ))}
          </ul>
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => setConfirmSave(false)}>
              Keep editing
            </Button>
            <Button size="sm" variant="outline" className="text-destructive" onClick={save} disabled={saving}>
              Save anyway
            </Button>
          </div>
        </div>
      </Dialog>

      {activeSubjectId && <EvidenceDialog subjectId={activeSubjectId} question={evidenceFor} onClose={() => setEvidenceFor(null)} />}
    </div>
  );
}
