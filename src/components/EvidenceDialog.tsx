import { useEffect, useState } from "react";
import { FileText, GitBranch, Info, Network } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { BLOOM_LABELS, QUESTION_TYPE_LABELS, SKILL_LABELS, fetchEvidence, type Evidence, type Question } from "@/lib/api";

/** "Where did this question come from?" - the material and knowledge-graph
 *  context behind a (generated) question. */
export function EvidenceDialog({
  subjectId,
  question,
  onClose,
}: {
  subjectId: string;
  question: Question | null;
  onClose: () => void;
}) {
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!question) return;
    setEvidence(null);
    setError(null);
    fetchEvidence(subjectId, question.id)
      .then(setEvidence)
      .catch((e) => setError(e instanceof Error ? e.message : "Couldn't load the evidence"));
  }, [subjectId, question]);

  return (
    <Dialog open={question !== null} onClose={onClose} title="Question source & evidence" description={question?.text}>
      {error ? (
        <p className="text-xs text-destructive">{error}</p>
      ) : !evidence ? (
        <div className="space-y-2">
          <Skeleton className="h-6 w-2/3" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : (
        <div className="space-y-4 text-xs">
          <div className="flex flex-wrap gap-1.5">
            <Badge variant="outline">{QUESTION_TYPE_LABELS[evidence.question_type]}</Badge>
            <Badge variant="accent">{BLOOM_LABELS[evidence.bloom_level]}</Badge>
            <Badge variant="outline">
              Difficulty: {evidence.difficulty}
              {evidence.difficulty_score != null && ` (${evidence.difficulty_score.toFixed(1)}/10)`}
            </Badge>
            <Badge variant="outline">{SKILL_LABELS[evidence.skill_category]}</Badge>
            {evidence.co_ids.map((c) => (
              <Badge key={c} variant="outline">
                {c}
              </Badge>
            ))}
          </div>

          <p className={evidence.recorded ? "flex items-start gap-1.5 text-muted-foreground" : "flex items-start gap-1.5 rounded-md bg-warning/[0.06] p-2 text-foreground"}>
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {evidence.note}
          </p>

          {evidence.requested_topic && (
            <p className="text-muted-foreground">
              Generated for topic <span className="font-medium text-foreground">{evidence.requested_topic}</span>
              {evidence.model && <> using {evidence.model}</>}
              {evidence.generated_at && <> on {new Date(evidence.generated_at).toLocaleString()}</>}.
            </p>
          )}

          <section>
            <p className="mb-1.5 flex items-center gap-1.5 font-semibold text-foreground">
              <FileText className="h-3.5 w-3.5 text-primary" /> {evidence.recorded ? "Course material the model was given" : "Closest course material"}
            </p>
            {evidence.chunks.length === 0 ? (
              <p className="text-muted-foreground">No indexed material found.</p>
            ) : (
              <ol className="space-y-2">
                {evidence.chunks.map((c, i) => (
                  <li key={i} className="rounded-lg border border-border p-2.5">
                    <p className="mb-1 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                      <span className="font-medium text-foreground">{c.source_document ?? "Unknown document"}</span>
                      {c.chunk_index != null && <span>passage {c.chunk_index + 1}</span>}
                      {c.relevance != null && <span>relevance {Math.round(c.relevance * 100)}%</span>}
                    </p>
                    <p className="whitespace-pre-wrap text-foreground">{c.excerpt}</p>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <section>
            <p className="mb-1.5 flex items-center gap-1.5 font-semibold text-foreground">
              <Network className="h-3.5 w-3.5 text-primary" /> Knowledge-graph context
            </p>
            {evidence.topics.length === 0 ? (
              <p className="text-muted-foreground">This question isn't tagged with any knowledge-graph topic.</p>
            ) : (
              <ul className="space-y-2">
                {evidence.topics.map((t) => (
                  <li key={t.id} className="rounded-lg border border-border p-2.5">
                    <p className="font-medium text-foreground">{t.name}</p>
                    {t.description && <p className="text-muted-foreground">{t.description}</p>}
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      Prerequisites: {t.prerequisites.join(", ") || "none"} · Leads to: {t.leads_to.join(", ") || "none"}
                      {t.course_outcomes.length > 0 && ` · Maps to: ${t.course_outcomes.join(", ")}`}
                    </p>
                  </li>
                ))}
              </ul>
            )}
            {evidence.graph_relations.length > 0 && (
              <div className="mt-2">
                <p className="mb-1 flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
                  <GitBranch className="h-3 w-3" /> Relations given to the model
                </p>
                <ul className="space-y-0.5 font-mono text-[11px] text-foreground">
                  {evidence.graph_relations.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        </div>
      )}
    </Dialog>
  );
}
