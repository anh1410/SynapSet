import { useState } from "react";
import { ChevronDown, Plus, BookOpen } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";

export function SubjectSwitcher() {
  const { subjects, activeSubjectId, setActiveSubjectId, createSubject } = useAuth();
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  const active = subjects.find((s) => s.id === activeSubjectId);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    await createSubject(name);
    setNewName("");
    setCreating(false);
    setOpen(false);
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-lg border border-border bg-white px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-secondary/50"
      >
        <BookOpen className="h-3.5 w-3.5 text-primary" />
        <span className="max-w-[9rem] truncate">{active?.name ?? "No subject"}</span>
        <ChevronDown className="h-3 w-3 text-muted-foreground" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full z-50 mt-1.5 w-56 rounded-lg border border-border bg-white py-1.5 shadow-lg animate-fade-in">
            {subjects.map((s) => (
              <button
                key={s.id}
                onClick={() => {
                  setActiveSubjectId(s.id);
                  setOpen(false);
                }}
                className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-secondary/60 ${
                  s.id === activeSubjectId ? "font-semibold text-primary" : "text-foreground"
                }`}
              >
                {s.name}
              </button>
            ))}
            {subjects.length > 0 && <div className="my-1 border-t border-border" />}
            {creating ? (
              <form onSubmit={handleCreate} className="px-2 pt-1">
                <input
                  autoFocus
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="Subject name"
                  className="w-full rounded-md border border-input px-2 py-1 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </form>
            ) : (
              <button
                onClick={() => setCreating(true)}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-primary hover:bg-secondary/60"
              >
                <Plus className="h-3.5 w-3.5" />
                New subject
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
