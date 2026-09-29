/**
 * Student dashboard at /student: student accounts (separate from teacher
 * login), joining subjects with a teacher's join code, the exams of joined
 * subjects with this student's own status, and their results.
 *
 * Exams are taken in the existing /take/<examId> flow; when a student is
 * signed in there, the attempt is linked to their account, which is what
 * makes its result appear here. Results show the final score and grade only
 * once the teacher has finished grading.
 */
import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  AlertCircle,
  BookOpen,
  CalendarClock,
  CheckCircle2,
  Clock,
  GraduationCap,
  Hourglass,
  Loader2,
  Lock,
  LogOut,
  PlayCircle,
  Plus,
  RotateCw,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  ApiError,
  joinSubject,
  leaveSubject,
  listMyExams,
  listMyResults,
  listMySubjects,
  studentLogin,
  studentMe,
  studentSignup,
  type MyExamStatus,
  type StudentExamRow,
  type StudentResult,
  type StudentSubject,
} from "@/lib/api";
import { clearStudentAccount, getStudentAccount, setStudentAccount, type StudentAccount } from "@/lib/studentAccount";
import { formatClock, useServerCountdown } from "@/lib/useServerCountdown";
import { cn } from "@/lib/utils";

const REFRESH_MS = 30_000;
const fmtDateTime = (iso: string) => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
const takeUrl = (examId: string) => `/take/${encodeURIComponent(examId)}`;

// ---------- sign in / sign up ----------

function StudentAuthPage({ onSignedIn }: { onSignedIn: (account: StudentAccount) => void }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [name, setName] = useState("");
  const [roll, setRoll] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res =
        mode === "login"
          ? await studentLogin(email, password)
          : await studentSignup({ name: name.trim(), roll_number: roll.trim(), email: email.trim(), password });
      onSignedIn({ token: res.access_token, student: res.student });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the server. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const tab = (value: "login" | "signup", label: string) => (
    <button
      type="button"
      onClick={() => {
        setMode(value);
        setError(null);
      }}
      className={cn(
        "flex-1 rounded-md py-1.5 transition-colors",
        mode === value ? "bg-white text-foreground shadow-sm" : "text-muted-foreground"
      )}
    >
      {label}
    </button>
  );

  return (
    <div className="flex min-h-screen items-center justify-center bg-secondary/40 px-4 py-8">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-2 text-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
            <GraduationCap className="h-6 w-6" />
          </div>
          <h1 className="text-lg font-semibold text-foreground">SynapSet for students</h1>
          <p className="text-xs text-muted-foreground">Your exams and results in one place</p>
        </div>
        <Card>
          <CardHeader>
            <div className="flex rounded-lg bg-secondary p-1 text-xs font-medium">
              {tab("login", "Log in")}
              {tab("signup", "Sign up")}
            </div>
            <CardTitle className="pt-2">{mode === "login" ? "Welcome back" : "Create your student account"}</CardTitle>
            <CardDescription>
              {mode === "login" ? "Log in with your student account" : "Use the roll number your school gave you"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-3" onSubmit={handleSubmit}>
              {mode === "signup" && (
                <>
                  <div>
                    <label htmlFor="st-name" className="mb-1 block text-xs font-medium text-foreground">
                      Full name
                    </label>
                    <Input id="st-name" value={name} onChange={(e) => setName(e.target.value)} required autoComplete="name" />
                  </div>
                  <div>
                    <label htmlFor="st-roll" className="mb-1 block text-xs font-medium text-foreground">
                      Roll number
                    </label>
                    <Input id="st-roll" value={roll} onChange={(e) => setRoll(e.target.value)} required autoComplete="off" />
                  </div>
                </>
              )}
              <div>
                <label htmlFor="st-email" className="mb-1 block text-xs font-medium text-foreground">
                  Email
                </label>
                <Input id="st-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
              </div>
              <div>
                <label htmlFor="st-password" className="mb-1 block text-xs font-medium text-foreground">
                  Password
                </label>
                <Input
                  id="st-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                />
              </div>
              {error && (
                <p className="flex items-center gap-1.5 text-xs text-destructive" role="alert">
                  <AlertCircle className="h-3.5 w-3.5 shrink-0" /> {error}
                </p>
              )}
              <Button type="submit" className="w-full" disabled={busy}>
                {busy ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}
              </Button>
            </form>
          </CardContent>
        </Card>
        <p className="mt-4 text-center text-xs text-muted-foreground">
          Teacher?{" "}
          <a href="/" className="font-medium text-primary hover:underline">
            Sign in to the teacher app
          </a>
        </p>
      </div>
    </div>
  );
}

// ---------- dashboard pieces ----------

const STATUS_BADGE: Record<MyExamStatus, { label: string; variant: "success" | "warning" | "secondary" | "outline" | "default" }> = {
  not_started: { label: "Not started", variant: "outline" },
  in_progress: { label: "In progress", variant: "warning" },
  submitted: { label: "Submitted", variant: "success" },
  auto_submitted: { label: "Submitted automatically", variant: "success" },
  not_submitted: { label: "Not submitted", variant: "secondary" },
  missed: { label: "Missed", variant: "secondary" },
};

function Section({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
        {count != null && ` (${count})`}
      </h2>
      {children}
    </section>
  );
}

function ExamCard({ exam, syncedAt }: { exam: StudentExamRow; syncedAt: number }) {
  const opensIn = useServerCountdown(exam.state === "upcoming" ? exam.opens_in_seconds : null, syncedAt);
  const timeLeft = useServerCountdown(exam.my_status === "in_progress" ? exam.remaining_seconds : null, syncedAt);
  const canStart = exam.state === "live" && (exam.my_status === "not_started" || exam.my_status === "in_progress");
  const status = STATUS_BADGE[exam.my_status];

  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-foreground">{exam.name}</p>
            {exam.exam_type !== "QUIZ" && <Badge variant="default">{exam.exam_type}</Badge>}
            {exam.state !== "upcoming" && <Badge variant={status.variant}>{status.label}</Badge>}
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <BookOpen className="h-3 w-3" /> {exam.subject_name}
            </span>
            <span>
              {exam.question_count} question{exam.question_count !== 1 && "s"} · {exam.total_marks} marks
            </span>
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" /> {exam.duration_minutes != null ? `${exam.duration_minutes} min` : "No time limit"}
            </span>
            {exam.password_required && exam.state !== "closed" && (
              <span className="flex items-center gap-1" title="Your teacher will give you the exam password">
                <Lock className="h-3 w-3" /> Password needed
              </span>
            )}
          </div>
          <p className="flex items-center gap-1 text-xs text-muted-foreground">
            <CalendarClock className="h-3 w-3" />
            {exam.state === "upcoming" && exam.go_live_at && (
              <>
                Opens {fmtDateTime(exam.go_live_at)}
                {opensIn != null && <span className="font-mono tabular-nums text-foreground">· in {formatClock(opensIn)}</span>}
              </>
            )}
            {exam.state === "live" && (exam.closes_at ? `Closes ${fmtDateTime(exam.closes_at)}` : "Open now")}
            {exam.state === "closed" &&
              (exam.submitted_at ? `Submitted ${fmtDateTime(exam.submitted_at)}` : exam.closes_at ? `Closed ${fmtDateTime(exam.closes_at)}` : "Closed")}
          </p>
        </div>
        {canStart ? (
          <Button size="sm" onClick={() => window.location.assign(takeUrl(exam.id))}>
            <PlayCircle className="h-3.5 w-3.5" />
            {exam.my_status === "in_progress" ? `Resume${timeLeft != null ? ` · ${formatClock(timeLeft)} left` : ""}` : "Start exam"}
          </Button>
        ) : exam.state === "upcoming" ? (
          <Badge variant="accent">Upcoming</Badge>
        ) : null}
      </CardContent>
    </Card>
  );
}

function ResultCard({ result }: { result: StudentResult }) {
  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-foreground">{result.exam_name}</p>
            {result.exam_type && result.exam_type !== "QUIZ" && <Badge variant="default">{result.exam_type}</Badge>}
          </div>
          <p className="text-xs text-muted-foreground">
            {result.subject_name && `${result.subject_name} · `}Submitted {fmtDateTime(result.submitted_at)}
            {result.auto_submitted && " (automatically)"}
          </p>
        </div>
        {result.status === "graded" && result.final_marks != null ? (
          <div className="text-right">
            <p className="text-lg font-semibold tabular-nums text-foreground">
              {result.final_marks}
              <span className="text-sm text-muted-foreground"> / {result.total_max_marks}</span>
            </p>
            <p className="flex items-center justify-end gap-1.5 text-xs text-muted-foreground">
              {result.final_percent}%{result.grade && <Badge variant="success">{result.grade}</Badge>}
            </p>
          </div>
        ) : (
          <div className="text-right">
            <p className="text-sm font-semibold tabular-nums text-foreground">
              {result.graded_marks}
              <span className="text-muted-foreground"> / {result.graded_max_marks} so far</span>
            </p>
            <p className="flex items-center justify-end gap-1 text-xs text-warning">
              <Hourglass className="h-3 w-3" /> + {result.pending_review_marks} mark{result.pending_review_marks !== 1 && "s"} pending teacher review
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Dashboard({ account, onSignOut }: { account: StudentAccount; onSignOut: () => void }) {
  const [subjects, setSubjects] = useState<StudentSubject[] | null>(null);
  const [exams, setExams] = useState<StudentExamRow[]>([]);
  const [results, setResults] = useState<StudentResult[]>([]);
  const [syncedAt, setSyncedAt] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [joinError, setJoinError] = useState<string | null>(null);
  const [joining, setJoining] = useState(false);

  const load = useCallback(async () => {
    try {
      const [subs, examList, res] = await Promise.all([
        listMySubjects(account.token),
        listMyExams(account.token),
        listMyResults(account.token),
      ]);
      setSubjects(subs);
      setExams(examList.exams);
      setResults(res);
      setSyncedAt(performance.now());
      setLoadError(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return onSignOut();
      setLoadError("Couldn't refresh your dashboard. Check your connection.");
    }
  }, [account.token, onSignOut]);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), REFRESH_MS);
    const onVisible = () => document.visibilityState === "visible" && void load();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [load]);

  const handleJoin = async (e: FormEvent) => {
    e.preventDefault();
    if (!code.trim()) return;
    setJoining(true);
    setJoinError(null);
    try {
      await joinSubject(account.token, code);
      setCode("");
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return onSignOut();
      setJoinError(err instanceof ApiError ? err.message : "Couldn't reach the server.");
    } finally {
      setJoining(false);
    }
  };

  const handleLeave = async (subject: StudentSubject) => {
    if (!window.confirm(`Leave ${subject.name}? Its exams will no longer appear here.`)) return;
    try {
      await leaveSubject(account.token, subject.id);
      await load();
    } catch {
      setLoadError("Couldn't leave the subject. Try again.");
    }
  };

  const live = exams.filter((e) => e.state === "live");
  const upcoming = exams.filter((e) => e.state === "upcoming");
  const past = exams.filter((e) => e.state === "closed").reverse();
  const { student } = account;

  return (
    <div className="min-h-screen bg-secondary/40">
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-3 px-4">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <GraduationCap className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-foreground">{student.name}</p>
            <p className="truncate text-[11px] text-muted-foreground">Roll {student.roll_number}</p>
          </div>
          <Button size="sm" variant="ghost" onClick={() => void load()} aria-label="Refresh">
            <RotateCw className="h-3.5 w-3.5" />
          </Button>
          <Button size="sm" variant="outline" onClick={onSignOut}>
            <LogOut className="h-3.5 w-3.5" /> Sign out
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-8 px-4 py-6">
        {loadError && (
          <p className="flex items-center gap-2 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning" role="alert">
            <AlertCircle className="h-4 w-4 shrink-0" /> {loadError}
          </p>
        )}

        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-semibold text-foreground">My subjects</p>
              {subjects?.map((s) => (
                <span key={s.id} className="inline-flex items-center gap-1 rounded-full border border-border bg-secondary/60 py-0.5 pl-2.5 pr-1 text-xs">
                  {s.name}
                  {s.teacher_name && <span className="text-muted-foreground">· {s.teacher_name}</span>}
                  <button
                    onClick={() => void handleLeave(s)}
                    className="rounded-full p-0.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
                    aria-label={`Leave ${s.name}`}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
            <form className="flex max-w-md gap-2" onSubmit={handleJoin}>
              <label htmlFor="join-code" className="sr-only">
                Join code
              </label>
              <Input
                id="join-code"
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                placeholder="Enter a join code from your teacher"
                autoComplete="off"
                className="font-mono tracking-wider placeholder:font-sans placeholder:tracking-normal"
              />
              <Button type="submit" variant="outline" disabled={joining || !code.trim()}>
                {joining ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />} Join
              </Button>
            </form>
            {joinError && (
              <p className="flex items-center gap-1.5 text-xs text-destructive" role="alert">
                <AlertCircle className="h-3.5 w-3.5" /> {joinError}
              </p>
            )}
          </CardContent>
        </Card>

        {subjects === null ? (
          <div className="flex justify-center py-10 text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin" aria-label="Loading" />
          </div>
        ) : subjects.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center gap-2 p-8 text-center">
              <BookOpen className="h-8 w-8 text-muted-foreground" />
              <p className="text-sm font-medium text-foreground">You haven't joined any subjects yet</p>
              <p className="text-xs text-muted-foreground">Ask your teacher for their subject's join code and enter it above.</p>
            </CardContent>
          </Card>
        ) : (
          <>
            <Section title="Live now" count={live.length}>
              {live.length ? live.map((e) => <ExamCard key={e.id} exam={e} syncedAt={syncedAt} />) : <Empty text="No exams are open right now." />}
            </Section>
            <Section title="Upcoming" count={upcoming.length}>
              {upcoming.length ? upcoming.map((e) => <ExamCard key={e.id} exam={e} syncedAt={syncedAt} />) : <Empty text="Nothing scheduled yet." />}
            </Section>
            <Section title="Results" count={results.length}>
              {results.length ? (
                results.map((r) => <ResultCard key={r.submission_id} result={r} />)
              ) : (
                <Empty text="Results for exams you take from this dashboard will appear here." />
              )}
            </Section>
            {past.length > 0 && (
              <Section title="Past exams" count={past.length}>
                {past.map((e) => (
                  <ExamCard key={e.id} exam={e} syncedAt={syncedAt} />
                ))}
              </Section>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <p className="flex items-center gap-2 rounded-lg border border-dashed border-border bg-white/60 px-4 py-3 text-xs text-muted-foreground">
      <CheckCircle2 className="h-3.5 w-3.5" /> {text}
    </p>
  );
}

export function StudentPortal() {
  const [account, setAccount] = useState<StudentAccount | null>(() => getStudentAccount());

  // Re-check a stored session once on load (it may have expired).
  const [initialToken] = useState(() => account?.token);
  useEffect(() => {
    if (!initialToken) return;
    studentMe(initialToken).catch((e) => {
      if (e instanceof ApiError && e.status === 401) {
        clearStudentAccount();
        setAccount(null);
      }
    });
  }, [initialToken]);

  const signIn = (next: StudentAccount) => {
    setStudentAccount(next);
    setAccount(next);
  };
  const signOut = useCallback(() => {
    clearStudentAccount();
    setAccount(null);
  }, []);

  return account ? <Dashboard account={account} onSignOut={signOut} /> : <StudentAuthPage onSignedIn={signIn} />;
}
