import { useEffect, useRef, useState } from "react";

/**
 * Counts down from a "seconds remaining" value the server computed with its
 * own clock. The count is anchored to the monotonic local clock at the moment
 * the response arrived, so a wrong device clock (or the student changing it
 * mid-exam) can't move the deadline. Pass a new `syncedAt` whenever a fresh
 * server value arrives, even if the number is the same.
 *
 * Returns whole seconds left (never negative), or null when there's no limit.
 */
export function useServerCountdown(seconds: number | null, syncedAt: number): number | null {
  const endAt = useRef<number | null>(null);
  const [left, setLeft] = useState<number | null>(seconds);

  useEffect(() => {
    if (seconds == null) {
      endAt.current = null;
      setLeft(null);
      return;
    }
    endAt.current = performance.now() + seconds * 1000;
    const tick = () => {
      if (endAt.current == null) return;
      setLeft(Math.max(0, Math.ceil((endAt.current - performance.now()) / 1000)));
    };
    tick();
    const id = setInterval(tick, 250);
    return () => clearInterval(id);
  }, [seconds, syncedAt]);

  return left;
}

/** 3725 -> "1:02:05", 125 -> "2:05". */
export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}
