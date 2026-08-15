import { useEffect, useState } from "react";
import { FileCheck2, FileText, FileType, Download, FileStack } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import {
  difficultyBucket,
  exportBlueprint,
  getBlueprint,
  listBlueprints,
  type DifficultyBucket,
  type PaperBlueprint,
  type Question,
} from "@/lib/api";
import type { Page } from "@/App";

export function ReviewExportPage({
  blueprintId,
  onNavigate,
  onSelectBlueprint,
}: {
  blueprintId: string | null;
  onNavigate: (p: Page) => void;
  onSelectBlueprint: (id: string) => void;
}) {
  const [tab, setTab] = useState<"preview" | "history">(blueprintId ? "preview" : "history");
  const [blueprint, setBlueprint] = useState<PaperBlueprint | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState<"pdf" | "docx" | null>(null);

  const [history, setHistory] = useState<PaperBlueprint[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);

  useEffect(() => {
    if (!blueprintId) return;
    setLoading(true);
    getBlueprint(blueprintId)
      .then(({ blueprint, questions }) => {
        setBlueprint(blueprint);
        setQuestions(questions);
        setTab("preview");
      })
      .finally(() => setLoading(false));
  }, [blueprintId]);

  const loadHistory = () => {
    setHistoryLoading(true);
    listBlueprints()
      .then(setHistory)
      .finally(() => setHistoryLoading(false));
  };

  useEffect(loadHistory, [blueprintId]);

  const handleExport = async (format: "pdf" | "docx") => {
    if (!blueprint) return;
    setExporting(format);
    try {
      await exportBlueprint(blueprint.id, blueprint.name, format);
      loadHistory();
    } finally {
      setExporting(null);
    }
  };

  const totalMarks = questions.reduce((s, q) => s + q.marks, 0);
  const topicsCovered = new Set(questions.flatMap((q) => q.topic_ids)).size;
  const buckets: Record<DifficultyBucket, number> = { Easy: 0, Medium: 0, Hard: 0 };
  questions.forEach((q) => (buckets[difficultyBucket(q.difficulty_score)] += 1));
  const pct = (n: number) => (questions.length ? Math.round((n / questions.length) * 100) : 0);

  return (
    <div className="space-y-4">
      <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <TabsList>
            <TabsTrigger value="preview">Paper Preview</TabsTrigger>
            <TabsTrigger value="history">Export History</TabsTrigger>
          </TabsList>

          {tab === "preview" && blueprint && (
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => handleExport("docx")} disabled={exporting !== null}>
                <FileType className="h-3.5 w-3.5" /> {exporting === "docx" ? "Exporting..." : "Export Word"}
              </Button>
              <Button size="sm" onClick={() => handleExport("pdf")} disabled={exporting !== null}>
                <Download className="h-3.5 w-3.5" /> {exporting === "pdf" ? "Exporting..." : "Export PDF"}
              </Button>
            </div>
          )}
        </div>

        <TabsContent value="preview" className="mt-4">
          {!blueprintId ? (
            <EmptyState
              icon={FileStack}
              title="No paper selected"
              description="Build a paper in the Exam Builder, or open one from Export History."
              action={
                <Button size="sm" onClick={() => onNavigate("exam")}>
                  Go to Exam Builder
                </Button>
              }
            />
          ) : loading ? (
            <Skeleton className="h-96 w-full" />
          ) : blueprint ? (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              <div className="space-y-4 lg:col-span-2">
                <Card>
                  <CardContent className="p-8">
                    <div className="border-b border-border pb-4 text-center">
                      <p className="text-xs uppercase tracking-widest text-muted-foreground">Examination Paper</p>
                      <h2 className="mt-1 text-lg font-semibold text-foreground">{blueprint.name}</h2>
                      <div className="mt-2 flex justify-center gap-4 text-xs text-muted-foreground">
                        <span>Total Marks: {totalMarks}</span>
                        {blueprint.duration_minutes != null && (
                          <>
                            <span>·</span>
                            <span>Duration: {blueprint.duration_minutes} min</span>
                          </>
                        )}
                      </div>
                    </div>

                    <div className="mt-6 space-y-5">
                      {questions.map((q, i) => (
                        <div key={q.id} className="flex items-start gap-3">
                          <span className="mt-0.5 text-sm font-medium text-foreground">Q{i + 1}.</span>
                          <div className="min-w-0 flex-1">
                            <p className="text-sm leading-relaxed text-foreground">{q.text}</p>
                            {q.question_type === "mcq" && q.options && (
                              <ul className="mt-1.5 space-y-0.5 text-xs text-muted-foreground">
                                {q.options.map((opt, oi) => (
                                  <li key={oi}>
                                    {String.fromCharCode(97 + oi)}) {opt}
                                  </li>
                                ))}
                              </ul>
                            )}
                          </div>
                          <span className="shrink-0 text-xs font-medium text-muted-foreground">[{q.marks}]</span>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              </div>

              <div className="space-y-4">
                <Card>
                  <CardHeader>
                    <div className="flex items-center gap-2">
                      <FileCheck2 className="h-4 w-4 text-primary" />
                      <CardTitle>Paper Summary</CardTitle>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {[
                      { label: "Total Questions", value: String(questions.length) },
                      { label: "Total Marks", value: String(totalMarks) },
                      { label: "Duration", value: blueprint.duration_minutes != null ? `${blueprint.duration_minutes} min` : "—" },
                      { label: "Topics Covered", value: String(topicsCovered) },
                      { label: "Status", value: blueprint.status === "exported" ? "Exported" : "Draft" },
                    ].map((row) => (
                      <div key={row.label} className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">{row.label}</span>
                        <span className="font-medium text-foreground">{row.value}</span>
                      </div>
                    ))}
                    {questions.length > 0 && (
                      <div className="border-t border-border pt-3">
                        <div className="flex gap-1.5">
                          <Badge variant="success">{pct(buckets.Easy)}% Easy</Badge>
                          <Badge variant="warning">{pct(buckets.Medium)}% Med</Badge>
                          <Badge variant="destructive">{pct(buckets.Hard)}% Hard</Badge>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            </div>
          ) : null}
        </TabsContent>

        <TabsContent value="history" className="mt-4">
          <Card>
            <CardContent className="p-0">
              {historyLoading ? (
                <div className="space-y-3 p-6">
                  {[1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-10 w-full" />
                  ))}
                </div>
              ) : history.length === 0 ? (
                <EmptyState
                  icon={FileText}
                  title="No papers yet"
                  description="Save a paper from the Exam Builder to see it here."
                  className="m-6"
                />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-y border-border bg-secondary/40 text-left text-xs text-muted-foreground">
                        <th className="px-6 py-2.5 font-medium">Paper Name</th>
                        <th className="px-4 py-2.5 font-medium">Marks</th>
                        <th className="px-4 py-2.5 font-medium">Duration</th>
                        <th className="px-4 py-2.5 font-medium">Questions</th>
                        <th className="px-4 py-2.5 font-medium">Status</th>
                        <th className="px-4 py-2.5 font-medium">Updated</th>
                        <th className="px-4 py-2.5"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {history.map((e) => (
                        <tr
                          key={e.id}
                          className="cursor-pointer border-b border-border last:border-0 transition-colors duration-150 hover:bg-secondary/30"
                          onClick={() => onSelectBlueprint(e.id)}
                        >
                          <td className="px-6 py-3">
                            <div className="flex items-center gap-2.5">
                              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary text-slate-500">
                                <FileText className="h-4 w-4" />
                              </div>
                              <span className="font-medium text-foreground">{e.name}</span>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-muted-foreground">{e.total_marks}</td>
                          <td className="px-4 py-3 text-muted-foreground">{e.duration_minutes ?? "—"} min</td>
                          <td className="px-4 py-3 text-muted-foreground">{e.question_ids.length}</td>
                          <td className="px-4 py-3">
                            <Badge variant={e.status === "exported" ? "success" : "secondary"}>
                              {e.status === "exported" ? "Exported" : "Draft"}
                            </Badge>
                          </td>
                          <td className="px-4 py-3 text-muted-foreground">{new Date(e.updated_at).toLocaleDateString()}</td>
                          <td className="px-4 py-3 text-right">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={(ev) => {
                                ev.stopPropagation();
                                exportBlueprint(e.id, e.name, "pdf").then(loadHistory);
                              }}
                            >
                              <Download className="h-3.5 w-3.5" /> Export
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
