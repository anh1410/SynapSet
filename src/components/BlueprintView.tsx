import { AlertTriangle, CheckCircle2, Info } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { SERIES_ACCENT } from "@/components/charts";
import type { Blueprint, CoRow, DistributionRow } from "@/lib/api";
import { cn } from "@/lib/utils";

function Status({ ok, info }: { ok: boolean; info?: boolean }) {
  if (info) return <span className="text-[11px] text-muted-foreground">info</span>;
  return ok ? (
    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-success">
      <CheckCircle2 className="h-3 w-3" /> Satisfied
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-destructive">
      <AlertTriangle className="h-3 w-3" /> Not met
    </span>
  );
}

/** Target band drawn as a pale range, actual share as a tick (same idiom as the builder's compliance panel). */
function Bar({ actual, target, tolerance }: { actual: number; target: number | null; tolerance: number | null }) {
  const lo = target == null ? null : Math.max(0, target - (tolerance ?? 0));
  const hi = target == null ? null : Math.min(100, target + (tolerance ?? 0));
  return (
    <div className="relative h-2 w-full rounded-full bg-secondary">
      {lo != null && hi != null && <div className="absolute inset-y-0 rounded-full bg-primary/15" style={{ left: `${lo}%`, width: `${Math.max(hi - lo, 1)}%` }} />}
      <div className="absolute inset-y-0 left-0 rounded-full opacity-40" style={{ width: `${Math.min(actual, 100)}%`, backgroundColor: SERIES_ACCENT }} />
      <div className="absolute -top-0.5 h-3 w-1 rounded-full" style={{ left: `calc(${Math.min(actual, 100)}% - 2px)`, backgroundColor: SERIES_ACCENT }} />
    </div>
  );
}

function DistTable({ title, rows, tolerance }: { title: string; rows: DistributionRow[]; tolerance: number | null }) {
  if (rows.length === 0) return null;
  return (
    <div>
      <p className="mb-1.5 text-xs font-semibold text-foreground">{title}</p>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-[11px] text-muted-foreground">
            <th className="w-[34%] py-1 font-medium" />
            <th className="py-1 text-right font-medium">Target</th>
            <th className="py-1 text-right font-medium">Actual</th>
            <th className="w-[28%] px-3 py-1 font-medium" />
            <th className="py-1 text-right font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className="border-t border-border/60">
              <td className="py-1.5 pr-2 text-foreground">{r.label}</td>
              <td className="py-1.5 text-right tabular-nums text-muted-foreground">
                {r.target_percent == null ? "—" : `${r.target_percent}%${tolerance != null ? ` ±${tolerance}` : ""}`}
              </td>
              <td className="py-1.5 text-right font-medium tabular-nums text-foreground">
                {r.actual_percent}% <span className="font-normal text-muted-foreground">({r.actual_marks})</span>
              </td>
              <td className="px-3 py-1.5">
                <Bar actual={r.actual_percent} target={r.target_percent} tolerance={tolerance} />
              </td>
              <td className="py-1.5 text-right">
                <Status ok={r.within_tolerance} info={r.target_percent == null} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function coTarget(c: CoRow): string {
  const parts = [];
  if (c.min_questions) parts.push(`≥ ${c.min_questions} question${c.min_questions === 1 ? "" : "s"}`);
  if (c.min_percent) parts.push(`≥ ${c.min_percent}% of marks`);
  return parts.join(" and ");
}

export function BlueprintView({ blueprint, compact = false }: { blueprint: Blueprint; compact?: boolean }) {
  const b = blueprint;
  const tol = b.tolerance_percent;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {b.compliant === null ? (
          <Badge variant="outline">
            <Info className="h-3 w-3" /> Free-form quiz — no pattern targets
          </Badge>
        ) : b.compliant ? (
          <Badge variant="success">
            <CheckCircle2 className="h-3 w-3" /> Satisfies the {b.exam_type} pattern
          </Badge>
        ) : (
          <Badge variant="destructive">
            <AlertTriangle className="h-3 w-3" /> Doesn't satisfy the pattern ({b.issues.length} issue{b.issues.length === 1 ? "" : "s"})
          </Badge>
        )}
        <span className="text-muted-foreground">
          {b.question_count} questions · {b.total_marks} marks
          {b.target_marks != null && b.target_marks !== b.total_marks && (
            <span className="font-medium text-destructive"> (pattern needs {b.target_marks})</span>
          )}
          {b.pattern_name && ` · pattern "${b.pattern_name}"`}
        </span>
      </div>

      {b.issues.length > 0 && (
        <ul className="space-y-0.5 rounded-lg border border-destructive/20 bg-destructive/[0.03] p-2.5 text-[11px] text-foreground">
          {b.issues.map((i) => (
            <li key={i} className="flex items-start gap-1.5">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-destructive" /> {i}
            </li>
          ))}
        </ul>
      )}

      {b.sections.length > 0 && (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {b.sections.map((s) => {
            const done = s.filled === s.required;
            return (
              <div key={s.name} className={cn("rounded-lg border p-2.5", done ? "border-success/30 bg-success/[0.03]" : "border-destructive/30")}>
                <p className="flex items-center justify-between text-xs font-medium text-foreground">
                  {s.name} <Status ok={done} />
                </p>
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  {s.filled} / {s.required} × {s.marks_per_question} marks
                </p>
              </div>
            );
          })}
        </div>
      )}

      <div className={cn("grid gap-5", compact ? "grid-cols-1" : "grid-cols-1 xl:grid-cols-2")}>
        <DistTable title="Units" rows={b.units} tolerance={tol} />
        <DistTable title="Bloom's taxonomy (% of marks)" rows={b.bloom} tolerance={tol} />
        <DistTable title="Difficulty (% of marks)" rows={b.difficulty} tolerance={tol} />
        <DistTable title="Question types" rows={b.question_types} tolerance={tol} />
        <DistTable title="Conceptual / reasoning / coding" rows={b.skills} tolerance={tol} />
        <DistTable title="Topics" rows={b.topics} tolerance={tol} />
      </div>

      {b.course_outcomes.length > 0 && (
        <div>
          <p className="mb-1.5 text-xs font-semibold text-foreground">Course outcomes</p>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-[11px] text-muted-foreground">
                <th className="py-1 font-medium">CO</th>
                <th className="py-1 font-medium">Target</th>
                <th className="py-1 text-right font-medium">Actual</th>
                <th className="py-1 text-right font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {b.course_outcomes.map((c) => {
                const target = coTarget(c);
                return (
                  <tr key={c.co_code} className="border-t border-border/60">
                    <td className="py-1.5 font-medium text-foreground">{c.co_code}</td>
                    <td className="py-1.5 text-muted-foreground">{target || "—"}</td>
                    <td className="py-1.5 text-right tabular-nums text-foreground">
                      {c.actual_percent}% of marks · {c.actual} question{c.actual === 1 ? "" : "s"}
                    </td>
                    <td className="py-1.5 text-right">
                      <Status ok={c.met} info={!target} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
