import { useEffect, useMemo, useState } from "react";
import { Search, Trash2, Library, ArrowRight, FileSearch } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { EvidenceDialog } from "@/components/EvidenceDialog";
import {
  BLOOM_LABELS,
  BLOOM_LEVELS,
  QUESTION_TYPE_LABELS,
  QUESTION_TYPE_ORDER,
  SKILL_LABELS,
  fetchQuestionUsage,
  deleteQuestion,
  difficultyBucket,
  effectiveSkill,
  fetchGraph,
  fetchQuestions,
  saveQuestion,
  topicNodes,
  type DifficultyBucket,
  type GraphNode,
  type BankUsage,
  type Question,
  type SkillCategory,
} from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { cn } from "@/lib/utils";

const difficultyVariant: Record<DifficultyBucket, "success" | "warning" | "destructive"> = {
  Easy: "success",
  Medium: "warning",
  Hard: "destructive",
};

export function BankPage({
  onSendToExam,
  initialSearch,
}: {
  onSendToExam: (questionIds: string[]) => void;
  initialSearch?: string;
}) {
  const { activeSubjectId } = useAuth();
  const [questions, setQuestions] = useState<Question[]>([]);
  const [topics, setTopics] = useState<GraphNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState(initialSearch ?? "");
  const [topicFilter, setTopicFilter] = useState("all");
  const [difficultyFilter, setDifficultyFilter] = useState("all");
  const [usageFilter, setUsageFilter] = useState("all");
  const [bloomFilter, setBloomFilter] = useState("all");
  const [skillFilter, setSkillFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [bankUsage, setBankUsage] = useState<BankUsage | null>(null);
  const [evidenceFor, setEvidenceFor] = useState<Question | null>(null);
  const [selected, setSelected] = useState<string[]>([]);

  useEffect(() => {
    if (initialSearch !== undefined) setSearch(initialSearch);
  }, [initialSearch]);

  useEffect(() => {
    if (!activeSubjectId) return;
    setLoading(true);
    setSelected([]);
    Promise.all([
      fetchQuestions(activeSubjectId).then(setQuestions),
      fetchGraph(activeSubjectId).then((g) => setTopics(topicNodes(g.nodes))),
      fetchQuestionUsage(activeSubjectId).then(setBankUsage).catch(() => setBankUsage(null)),
    ]).finally(() => setLoading(false));
  }, [activeSubjectId]);

  const topicName = useMemo(() => {
    const map = new Map(topics.map((t) => [t.id, t.name]));
    return (id: string) => map.get(id) ?? id;
  }, [topics]);

  const filtered = questions.filter((q) => {
    if (search && !q.text.toLowerCase().includes(search.toLowerCase())) return false;
    if (topicFilter !== "all" && !q.topic_ids.includes(topicFilter)) return false;
    if (difficultyFilter !== "all" && difficultyBucket(q.difficulty_score) !== difficultyFilter) return false;
    if (bloomFilter !== "all" && String(q.bloom_level) !== bloomFilter) return false;
    if (skillFilter !== "all" && effectiveSkill(q) !== skillFilter) return false;
    if (typeFilter !== "all" && q.question_type !== typeFilter) return false;
    const u = bankUsage?.usage[q.id];
    if (usageFilter === "never" && u && !u.never_used) return false;
    if (usageFilter === "recent" && !u?.recently_used) return false;
    if (usageFilter === "frequent" && !u?.frequently_used) return false;
    if (usageFilter === "not_recent" && u?.recently_used) return false;
    return true;
  });

  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const handleDelete = async (id: string) => {
    if (!activeSubjectId) return;
    await deleteQuestion(activeSubjectId, id);
    setQuestions((qs) => qs.filter((q) => q.id !== id));
    setSelected((s) => s.filter((x) => x !== id));
  };

  // Skill category is derived from type + Bloom's level; the teacher can pin
  // it when the default is wrong. "" = back to automatic.
  const handleSkillChange = async (q: Question, value: SkillCategory | "") => {
    if (!activeSubjectId) return;
    const updated = await saveQuestion(activeSubjectId, { ...q, skill_category: value || null });
    setQuestions((qs) => qs.map((x) => (x.id === q.id ? updated : x)));
  };

  const handleBulkDelete = async () => {
    if (!activeSubjectId) return;
    await Promise.all(selected.map((id) => deleteQuestion(activeSubjectId, id)));
    setQuestions((qs) => qs.filter((q) => !selected.includes(q.id)));
    setSelected([]);
  };

  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search questions..."
              className="pl-8"
            />
          </div>
          <div className="grid grid-cols-2 gap-2 sm:flex sm:w-auto">
            <Select value={topicFilter} onChange={(e) => setTopicFilter(e.target.value)} className="sm:w-44">
              <option value="all">All topics</option>
              {topics.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
            <Select value={difficultyFilter} onChange={(e) => setDifficultyFilter(e.target.value)} className="sm:w-36">
              <option value="all">All difficulty</option>
              <option value="Easy">Easy</option>
              <option value="Medium">Medium</option>
              <option value="Hard">Hard</option>
            </Select>
          </div>
        </CardContent>
        <CardContent className="grid grid-cols-2 gap-2 px-4 pb-4 pt-0 sm:grid-cols-4">
          <Select value={usageFilter} onChange={(e) => setUsageFilter(e.target.value)} aria-label="Usage filter">
            <option value="all">Any usage</option>
            <option value="never">Never used</option>
            <option value="recent">Used in the last {bankUsage?.thresholds.recent_days ?? 30} days</option>
            <option value="not_recent">Not used recently</option>
            <option value="frequent">Frequently used ({bankUsage?.thresholds.frequent_count ?? 3}+ exams)</option>
          </Select>
          <Select value={bloomFilter} onChange={(e) => setBloomFilter(e.target.value)} aria-label="Bloom filter">
            <option value="all">All Bloom's levels</option>
            {BLOOM_LEVELS.map((b) => (
              <option key={b} value={b}>
                {BLOOM_LABELS[b]}
              </option>
            ))}
          </Select>
          <Select value={skillFilter} onChange={(e) => setSkillFilter(e.target.value)} aria-label="Skill filter">
            <option value="all">All skills</option>
            {(Object.keys(SKILL_LABELS) as SkillCategory[]).map((s) => (
              <option key={s} value={s}>
                {SKILL_LABELS[s]}
              </option>
            ))}
          </Select>
          <Select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} aria-label="Question type filter">
            <option value="all">All question types</option>
            {QUESTION_TYPE_ORDER.map((t) => (
              <option key={t} value={t}>
                {QUESTION_TYPE_LABELS[t]}
              </option>
            ))}
          </Select>
        </CardContent>
      </Card>

      {selected.length > 0 && (
        <div className="flex items-center justify-between rounded-lg border border-primary/20 bg-accent px-4 py-2.5 text-sm animate-fade-in">
          <span className="font-medium text-accent-foreground">{selected.length} selected</span>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" onClick={() => onSendToExam(selected)}>
              Add to exam <ArrowRight className="h-3.5 w-3.5" />
            </Button>
            <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={handleBulkDelete}>
              <Trash2 className="h-3.5 w-3.5" /> Delete
            </Button>
          </div>
        </div>
      )}

      <Card>
        <CardContent className="p-0">
          {questions.length === 0 ? (
            <EmptyState
              icon={Library}
              title="No questions yet"
              description="Generate questions from your uploaded material to build your bank."
              className="m-6"
            />
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={Library}
              title="No questions found"
              description="Try adjusting your filters or generate new questions for this topic."
              className="m-6"
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-y border-border bg-secondary/40 text-left text-xs text-muted-foreground">
                    <th className="w-10 px-6 py-2.5"></th>
                    <th className="px-2 py-2.5 font-medium">Question</th>
                    <th className="px-4 py-2.5 font-medium">Topic</th>
                    <th className="px-4 py-2.5 font-medium">Difficulty</th>
                    <th className="px-4 py-2.5 font-medium">Marks</th>
                    <th className="px-4 py-2.5 font-medium">Bloom's</th>
                    <th className="px-4 py-2.5 font-medium">Skill</th>
                    <th className="px-4 py-2.5 font-medium">Usage</th>
                    <th className="px-4 py-2.5"></th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((q) => {
                    const bucket = difficultyBucket(q.difficulty_score);
                    return (
                      <tr
                        key={q.id}
                        className={cn(
                          "border-b border-border last:border-0 transition-colors duration-150 hover:bg-secondary/30",
                          selected.includes(q.id) && "bg-accent/50"
                        )}
                      >
                        <td className="px-6 py-3">
                          <Checkbox checked={selected.includes(q.id)} onCheckedChange={() => toggle(q.id)} />
                        </td>
                        <td className="max-w-md px-2 py-3">
                          <p className="line-clamp-2 text-foreground">{q.text}</p>
                          <p className="mt-0.5 text-[11px] text-muted-foreground">{QUESTION_TYPE_LABELS[q.question_type]}</p>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {q.topic_ids.length > 0 ? q.topic_ids.map(topicName).join(", ") : "—"}
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant={difficultyVariant[bucket]}>{bucket}</Badge>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">{q.marks}</td>
                        <td className="px-4 py-3">
                          <Badge variant="accent">{BLOOM_LABELS[q.bloom_level]}</Badge>
                        </td>
                        <td className="px-4 py-3">
                          <Select
                            value={q.skill_category ?? ""}
                            onChange={(e) => handleSkillChange(q, e.target.value as SkillCategory | "")}
                            className="h-7 w-36 text-xs"
                            aria-label="Skill category"
                            title="Used by Student Performance to split conceptual, reasoning, and coding scores"
                          >
                            <option value="">Auto ({SKILL_LABELS[effectiveSkill({ ...q, skill_category: null })]})</option>
                            <option value="conceptual">Conceptual</option>
                            <option value="reasoning">Reasoning</option>
                            <option value="coding">Coding</option>
                          </Select>
                        </td>
                        <td className="px-4 py-3 text-xs">
                          {(() => {
                            const u = bankUsage?.usage[q.id];
                            if (!u) return <span className="text-muted-foreground">—</span>;
                            if (u.never_used)
                              return (
                                <Badge variant="outline" title={u.exams.length ? `In draft: ${u.exams.map((e) => e.name).join(", ")}` : undefined}>
                                  Never used
                                </Badge>
                              );
                            return (
                              <div title={u.exams.map((e) => `${e.name} (${new Date(e.date).toLocaleDateString()})`).join("\n")}>
                                <p className="font-medium text-foreground">
                                  {u.times_used}× {u.frequently_used && <Badge variant="warning">frequent</Badge>}
                                </p>
                                <p className="text-[11px] text-muted-foreground">
                                  last {new Date(u.last_used_at!).toLocaleDateString()}
                                  {u.average_percent != null && ` · avg ${Math.round(u.average_percent)}% (${u.responses})`}
                                </p>
                              </div>
                            );
                          })()}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7"
                              onClick={() => setEvidenceFor(q)}
                              title="Where this question came from"
                              aria-label="Question source"
                            >
                              <FileSearch className="h-3.5 w-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 text-destructive hover:text-destructive"
                              onClick={() => handleDelete(q.id)}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        Showing {filtered.length} of {questions.length} questions
      </p>
      {activeSubjectId && <EvidenceDialog subjectId={activeSubjectId} question={evidenceFor} onClose={() => setEvidenceFor(null)} />}
    </div>
  );
}
