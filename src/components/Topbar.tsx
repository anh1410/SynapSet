import { Menu, Search, Bell } from "lucide-react";
import { Avatar } from "@/components/ui/avatar";
import { Input } from "@/components/ui/input";
import type { Page } from "@/App";

const titles: Record<Page, { title: string; subtitle: string }> = {
  overview: { title: "Overview", subtitle: "Your course content and question bank at a glance" },
  upload: { title: "Upload Materials", subtitle: "Add syllabus, notes, and past papers for analysis" },
  analysis: { title: "Topic Analysis", subtitle: "Coverage, relationships, and neglected areas" },
  generate: { title: "Generate Questions", subtitle: "Create new questions grounded in your material" },
  bank: { title: "Question Bank", subtitle: "Browse and manage tagged questions" },
  exam: { title: "Exam Builder", subtitle: "Assemble a paper against your constraints" },
  review: { title: "Review & Export", subtitle: "Finalize and export the exam paper" },
};

export function Topbar({ page, onMenuClick }: { page: Page; onMenuClick: () => void }) {
  const { title, subtitle } = titles[page];
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-4 border-b border-border bg-white/80 px-4 backdrop-blur-md sm:px-6">
      <button
        onClick={onMenuClick}
        className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary lg:hidden"
      >
        <Menu className="h-5 w-5" />
      </button>

      <div className="min-w-0 flex-1">
        <h1 className="truncate text-[15px] font-semibold text-foreground">{title}</h1>
        <p className="hidden truncate text-xs text-muted-foreground sm:block">{subtitle}</p>
      </div>

      <div className="relative hidden w-64 md:block">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input placeholder="Search topics, questions..." className="pl-8" />
      </div>

      <button className="relative rounded-md p-1.5 text-muted-foreground transition-colors duration-200 hover:bg-secondary hover:text-foreground">
        <Bell className="h-4.5 w-4.5" />
        <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-primary" />
      </button>

      <div className="hidden items-center gap-2 border-l border-border pl-4 sm:flex">
        <Avatar initials="AS" />
        <div className="text-xs">
          <p className="font-medium text-foreground">Anagha Surathkal</p>
          <p className="text-muted-foreground">Faculty</p>
        </div>
      </div>
    </header>
  );
}
