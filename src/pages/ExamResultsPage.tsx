import { useEffect, useState } from "react";
import { ArrowLeft, Users, CheckCircle2, XCircle, HelpCircle, PenLine, CircleDot } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import {
  ASSESSMENT_TYPE_LABELS,
  QUESTION_TYPE_LABELS,
  isCodingType,
  SKILL_LABELS,
  getExam,
  getExamAttempts,
  getExamSubmissions,
  gradeSubmissionAnswer,
  type AttemptSummary,
  type Exam,
  type GradedAnswer,
  type Question,
  type Submission,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/** Inline marks entry for one answer. Short/long answers start ungraded;
 *  auto-graded answers can be overridden via "Adjust". */
function ManualGrade({
  examId,
  submissionId,
  answer,
  onGraded,
}: {
  examId: string;
  submissionId: string;
  answer: GradedAnswer;
  onGraded: (s: Submission) => void;
}) {
  const needsGrading = !answer.auto_graded && !answer.manually_graded;
  const [open, setOpen] = useState(needsGrading);
  const [marks, setMarks] = useState(String(answer.marks_awarded));
  const [feedback, setFeedback] = useState(answer.feedback ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="flex items-center gap-1 text-[11px] font-medium text-primary hover:underline">
        <PenLine className="h-3 w-3" /> {answer.manually_graded ? "Re-grade" : "Adjust"}
      </button>
    );
  }

  const save = async () => {
    const value = Number(marks);
    if (!Number.isInteger(value) || value < 0 || value > answer.max_marks) {
      setError(`Enter a whole number from 0 to ${answer.max_marks}`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onGraded(await gradeSubmissionAnswer(examId, submissionId, answer.question_id, value, feedback));
      setOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save the grade");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-1">
        <Input
          type="number"
          min={0}
          max={answer.max_marks}
          value={marks}
          onChange={(e) => setMarks(e.target.value)}
          className="h-7 w-16"
          aria-label="Marks awarded"
        />
        <span className="text-[11px] text-muted-foreground">/ {answer.max_marks}</span>
      </div>
      <Input value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="Feedback (optional)" className="h-7 min-w-[160px] flex-1" />
      <Button size="sm" className="h-7" onClick={save} disabled={busy}>
        {busy ? "Saving..." : "Save grade"}
      </Button>
      {!needsGrading && (
        <Button size="sm" variant="ghost" className="h-7" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      )}
      {error && <p className="w-full text-[11px] text-destructive">{error}</p>}
    </div>
  );
}

export function ExamResultsPage({ examId, onBack }: { examId: string; onBack: () => void }) {
  const [exam, setExam] = useState<Exam | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [attempts, setAttempts] = useState<AttemptSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    getExamAttempts(examId).then(setAttempts).catch(() => setAttempts([]));
    Promise.all([getExam(examId), getExamSubmissions(examId)]).then(([detail, subs]) => {
      setExam(detail.exam);
      setQuestions(detail.questions);
      setSubmissions(subs);
      setLoading(false);
    });
  }, [examId]);

  const questionText = (id: string) => questions.find((q) => q.id === id)?.text ?? id;
  const inProgress = attempts.filter((a) => !a.submitted && !a.expired).length;
  const timedOut = attempts.filter((a) => !a.submitted && a.expired).length;
  const replaceSubmission = (updated: Submission) =>
    setSubmissions((subs) => subs.map((s) => (s.id === updated.id ? updated : s)));
  const pendingAnswers = submissions.reduce(
    (n, s) => n + s.answers.filter((a) => !a.auto_graded && !a.manually_graded).length,
    0
  );

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
        <h1 className="flex flex-wrap items-center gap-2 text-lg font-semibold text-foreground">
          {exam?.name} — Results
          {exam && exam.exam_type !== "QUIZ" && <Badge variant="default">{ASSESSMENT_TYPE_LABELS[exam.exam_type]}</Badge>}
        </h1>
        <p className="text-sm text-muted-foreground">
          Objective and coding answers are graded automatically on submission; short and long answers are graded here by you.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card>
          <CardContent className="p-4">
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Users className="h-3.5 w-3.5" /> Submissions
            </p>
            <p className="mt-1 text-2xl font-semibold text-foreground">{submissions.length}</p>
            {(inProgress > 0 || timedOut > 0) && (
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                {inProgress > 0 && `${inProgress} in progress`}
                {inProgress > 0 && timedOut > 0 && " · "}
                {timedOut > 0 && `${timedOut} ran out of time without submitting`}
              </p>
            )}
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
              {needsManualReview
                ? `${pendingAnswers} answer${pendingAnswers === 1 ? "" : "s"} need${pendingAnswers === 1 ? "s" : ""} grading`
                : "Everything is graded"}
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
                        {sub.auto_submitted && (
                          <Badge variant="outline" title="Time ran out or the exam closed before the student submitted; their autosaved answers were submitted for them.">
                            Auto-submitted
                          </Badge>
                        )}
                        {!sub.fully_auto_graded && <Badge variant="warning">Needs review</Badge>}
                        <Badge variant={pct >= 70 ? "success" : pct >= 40 ? "warning" : "destructive"}>
                          {sub.total_marks_awarded} / {sub.total_max_marks} ({pct}%)
                        </Badge>
                      </div>
                    </button>
                    {isOpen && (
                      <div className="space-y-2 bg-secondary/20 px-4 pb-4">
                        {sub.answers.map((a) => {
                          const pending = !a.auto_graded && !a.manually_graded;
                          // Hidden-test grading can award part of the marks (e.g. 2 of 3 tests passed).
                          const partial = !pending && a.correct === false && a.marks_awarded > 0 && a.marks_awarded < a.max_marks;
                          return (
                            <div key={a.question_id} className="flex items-start gap-2 rounded-lg border border-border bg-white p-2.5">
                              {pending ? (
                                <HelpCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" aria-label="Needs grading" />
                              ) : partial ? (
                                <CircleDot className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" aria-label="Partial credit" />
                              ) : a.correct === true ? (
                                <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" aria-label="Correct" />
                              ) : a.correct === false ? (
                                <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" aria-label="Incorrect" />
                              ) : (
                                <CircleDot className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" aria-label="Partial credit" />
                              )}
                              <div className="min-w-0 flex-1">
                                <p className="line-clamp-2 text-xs text-foreground">{questionText(a.question_id)}</p>
                                {a.answer != null && a.answer !== "" && (
                                  <pre
                                    className={cn(
                                      "mt-1.5 max-h-40 overflow-auto whitespace-pre-wrap rounded-md bg-secondary/50 p-2 text-[11px] text-foreground",
                                      isCodingType(a.question_type) ? "font-mono" : "font-sans"
                                    )}
                                  >
                                    {a.answer}
                                  </pre>
                                )}
                                {a.answer === "" && <p className="mt-1 text-[11px] italic text-muted-foreground">No answer given</p>}
                                <div className="mt-1 flex flex-wrap items-center gap-1.5">
                                  <Badge variant="outline">{QUESTION_TYPE_LABELS[a.question_type]}</Badge>
                                  {a.skill_category && <Badge variant="outline">{SKILL_LABELS[a.skill_category]}</Badge>}
                                  {pending && <Badge variant="warning">Needs grading</Badge>}
                                  <span className="text-[11px] text-muted-foreground">
                                    {a.marks_awarded}/{a.max_marks} marks · {a.detail}
                                  </span>
                                </div>
                                {a.feedback && <p className="mt-1 text-[11px] text-muted-foreground">Feedback: {a.feedback}</p>}
                                <ManualGrade key={`${a.question_id}-${a.marks_awarded}`} examId={examId} submissionId={sub.id} answer={a} onGraded={replaceSubmission} />
                              </div>
                            </div>
                          );
                        })}
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
