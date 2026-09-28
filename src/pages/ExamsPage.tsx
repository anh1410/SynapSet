import { Fragment, useEffect, useState } from "react";
import { FileStack, Clock, Lock, LockOpen, Pencil, Trash2, XCircle, CalendarClock, BarChart3, KeyRound, FileCheck2, Link2, Check } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { deleteExam, listExams, updateExam, type Exam, type ExamBucket } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";

const bucketOrder: ExamBucket[] = ["live", "upcoming", "draft", "closed"];
const bucketLabels: Record<ExamBucket, string> = {
  live: "Live now",
  upcoming: "Upcoming",
  draft: "Drafts",
  closed: "Closed",
};
const bucketVariant: Record<ExamBucket, "success" | "accent" | "secondary" | "outline"> = {
  live: "success",
  upcoming: "accent",
  draft: "secondary",
  closed: "outline",
};

function relative(iso: string, now: number): string {
  const mins = Math.round((new Date(iso).getTime() - now) / 60000);
  const abs = Math.abs(mins);
  const text = abs < 60 ? `${abs} min` : abs < 48 * 60 ? `${Math.round(abs / 60)} h` : `${Math.round(abs / 1440)} days`;
  return mins >= 0 ? `in ${text}` : `${text} ago`;
}

/** The public link students open to take an exam (see StudentApp). */
const studentExamUrl = (examId: string) => `${window.location.origin}/take/${encodeURIComponent(examId)}`;

const fmt = (iso: string) => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

/** One line saying where the exam is in its schedule and what happens next. */
function ScheduleLine({ exam, now }: { exam: Exam; now: number }) {
  const parts: string[] = [];
  if (exam.bucket === "draft") {
    parts.push(exam.go_live_at ? `Go-live ${fmt(exam.go_live_at)} (not scheduled yet)` : "Not scheduled - set a go-live time to publish");
  } else if (exam.bucket === "upcoming") {
    parts.push(`Opens ${fmt(exam.go_live_at!)} (${relative(exam.go_live_at!, now)})`);
    parts.push(exam.closes_at ? `closes ${fmt(exam.closes_at)}` : "no closing time");
  } else if (exam.bucket === "live") {
    parts.push(exam.closes_at ? `Closes ${fmt(exam.closes_at)} (${relative(exam.closes_at, now)})` : "Open until you close it");
  } else if (exam.closed_by === "schedule" && exam.closes_at) {
    parts.push(`Closed automatically ${fmt(exam.closes_at)}`);
  } else {
    parts.push("Closed by you");
  }
  return (
    <span className="flex items-center gap-1">
      <CalendarClock className="h-3 w-3" /> {parts.join(" · ")}
    </span>
  );
}

export function ExamsPage({
  onEdit,
  onViewResults,
  onViewAnswerKey,
  onReview,
}: {
  onEdit: (examId: string) => void;
  onViewResults: (examId: string) => void;
  onViewAnswerKey: (examId: string) => void;
  onReview: (examId: string) => void;
}) {
  const { activeSubjectId } = useAuth();
  const [exams, setExams] = useState<Exam[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [copiedId, setCopiedId] = useState<string | null>(null);

  useEffect(() => {
    if (!activeSubjectId) return;
    setLoading(true);
    listExams(activeSubjectId)
      .then(setExams)
      .finally(() => setLoading(false));
    // Exams open and close on their own schedule; refresh quietly so the
    // Upcoming / Live / Closed grouping doesn't go stale while the page is open.
    const timer = setInterval(() => {
      setNow(Date.now());
      listExams(activeSubjectId).then(setExams).catch(() => {});
    }, 60_000);
    return () => clearInterval(timer);
  }, [activeSubjectId]);

  const handleClose = async (id: string) => {
    setBusyId(id);
    try {
      const updated = await updateExam(id, { status: "closed" });
      setExams((es) => es.map((e) => (e.id === id ? updated : e)));
    } finally {
      setBusyId(null);
    }
  };

  const handleCopyLink = async (id: string) => {
    const url = studentExamUrl(id);
    try {
      await navigator.clipboard.writeText(url);
      setCopiedId(id);
      setTimeout(() => setCopiedId((c) => (c === id ? null : c)), 2000);
    } catch {
      // Clipboard blocked (e.g. not a secure context): let the teacher copy it by hand.
      window.prompt("Copy this link and share it with your students:", url);
    }
  };

  const handleDelete = async (id: string) => {
    setBusyId(id);
    try {
      await deleteExam(id);
      setExams((es) => es.filter((e) => e.id !== id));
    } finally {
      setBusyId(null);
    }
  };

  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
    );
  }

  const groups = bucketOrder
    .map((bucket) => ({ bucket, exams: exams.filter((e) => e.bucket === bucket) }))
    .filter((g) => g.exams.length > 0);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-foreground">Exams</h1>
        <p className="text-sm text-muted-foreground">Every quiz you've built — upcoming, live, and closed.</p>
      </div>

      {exams.length === 0 ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState
              icon={FileStack}
              title="No exams yet"
              description='Build one in Exam Builder, then it lands here for scheduling and later editing.'
              className="m-6"
            />
          </CardContent>
        </Card>
      ) : (
        groups.map((group) => (
          <Fragment key={group.bucket}>
            <p className="pt-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              {bucketLabels[group.bucket]} ({group.exams.length})
            </p>
            <div className="space-y-3">
              {group.exams.map((exam) => (
                <Card key={exam.id}>
                  <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm font-semibold text-foreground">{exam.name}</p>
                        <Badge variant={bucketVariant[exam.bucket]}>{bucketLabels[exam.bucket]}</Badge>
                        {exam.exam_type !== "QUIZ" && <Badge variant="default">{exam.exam_type}</Badge>}
                        {exam.password ? (
                          <Lock className="h-3.5 w-3.5 text-muted-foreground" />
                        ) : (
                          <LockOpen className="h-3.5 w-3.5 text-muted-foreground" />
                        )}
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                        <span>
                          {exam.question_ids.length} question{exam.question_ids.length !== 1 && "s"} · {exam.total_marks} marks
                        </span>
                        {exam.duration_minutes != null && (
                          <span className="flex items-center gap-1">
                            <Clock className="h-3 w-3" /> {exam.duration_minutes} min per student
                          </span>
                        )}
                        <ScheduleLine exam={exam} now={now} />
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {(exam.bucket === "live" || exam.bucket === "upcoming") && (
                        <Button size="sm" variant="outline" onClick={() => handleCopyLink(exam.id)} title={studentExamUrl(exam.id)}>
                          {copiedId === exam.id ? <Check className="h-3.5 w-3.5 text-success" /> : <Link2 className="h-3.5 w-3.5" />}
                          {copiedId === exam.id ? "Copied" : "Copy student link"}
                        </Button>
                      )}
                      <Button size="sm" variant="outline" onClick={() => onEdit(exam.id)}>
                        <Pencil className="h-3.5 w-3.5" /> Edit
                      </Button>
                      {(exam.bucket === "live" || exam.bucket === "closed") && (
                        <Button size="sm" variant="outline" onClick={() => onViewResults(exam.id)}>
                          <BarChart3 className="h-3.5 w-3.5" /> Results
                        </Button>
                      )}
                      {exam.question_ids.length > 0 && (
                        <Button size="sm" variant="outline" onClick={() => onReview(exam.id)}>
                          <FileCheck2 className="h-3.5 w-3.5" /> Review & export
                        </Button>
                      )}
                      {exam.question_ids.length > 0 && (
                        <Button size="sm" variant="outline" onClick={() => onViewAnswerKey(exam.id)}>
                          <KeyRound className="h-3.5 w-3.5" /> Answer Key
                        </Button>
                      )}
                      {exam.bucket !== "closed" && exam.bucket !== "draft" && (
                        <Button size="sm" variant="ghost" onClick={() => handleClose(exam.id)} disabled={busyId === exam.id}>
                          <XCircle className="h-3.5 w-3.5" /> Close
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-destructive hover:text-destructive"
                        onClick={() => handleDelete(exam.id)}
                        disabled={busyId === exam.id}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </Fragment>
        ))
      )}
    </div>
  );
}
