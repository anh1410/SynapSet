import { Fragment, useEffect, useState } from "react";
import { FileStack, Clock, Lock, LockOpen, Pencil, Trash2, XCircle, CalendarClock } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { deleteExam, listExams, updateExam, type Exam, type ExamBucket } from "@/lib/api";

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

export function ExamsPage({ onEdit }: { onEdit: (examId: string) => void }) {
  const [exams, setExams] = useState<Exam[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    listExams()
      .then(setExams)
      .finally(() => setLoading(false));
  }, []);

  const handleClose = async (id: string) => {
    setBusyId(id);
    try {
      const updated = await updateExam(id, { status: "closed" });
      setExams((es) => es.map((e) => (e.id === id ? updated : e)));
    } finally {
      setBusyId(null);
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
                            <Clock className="h-3 w-3" /> {exam.duration_minutes} min
                          </span>
                        )}
                        {exam.go_live_at && (
                          <span className="flex items-center gap-1">
                            <CalendarClock className="h-3 w-3" /> {new Date(exam.go_live_at).toLocaleString()}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button size="sm" variant="outline" onClick={() => onEdit(exam.id)}>
                        <Pencil className="h-3.5 w-3.5" /> Edit
                      </Button>
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
