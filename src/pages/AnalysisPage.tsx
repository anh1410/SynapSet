import { useState } from "react";
import { Network, TrendingUp, TrendingDown, Minus, AlertTriangle, Info } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tooltip } from "@/components/ui/tooltip";
import { topics } from "@/lib/mock-data";
import { cn } from "@/lib/utils";

const nodePositions = [
  { x: 50, y: 12 },
  { x: 20, y: 32 },
  { x: 80, y: 32 },
  { x: 12, y: 60 },
  { x: 50, y: 55 },
  { x: 88, y: 60 },
  { x: 30, y: 85 },
  { x: 70, y: 85 },
];

const edges = [
  [0, 1], [0, 2], [1, 3], [1, 4], [2, 4], [2, 5],
  [4, 6], [4, 7], [3, 6], [5, 7], [0, 4],
];

export function AnalysisPage() {
  const [hovered, setHovered] = useState<number | null>(null);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        {/* Knowledge graph visualization */}
        <Card className="lg:col-span-3">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Network className="h-4 w-4 text-primary" />
              <CardTitle>Knowledge Graph</CardTitle>
            </div>
            <CardDescription>Relationships between topics inferred from your materials</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="relative h-96 w-full overflow-hidden rounded-lg border border-border bg-grid bg-secondary/20">
              <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none">
                {edges.map(([a, b], i) => {
                  const pa = nodePositions[a];
                  const pb = nodePositions[b];
                  const active = hovered === a || hovered === b;
                  return (
                    <line
                      key={i}
                      x1={pa.x}
                      y1={pa.y}
                      x2={pb.x}
                      y2={pb.y}
                      stroke={active ? "hsl(245 58% 51%)" : "hsl(220 16% 85%)"}
                      strokeWidth={active ? 0.5 : 0.3}
                      vectorEffect="non-scaling-stroke"
                      className="transition-all duration-200"
                    />
                  );
                })}
              </svg>
              {topics.map((t, i) => {
                const pos = nodePositions[i];
                const size = 34 + t.coverage * 0.3;
                const low = t.coverage < 40;
                return (
                  <div
                    key={t.id}
                    onMouseEnter={() => setHovered(i)}
                    onMouseLeave={() => setHovered(null)}
                    className="absolute -translate-x-1/2 -translate-y-1/2 cursor-pointer"
                    style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
                  >
                    <Tooltip label={`${t.name} — ${t.coverage}% coverage, ${t.questions} questions`}>
                      <div
                        style={{ width: size, height: size }}
                        className={cn(
                          "flex items-center justify-center rounded-full border-2 bg-white text-center text-[9px] font-semibold shadow-card transition-all duration-200",
                          low
                            ? "border-warning text-warning"
                            : hovered === i
                            ? "border-primary text-primary scale-110"
                            : "border-primary/40 text-primary/80"
                        )}
                      >
                        {t.name.split(" ")[0]}
                      </div>
                    </Tooltip>
                  </div>
                );
              })}
            </div>
            <p className="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
              <Info className="h-3.5 w-3.5" /> Node size reflects topic coverage. Hover a node to trace its relationships.
            </p>
          </CardContent>
        </Card>

        {/* Topic list with coverage */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Coverage Breakdown</CardTitle>
            <CardDescription>Frequency of topic appearance across uploaded content</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 max-h-[27rem] overflow-y-auto scrollbar-thin pr-1">
            {[...topics]
              .sort((a, b) => a.coverage - b.coverage)
              .map((t) => (
                <div
                  key={t.id}
                  className={cn(
                    "rounded-lg border p-3 transition-all duration-200",
                    t.coverage < 40 ? "border-warning/30 bg-warning/5" : "border-border bg-white"
                  )}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      {t.coverage < 40 && <AlertTriangle className="h-3.5 w-3.5 text-warning" />}
                      <p className="text-sm font-medium text-foreground">{t.name}</p>
                    </div>
                    <div className="flex items-center gap-1 text-xs font-medium text-foreground">
                      {t.coverage}%
                      {t.trend === "up" && <TrendingUp className="h-3.5 w-3.5 text-success" />}
                      {t.trend === "down" && <TrendingDown className="h-3.5 w-3.5 text-destructive" />}
                      {t.trend === "flat" && <Minus className="h-3.5 w-3.5 text-muted-foreground" />}
                    </div>
                  </div>
                  <Progress value={t.coverage} className="mt-2" barClassName={t.coverage < 40 ? "bg-warning" : "bg-primary"} />
                  <div className="mt-2 flex items-center gap-3 text-[11px] text-muted-foreground">
                    <span>{t.subtopics} subtopics</span>
                    <span>·</span>
                    <span>{t.questions} questions</span>
                  </div>
                </div>
              ))}
          </CardContent>
        </Card>
      </div>

      {/* Subtopics table */}
      <Card>
        <CardHeader>
          <CardTitle>Extracted Topics & Subtopics</CardTitle>
          <CardDescription>Structured breakdown from syllabus, notes, and past papers</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-y border-border bg-secondary/40 text-left text-xs text-muted-foreground">
                  <th className="px-6 py-2.5 font-medium">Topic</th>
                  <th className="px-4 py-2.5 font-medium">Subtopics</th>
                  <th className="px-4 py-2.5 font-medium">Questions Generated</th>
                  <th className="px-4 py-2.5 font-medium">Coverage</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {topics.map((t) => (
                  <tr key={t.id} className="border-b border-border last:border-0 transition-colors duration-150 hover:bg-secondary/30">
                    <td className="px-6 py-3 font-medium text-foreground">{t.name}</td>
                    <td className="px-4 py-3 text-muted-foreground">{t.subtopics}</td>
                    <td className="px-4 py-3 text-muted-foreground">{t.questions}</td>
                    <td className="px-4 py-3 text-muted-foreground">{t.coverage}%</td>
                    <td className="px-4 py-3">
                      <Badge variant={t.coverage < 40 ? "warning" : t.coverage > 75 ? "success" : "secondary"}>
                        {t.coverage < 40 ? "Neglected" : t.coverage > 75 ? "Well covered" : "Moderate"}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
