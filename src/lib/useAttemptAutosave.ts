/**
 * Autosave for a student's timed attempt, used by the Student exam page
 * (src/pages/student/StudentExam.tsx).
 *
 * - Debounces edits and PUTs only the answers that changed since the last
 *   successful save, each with an increasing sequence number. The server
 *   ignores any save older than one it already applied, so a retry that
 *   arrives late after a reconnect can't overwrite newer answers.
 * - On a network failure it keeps the unsaved answers, reports "offline",
 *   and retries with backoff (and immediately when the browser comes back online).
 * - Stops for good once the server says the attempt is over (403/409):
 *   saving never extends the server-side deadline.
 * - Seed it with `saved_answers` / `save_seq` from the start or attempt-status
 *   response so a refreshed page resumes where it left off.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, saveAttemptAnswers } from "@/lib/api";

export type AutosaveStatus = "idle" | "saving" | "saved" | "offline" | "ended";

export function useAttemptAutosave({
  examId,
  attemptId,
  initialSeq = 0,
  debounceMs = 1200,
}: {
  examId: string;
  attemptId: string;
  initialSeq?: number;
  debounceMs?: number;
}) {
  const [status, setStatus] = useState<AutosaveStatus>("idle");
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const pending = useRef<Record<string, string>>({});
  const seq = useRef(initialSeq);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryDelay = useRef(2000);
  const inFlight = useRef(false);
  const ended = useRef(false);

  const flush = useCallback(async () => {
    if (inFlight.current || ended.current || Object.keys(pending.current).length === 0) return;
    const batch = pending.current;
    pending.current = {};
    inFlight.current = true;
    seq.current += 1;
    setStatus("saving");
    let failed = false;
    try {
      const result = await saveAttemptAnswers(examId, attemptId, batch, seq.current);
      seq.current = Math.max(seq.current, result.save_seq);
      retryDelay.current = 2000;
      setLastSavedAt(result.saved_at ? new Date(result.saved_at) : new Date());
      setStatus(Object.keys(pending.current).length ? "saving" : "saved");
    } catch (e) {
      const message = e instanceof ApiError ? e.message : "";
      if (e instanceof ApiError && /closed|Time is up|already submitted|already been submitted/i.test(message)) {
        ended.current = true;
        setStatus("ended");
        return;
      }
      // Network trouble: put the batch back (newer edits win) and retry later with backoff.
      failed = true;
      pending.current = { ...batch, ...pending.current };
      setStatus("offline");
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => void flush(), retryDelay.current);
      retryDelay.current = Math.min(retryDelay.current * 2, 30_000);
    } finally {
      inFlight.current = false;
    }
    // Edits made while this save was in flight go out right away (not after a failure - the backoff timer handles that).
    if (!failed && !ended.current && Object.keys(pending.current).length) {
      void flush();
    }
  }, [examId, attemptId]);

  /** Record an answer change; it's saved after a short pause in typing. */
  const update = useCallback(
    (questionId: string, answer: string) => {
      if (ended.current) return;
      pending.current[questionId] = answer;
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => void flush(), debounceMs);
    },
    [flush, debounceMs]
  );

  useEffect(() => {
    const onOnline = () => void flush();
    window.addEventListener("online", onOnline);
    return () => {
      window.removeEventListener("online", onOnline);
      if (timer.current) clearTimeout(timer.current);
    };
  }, [flush]);

  return { status, lastSavedAt, update, flushNow: flush };
}
