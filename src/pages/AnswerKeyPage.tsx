import { useEffect, useState } from "react";
import { ArrowLeft, KeyRound } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { BLOOM_LABELS, QUESTION_TYPE_LABELS, getExam, type Exam, type Question, isCodingType } from "@/lib/api";
import { cn } from "@/lib/utils";

export function AnswerKeyPage({ examId, onBack }: { examId: string; onBack: () => void }) {
  const [exam, setExam] = useState<Exam | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getExam(examId).then(({ exam, questions }) => {
      setExam(exam);
      setQuestions(questions);
      setLoading(false);
    });
  }, [examId]);

  if (loading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-10 w-64" />
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to Exams
      </button>

      <div className="flex items-center gap-2">
        <KeyRound className="h-4.5 w-4.5 text-primary" />
        <div>
          <h1 className="text-lg font-semibold text-foreground">{exam?.name} — Answer Key</h1>
          <p className="text-sm text-muted-foreground">
            {questions.length} question{questions.length !== 1 && "s"} · {exam?.total_marks} marks
          </p>
        </div>
      </div>

      <div className="space-y-3">
        {questions.map((q, idx) => (
          <Card key={q.id}>
            <CardContent className="space-y-2 p-4">
              <p className="whitespace-pre-wrap text-sm text-foreground">
                {idx + 1}. {q.text}
              </p>
              {isCodingType(q.question_type) && q.starter_code && (
                <>
                  <p className="text-[11px] font-semibold text-muted-foreground">Starter Code</p>
                  <pre className="overflow-x-auto rounded-md bg-slate-900 p-3 text-xs text-slate-100">
                    <code>{q.starter_code}</code>
                  </pre>
                </>
              )}
              {(q.question_type === "mcq" || q.question_type === "fill_in_blank") && q.options && (
                <ul className="space-y-0.5 text-xs text-muted-foreground">
                  {q.options.map((opt, oi) => (
                    <li key={oi} className={cn(opt === q.correct_answer && "font-medium text-success")}>
                      {String.fromCharCode(97 + oi)}) {opt}
                    </li>
                  ))}
                </ul>
              )}
              {q.correct_answer && (
                <div className="rounded-md border border-success/30 bg-success/[0.04] p-2.5">
                  <p className="text-[11px] font-semibold text-success">
                    {isCodingType(q.question_type) ? "Reference Solution" : "Answer"}
                  </p>
                  {isCodingType(q.question_type) ? (
                    <pre className="mt-1 overflow-x-auto rounded-md bg-slate-900 p-3 text-xs text-slate-100">
                      <code>{q.correct_answer}</code>
                    </pre>
                  ) : (
                    <p className="mt-0.5 whitespace-pre-wrap text-xs text-foreground">{q.correct_answer}</p>
                  )}
                </div>
              )}
              {isCodingType(q.question_type) && q.test_cases && q.test_cases.length > 0 && (
                <div className="rounded-md border border-border p-2.5">
                  <p className="text-[11px] font-semibold text-muted-foreground">
                    Hidden test cases ({q.test_cases.length}) - students never see these
                  </p>
                  <table className="mt-1.5 w-full text-left font-mono text-[11px]">
                    <thead className="text-muted-foreground">
                      <tr>
                        <th className="w-1/2 pb-1 font-medium">Input</th>
                        <th className="pb-1 font-medium">Expected output</th>
                      </tr>
                    </thead>
                    <tbody>
                      {q.test_cases.map((t, ti) => (
                        <tr key={ti} className="border-t border-border align-top">
                          <td className="whitespace-pre-wrap py-1 pr-2">{t.input || "(no input)"}</td>
                          <td className="whitespace-pre-wrap py-1">{t.expected_output}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <div className="flex flex-wrap gap-1.5">
                <Badge variant="outline">{QUESTION_TYPE_LABELS[q.question_type]}</Badge>
                {q.scenario_based && <Badge variant="default">Interview scenario</Badge>}
                {q.origin === "manual" && <Badge variant="secondary">Teacher-written</Badge>}
                <Badge variant="outline">{q.marks} marks</Badge>
                <Badge variant="accent">{BLOOM_LABELS[q.bloom_level]}</Badge>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Button variant="outline" onClick={onBack}>
        <ArrowLeft className="h-3.5 w-3.5" /> Back to Exams
      </Button>
    </div>
  );
}
