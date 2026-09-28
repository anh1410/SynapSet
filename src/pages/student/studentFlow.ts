/** The student interface's screens and how server responses map onto them. */
import { ApiError, type AttemptState, type ExamTiming, type StudentIdentity, type SubmissionReceipt } from "@/lib/api";

export type EndedReason = "submitted" | "auto_submitted" | "time_up" | "closed";

export type StudentView =
  | { kind: "loading" }
  | { kind: "not_found" }
  | { kind: "lobby"; timing: ExamTiming; syncedAt: number }
  | { kind: "exam"; attempt: AttemptState; identity: StudentIdentity; syncedAt: number }
  | { kind: "receipt"; receipt: SubmissionReceipt; timeRanOut?: boolean }
  | { kind: "ended"; reason: EndedReason }
  | { kind: "error"; message: string };

/** Maps the server's "this attempt/exam is over" refusals to an ended screen. */
export function endedFromError(e: unknown): StudentView | null {
  if (!(e instanceof ApiError)) return null;
  const msg = e.message;
  if (e.status === 404) return { kind: "not_found" };
  if (/submitted automatically/i.test(msg)) return { kind: "ended", reason: "auto_submitted" };
  if (e.status === 409 && /already submitted/i.test(msg)) return { kind: "ended", reason: "submitted" };
  if (e.status === 403 && /time is up/i.test(msg)) return { kind: "ended", reason: "time_up" };
  if (e.status === 403 && /closed/i.test(msg)) return { kind: "ended", reason: "closed" };
  return null;
}

/** What to show for an attempt the server returned (start/resume/status). */
export function viewForAttempt(attempt: AttemptState, identity: StudentIdentity): StudentView {
  if (attempt.attempt.submitted) return { kind: "ended", reason: "submitted" };
  if (attempt.exam) return { kind: "exam", attempt, identity, syncedAt: performance.now() };
  if (attempt.timing.state === "closed") return { kind: "ended", reason: "closed" };
  return { kind: "ended", reason: "time_up" };
}
