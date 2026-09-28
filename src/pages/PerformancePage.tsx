import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  Brain,
  ClipboardCheck,
  Code2,
  GraduationCap,
  Lightbulb,
  Network,
  Percent,
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
  fetchClassOverview,
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
                    <Icon className="h-3.5 w-3.5 text-primary" /> {row?.label ?? skill}
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

// ---------- class view ----------

function ClassView({ data, onOpenStudent }: { data: ClassOverview; onOpenStudent: (key: string) => void }) {
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
  const [view, setView] = useState<"class" | "student">("class");
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
  }, [activeSubjectId, examType]);

  // Reset the student picker when switching subject.
  useEffect(() => {
    setStudentKey("");
    setStudent(null);
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
        <Tabs value={view} onValueChange={(v) => setView(v as "class" | "student")}>
          <TabsList>
            <TabsTrigger value="class">Class overview</TabsTrigger>
            <TabsTrigger value="student">Individual student</TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="flex flex-wrap gap-2">
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
            <ClassView data={overview} onOpenStudent={openStudent} />
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
