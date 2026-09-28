import { CheckCircle2, CloudOff, Loader2, Lock } from "lucide-react";
import type { AutosaveStatus as Status } from "@/lib/useAttemptAutosave";
import { cn } from "@/lib/utils";

/** Small "Saved / Saving... / Connection lost" indicator for a student's
 *  attempt, driven by useAttemptAutosave. Shown in the Student exam header. */
export function AutosaveStatus({ status, lastSavedAt, className }: { status: Status; lastSavedAt: Date | null; className?: string }) {
  const base = cn("inline-flex items-center gap-1.5 text-xs", className);
  switch (status) {
    case "saving":
      return (
        <span className={cn(base, "text-muted-foreground")} role="status" aria-live="polite">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Saving...
        </span>
      );
    case "saved":
      return (
        <span className={cn(base, "text-success")} role="status" aria-live="polite">
          <CheckCircle2 className="h-3.5 w-3.5" /> Saved{lastSavedAt && ` ${lastSavedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`}
        </span>
      );
    case "offline":
      return (
        <span className={cn(base, "font-medium text-warning")} role="status" aria-live="assertive">
          <CloudOff className="h-3.5 w-3.5" /> Connection lost - your answers will be saved when you're back online
        </span>
      );
    case "ended":
      return (
        <span className={cn(base, "text-muted-foreground")} role="status">
          <Lock className="h-3.5 w-3.5" /> Time's up - answers can no longer be changed
        </span>
      );
    default:
      return null;
  }
}
