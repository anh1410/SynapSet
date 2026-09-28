import { CheckCircle2, Hourglass } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { SubmissionReceipt } from "@/lib/api";

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** Auto-graded score, plus the marks still with the teacher (never shown as zero).
 *  No per-question marks, correctness or answer key. */
export function SubmissionReceiptView({ receipt, timeRanOut }: { receipt: SubmissionReceipt; timeRanOut?: boolean }) {
  const hasAuto = receipt.auto_graded_max_marks > 0;
  const hasPending = receipt.pending_review_count > 0;

  return (
    <Card className="mx-auto max-w-lg">
      <CardContent className="space-y-6 p-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-success/10 text-success">
            <CheckCircle2 className="h-6 w-6" />
          </div>
          <h1 className="text-base font-semibold text-foreground">Exam submitted</h1>
          <p className="text-xs text-muted-foreground">
            {timeRanOut && "Time ran out, so your answers were submitted automatically. "}
            Submitted {new Date(receipt.submitted_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })} ·{" "}
            {receipt.student_name}
            {receipt.student_identifier && ` (${receipt.student_identifier})`}
          </p>
        </div>

        <div className="rounded-xl border border-border bg-secondary/40 p-5 text-center">
          {hasAuto ? (
            <>
              <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Score so far</p>
              <p className="mt-1 text-3xl font-semibold tabular-nums text-foreground" aria-label={`${receipt.auto_graded_marks} out of ${receipt.auto_graded_max_marks} marks`}>
                {receipt.auto_graded_marks}
                <span className="text-lg text-muted-foreground"> / {receipt.auto_graded_max_marks}</span>
              </p>
              {hasPending && (
                <p className="mt-1 text-sm font-medium text-warning">+ {plural(receipt.pending_review_marks, "mark")} pending teacher review</p>
              )}
            </>
          ) : (
            <>
              <p className="text-sm font-medium text-warning">All {plural(receipt.pending_review_marks, "mark")} pending teacher review</p>
              <p className="mt-1 text-xs text-muted-foreground">Your teacher will grade your answers.</p>
            </>
          )}
          <p className="mt-3 text-xs text-muted-foreground">Paper total: {plural(receipt.total_max_marks, "mark")}</p>
        </div>

        <div className="space-y-2">
          <p className="text-xs font-medium text-foreground">Questions</p>
          <ul className="divide-y divide-border rounded-lg border border-border bg-white">
            {receipt.answers.map((a, i) => (
              <li key={a.question_id} className="flex items-center justify-between px-3 py-2 text-sm">
                <span className="text-foreground">Question {i + 1}</span>
                {a.status === "pending_review" ? (
                  <Badge variant="warning">
                    <Hourglass className="h-3 w-3" /> Pending teacher review
                  </Badge>
                ) : (
                  <Badge variant="secondary">Auto-graded</Badge>
                )}
              </li>
            ))}
          </ul>
          {hasPending && (
            <p className="text-[11px] text-muted-foreground">
              Written answers are graded by your teacher, so your final score may go up once they're reviewed.
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
