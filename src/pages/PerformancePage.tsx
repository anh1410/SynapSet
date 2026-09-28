import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Brain,
  CheckCircle2,
  CircleDashed,
  ClipboardCheck,
  Code2,
  GraduationCap,
  Lightbulb,
  Network,
  Percent,
  ShieldAlert,
  Sigma,
  TrendingDown,
  TrendingUp,
  Trophy,
  Users,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { EmptyState } from "@/components/ui/empty-state";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  BandBadge,
  ChartCard,
  ColumnChart,
  DataTable,
  PercentBars,
  SERIES_ACCENT,
  SERIES_CONTEXT,
  StatTile,
  TrendChart,
  fmtPct,
  type BarRow,
} from "@/components/charts";
import {
  ASSESSMENT_TYPE_LABELS,
  QUESTION_TYPE_LABELS,
  BLOOM_LABELS,
  fetchAssessmentAnalytics,
  fetchClassOverview,
  fetchTopicRisk,
  type AssessmentAnalytics,
  type BloomLevel,
  type TopicRisk,
  fetchStudentDetail,
  type AssessmentType,
  type BreakdownRow,
  type Breakdowns,
  type ClassOverview,
  type QuestionType,
  type ScoreStat,
  type SkillCategory,
  type StudentDetail,
} from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { cn } from "@/lib/utils";

const skillIcon: Record<SkillCategory, typeof Brain> = { conceptual: Lightbulb, reasoning: Brain, coding: Code2 };
const skillTitle: Record<SkillCategory, string> = {
  conceptual: "Conceptual understanding",
  reasoning: "Reasoning & analysis",
  coding: "Coding",
};
const skillHelp: Record<SkillCategory, string> = {
  conceptual: "Remember / Understand-level questions",
  reasoning: "Apply, Analyze, Evaluate, Create",
  coding: "Fix-the-code questions, run against test cases",
};

function scoreDetail(s: ScoreStat): string {
  const parts = [`${s.awarded} / ${s.max} marks`, `${s.answers} graded answer${s.answers === 1 ? "" : "s"}`];
  if (s.pending) parts.push(`${s.pending} pending`);
  return parts.join(" · ");
}

function toBars(rows: BreakdownRow[]): BarRow[] {
  return rows.map((r) => ({ key: r.key, label: r.label, percent: r.score.percent, band: r.band, detail: scoreDetail(r.score) }));
}

/** Question-type rows use the same labels as the rest of the app. */
function withTypeLabels(rows: BreakdownRow[]): BreakdownRow[] {
  return rows.map((r) => ({ ...r, label: QUESTION_TYPE_LABELS[r.key as QuestionType] ?? r.label }));
}

function breakdownTable(rows: BreakdownRow[], first: string) {
  return (
    <DataTable
      headers={[first, "Marks", "Answers", "Pending", "Score"]}
      rows={rows.map((r) => [r.label, `${r.score.awarded} / ${r.score.max}`, r.score.answers, r.score.pending, fmtPct(r.score.percent, 1)])}
    />
  );
}

// ---------- shared panels (class + student) ----------

function SkillCards({ b }: { b: Breakdowns }) {
  const skills: SkillCategory[] = ["conceptual", "reasoning", "coding"];
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      {skills.map((skill) => {
        const row = b.skills.find((s) => s.skill === skill);
        const Icon = skillIcon[skill];
        return (
          <Card key={skill}>
            <CardContent className="space-y-2 p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                    <Icon className="h-3.5 w-3.5 text-primary" /> {row?.label ?? skillTitle[skill]}
                  </p>
                  <p className="text-[11px] text-muted-foreground">{skillHelp[skill]}</p>
                </div>
                {row && <BandBadge band={row.band} />}
              </div>
              {row ? (
                <>
                  <p className="text-2xl font-semibold text-foreground">{fmtPct(row.score.percent)}</p>
                  <Progress value={row.score.percent ?? 0} className="h-2" barClassName="bg-primary" />
                  <p className="text-[11px] text-muted-foreground">{scoreDetail(row.score)}</p>
                  {skill === "coding" && b.coding_tests && (
                    <p className="text-[11px] text-muted-foreground">
                      Test cases passed: <span className="font-medium text-foreground">{b.coding_tests.passed} / {b.coding_tests.total}</span> (
                      {fmtPct(b.coding_tests.percent)})
                    </p>
                  )}
                </>
              ) : (
                <p className="py-3 text-xs text-muted-foreground">No {skill} questions in these assessments yet.</p>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

function StrengthsWeaknesses({ b, who }: { b: Breakdowns; who: string }) {
  const list = (rows: BreakdownRow[], empty: string) =>
    rows.length === 0 ? (
      <p className="text-xs text-muted-foreground">{empty}</p>
    ) : (
      <ul className="space-y-1.5">
        {rows.map((r) => (
          <li key={r.key} className="flex items-center justify-between gap-2 text-xs">
            <span className="truncate text-foreground">{r.label}</span>
            <span className="shrink-0 font-medium tabular-nums text-foreground">{fmtPct(r.score.percent)}</span>
          </li>
        ))}
      </ul>
    );
  return (
    <Card>
      <CardHeader>
        <CardTitle>Strengths & weaknesses</CardTitle>
        <CardDescription>
          Topics where {who} scores ≥ 75% or &lt; 50% (at least 2 graded answers each)
        </CardDescription>
      </CardHeader>
      <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-success">
            <TrendingUp className="h-3.5 w-3.5" /> Strengths
          </p>
          {list(b.strengths, "None yet.")}
        </div>
        <div>
          <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-destructive">
            <TrendingDown className="h-3.5 w-3.5" /> Needs attention
          </p>
          {list(b.weaknesses, "None - no topic below 50%.")}
        </div>
      </CardContent>
    </Card>
  );
}

function BreakdownGrid({ b, who }: { b: Breakdowns; who: string }) {
  return (
    <>
      <SkillCards b={b} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard
          title="Bloom's Taxonomy performance"
          description="Score on questions at each cognitive level"
          icon={Brain}
          table={breakdownTable(b.bloom, "Bloom's level")}
          empty={b.bloom.length ? null : "No graded answers yet."}
        >
          <PercentBars rows={toBars(b.bloom)} />
        </ChartCard>
        <ChartCard
          title="Topic performance"
          description="Knowledge-graph topics, highest score first"
          icon={Network}
          table={breakdownTable(b.topics, "Topic")}
          empty={b.topics.length ? null : "Questions in these assessments aren't tagged with topics."}
        >
          <div className="max-h-80 overflow-y-auto pr-1 scrollbar-thin">
            <PercentBars rows={toBars(b.topics)} />
          </div>
        </ChartCard>
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <StrengthsWeaknesses b={b} who={who} />
        <ChartCard
          title="By question type"
          icon={ClipboardCheck}
          table={breakdownTable(withTypeLabels(b.question_types), "Type")}
          empty={b.question_types.length ? null : "No answers yet."}
        >
          <PercentBars rows={toBars(withTypeLabels(b.question_types))} showBands={false} />
        </ChartCard>
        <ChartCard
          title="By difficulty"
          description="Difficulty scored when each question was generated"
          icon={Sigma}
          table={breakdownTable(b.difficulty, "Difficulty")}
          empty={b.difficulty.length ? null : "No answers yet."}
        >
          <PercentBars rows={toBars(b.difficulty)} showBands={false} />
        </ChartCard>
      </div>
    </>
  );
}

// ---------- weak-topic detection ----------

const coverageLabel = { good: "Good", low: "Low", none: "No questions" } as const;

function TopicRiskCard({ risk }: { risk: TopicRisk }) {
  const perfCell = (r: TopicRisk["rows"][number]) => {
    if (r.performance === "insufficient")
      return (
        <span className="inline-flex items-center gap-1 text-muted-foreground">
          <CircleDashed className="h-3 w-3" /> {r.percent == null ? "No answers" : `${fmtPct(r.percent)} · too few answers`}
        </span>
      );
    return (
      <span className={cn("inline-flex items-center gap-1 font-medium", r.performance === "at_risk" ? "text-destructive" : "text-foreground")}>
        {r.performance === "at_risk" ? <AlertTriangle className="h-3 w-3" /> : <CheckCircle2 className="h-3 w-3 text-success" />}
        {fmtPct(r.percent)}
      </span>
    );
  };
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-primary" />
          <CardTitle>Topic risk</CardTitle>
        </div>
        <CardDescription>
          Coverage risk: fewer than {risk.min_questions} bank questions. Performance risk: class score below {risk.risk_percent}% with at
          least {risk.min_answers} graded answers. Two separate signals — a topic can be well covered and still poorly understood.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-border p-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Coverage risk ({risk.coverage_risks.length})</p>
            <p className="mt-1 text-xs text-foreground">
              {risk.coverage_risks.length ? risk.coverage_risks.map((r) => r.name).join(", ") : "Every topic has enough questions."}
            </p>
          </div>
          <div className={cn("rounded-lg border p-3", risk.performance_risks.length ? "border-destructive/30 bg-destructive/[0.03]" : "border-border")}>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Performance risk ({risk.performance_risks.length})</p>
            <p className="mt-1 text-xs text-foreground">
              {risk.performance_risks.length
                ? risk.performance_risks.map((r) => `${r.name} (${fmtPct(r.percent)})`).join(", ")
                : "No topic below the threshold with enough evidence."}
            </p>
          </div>
        </div>
        <div className="max-h-80 overflow-y-auto scrollbar-thin">
          <DataTable
            headers={["Topic", "Question coverage", "Bank questions", "Student performance", "Graded answers"]}
            rows={risk.rows.map((r) => [
              r.name,
              <span key="c" className={cn(r.coverage === "good" ? "text-foreground" : "font-medium text-warning")}>
                {coverageLabel[r.coverage]}
              </span>,
              r.question_count,
              perfCell(r),
              r.answers,
            ])}
          />
        </div>
      </CardContent>
    </Card>
  );
}

// ---------- assessment view ----------

const flagLabel = { harder_than_predicted: "Harder than predicted", easier_than_predicted: "Easier than predicted" } as const;

function AssessmentView({ data }: { data: AssessmentAnalytics }) {
  const s = data.summary;
  const p = data.participation;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile
          label="Submitted"
          value={p.submitted}
          sub={`${p.started} started${p.in_progress ? ` · ${p.in_progress} in progress` : ""}${p.timed_out ? ` · ${p.timed_out} timed out` : ""}${p.auto_submitted ? ` · ${p.auto_submitted} auto-submitted` : ""}`}
          icon={Users}
        />
        <StatTile label="Average" value={fmtPct(s.average_percent, 1)} sub={`Median ${fmtPct(s.median_percent, 1)}`} icon={Percent} />
        <StatTile label="Pass rate" value={fmtPct(s.pass_rate)} sub={`Range ${fmtPct(s.lowest_percent)} – ${fmtPct(s.highest_percent)}`} icon={Trophy} />
        <StatTile
          label="Awaiting grading"
          value={s.pending_answers}
          sub={s.pending_answers ? "Excluded from scores until graded" : "Everything is graded"}
          icon={ClipboardCheck}
          tone={s.pending_answers ? "warning" : undefined}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard
          title="Score distribution"
          icon={Users}
          table={<DataTable headers={["Range", "Students"]} rows={data.score_histogram.map((h) => [`${h.start}–${h.end}%`, h.count])} />}
        >
          <ColumnChart
            data={data.score_histogram.map((h) => ({ key: String(h.start), label: `${h.start}`, value: h.count, tooltip: `${h.start}–${h.end}%: ${h.count}` }))}
          />
        </ChartCard>
        <ChartCard
          title="Grade distribution"
          icon={GraduationCap}
          table={<DataTable headers={["Grade", "Students"]} rows={data.grade_distribution.map((g) => [g.grade, g.count])} />}
        >
          <ColumnChart data={data.grade_distribution.map((g) => ({ key: g.grade, label: g.grade, value: g.count, tooltip: `${g.grade} (${g.label}): ${g.count}` }))} />
        </ChartCard>
      </div>

      <BreakdownGrid b={data.breakdowns} who="students on this assessment" />

      <Card>
        <CardHeader>
          <CardTitle>Question-by-question</CardTitle>
          <CardDescription>
            Averages need at least {data.min_responses} graded responses before they're interpreted; flags compare the result with the difficulty
            predicted when the question was generated.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <p
            className={cn(
              "flex items-start gap-1.5 rounded-md p-2 text-xs",
              data.calibration.status === "ok" ? "bg-secondary/50 text-foreground" : "bg-warning/[0.06] text-foreground"
            )}
          >
            {data.calibration.status === "ok" ? <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 text-success" /> : <CircleDashed className="mt-0.5 h-3.5 w-3.5 text-warning" />}
            <span>
              <span className="font-medium">Predicted vs actual difficulty: </span>
              {data.calibration.note}
            </span>
          </p>
          <DataTable
            headers={["#", "Question", "Bloom's", "Predicted", "Responses", "Average", "Result"]}
            rows={data.questions.map((q) => [
              q.position,
              <span key="t" className="block max-w-[340px] truncate" title={q.text}>
                {q.text}
              </span>,
              q.bloom_level ? BLOOM_LABELS[q.bloom_level as BloomLevel] : "—",
              q.predicted_bucket ? `${q.predicted_bucket} (${q.predicted_difficulty?.toFixed(1)})` : "—",
              q.pending ? `${q.responses} (+${q.pending} pending)` : q.responses,
              q.sufficient ? fmtPct(q.average_percent) : q.average_percent == null ? "—" : `${fmtPct(q.average_percent)}*`,
              !q.sufficient ? (
                <span key="f" className="text-muted-foreground">Not enough data</span>
              ) : q.calibration_flag ? (
                <span key="f" className="inline-flex items-center gap-1 font-medium text-warning">
                  <AlertTriangle className="h-3 w-3" /> {flagLabel[q.calibration_flag]}
                </span>
              ) : (
                <span key="f" className="inline-flex items-center gap-1 text-success">
                  <CheckCircle2 className="h-3 w-3" /> As predicted
                </span>
              ),
            ])}
          />
          {data.questions.some((q) => !q.sufficient && q.average_percent != null) && (
            <p className="text-[11px] text-muted-foreground">* Shown for reference only — fewer than {data.min_responses} graded responses.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ---------- class view ----------

function ClassView({ data, risk, onOpenStudent }: { data: ClassOverview; risk: TopicRisk | null; onOpenStudent: (key: string) => void }) {
  const s = data.summary;
  const b = data.breakdowns;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Students" value={s.students} sub={`${s.submissions} submissions · ${s.assessments} assessments`} icon={Users} />
        <StatTile label="Class average" value={fmtPct(s.average_percent, 1)} sub={`Median ${fmtPct(s.median_percent, 1)}`} icon={Percent} />
        <StatTile
          label="Pass rate"
          value={fmtPct(s.pass_rate)}
          sub={`Range ${fmtPct(s.lowest_percent)} – ${fmtPct(s.highest_percent)}`}
          icon={Trophy}
        />
        <StatTile
          label="Awaiting grading"
          value={s.pending_answers}
          sub={s.pending_answers ? "Excluded from scores until graded" : "Everything is graded"}
          icon={ClipboardCheck}
          tone={s.pending_answers ? "warning" : undefined}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard
          title="Score distribution"
          description="Students by overall percentage"
          icon={Users}
          table={
            <DataTable
              headers={["Range", "Students"]}
              rows={data.score_histogram.map((h) => [`${h.start}–${h.end}%`, h.count])}
            />
          }
        >
          <ColumnChart
            data={data.score_histogram.map((h) => ({
              key: String(h.start),
              label: `${h.start}`,
              value: h.count,
              tooltip: `${h.start}–${h.end}%: ${h.count} student${h.count === 1 ? "" : "s"}`,
            }))}
          />
        </ChartCard>
        <ChartCard
          title="Grade distribution"
          description="10-point scale: O ≥ 90, A+ ≥ 80, A ≥ 70, B+ ≥ 60, B ≥ 50, C ≥ 45, P ≥ 40, F < 40"
          icon={GraduationCap}
          table={
            <DataTable
              headers={["Grade", "Meaning", "Min %", "Students"]}
              rows={data.grade_distribution.map((g) => [g.grade, g.label, g.min_percent, g.count])}
            />
          }
        >
          <ColumnChart
            data={data.grade_distribution.map((g) => ({
              key: g.grade,
              label: g.grade,
              value: g.count,
              tooltip: `${g.grade} (${g.label}): ${g.count} student${g.count === 1 ? "" : "s"}`,
            }))}
          />
        </ChartCard>
      </div>

      <ChartCard
        title="Class average over time"
        description="Average graded score per assessment, in date order"
        icon={TrendingUp}
        empty={data.trend.length < 2 ? "Trends appear once the class has taken at least two assessments." : null}
        table={
          <DataTable headers={["Assessment", "Date", "Average"]} rows={data.trend.map((t) => [t.name, new Date(t.date).toLocaleDateString(), fmtPct(t.percent, 1)])} />
        }
      >
        <TrendChart
          labels={data.trend.map((t) => t.name)}
          series={[{ name: "Class average", color: SERIES_ACCENT, values: data.trend.map((t) => t.percent), emphasis: true }]}
        />
      </ChartCard>

      {risk && <TopicRiskCard risk={risk} />}

      <BreakdownGrid b={b} who="the class" />

      <Card>
        <CardHeader>
          <CardTitle>Assessments</CardTitle>
          <CardDescription>Quizzes and MSE/SEE exams with at least one submission</CardDescription>
        </CardHeader>
        <CardContent>
          <DataTable
            headers={["Assessment", "Type", "Submissions", "Average", "Highest", "Lowest", "Pending"]}
            rows={data.assessments.map((a) => [
              <span key="n" className="font-medium">{a.name}</span>,
              ASSESSMENT_TYPE_LABELS[a.exam_type],
              a.submissions,
              fmtPct(a.average_percent, 1),
              fmtPct(a.highest_percent),
              fmtPct(a.lowest_percent),
              a.pending || "—",
            ])}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Students</CardTitle>
          <CardDescription>Click a student for their individual report</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="px-4 py-2 font-medium">Student</th>
                  <th className="px-2 py-2 text-right font-medium">Assessments</th>
                  <th className="px-2 py-2 text-right font-medium">Overall</th>
                  <th className="px-2 py-2 font-medium">Grade</th>
                  <th className="px-2 py-2 text-right font-medium">Conceptual</th>
                  <th className="px-2 py-2 text-right font-medium">Reasoning</th>
                  <th className="px-2 py-2 text-right font-medium">Coding</th>
                  <th className="px-2 py-2 text-right font-medium">Trend</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.students.map((st) => (
                  <tr
                    key={st.key}
                    tabIndex={0}
                    onClick={() => onOpenStudent(st.key)}
                    onKeyDown={(e) => e.key === "Enter" && onOpenStudent(st.key)}
                    className="cursor-pointer outline-none hover:bg-secondary/40 focus-visible:bg-secondary/40"
                  >
                    <td className="px-4 py-2.5">
                      <p className="font-medium text-foreground">{st.name}</p>
                      {st.identifier && <p className="text-[11px] text-muted-foreground">{st.identifier}</p>}
                    </td>
                    <td className="px-2 py-2.5 text-right tabular-nums">{st.assessments}</td>
                    <td className="px-2 py-2.5 text-right font-semibold tabular-nums">{fmtPct(st.percent, 1)}</td>
                    <td className="px-2 py-2.5">
                      {st.grade ? (
                        <span title={st.grade.label} className="font-medium text-foreground">
                          {st.grade.grade}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-2 py-2.5 text-right tabular-nums">{fmtPct(st.skills.conceptual)}</td>
                    <td className="px-2 py-2.5 text-right tabular-nums">{fmtPct(st.skills.reasoning)}</td>
                    <td className="px-2 py-2.5 text-right tabular-nums">{fmtPct(st.skills.coding)}</td>
                    <td className="px-2 py-2.5 text-right tabular-nums">
                      {st.trend_delta == null ? (
                        "—"
                      ) : (
                        <span className={cn("inline-flex items-center gap-0.5", st.trend_delta >= 0 ? "text-success" : "text-destructive")}>
                          {st.trend_delta >= 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                          {st.trend_delta > 0 ? "+" : ""}
                          {st.trend_delta.toFixed(1)}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex flex-wrap gap-1">
                        <BandBadge band={st.band} />
                        {st.pending > 0 && <Badge variant="warning">{st.pending} pending</Badge>}
                      </div>
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

// ---------- student view ----------

function StudentView({ data, onBack }: { data: StudentDetail; onBack: () => void }) {
  const s = data.summary;
  return (
    <div className="space-y-4">
      <button onClick={onBack} className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to class overview
      </button>

      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-4 p-5">
          <div>
            <p className="text-base font-semibold text-foreground">{data.name}</p>
            <p className="text-xs text-muted-foreground">
              {data.identifier ? `${data.identifier} · ` : ""}
              {s.assessments} assessment{s.assessments === 1 ? "" : "s"}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {s.grade && (
              <Badge variant="default" className="text-xs">
                Grade {s.grade.grade} · {s.grade.label}
              </Badge>
            )}
            <BandBadge band={s.band} />
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Overall score" value={fmtPct(s.percent, 1)} sub={`Class average ${fmtPct(s.class_average_percent, 1)}`} icon={Percent} />
        <StatTile label="Grade" value={s.grade?.grade ?? "—"} sub={s.grade?.label} icon={GraduationCap} />
        <StatTile label="Class rank" value={s.rank ? `${s.rank} / ${s.class_size}` : "—"} sub="By overall graded score" icon={Trophy} />
        <StatTile
          label="Awaiting grading"
          value={s.pending_answers}
          sub={s.pending_answers ? "Excluded until graded" : "Everything is graded"}
          icon={ClipboardCheck}
          tone={s.pending_answers ? "warning" : undefined}
        />
      </div>

      <ChartCard
        title="Progress over time"
        description={`${data.name} compared with the class average on each assessment`}
        icon={TrendingUp}
        empty={data.trend.length < 2 ? "Progress appears once this student has taken at least two assessments." : null}
        table={
          <DataTable
            headers={["Assessment", "Date", "Student", "Class average"]}
            rows={data.history.map((h) => [h.name, new Date(h.date).toLocaleDateString(), fmtPct(h.percent, 1), fmtPct(h.class_average_percent, 1)])}
          />
        }
      >
        <TrendChart
          labels={data.history.map((h) => h.name)}
          series={[
            { name: "Class average", color: SERIES_CONTEXT, values: data.history.map((h) => h.class_average_percent) },
            { name: data.name, color: SERIES_ACCENT, values: data.history.map((h) => h.percent), emphasis: true },
          ]}
        />
      </ChartCard>

      <BreakdownGrid b={data.breakdowns} who={data.name} />

      <Card>
        <CardHeader>
          <CardTitle>Assessment history</CardTitle>
          <CardDescription>Latest attempt per assessment</CardDescription>
        </CardHeader>
        <CardContent>
          <DataTable
            headers={["Assessment", "Type", "Submitted", "Marks", "Score", "Grade", "Class avg", "Pending"]}
            rows={data.history.map((h) => [
              <span key="n" className="font-medium">{h.name}</span>,
              ASSESSMENT_TYPE_LABELS[h.exam_type],
              new Date(h.submitted_at).toLocaleDateString(),
              `${h.awarded} / ${h.max}`,
              fmtPct(h.percent, 1),
              h.grade?.grade ?? "—",
              fmtPct(h.class_average_percent, 1),
              h.pending || "—",
            ])}
          />
        </CardContent>
      </Card>
    </div>
  );
}

// ---------- page ----------

export function PerformancePage() {
  const { activeSubjectId } = useAuth();
  const [view, setView] = useState<"class" | "assessment" | "student">("class");
  const [risk, setRisk] = useState<TopicRisk | null>(null);
  const [assessmentId, setAssessmentId] = useState("");
  const [assessment, setAssessment] = useState<AssessmentAnalytics | null>(null);
  const [examType, setExamType] = useState<AssessmentType | "">("");
  const [overview, setOverview] = useState<ClassOverview | null>(null);
  const [studentKey, setStudentKey] = useState<string>("");
  const [student, setStudent] = useState<StudentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!activeSubjectId) return;
    setLoading(true);
    setError(null);
    fetchClassOverview(activeSubjectId, examType || null)
      .then(setOverview)
      .catch((e) => setError(e instanceof Error ? e.message : "Couldn't load performance data"))
      .finally(() => setLoading(false));
    fetchTopicRisk(activeSubjectId, examType || null).then(setRisk).catch(() => setRisk(null));
  }, [activeSubjectId, examType]);

  useEffect(() => {
    if (view !== "assessment" || !assessmentId) return;
    setAssessment(null);
    fetchAssessmentAnalytics(assessmentId).then(setAssessment).catch(() => setAssessment(null));
  }, [view, assessmentId]);

  // Reset the student picker when switching subject.
  useEffect(() => {
    setStudentKey("");
    setStudent(null);
    setAssessmentId("");
    setView("class");
  }, [activeSubjectId]);

  useEffect(() => {
    if (view !== "student" || !studentKey || !activeSubjectId) return;
    fetchStudentDetail(activeSubjectId, studentKey, examType || null)
      .then(setStudent)
      .catch(() => setStudent(null));
  }, [view, studentKey, activeSubjectId, examType]);

  const students = useMemo(
    () => [...(overview?.students ?? [])].sort((a, b) => a.name.localeCompare(b.name)),
    [overview]
  );

  const openStudent = (key: string) => {
    setStudentKey(key);
    setView("student");
  };

  return (
    <div className="space-y-4">
      {/* One filter row scopes everything below it. */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Tabs value={view} onValueChange={(v) => setView(v as "class" | "assessment" | "student")}>
          <TabsList>
            <TabsTrigger value="class">Class overview</TabsTrigger>
            <TabsTrigger value="assessment">Assessment</TabsTrigger>
            <TabsTrigger value="student">Individual student</TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="flex flex-wrap gap-2">
          {view === "assessment" && (
            <Select value={assessmentId} onChange={(e) => setAssessmentId(e.target.value)} className="w-64" aria-label="Assessment">
              <option value="">Select an assessment…</option>
              {(overview?.assessments ?? []).map((a) => (
                <option key={a.exam_id} value={a.exam_id}>
                  {ASSESSMENT_TYPE_LABELS[a.exam_type]} · {a.name}
                </option>
              ))}
            </Select>
          )}
          {view === "student" && (
            <Select value={studentKey} onChange={(e) => setStudentKey(e.target.value)} className="w-56" aria-label="Student">
              <option value="">Select a student…</option>
              {students.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.name}
                  {s.identifier ? ` (${s.identifier})` : ""}
                </option>
              ))}
            </Select>
          )}
          <Select value={examType} onChange={(e) => setExamType(e.target.value as AssessmentType | "")} className="w-44" aria-label="Assessment type">
            <option value="">All assessments</option>
            <option value="QUIZ">Quizzes only</option>
            <option value="MSE">MSE only</option>
            <option value="SEE">SEE only</option>
          </Select>
        </div>
      </div>

      {error ? (
        <EmptyState icon={Users} title="Couldn't load performance data" description={error} />
      ) : loading && !overview ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
          <Skeleton className="h-64 w-full" />
        </div>
      ) : !overview || overview.summary.students === 0 ? (
        <EmptyState
          icon={Users}
          title="No student results yet"
          description={
            examType
              ? `No ${ASSESSMENT_TYPE_LABELS[examType]} submissions in this subject yet. Try "All assessments".`
              : "Performance analysis appears once students submit a live quiz or exam in this subject."
          }
        />
      ) : (
        <div className={cn("transition-opacity", loading && "opacity-60")}>
          {view === "class" ? (
            <ClassView data={overview} risk={risk} onOpenStudent={openStudent} />
          ) : view === "assessment" ? (
            !assessmentId ? (
              <EmptyState icon={ClipboardCheck} title="Pick an assessment" description="Choose a quiz or exam above to see its results question by question." />
            ) : assessment && assessment.exam_id === assessmentId ? (
              <AssessmentView data={assessment} />
            ) : (
              <Skeleton className="h-64 w-full" />
            )
          ) : !studentKey ? (
            <EmptyState icon={Users} title="Pick a student" description="Choose a student above, or click one in the class overview's student table." />
          ) : student && student.key === studentKey ? (
            <StudentView data={student} onBack={() => setView("class")} />
          ) : (
            <Skeleton className="h-64 w-full" />
          )}
        </div>
      )}
    </div>
  );
}
