import { useEffect, useRef, useState } from "react";
import { FileUp, LayoutTemplate, Pencil, Plus, Sparkles, Trash2, Clock } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { PatternEditor } from "@/components/PatternEditor";
import {
  BLOOM_LABELS,
  QUESTION_TYPE_LABELS,
  createPattern,
  deletePattern,
  fetchGraph,
  importPatternDocument,
  listPatternPresets,
  listPatterns,
  updatePattern,
  type ExamPattern,
  type ExamPatternFields,
  type GraphNode,
  type PatternExamType,
} from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";

type EditorState =
  | { mode: "closed" }
  | { mode: "create"; initial: ExamPatternFields; warnings?: string[]; sourceFilename?: string }
  | { mode: "edit"; pattern: ExamPattern };

export function PatternsPage({ onBuildExam }: { onBuildExam: (patternId: string) => void }) {
  const { activeSubjectId } = useAuth();
  const [patterns, setPatterns] = useState<ExamPattern[]>([]);
  const [presets, setPresets] = useState<ExamPatternFields[]>([]);
  const [topics, setTopics] = useState<GraphNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [editor, setEditor] = useState<EditorState>({ mode: "closed" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [importHint, setImportHint] = useState<PatternExamType | "">("");
  const [importError, setImportError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    listPatternPresets().then(setPresets);
  }, []);

  useEffect(() => {
    if (!activeSubjectId) return;
    setLoading(true);
    setEditor({ mode: "closed" });
    Promise.all([listPatterns(activeSubjectId).then(setPatterns), fetchGraph(activeSubjectId).then((g) => setTopics(g.nodes))]).finally(() =>
      setLoading(false)
    );
  }, [activeSubjectId]);

  const openPreset = (type: PatternExamType) => {
    const preset = presets.find((p) => p.exam_type === type);
    if (!preset) return;
    setError(null);
    setEditor({ mode: "create", initial: structuredClone(preset) });
  };

  const handleImport = async (file: File) => {
    if (!activeSubjectId) return;
    setImporting(true);
    setImportError(null);
    try {
      const result = await importPatternDocument(activeSubjectId, file, importHint || undefined);
      setError(null);
      setEditor({ mode: "create", initial: result.draft, warnings: result.warnings, sourceFilename: result.source_filename });
    } catch (e) {
      setImportError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleSave = async (fields: ExamPatternFields) => {
    if (!activeSubjectId || editor.mode === "closed") return;
    setSaving(true);
    setError(null);
    try {
      if (editor.mode === "edit") {
        const updated = await updatePattern(editor.pattern.id, fields);
        setPatterns((ps) => ps.map((p) => (p.id === updated.id ? updated : p)));
      } else {
        const created = await createPattern(activeSubjectId, fields, editor.sourceFilename);
        setPatterns((ps) => [...ps, created]);
      }
      setEditor({ mode: "closed" });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save the pattern");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    setBusyId(id);
    try {
      await deletePattern(id);
      setPatterns((ps) => ps.filter((p) => p.id !== id));
    } finally {
      setBusyId(null);
    }
  };

  if (editor.mode !== "closed") {
    return (
      <PatternEditor
        key={editor.mode === "edit" ? editor.pattern.id : "new"}
        initial={editor.mode === "edit" ? editor.pattern : editor.initial}
        title={editor.mode === "edit" ? `Edit ${editor.pattern.name}` : editor.sourceFilename ? `New pattern from ${editor.sourceFilename}` : "New pattern"}
        warnings={editor.mode === "create" ? editor.warnings : undefined}
        topics={topics}
        saving={saving}
        error={error}
        onSave={handleSave}
        onCancel={() => setEditor({ mode: "closed" })}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-foreground">Exam Patterns</h1>
          <p className="text-sm text-muted-foreground">
            Question paper patterns for this subject's MSE and SEE. The Exam Builder assembles papers that satisfy them.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => openPreset("MSE")} disabled={!presets.length}>
            <Plus className="h-3.5 w-3.5" /> New MSE pattern
          </Button>
          <Button variant="outline" size="sm" onClick={() => openPreset("SEE")} disabled={!presets.length}>
            <Plus className="h-3.5 w-3.5" /> New SEE pattern
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
          <div className="min-w-0">
            <p className="flex items-center gap-1.5 text-sm font-medium text-foreground">
              <FileUp className="h-4 w-4 text-primary" /> Import from a document
            </p>
            <p className="text-xs text-muted-foreground">
              Upload your institution's pattern / scheme of examination (PDF, DOCX, PPTX, TXT). It's read into a draft you review before saving.
            </p>
            {importError && <p className="mt-1 text-xs text-destructive">{importError}</p>}
          </div>
          <div className="flex items-center gap-2">
            <Select value={importHint} onChange={(e) => setImportHint(e.target.value as PatternExamType | "")} className="w-36" aria-label="Exam type in document">
              <option value="">MSE or SEE</option>
              <option value="MSE">It's an MSE</option>
              <option value="SEE">It's an SEE</option>
            </Select>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.docx,.pptx,.txt"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && handleImport(e.target.files[0])}
            />
            <Button size="sm" onClick={() => fileRef.current?.click()} disabled={importing}>
              <FileUp className="h-3.5 w-3.5" /> {importing ? "Reading document..." : "Upload pattern"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {loading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
      ) : patterns.length === 0 ? (
        <EmptyState
          icon={LayoutTemplate}
          title="No patterns yet"
          description="Start from the MSE or SEE template, or import your institution's pattern document."
        />
      ) : (
        <div className="space-y-3">
          {patterns.map((p) => (
            <Card key={p.id}>
              <CardContent className="space-y-3 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={p.exam_type === "SEE" ? "accent" : "default"}>{p.exam_type}</Badge>
                      <p className="text-sm font-semibold text-foreground">{p.name}</p>
                    </div>
                    <p className="mt-1 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                      <span>
                        {p.sections.reduce((s, x) => s + x.num_questions, 0)} questions · {p.total_marks} marks
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" /> {p.duration_minutes} min
                      </span>
                      {p.source_filename && <span>Imported from {p.source_filename}</span>}
                    </p>
                    {p.description && <p className="mt-1 text-xs text-muted-foreground">{p.description}</p>}
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => onBuildExam(p.id)}>
                      <Sparkles className="h-3.5 w-3.5" /> Build exam
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => (setError(null), setEditor({ mode: "edit", pattern: p }))}>
                      <Pencil className="h-3.5 w-3.5" /> Edit
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-destructive hover:text-destructive"
                      onClick={() => handleDelete(p.id)}
                      disabled={busyId === p.id}
                      aria-label={`Delete ${p.name}`}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                  {p.sections.map((s) => (
                    <div key={s.name} className="rounded-lg border border-border bg-secondary/30 p-2.5">
                      <p className="text-xs font-medium text-foreground">
                        {s.name}: {s.num_questions} × {s.marks_per_question} marks
                      </p>
                      <p className="mt-0.5 text-[11px] text-muted-foreground">
                        {s.question_types.length ? s.question_types.map((t) => QUESTION_TYPE_LABELS[t]).join(", ") : "Any type"}
                        {" · "}
                        {s.bloom_levels.length ? s.bloom_levels.map((b) => BLOOM_LABELS[b]).join(", ") : "Any level"}
                      </p>
                    </div>
                  ))}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {p.bloom_distribution.map((b) => (
                    <Badge key={b.bloom_level} variant="outline">
                      {BLOOM_LABELS[b.bloom_level]} {b.percent}%
                    </Badge>
                  ))}
                  {p.difficulty_distribution.map((d) => (
                    <Badge key={d.difficulty} variant="secondary">
                      {d.difficulty} {d.percent}%
                    </Badge>
                  ))}
                  {p.units.map((u) => (
                    <Badge key={u.unit} variant="outline">
                      {u.name || `Unit ${u.unit}`} {u.percent}% · {u.topic_ids.length} topics
                    </Badge>
                  ))}
                  {p.co_requirements.map((c) => (
                    <Badge key={c.co_code} variant="outline">
                      {c.co_code} ≥ {c.min_questions}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
