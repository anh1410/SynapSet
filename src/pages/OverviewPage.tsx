import { useEffect, useState } from "react";
import {
  FileText,
  Sparkles,
  Network,
  AlertTriangle,
  ArrowUpRight,
  UploadCloud,
  ArrowRight,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import {
  fetchGraph,
  fetchDocuments,
  fetchQuestions,
  listExams,
  timeAgo,
  type GraphNode,
  type UploadedDocument,
  type Exam,
} from "@/lib/api";
import type { Page } from "@/App";

type Activity = {
  id: string;
  label: string;
  time: string;
  type: "upload" | "create";
  ts: number;
};

export function OverviewPage({ onNavigate }: { onNavigate: (p: Page) => void }) {
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [documents, setDocuments] = useState<UploadedDocument[]>([]);
  const [questionCount, setQuestionCount] = useState(0);
  const [exams, setExams] = useState<Exam[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetchGraph().then((g) => setNodes(g.nodes)),
      fetchDocuments().then(setDocuments),
      fetchQuestions().then((qs) => setQuestionCount(qs.length)),
      listExams().then(setExams),
    ])
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-28 w-full" />
        ))}
        <Skeleton className="h-80 w-full lg:col-span-2" />
        <Skeleton className="h-80 w-full" />
        <Skeleton className="h-80 w-full" />
      </div>
    );
  }

  const neglected = nodes.filter((n) => n.neglected);
  const topicsByImportance = [...nodes].sort((a, b) => b.importance_score - a.importance_score);

  const stats = [
    { label: "Documents Uploaded", value: String(documents.length), icon: FileText },
    { label: "Topics Extracted", value: String(nodes.length), icon: Network },
    { label: "Questions in Bank", value: String(questionCount), icon: Sparkles },
    { label: "Neglected Topics", value: String(neglected.length), icon: AlertTriangle, warn: true },
  ];

  const activity: Activity[] = [
    ...documents.slice(0, 5).map(
      (d): Activity => ({
        id: `doc-${d.id}`,
        label: `Uploaded ${d.filename}`,
        time: timeAgo(d.uploaded_at),
        type: "upload",
        ts: new Date(d.uploaded_at).getTime(),
      })
    ),
    ...exams.slice(0, 5).map(
      (e): Activity => ({
        id: `exam-${e.id}`,
        label: e.bucket === "closed" ? `Closed "${e.name}"` : `Created quiz "${e.name}"`,
        time: timeAgo(e.updated_at),
        type: "create",
        ts: new Date(e.updated_at).getTime(),
      })
    ),
  ]
    .sort((a, b) => b.ts - a.ts)
    .slice(0, 5);

  const activityIcon = { upload: UploadCloud, create: FileText };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <Card key={s.label} className="hover:shadow-md hover:-translate-y-0.5">
              <CardContent className="p-5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-muted-foreground">{s.label}</span>
                  <div
                    className={`flex h-8 w-8 items-center justify-center rounded-lg ${
                      s.warn ? "bg-warning/10 text-warning" : "bg-primary/10 text-primary"
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                  </div>
                </div>
                <p className="mt-3 text-2xl font-semibold tracking-tight text-foreground">{s.value}</p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle>Topic Coverage</CardTitle>
              <CardDescription>Share of question bank drawn from each topic</CardDescription>
            </div>
            <Button variant="ghost" size="sm" onClick={() => onNavigate("analysis")}>
              View graph <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            {topicsByImportance.length === 0 ? (
              <p className="text-sm text-muted-foreground">Upload material to build your knowledge graph.</p>
            ) : (
              topicsByImportance.slice(0, 6).map((t) => (
                <div key={t.id} className="flex items-center gap-4">
                  <div className="w-40 shrink-0 truncate text-sm font-medium text-foreground">{t.name}</div>
                  <Progress value={t.coverage_pct} className="flex-1" barClassName={t.neglected ? "bg-warning" : "bg-primary"} />
                  <div className="flex w-16 shrink-0 items-center justify-end gap-1.5 text-xs">
                    <span className="font-medium text-foreground">{t.coverage_pct}%</span>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card className="border-warning/30 bg-warning/[0.03]">
          <CardHeader>
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-warning" />
              <CardTitle>Neglected Topics</CardTitle>
            </div>
            <CardDescription>Low question coverage — consider generating here</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {neglected.length === 0 ? (
              <p className="text-sm text-muted-foreground">No neglected topics right now.</p>
            ) : (
              neglected.slice(0, 6).map((t) => (
                <div
                  key={t.id}
                  className="flex items-center justify-between rounded-lg border border-border bg-white p-3 transition-all duration-200 hover:border-warning/40"
                >
                  <div>
                    <p className="text-sm font-medium text-foreground">{t.name}</p>
                    <p className="text-xs text-muted-foreground">{t.question_count} questions · {t.degree} related topics</p>
                  </div>
                  <Badge variant="warning">{t.coverage_pct}%</Badge>
                </div>
              ))
            )}
            <Button variant="secondary" size="sm" className="w-full" onClick={() => onNavigate("exam")}>
              Generate questions <ArrowUpRight className="h-3.5 w-3.5" />
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent Activity</CardTitle>
            <CardDescription>Latest actions across your workspace</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {activity.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nothing yet — upload a document to get started.</p>
            ) : (
              activity.map((a) => {
                const Icon = activityIcon[a.type];
                return (
                  <div key={a.id} className="flex items-start gap-3">
                    <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-secondary text-slate-500">
                      <Icon className="h-3.5 w-3.5" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm text-foreground">{a.label}</p>
                      <p className="text-xs text-muted-foreground">{a.time}</p>
                    </div>
                  </div>
                );
              })
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle>Recent Uploads</CardTitle>
            <Button variant="ghost" size="sm" onClick={() => onNavigate("upload")}>
              Upload <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {documents.length === 0 ? (
              <p className="text-sm text-muted-foreground">No documents uploaded yet.</p>
            ) : (
              documents.slice(0, 4).map((d) => (
                <div key={d.id} className="flex items-center gap-3">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-secondary text-slate-500">
                    <FileText className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium text-foreground">{d.filename}</p>
                    <p className="text-[11px] text-muted-foreground">{d.category} · {timeAgo(d.uploaded_at)}</p>
                  </div>
                  <Badge variant={d.status === "processed" ? "success" : d.status === "processing" ? "warning" : "destructive"}>
                    {d.status}
                  </Badge>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-1 bg-gradient-to-br from-primary to-primary/80 text-primary-foreground border-0">
          <CardContent className="flex h-full flex-col justify-between p-6">
            <div>
              <Sparkles className="h-5 w-5 opacity-90" />
              <p className="mt-3 text-sm font-semibold">Ready to build your next quiz?</p>
              <p className="mt-1 text-xs text-primary-foreground/80">
                Add questions, set a difficulty and Bloom's level for each, then schedule it to go live.
              </p>
            </div>
            <Button
              variant="secondary"
              size="sm"
              className="mt-4 w-fit bg-white text-primary hover:bg-white/90"
              onClick={() => onNavigate("exam")}
            >
              Build a quiz <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
