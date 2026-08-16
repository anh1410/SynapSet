import { useRef, useState } from "react";
import { Menu, Search, Bell, Network, HelpCircle } from "lucide-react";
import { Avatar } from "@/components/ui/avatar";
import { Input } from "@/components/ui/input";
import { fetchGraph, fetchQuestions, type GraphNode, type Question } from "@/lib/api";
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

export function Topbar({
  page,
  onMenuClick,
  onNavigate,
  onSelectQuestion,
}: {
  page: Page;
  onMenuClick: () => void;
  onNavigate: (p: Page) => void;
  onSelectQuestion: (searchText: string) => void;
}) {
  const { title, subtitle } = titles[page];

  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [topics, setTopics] = useState<GraphNode[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const blurTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  const ensureLoaded = () => {
    if (loaded) return;
    Promise.all([fetchGraph(), fetchQuestions()]).then(([g, qs]) => {
      setTopics(g.nodes);
      setQuestions(qs);
      setLoaded(true);
    });
  };

  const q = query.trim().toLowerCase();
  const matchedTopics = q ? topics.filter((t) => t.name.toLowerCase().includes(q)).slice(0, 5) : [];
  const matchedQuestions = q ? questions.filter((qu) => qu.text.toLowerCase().includes(q)).slice(0, 5) : [];
  const hasResults = matchedTopics.length > 0 || matchedQuestions.length > 0;

  const closeDropdown = () => {
    setOpen(false);
    setQuery("");
  };

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
        <Input
          placeholder="Search topics, questions..."
          className="pl-8"
          value={query}
          onFocus={() => {
            ensureLoaded();
            setOpen(true);
          }}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onBlur={() => {
            // delay so a click on a result registers before the dropdown unmounts
            blurTimeout.current = setTimeout(() => setOpen(false), 150);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") closeDropdown();
          }}
        />

        {open && q && (
          <div className="absolute right-0 top-full mt-1.5 w-80 rounded-lg border border-border bg-white py-1.5 shadow-lg animate-fade-in">
            {!hasResults ? (
              <p className="px-3 py-3 text-xs text-muted-foreground">No matches for "{query}"</p>
            ) : (
              <>
                {matchedTopics.length > 0 && (
                  <div className="px-1.5">
                    <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                      Topics
                    </p>
                    {matchedTopics.map((t) => (
                      <button
                        key={t.id}
                        className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-foreground hover:bg-secondary/60"
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => {
                          closeDropdown();
                          onNavigate("analysis");
                        }}
                      >
                        <Network className="h-3.5 w-3.5 shrink-0 text-primary" />
                        <span className="truncate">{t.name}</span>
                      </button>
                    ))}
                  </div>
                )}
                {matchedQuestions.length > 0 && (
                  <div className="px-1.5 pt-1">
                    <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                      Questions
                    </p>
                    {matchedQuestions.map((qu) => (
                      <button
                        key={qu.id}
                        className="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-xs text-foreground hover:bg-secondary/60"
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => {
                          const term = query;
                          closeDropdown();
                          onSelectQuestion(term);
                        }}
                      >
                        <HelpCircle className="h-3.5 w-3.5 shrink-0 mt-0.5 text-primary" />
                        <span className="line-clamp-2">{qu.text}</span>
                      </button>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        )}
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
