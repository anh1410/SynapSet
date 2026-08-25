import { useEffect, useState } from "react";
import { ArrowLeft, Users, CheckCircle2, XCircle, HelpCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { QUESTION_TYPE_LABELS, getExam, getExamSubmissions, type Exam, type Question, type Submission } from "@/lib/api";
import { cn } from "@/lib/utils";

export function ExamResultsPage({ examId, onBack }: { examId: string; onBack: () => void }) {
  const [exam, setExam] = useState<Exam | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getExam(examId), getExamSubmissions(examId)]).then(([detail, subs]) => {
      setExam(detail.exam);
      setQuestions(detail.questions);
      setSubmissions(subs);
      setLoading(false);
    });
  }, [examId]);

  const questionText = (id: string) => questions.find((q) => q.id === id)?.text ?? id;

  if (loading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-10 w-64" />
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  const average =
    submissions.length > 0
      ? Math.round((submissions.reduce((s, sub) => s + sub.total_marks_awarded, 0) / submissions.length) * 10) / 10
      : 0;
  const needsManualReview = submissions.some((s) => !s.fully_auto_graded);

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to Exams
      </button>

      <div>
        <h1 className="text-lg font-semibold text-foreground">{exam?.name} — Results</h1>
        <p className="text-sm text-muted-foreground">Scores are graded automatically the moment a student submits.</p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card>
          <CardContent className="p-4">
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Users className="h-3.5 w-3.5" /> Submissions
            </p>
            <p className="mt-1 text-2xl font-semibold text-foreground">{submissions.length}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground">Average Score</p>
            <p className="mt-1 text-2xl font-semibold text-foreground">
              {average} <span className="text-sm font-normal text-muted-foreground">/ {exam?.total_marks}</span>
            </p>
          </CardContent>
        </Card>
        <Card className={cn(needsManualReview && "border-warning/30 bg-warning/[0.03]")}>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground">Manual Review</p>
            <p className="mt-1 text-sm font-medium text-foreground">
              {needsManualReview ? "Some answers need grading" : "All auto-graded"}
            </p>
          </CardContent>
        </Card>
      </div>

      {submissions.length === 0 ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState icon={Users} title="No submissions yet" description="Results will appear here as soon as students submit." className="m-6" />
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Student Scores</CardTitle>
            <CardDescription>Click a row to see the per-question breakdown</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-border">
              {submissions.map((sub) => {
                const isOpen = expanded === sub.id;
                const pct = sub.total_max_marks > 0 ? Math.round((sub.total_marks_awarded / sub.total_max_marks) * 100) : 0;
                return (
                  <div key={sub.id}>
                    <button
                      className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-secondary/30"
                      onClick={() => setExpanded(isOpen ? null : sub.id)}
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground">{sub.student_name}</p>
                        <p className="text-xs text-muted-foreground">
                          {sub.student_identifier ? `${sub.student_identifier} · ` : ""}
                          {new Date(sub.submitted_at).toLocaleString()}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {!sub.fully_auto_graded && <Badge variant="warning">Needs review</Badge>}
                        <Badge variant={pct >= 70 ? "success" : pct >= 40 ? "warning" : "destructive"}>
                          {sub.total_marks_awarded} / {sub.total_max_marks} ({pct}%)
                        </Badge>
                      </div>
                    </button>
                    {isOpen && (
                      <div className="space-y-2 bg-secondary/20 px-4 pb-4">
                        {sub.answers.map((a) => (
                          <div key={a.question_id} className="flex items-start gap-2 rounded-lg border border-border bg-white p-2.5">
                            {a.correct === true ? (
                              <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" />
                            ) : a.correct === false ? (
                              <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
                            ) : (
                              <HelpCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
                            )}
                            <div className="min-w-0 flex-1">
                              <p className="line-clamp-1 text-xs text-foreground">{questionText(a.question_id)}</p>
                              <div className="mt-1 flex flex-wrap items-center gap-1.5">
                                <Badge variant="outline">{QUESTION_TYPE_LABELS[a.question_type]}</Badge>
                                <span className="text-[11px] text-muted-foreground">
                                  {a.marks_awarded}/{a.max_marks} marks · {a.detail}
                                </span>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      <Button variant="outline" onClick={onBack}>
        <ArrowLeft className="h-3.5 w-3.5" /> Back to Exams
      </Button>
    </div>
  );
}
