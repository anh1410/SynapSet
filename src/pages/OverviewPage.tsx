import {
  FileText,
  Sparkles,
  Network,
  AlertTriangle,
  ArrowUpRight,
  TrendingUp,
  TrendingDown,
  Minus,
  UploadCloud,
  ArrowRight,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { topics, neglectedTopics, recentActivity, uploadedDocuments } from "@/lib/mock-data";
import type { Page } from "@/App";

const stats = [
  { label: "Documents Uploaded", value: "18", change: "+3 this week", icon: FileText },
  { label: "Topics Extracted", value: "142", change: "+12 this week", icon: Network },
  { label: "Questions in Bank", value: "247", change: "+34 this week", icon: Sparkles },
  { label: "Neglected Topics", value: String(neglectedTopics.length), change: "Needs attention", icon: AlertTriangle, warn: true },
];

const activityIcon = {
  generate: Sparkles,
  upload: UploadCloud,
  export: FileText,
  flag: AlertTriangle,
  create: FileText,
};

export function OverviewPage({ onNavigate }: { onNavigate: (p: Page) => void }) {
  return (
    <div className="space-y-6">
      {/* Stat cards */}
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
                <p className={`mt-1 text-xs ${s.warn ? "text-warning" : "text-success"}`}>{s.change}</p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Bento grid */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Knowledge graph coverage - spans 2 */}
        <Card className="lg:col-span-2">
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle>Topic Coverage</CardTitle>
              <CardDescription>How frequently each topic appears across your materials</CardDescription>
            </div>
            <Button variant="ghost" size="sm" onClick={() => onNavigate("analysis")}>
              View graph <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            {topics.slice(0, 6).map((t) => (
              <div key={t.id} className="flex items-center gap-4">
                <div className="w-40 shrink-0 truncate text-sm font-medium text-foreground">{t.name}</div>
                <Progress
                  value={t.coverage}
                  className="flex-1"
                  barClassName={t.coverage < 40 ? "bg-warning" : "bg-primary"}
                />
                <div className="flex w-20 shrink-0 items-center justify-end gap-1.5 text-xs">
                  <span className="font-medium text-foreground">{t.coverage}%</span>
                  {t.trend === "up" && <TrendingUp className="h-3.5 w-3.5 text-success" />}
                  {t.trend === "down" && <TrendingDown className="h-3.5 w-3.5 text-destructive" />}
                  {t.trend === "flat" && <Minus className="h-3.5 w-3.5 text-muted-foreground" />}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Neglected topics */}
        <Card className="border-warning/30 bg-warning/[0.03]">
          <CardHeader>
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-warning" />
              <CardTitle>Neglected Topics</CardTitle>
            </div>
            <CardDescription>Low coverage — consider generating questions here</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {neglectedTopics.map((t) => (
              <div
                key={t.id}
                className="flex items-center justify-between rounded-lg border border-border bg-white p-3 transition-all duration-200 hover:border-warning/40"
              >
                <div>
                  <p className="text-sm font-medium text-foreground">{t.name}</p>
                  <p className="text-xs text-muted-foreground">{t.questions} questions · {t.subtopics} subtopics</p>
                </div>
                <Badge variant="warning">{t.coverage}%</Badge>
              </div>
            ))}
            <Button variant="secondary" size="sm" className="w-full" onClick={() => onNavigate("generate")}>
              Generate questions <ArrowUpRight className="h-3.5 w-3.5" />
            </Button>
          </CardContent>
        </Card>

        {/* Recent activity */}
        <Card>
          <CardHeader>
            <CardTitle>Recent Activity</CardTitle>
            <CardDescription>Latest actions across your workspace</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {recentActivity.map((a) => {
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
            })}
          </CardContent>
        </Card>

        {/* Recent documents */}
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle>Recent Uploads</CardTitle>
            <Button variant="ghost" size="sm" onClick={() => onNavigate("upload")}>
              Upload <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {uploadedDocuments.slice(0, 4).map((d) => (
              <div key={d.id} className="flex items-center gap-3">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-secondary text-slate-500">
                  <FileText className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-foreground">{d.name}</p>
                  <p className="text-[11px] text-muted-foreground">{d.type} · {d.size}</p>
                </div>
                <Badge
                  variant={d.status === "Processed" ? "success" : d.status === "Processing" ? "warning" : "destructive"}
                >
                  {d.status}
                </Badge>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Quick action / CTA card */}
        <Card className="lg:col-span-1 bg-gradient-to-br from-primary to-primary/80 text-primary-foreground border-0">
          <CardContent className="flex h-full flex-col justify-between p-6">
            <div>
              <Sparkles className="h-5 w-5 opacity-90" />
              <p className="mt-3 text-sm font-semibold">Ready to build your next paper?</p>
              <p className="mt-1 text-xs text-primary-foreground/80">
                Set your constraints and let the system assemble a balanced exam automatically.
              </p>
            </div>
            <Button
              variant="secondary"
              size="sm"
              className="mt-4 w-fit bg-white text-primary hover:bg-white/90"
              onClick={() => onNavigate("exam")}
            >
              Create exam paper <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
