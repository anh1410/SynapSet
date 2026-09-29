import { useEffect, useState } from "react";
import { Check, Copy, RefreshCw, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { fetchJoinCode, rotateJoinCode, type JoinCodeInfo } from "@/lib/api";

/** The active subject's join code for the student dashboard (/student),
 *  how many students have joined, and a way to rotate the code. */
export function StudentAccessCard({ subjectId }: { subjectId: string }) {
  const [info, setInfo] = useState<JoinCodeInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const portalUrl = `${window.location.origin}/student`;

  useEffect(() => {
    setInfo(null);
    fetchJoinCode(subjectId).then(setInfo).catch(() => {});
  }, [subjectId]);

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt("Copy this and share it with your students:", text);
    }
  };

  const rotate = async () => {
    if (!window.confirm("Make a new join code? The current code stops working; students who already joined stay enrolled.")) return;
    setBusy(true);
    try {
      setInfo(await rotateJoinCode(subjectId));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-4 p-5">
        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground">Student join code</p>
          <div className="flex items-center gap-2">
            <span className="font-mono text-2xl font-semibold tracking-[0.2em] text-foreground">{info?.join_code ?? "·······"}</span>
            {info && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => void copy(`Join my subject on SynapSet: ${portalUrl} - join code ${info.join_code}`)}
                aria-label="Copy join instructions"
              >
                {copied ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
              </Button>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            Students sign up at <span className="font-medium text-foreground">{portalUrl}</span> and enter this code to see this subject's exams and their results.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {info && (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Users className="h-3.5 w-3.5" /> {info.enrolled_count} student{info.enrolled_count !== 1 && "s"} joined
            </span>
          )}
          <Button size="sm" variant="outline" onClick={() => void rotate()} disabled={busy || !info}>
            <RefreshCw className="h-3.5 w-3.5" /> New code
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
