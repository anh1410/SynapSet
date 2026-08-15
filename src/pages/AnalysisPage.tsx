import { useEffect, useMemo, useState } from "react";
import { Network, AlertTriangle, Info, Share2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tooltip } from "@/components/ui/tooltip";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { fetchGraph, type GraphEdge, type GraphNode } from "@/lib/api";
import { cn } from "@/lib/utils";

function computeLayout(nodes: GraphNode[]): Record<string, { x: number; y: number }> {
  const n = nodes.length;
  const positions: Record<string, { x: number; y: number }> = {};
  nodes.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / Math.max(n, 1) - Math.PI / 2;
    const radius = n <= 1 ? 0 : 38;
    positions[node.id] = { x: 50 + radius * Math.cos(angle), y: 50 + radius * Math.sin(angle) };
  });
  return positions;
}

export function AnalysisPage() {
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [loading, setLoading] = useState(true);
  const [hovered, setHovered] = useState<string | null>(null);

  useEffect(() => {
    fetchGraph()
      .then((g) => {
        setNodes(g.nodes);
        setEdges(g.edges);
      })
      .finally(() => setLoading(false));
  }, []);

  const positions = useMemo(() => computeLayout(nodes), [nodes]);
  const maxImportance = Math.max(...nodes.map((n) => n.importance_score), 0.0001);

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <Skeleton className="h-96 w-full lg:col-span-3" />
        <Skeleton className="h-96 w-full lg:col-span-2" />
      </div>
    );
  }

  if (nodes.length === 0) {
    return (
      <EmptyState
        icon={Network}
        title="No knowledge graph yet"
        description="Upload a syllabus or notes to extract topics and relationships."
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
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
                {edges.map((e, i) => {
                  const pa = positions[e.source];
                  const pb = positions[e.target];
                  if (!pa || !pb) return null;
                  const active = hovered === e.source || hovered === e.target;
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
              {nodes.map((t) => {
                const pos = positions[t.id];
                const size = 26 + (t.importance_score / maxImportance) * 24;
                return (
                  <div
                    key={t.id}
                    onMouseEnter={() => setHovered(t.id)}
                    onMouseLeave={() => setHovered(null)}
                    className="absolute -translate-x-1/2 -translate-y-1/2 cursor-pointer"
                    style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
                  >
                    <Tooltip label={`${t.name} — ${t.coverage_pct}% coverage, ${t.question_count} questions`}>
                      <div
                        style={{ width: size, height: size }}
                        className={cn(
                          "flex items-center justify-center rounded-full border-2 bg-white text-center text-[9px] font-semibold shadow-card transition-all duration-200 px-1",
                          t.neglected
                            ? "border-warning text-warning"
                            : hovered === t.id
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
              <Info className="h-3.5 w-3.5" /> Node size reflects topic importance (PageRank). Hover a node to trace its relationships.
            </p>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Coverage Breakdown</CardTitle>
            <CardDescription>Question bank coverage relative to the best-covered topic</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 max-h-[27rem] overflow-y-auto scrollbar-thin pr-1">
            {[...nodes]
              .sort((a, b) => a.coverage_pct - b.coverage_pct)
              .map((t) => (
                <div
                  key={t.id}
                  className={cn(
                    "rounded-lg border p-3 transition-all duration-200",
                    t.neglected ? "border-warning/30 bg-warning/5" : "border-border bg-white"
                  )}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      {t.neglected && <AlertTriangle className="h-3.5 w-3.5 text-warning" />}
                      <p className="text-sm font-medium text-foreground">{t.name}</p>
                    </div>
                    <div className="flex items-center gap-1 text-xs font-medium text-foreground">{t.coverage_pct}%</div>
                  </div>
                  <Progress value={t.coverage_pct} className="mt-2" barClassName={t.neglected ? "bg-warning" : "bg-primary"} />
                  <div className="mt-2 flex items-center gap-3 text-[11px] text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <Share2 className="h-3 w-3" /> {t.degree} related
                    </span>
                    <span>·</span>
                    <span>{t.question_count} questions</span>
                  </div>
                </div>
              ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Extracted Topics</CardTitle>
          <CardDescription>Structured breakdown from syllabus, notes, and past papers</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-y border-border bg-secondary/40 text-left text-xs text-muted-foreground">
                  <th className="px-6 py-2.5 font-medium">Topic</th>
                  <th className="px-4 py-2.5 font-medium">Related Topics</th>
                  <th className="px-4 py-2.5 font-medium">Questions</th>
                  <th className="px-4 py-2.5 font-medium">Coverage</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {nodes.map((t) => (
                  <tr key={t.id} className="border-b border-border last:border-0 transition-colors duration-150 hover:bg-secondary/30">
                    <td className="px-6 py-3 font-medium text-foreground">{t.name}</td>
                    <td className="px-4 py-3 text-muted-foreground">{t.degree}</td>
                    <td className="px-4 py-3 text-muted-foreground">{t.question_count}</td>
                    <td className="px-4 py-3 text-muted-foreground">{t.coverage_pct}%</td>
                    <td className="px-4 py-3">
                      <Badge variant={t.neglected ? "warning" : t.coverage_pct > 75 ? "success" : "secondary"}>
                        {t.neglected ? "Neglected" : t.coverage_pct > 75 ? "Well covered" : "Moderate"}
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
