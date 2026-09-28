import type { KeyboardEvent } from "react";
import { RotateCcw } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { PublicQuestion, QuestionType } from "@/lib/api";
import { cn } from "@/lib/utils";

const STUDENT_TYPE_LABELS: Record<QuestionType, string> = {
  mcq: "Multiple choice",
  fill_in_blank: "Fill in the blank",
  short_answer: "Short answer",
  long_answer: "Long answer",
  numerical: "Numerical",
  code_fix: "Fix the code",
};

const textareaClass = cn(
  "w-full rounded-lg border border-input bg-white px-3 py-2 text-sm shadow-subtle transition-all duration-200",
  "placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:border-primary",
  "disabled:cursor-not-allowed disabled:opacity-50"
);

/** Answered = something meaningful was entered (unchanged starter code doesn't count). */
export function isAnswered(q: PublicQuestion, answer: string | undefined): boolean {
  if (!answer || !answer.trim()) return false;
  return !(q.question_type === "code_fix" && q.starter_code != null && answer === q.starter_code);
}

/** Tab inserts spaces in the code editor instead of leaving the field. */
function handleCodeTab(e: KeyboardEvent<HTMLTextAreaElement>, onChange: (value: string) => void) {
  if (e.key !== "Tab" || e.shiftKey) return;
  e.preventDefault();
  const el = e.currentTarget;
  const { selectionStart: start, selectionEnd: end, value } = el;
  const next = value.slice(0, start) + "    " + value.slice(end);
  onChange(next);
  requestAnimationFrame(() => el.setSelectionRange(start + 4, start + 4));
}

function Choices({ q, answer, disabled, onChange }: { q: PublicQuestion; answer: string; disabled: boolean; onChange: (v: string) => void }) {
  return (
    <div role="radiogroup" aria-label="Answer options" className="space-y-2">
      {(q.options ?? []).map((option, i) => {
        const selected = answer === option;
        return (
          <label
            key={i}
            className={cn(
              "flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 text-sm transition-colors",
              selected ? "border-primary bg-primary/5" : "border-border hover:bg-secondary/50",
              disabled && "cursor-not-allowed opacity-60"
            )}
          >
            <input
              type="radio"
              name={`q-${q.id}`}
              value={option}
              className="mt-0.5 h-4 w-4 accent-primary"
              checked={selected}
              disabled={disabled}
              onChange={() => onChange(option)}
            />
            <span className="whitespace-pre-wrap text-foreground">{option}</span>
          </label>
        );
      })}
    </div>
  );
}

export function QuestionCard({
  q,
  index,
  answer,
  disabled,
  onChange,
}: {
  q: PublicQuestion;
  index: number;
  answer: string | undefined;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const value = answer ?? "";
  const answered = isAnswered(q, answer);
  const inputId = `answer-${q.id}`;
  const codeValue = answer ?? q.starter_code ?? "";

  return (
    <Card id={`question-${q.id}`} className="scroll-mt-28">
      <CardContent className="space-y-4 p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-foreground">Question {index + 1}</span>
            <Badge variant="secondary">{STUDENT_TYPE_LABELS[q.question_type]}</Badge>
          </div>
          <div className="flex items-center gap-2">
            {answered ? <Badge variant="success">Answered</Badge> : <Badge variant="outline">Not answered</Badge>}
            <span className="text-xs font-medium text-muted-foreground">
              {q.marks} mark{q.marks !== 1 && "s"}
            </span>
          </div>
        </div>

        <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">{q.text}</p>

        {q.question_type === "mcq" || (q.question_type === "fill_in_blank" && q.options && q.options.length > 0) ? (
          <Choices q={q} answer={value} disabled={disabled} onChange={onChange} />
        ) : q.question_type === "fill_in_blank" || q.question_type === "numerical" ? (
          <div className="max-w-sm space-y-1">
            <label htmlFor={inputId} className="sr-only">
              Your answer
            </label>
            <Input
              id={inputId}
              value={value}
              disabled={disabled}
              inputMode={q.question_type === "numerical" ? "decimal" : "text"}
              placeholder={q.question_type === "numerical" ? "Enter a number" : "Your answer"}
              autoComplete="off"
              onChange={(e) => onChange(e.target.value)}
            />
          </div>
        ) : q.question_type === "code_fix" ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label htmlFor={inputId} className="text-xs font-medium text-muted-foreground">
                Your code{q.code_language ? ` (${q.code_language})` : ""}
              </label>
              {q.starter_code != null && codeValue !== q.starter_code && (
                <Button size="sm" variant="ghost" disabled={disabled} onClick={() => onChange(q.starter_code ?? "")}>
                  <RotateCcw className="h-3.5 w-3.5" /> Reset to starter code
                </Button>
              )}
            </div>
            <textarea
              id={inputId}
              value={codeValue}
              disabled={disabled}
              spellCheck={false}
              autoCapitalize="off"
              autoCorrect="off"
              rows={Math.min(24, Math.max(8, codeValue.split("\n").length + 2))}
              className={cn(textareaClass, "font-mono text-[13px] leading-5")}
              onKeyDown={(e) => handleCodeTab(e, onChange)}
              onChange={(e) => onChange(e.target.value)}
            />
          </div>
        ) : (
          <div className="space-y-1">
            <label htmlFor={inputId} className="sr-only">
              Your answer
            </label>
            <textarea
              id={inputId}
              value={value}
              disabled={disabled}
              rows={q.question_type === "long_answer" ? 10 : 4}
              placeholder="Write your answer…"
              className={textareaClass}
              onChange={(e) => onChange(e.target.value)}
            />
            <p className="text-[11px] text-muted-foreground">Your teacher will review this answer.</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
