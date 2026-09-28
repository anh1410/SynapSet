import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, Clock, GraduationCap, Loader2, Send } from "lucide-react";
import { AutosaveStatus } from "@/components/AutosaveStatus";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { ApiError, getAttemptState, submitAttempt, type AttemptState, type StudentIdentity } from "@/lib/api";
import { useAttemptAutosave } from "@/lib/useAttemptAutosave";
import { formatClock, useServerCountdown } from "@/lib/useServerCountdown";
import { cn } from "@/lib/utils";
import { endedFromError, viewForAttempt, type StudentView } from "@/pages/student/studentFlow";
import { QuestionCard, isAnswered } from "@/pages/student/QuestionCard";

const RESYNC_MS = 60_000;

export function StudentExam({
  examId,
  initial,
  identity,
  syncedAt: initialSyncedAt,
  onFinished,
}: {
  examId: string;
  initial: AttemptState;
  identity: StudentIdentity;
  syncedAt: number;
  onFinished: (view: StudentView) => void;
}) {
  const exam = initial.exam!;
  const attemptId = initial.attempt.attempt_id;
  const questions = exam.questions;

  const [answers, setAnswers] = useState<Record<string, string>>(() => ({ ...initial.saved_answers }));
  const [remaining, setRemaining] = useState({ seconds: initial.attempt.remaining_seconds, syncedAt: initialSyncedAt });
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const finished = useRef(false);
  const answersRef = useRef(answers);
  answersRef.current = answers;

  const autosave = useAttemptAutosave({ examId, attemptId, initialSeq: initial.save_seq });
  const secondsLeft = useServerCountdown(remaining.seconds, remaining.syncedAt);

  const end = useCallback(
    (view: StudentView) => {
      if (finished.current) return;
      finished.current = true;
      onFinished(view);
    },
    [onFinished]
  );

  const submit = useCallback(
    async (timeRanOut: boolean) => {
      if (finished.current) return;
      setSubmitting(true);
      setSubmitError(null);
      try {
        // Sends every answer: the server overlays them on the autosaved ones.
        const receipt = await submitAttempt(examId, identity, attemptId, answersRef.current);
        end({ kind: "receipt", receipt, timeRanOut });
      } catch (e) {
        const ended = endedFromError(e);
        if (ended) return end(ended);
        setSubmitError(
          e instanceof ApiError
            ? e.message
            : timeRanOut
              ? "Couldn't reach the server. Your saved answers will be submitted automatically."
              : "Couldn't reach the server. Your answers are saved - try submitting again."
        );
      } finally {
        setSubmitting(false);
        setConfirmOpen(false);
      }
    },
    [examId, identity, attemptId, end]
  );

  // Re-sync the timer with the server now and then (and when the tab comes
  // back or the network returns); also notices the teacher closing the exam.
  const resync = useCallback(async () => {
    if (finished.current) return;
    try {
      const state = await getAttemptState(examId, attemptId);
      // Submitted while this page was still open: the server finalised it
      // from the autosaved answers (time ran out or the teacher closed the exam).
      if (state.attempt.submitted) return end({ kind: "ended", reason: "auto_submitted" });
      const view = viewForAttempt(state, identity);
      if (view.kind !== "exam") return end(view);
      setRemaining({ seconds: state.attempt.remaining_seconds, syncedAt: performance.now() });
    } catch (e) {
      const ended = endedFromError(e);
      if (ended) end(ended);
      // otherwise offline: keep counting locally
    }
  }, [examId, attemptId, identity, end]);

  useEffect(() => {
    const id = setInterval(() => void resync(), RESYNC_MS);
    const onVisible = () => document.visibilityState === "visible" && void resync();
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", resync);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("online", resync);
    };
  }, [resync]);

  // Time's up: submit what we have (within the server's short grace period).
  useEffect(() => {
    if (secondsLeft === 0 && !finished.current) void submit(true);
  }, [secondsLeft, submit]);

  // Warn before leaving while answers are still unsaved.
  useEffect(() => {
    if (autosave.status !== "saving" && autosave.status !== "offline") return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [autosave.status]);

  const handleChange = (questionId: string, value: string) => {
    setAnswers((prev) => ({ ...prev, [questionId]: value }));
    autosave.update(questionId, value);
  };

  const answeredFlags = useMemo(() => questions.map((q) => isAnswered(q, answers[q.id])), [questions, answers]);
  const answeredCount = answeredFlags.filter(Boolean).length;
  const unanswered = questions.map((_, i) => i + 1).filter((n) => !answeredFlags[n - 1]);
  const timeUp = secondsLeft === 0;
  const locked = submitting || timeUp;

  const scrollTo = (qid: string) => document.getElementById(`question-${qid}`)?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <div className="min-h-screen bg-secondary/40">
      <header className="sticky top-0 z-40 border-b border-border bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5">
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <GraduationCap className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-foreground">{exam.name}</p>
              <p className="truncate text-[11px] text-muted-foreground">
                {identity.student_name}
                {identity.student_identifier && ` · ${identity.student_identifier}`} · {exam.total_marks} marks
              </p>
            </div>
          </div>
          <AutosaveStatus status={autosave.status} lastSavedAt={autosave.lastSavedAt} className="order-last w-full sm:order-none sm:w-auto" />
          {secondsLeft != null ? (
            <div
              className={cn(
                "flex items-center gap-1.5 rounded-lg px-2.5 py-1 font-mono text-sm font-semibold tabular-nums",
                secondsLeft <= 60 ? "bg-destructive/10 text-destructive" : secondsLeft <= 300 ? "bg-warning/10 text-warning" : "bg-secondary text-foreground"
              )}
              role="timer"
              aria-label={`Time remaining ${formatClock(secondsLeft)}`}
            >
              <Clock className="h-4 w-4" /> {formatClock(secondsLeft)}
            </div>
          ) : (
            <span className="text-xs text-muted-foreground">No time limit</span>
          )}
          <Button size="sm" onClick={() => setConfirmOpen(true)} disabled={locked}>
            <Send className="h-3.5 w-3.5" /> Submit
          </Button>
        </div>
      </header>

      <div className="mx-auto grid max-w-5xl gap-6 px-4 py-6 lg:grid-cols-[1fr_220px]">
        <div className="space-y-4">
          {timeUp && (
            <p className="flex items-center gap-2 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning" role="alert">
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <AlertCircle className="h-4 w-4" />}
              Time is up - submitting your answers…
            </p>
          )}
          {submitError && (
            <p className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
              <AlertCircle className="h-4 w-4 shrink-0" /> {submitError}
            </p>
          )}
          {questions.map((q, i) => (
            <QuestionCard key={q.id} q={q} index={i} answer={answers[q.id]} disabled={locked} onChange={(v) => handleChange(q.id, v)} />
          ))}
          <div className="flex justify-end">
            <Button onClick={() => setConfirmOpen(true)} disabled={locked}>
              <Send className="h-4 w-4" /> Submit exam
            </Button>
          </div>
        </div>

        <aside className="order-first lg:order-none">
          <Card className="lg:sticky lg:top-20">
            <CardContent className="space-y-3 p-4">
              <div className="space-y-1.5">
                <p className="text-xs font-medium text-foreground">
                  {answeredCount} of {questions.length} answered
                </p>
                <Progress value={questions.length ? (answeredCount / questions.length) * 100 : 0} />
              </div>
              <nav aria-label="Questions" className="grid grid-cols-8 gap-1.5 lg:grid-cols-5">
                {questions.map((q, i) => (
                  <button
                    key={q.id}
                    onClick={() => scrollTo(q.id)}
                    aria-label={`Question ${i + 1}${answeredFlags[i] ? ", answered" : ""}`}
                    className={cn(
                      "h-8 rounded-md border text-xs font-medium transition-colors",
                      answeredFlags[i] ? "border-primary bg-primary text-primary-foreground" : "border-border bg-white text-foreground hover:bg-secondary"
                    )}
                  >
                    {i + 1}
                  </button>
                ))}
              </nav>
            </CardContent>
          </Card>
        </aside>
      </div>

      <Dialog open={confirmOpen} onClose={() => !submitting && setConfirmOpen(false)} title="Submit your exam?" className="max-w-md">
        <div className="space-y-4 text-sm">
          <p className="text-foreground">
            You've answered {answeredCount} of {questions.length} questions.
          </p>
          {unanswered.length > 0 && (
            <p className="rounded-lg bg-warning/10 px-3 py-2 text-xs text-warning">
              Not answered: {unanswered.map((n) => `Q${n}`).join(", ")}
            </p>
          )}
          <p className="text-xs text-muted-foreground">You can't change your answers after submitting.</p>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setConfirmOpen(false)} disabled={submitting}>
              Keep working
            </Button>
            <Button onClick={() => void submit(false)} disabled={submitting}>
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Submitting…
                </>
              ) : (
                "Submit"
              )}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
