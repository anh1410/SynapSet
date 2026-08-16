import {
  LayoutGrid,
  UploadCloud,
  Network,
  Sparkles,
  Library,
  FileStack,
  FileCheck2,
  Settings,
  X,
  GraduationCap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { Page } from "@/App";

const nav: { id: Page; label: string; icon: typeof LayoutGrid }[] = [
  { id: "overview", label: "Overview", icon: LayoutGrid },
  { id: "upload", label: "Upload Materials", icon: UploadCloud },
  { id: "analysis", label: "Topic Analysis", icon: Network },
  { id: "generate", label: "Generate Questions", icon: Sparkles },
  { id: "bank", label: "Question Bank", icon: Library },
  { id: "exam", label: "Exam Builder", icon: FileStack },
  { id: "review", label: "Review & Export", icon: FileCheck2 },
];

export function Sidebar({
  active,
  onNavigate,
  open,
  onClose,
}: {
  active: Page;
  onNavigate: (p: Page) => void;
  open: boolean;
  onClose: () => void;
}) {
  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-40 bg-slate-900/30 backdrop-blur-[2px] lg:hidden"
          onClick={onClose}
        />
      )}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-border bg-white transition-transform duration-200 lg:static lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex h-16 items-center justify-between border-b border-border px-5">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <GraduationCap className="h-4.5 w-4.5" />
            </div>
            <span className="text-sm font-semibold tracking-tight text-foreground">QuestionForge</span>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground hover:bg-secondary lg:hidden"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto p-3">
          <p className="px-3 pb-2 pt-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Workspace
          </p>
          {nav.map((item) => {
            const Icon = item.icon;
            const isActive = active === item.id;
            return (
              <button
                key={item.id}
                onClick={() => {
                  onNavigate(item.id);
                  onClose();
                }}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200",
                  isActive
                    ? "bg-accent text-accent-foreground"
                    : "text-slate-600 hover:bg-secondary hover:text-foreground"
                )}
              >
                <Icon className={cn("h-4 w-4", isActive ? "text-primary" : "text-slate-400")} />
                {item.label}
              </button>
            );
          })}
        </nav>

        <div className="border-t border-border p-3">
          <button className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 transition-all duration-200 hover:bg-secondary hover:text-foreground">
            <Settings className="h-4 w-4 text-slate-400" />
            Settings
          </button>
        </div>
      </aside>
    </>
  );
}
