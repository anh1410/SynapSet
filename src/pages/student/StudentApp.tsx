/**
 * Student interface at /take/<examId>: public, no teacher login.
 *
 * Lobby (schedule + name/roll/password) -> POST /start -> StudentExam
 * (autosave, server-anchored timer) -> POST /submit -> receipt.
 * A refresh resumes the same attempt from sessionStorage via /start, which
 * returns the same timer and the autosaved answers. Every "the exam is over"
 * answer from the server (403/409) lands on a clear ended screen.
 */
import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { AlertCircle, CalendarClock, CheckCircle2, Clock, GraduationCap, Hourglass, LayoutDashboard, Loader2, Lock, SearchX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, fetchExamTiming, startAttempt, type AttemptState, type ExamTiming, type StudentIdentity } from "@/lib/api";
import {
  clearStoredAttempt,
  getStoredAttempt,
  getStoredReceipt,
  setStoredAttempt,
  setStoredReceipt,
} from "@/lib/studentSession";
import { clearStudentAccount, getStudentAccount } from "@/lib/studentAccount";
import { formatClock, useServerCountdown } from "@/lib/useServerCountdown";
import { StudentExam } from "@/pages/student/StudentExam";
import { SubmissionReceiptView } from "@/pages/student/SubmissionReceiptView";
import { endedFromError, viewForAttempt, type EndedReason, type StudentView } from "@/pages/student/studentFlow";

const fmtDateTime = (iso: string) => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

function Shell({ title, children }: { title?: string; children: ReactNode }) {
  const signedIn = getStudentAccount() !== null;
  return (
    <div className="min-h-screen bg-secondary/40">
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-2 px-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <GraduationCap className="h-4 w-4" />
          </div>
          <span className="text-sm font-semibold text-foreground">SynapSet</span>
          {title && <span className="truncate text-sm text-muted-foreground">· {title}</span>}
          {signedIn && (
            <a href="/student" className="ml-auto flex items-center gap-1 text-xs font-medium text-primary hover:underline">
              <LayoutDashboard className="h-3.5 w-3.5" /> My dashboard
            </a>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
    </div>
  );
}

function MessageCard({ icon, title, children, tone = "default" }: { icon: ReactNode; title: string; children?: ReactNode; tone?: "default" | "success" | "warning" }) {
  const toneClass = tone === "success" ? "bg-success/10 text-success" : tone === "warning" ? "bg-warning/10 text-warning" : "bg-primary/10 text-primary";
  return (
    <Card className="mx-auto max-w-md">
      <CardContent className="flex flex-col items-center gap-3 p-8 text-center">
        <div className={`flex h-12 w-12 items-center justify-center rounded-full ${toneClass}`}>{icon}</div>
        <h1 className="text-base font-semibold text-foreground">{title}</h1>
        {children && <div className="space-y-2 text-sm text-muted-foreground">{children}</div>}
      </CardContent>
    </Card>
  );
}

const ENDED_COPY: Record<EndedReason, { title: string; body: string; tone: "success" | "warning" | "default" }> = {
  submitted: {
    title: "Exam submitted",
    body: "Your answers have been submitted. Your teacher will share your results.",
    tone: "success",
  },
  auto_submitted: {
    title: "Your answers were submitted",
    body: "The exam ended before you submitted, so your saved answers were submitted automatically.",
    tone: "success",
  },
  time_up: {
    title: "Time is up",
    body: "The time for this exam has ended and answers can no longer be changed.",
    tone: "warning",
  },
  closed: {
    title: "This exam is closed",
    body: "This exam has closed. If you had saved answers, they were submitted automatically.",
    tone: "warning",
  },
};

function Lobby({
  examId,
  timing,
  syncedAt,
  onRefresh,
  onStarted,
  onEnded,
}: {
  examId: string;
  timing: ExamTiming;
  syncedAt: number;
  onRefresh: () => void;
  onStarted: (attempt: AttemptState, identity: StudentIdentity) => void;
  onEnded: (view: StudentView) => void;
}) {
  // Signed in from the dashboard: the account is the identity (and links the attempt).
  const [account, setAccount] = useState(() => getStudentAccount());
  const [name, setName] = useState("");
  const [roll, setRoll] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const opensIn = useServerCountdown(timing.opens_in_seconds, syncedAt);
  const closesIn = useServerCountdown(timing.closes_in_seconds, syncedAt);

  // The exam opens (or closes) while the student waits: fetch the new state.
  // Keyed on syncedAt too, so if the server still says "0 seconds" we keep polling.
  useEffect(() => {
    if ((timing.state === "upcoming" && opensIn === 0) || (timing.state === "live" && closesIn === 0)) {
      const id = setTimeout(onRefresh, 1000);
      return () => clearTimeout(id);
    }
  }, [timing.state, opensIn, closesIn, onRefresh, syncedAt]);

  const handleStart = async (e: FormEvent) => {
    e.preventDefault();
    const identity: StudentIdentity = account
      ? { student_name: account.student.name, student_identifier: account.student.roll_number, password }
      : { student_name: name.trim(), student_identifier: roll.trim() || null, password };
    if (!identity.student_name) return;
    setBusy(true);
    setError(null);
    try {
      const attempt = await startAttempt(examId, identity, account?.token);
      onStarted(attempt, identity);
    } catch (err) {
      const ended = endedFromError(err);
      if (ended) return onEnded(ended);
      if (err instanceof ApiError && err.status === 401 && /student session/i.test(err.message)) {
        clearStudentAccount();
        setAccount(null);
        setError("Your student session has expired. Sign in again from your dashboard, or enter your details below.");
      } else if (err instanceof ApiError && err.status === 401) setError("Incorrect exam password.");
      else if (err instanceof ApiError && /not live yet/i.test(err.message)) onRefresh();
      else setError(err instanceof ApiError ? err.message : "Couldn't reach the server. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  };

  if (timing.state === "closed") {
    return (
      <MessageCard icon={<Lock className="h-6 w-6" />} title="This exam is closed" tone="warning">
        <p>{timing.closed_by === "schedule" && timing.closes_at ? `It closed at ${fmtDateTime(timing.closes_at)}.` : "Your teacher has closed it."}</p>
      </MessageCard>
    );
  }

  if (timing.state === "upcoming") {
    return (
      <MessageCard icon={<CalendarClock className="h-6 w-6" />} title="This exam hasn't opened yet">
        {opensIn != null && (
          <p>
            Opens in <span className="font-mono text-lg font-semibold text-foreground">{formatClock(opensIn)}</span>
          </p>
        )}
        {timing.go_live_at && <p>Scheduled for {fmtDateTime(timing.go_live_at)}.</p>}
        {timing.duration_minutes != null && <p>You'll have {timing.duration_minutes} minutes once you start.</p>}
        <p className="text-xs">Keep this page open - it will let you in when the exam opens.</p>
      </MessageCard>
    );
  }

  return (
    <Card className="mx-auto max-w-md">
      <CardContent className="space-y-5 p-6">
        <div className="space-y-1">
          <h1 className="text-base font-semibold text-foreground">Start your exam</h1>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" />
              {timing.duration_minutes != null ? `${timing.duration_minutes} minutes` : "No time limit"}
            </span>
            {closesIn != null && (
              <span className="flex items-center gap-1">
                <Hourglass className="h-3.5 w-3.5" /> Closes in {formatClock(closesIn)}
              </span>
            )}
          </div>
        </div>
        <form className="space-y-3" onSubmit={handleStart}>
          {account ? (
            <div className="rounded-lg border border-border bg-secondary/40 px-3 py-2 text-xs">
              <p className="text-muted-foreground">Signed in as</p>
              <p className="font-medium text-foreground">
                {account.student.name} · {account.student.roll_number}
              </p>
              <p className="mt-1 text-[11px] text-muted-foreground">Your result will appear on your dashboard.</p>
            </div>
          ) : (
            <>
              <div className="space-y-1">
                <label htmlFor="student-name" className="text-xs font-medium text-foreground">
                  Full name
                </label>
                <Input id="student-name" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" required />
              </div>
              <div className="space-y-1">
                <label htmlFor="student-roll" className="text-xs font-medium text-foreground">
                  Roll number
                </label>
                <Input id="student-roll" value={roll} onChange={(e) => setRoll(e.target.value)} autoComplete="off" />
                <p className="text-[11px] text-muted-foreground">Use the same name and roll number to get back into your exam if you're disconnected.</p>
              </div>
            </>
          )}
          <div className="space-y-1">
            <label htmlFor="exam-password" className="text-xs font-medium text-foreground">
              Exam password
            </label>
            <Input
              id="exam-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="off"
              placeholder="Leave blank if your teacher didn't give one"
            />
          </div>
          {error && (
            <p className="flex items-center gap-1.5 text-xs text-destructive" role="alert">
              <AlertCircle className="h-3.5 w-3.5" /> {error}
            </p>
          )}
          {timing.duration_minutes != null && (
            <p className="rounded-lg bg-warning/10 px-3 py-2 text-xs text-warning">
              Once you start, the {timing.duration_minutes}-minute timer keeps running even if you close this page.
            </p>
          )}
          <Button type="submit" className="w-full" disabled={busy || (!account && !name.trim())}>
            {busy ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Starting…
              </>
            ) : (
              "Start exam"
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

export function StudentApp({ examId }: { examId: string }) {
  const [view, setView] = useState<StudentView>({ kind: "loading" });

  const loadTiming = useCallback(async () => {
    try {
      const timing = await fetchExamTiming(examId);
      setView({ kind: "lobby", timing, syncedAt: performance.now() });
    } catch (e) {
      setView(endedFromError(e) ?? { kind: "error", message: "Couldn't load this exam. Check your connection and refresh the page." });
    }
  }, [examId]);

  // A finished exam: forget the attempt (and the password with it).
  const finish = useCallback(
    (next: StudentView) => {
      if (next.kind === "receipt") setStoredReceipt(examId, next.receipt);
      if (next.kind === "receipt" || next.kind === "ended" || next.kind === "not_found") clearStoredAttempt(examId);
      setView(next);
    },
    [examId]
  );

  useEffect(() => {
    const receipt = getStoredReceipt(examId);
    if (receipt) {
      setView({ kind: "receipt", receipt });
      return;
    }
    const stored = getStoredAttempt(examId);
    if (!stored) {
      void loadTiming();
      return;
    }
    // Resume: /start with the same identity returns the same attempt.
    startAttempt(examId, stored.identity, getStudentAccount()?.token)
      .then((attempt) => finish(viewForAttempt(attempt, stored.identity)))
      .catch((e) => {
        const ended = endedFromError(e);
        if (ended) return finish(ended);
        if (e instanceof ApiError) {
          if (e.status === 401 && /student session/i.test(e.message)) clearStudentAccount();
          clearStoredAttempt(examId); // e.g. the password changed: start over from the lobby
          return void loadTiming();
        }
        setView({ kind: "error", message: "Couldn't reach the server. Your saved answers are safe - refresh to try again." });
      });
  }, [examId, loadTiming, finish]);

  const handleStarted = (attempt: AttemptState, identity: StudentIdentity) => {
    const next = viewForAttempt(attempt, identity);
    if (next.kind === "exam") setStoredAttempt(examId, { attemptId: attempt.attempt.attempt_id, identity });
    finish(next);
  };

  switch (view.kind) {
    case "loading":
      return (
        <Shell>
          <div className="flex justify-center py-16 text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin" aria-label="Loading" />
          </div>
        </Shell>
      );
    case "not_found":
      return (
        <Shell>
          <MessageCard icon={<SearchX className="h-6 w-6" />} title="Exam not found">
            <p>Check the link your teacher shared with you.</p>
          </MessageCard>
        </Shell>
      );
    case "error":
      return (
        <Shell>
          <MessageCard icon={<AlertCircle className="h-6 w-6" />} title="Something went wrong" tone="warning">
            <p>{view.message}</p>
            <Button variant="outline" onClick={() => window.location.reload()}>
              Refresh
            </Button>
          </MessageCard>
        </Shell>
      );
    case "lobby":
      return (
        <Shell>
          <Lobby
            examId={examId}
            timing={view.timing}
            syncedAt={view.syncedAt}
            onRefresh={loadTiming}
            onStarted={handleStarted}
            onEnded={finish}
          />
        </Shell>
      );
    case "exam":
      return (
        <StudentExam
          key={view.attempt.attempt.attempt_id}
          examId={examId}
          initial={view.attempt}
          identity={view.identity}
          syncedAt={view.syncedAt}
          onFinished={finish}
        />
      );
    case "receipt":
      return (
        <Shell>
          <SubmissionReceiptView receipt={view.receipt} timeRanOut={view.timeRanOut} />
        </Shell>
      );
    case "ended": {
      const copy = ENDED_COPY[view.reason];
      return (
        <Shell>
          <MessageCard
            icon={view.reason === "submitted" || view.reason === "auto_submitted" ? <CheckCircle2 className="h-6 w-6" /> : <Lock className="h-6 w-6" />}
            title={copy.title}
            tone={copy.tone}
          >
            <p>{copy.body}</p>
          </MessageCard>
        </Shell>
      );
    }
  }
}
