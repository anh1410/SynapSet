import { AlertTriangle, CheckCircle2, LayoutTemplate } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { ComplianceReport, DistributionRow, ExamPattern } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Target vs actual for one distribution: the tolerance band is drawn as a
 *  pale range on the track, the actual share as a tick, so "inside the band"
 *  reads at a glance; the ✓ / ! icon + numbers carry it without colour. */
function DistributionBars({ title, rows, tolerance }: { title: string; rows: DistributionRow[]; tolerance: number }) {
  if (rows.length === 0) return null;
  return (
    <div className="space-y-1.5">
      <p className="text-[11px] font-semibold text-foreground">{title}</p>
      {rows.map((r) => {
        const lo = r.target_percent == null ? null : Math.max(0, r.target_percent - tolerance);
        const hi = r.target_percent == null ? null : Math.min(100, r.target_percent + tolerance);
        return (
          <div key={r.key} className="grid grid-cols-[88px_1fr_96px] items-center gap-2 text-[11px]">
            <span className="truncate text-muted-foreground">{r.label}</span>
            <div className="relative h-2 rounded-full bg-secondary">
              {lo != null && hi != null && (
                <div className="absolute inset-y-0 rounded-full bg-primary/15" style={{ left: `${lo}%`, width: `${hi - lo}%` }} />
              )}
              <div
                className="absolute -top-0.5 h-3 w-1 rounded-full bg-primary"
                style={{ left: `calc(${Math.min(r.actual_percent, 100)}% - 2px)` }}
              />
            </div>
            <span className="flex items-center justify-end gap-1 tabular-nums text-foreground">
              {r.actual_percent}%{r.target_percent != null && <span className="text-muted-foreground">/{r.target_percent}%</span>}
              {r.within_tolerance ? (
                <CheckCircle2 className="h-3 w-3 text-success" aria-label="within tolerance" />
              ) : (
                <AlertTriangle className="h-3 w-3 text-warning" aria-label="outside tolerance" />
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function PatternCompliancePanel({ pattern, report }: { pattern: ExamPattern; report: ComplianceReport }) {
  return (
    <Card className={cn(report.compliant ? "border-success/30" : "border-warning/30")}>
      <CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
        <div>
          <div className="flex items-center gap-2">
            <LayoutTemplate className="h-4 w-4 text-primary" />
            <CardTitle>
              {pattern.exam_type} pattern: {pattern.name}
            </CardTitle>
          </div>
          <CardDescription className="mt-1">
            {report.actual_marks} / {report.target_marks} marks · {report.topics_covered} topic{report.topics_covered === 1 ? "" : "s"} covered
          </CardDescription>
        </div>
        {report.compliant ? (
          <Badge variant="success">
            <CheckCircle2 className="h-3 w-3" /> Matches pattern
          </Badge>
        ) : (
          <Badge variant="warning">
            <AlertTriangle className="h-3 w-3" /> {report.issues.length} issue{report.issues.length === 1 ? "" : "s"}
          </Badge>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {report.sections.map((s) => {
            const done = s.filled === s.required;
            return (
              <div key={s.name} className={cn("rounded-lg border p-2.5", done ? "border-success/30 bg-success/[0.03]" : "border-border")}>
                <p className="flex items-center justify-between text-xs font-medium text-foreground">
                  {s.name}
                  {done ? <CheckCircle2 className="h-3.5 w-3.5 text-success" /> : <span className="text-[11px] text-muted-foreground">{s.required - s.filled} to go</span>}
                </p>
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  {s.filled} / {s.required} × {s.marks_per_question} marks
                </p>
              </div>
            );
          })}
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <DistributionBars title="Bloom's levels (% of marks)" rows={report.bloom} tolerance={pattern.tolerance_percent} />
          <DistributionBars title="Difficulty (% of marks)" rows={report.difficulty} tolerance={pattern.tolerance_percent} />
          <DistributionBars title="Units (% of marks)" rows={report.units} tolerance={pattern.tolerance_percent} />
          {report.course_outcomes.length > 0 && (
            <div className="space-y-1">
              <p className="text-[11px] font-semibold text-foreground">Course outcomes</p>
              <div className="flex flex-wrap gap-1.5">
                {report.course_outcomes.map((c) => (
                  <Badge key={c.co_code} variant={c.met ? "success" : "warning"}>
                    {c.met ? <CheckCircle2 className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
                    {c.co_code} {c.actual}/{c.min_questions}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>

        {report.issues.length > 0 && (
          <ul className="list-disc space-y-0.5 pl-5 text-[11px] text-muted-foreground">
            {report.issues.map((i) => (
              <li key={i}>{i}</li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
