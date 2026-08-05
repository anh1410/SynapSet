import { useState } from "react";
import { Search, SlidersHorizontal, Pencil, Trash2, Library } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { EmptyState } from "@/components/ui/empty-state";
import { questions, topics, type Difficulty } from "@/lib/mock-data";
import { cn } from "@/lib/utils";

const difficultyVariant: Record<Difficulty, "success" | "warning" | "destructive"> = {
  Easy: "success",
  Medium: "warning",
  Hard: "destructive",
};

export function BankPage() {
  const [search, setSearch] = useState("");
  const [topicFilter, setTopicFilter] = useState("all");
  const [difficultyFilter, setDifficultyFilter] = useState("all");
  const [selected, setSelected] = useState<string[]>([]);

  const filtered = questions.filter((q) => {
    if (search && !q.text.toLowerCase().includes(search.toLowerCase())) return false;
    if (topicFilter !== "all" && q.topic !== topicFilter) return false;
    if (difficultyFilter !== "all" && q.difficulty !== difficultyFilter) return false;
    return true;
  });

  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search questions..."
              className="pl-8"
            />
          </div>
          <div className="grid grid-cols-2 gap-2 sm:flex sm:w-auto">
            <Select value={topicFilter} onChange={(e) => setTopicFilter(e.target.value)} className="sm:w-44">
              <option value="all">All topics</option>
              {topics.map((t) => (
                <option key={t.id} value={t.name}>
                  {t.name}
                </option>
              ))}
            </Select>
            <Select value={difficultyFilter} onChange={(e) => setDifficultyFilter(e.target.value)} className="sm:w-36">
              <option value="all">All difficulty</option>
              <option value="Easy">Easy</option>
              <option value="Medium">Medium</option>
              <option value="Hard">Hard</option>
            </Select>
          </div>
          <Button variant="outline" size="sm">
            <SlidersHorizontal className="h-3.5 w-3.5" /> More filters
          </Button>
        </CardContent>
      </Card>

      {selected.length > 0 && (
        <div className="flex items-center justify-between rounded-lg border border-primary/20 bg-accent px-4 py-2.5 text-sm animate-fade-in">
          <span className="font-medium text-accent-foreground">{selected.length} selected</span>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary">
              Add to exam
            </Button>
            <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive">
              <Trash2 className="h-3.5 w-3.5" /> Delete
            </Button>
          </div>
        </div>
      )}

      <Card>
        <CardContent className="p-0">
          {filtered.length === 0 ? (
            <EmptyState
              icon={Library}
              title="No questions found"
              description="Try adjusting your filters or generate new questions for this topic."
              className="m-6"
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-y border-border bg-secondary/40 text-left text-xs text-muted-foreground">
                    <th className="w-10 px-6 py-2.5"></th>
                    <th className="px-2 py-2.5 font-medium">Question</th>
                    <th className="px-4 py-2.5 font-medium">Topic</th>
                    <th className="px-4 py-2.5 font-medium">Difficulty</th>
                    <th className="px-4 py-2.5 font-medium">Marks</th>
                    <th className="px-4 py-2.5 font-medium">Bloom's</th>
                    <th className="px-4 py-2.5"></th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((q) => (
                    <tr
                      key={q.id}
                      className={cn(
                        "border-b border-border last:border-0 transition-colors duration-150 hover:bg-secondary/30",
                        selected.includes(q.id) && "bg-accent/50"
                      )}
                    >
                      <td className="px-6 py-3">
                        <Checkbox checked={selected.includes(q.id)} onCheckedChange={() => toggle(q.id)} />
                      </td>
                      <td className="max-w-md px-2 py-3">
                        <p className="line-clamp-2 text-foreground">{q.text}</p>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{q.topic}</td>
                      <td className="px-4 py-3">
                        <Badge variant={difficultyVariant[q.difficulty]}>{q.difficulty}</Badge>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{q.marks}</td>
                      <td className="px-4 py-3">
                        <Badge variant="accent">{q.bloom}</Badge>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end gap-1">
                          <Button variant="ghost" size="icon" className="h-7 w-7">
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive hover:text-destructive">
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        Showing {filtered.length} of {questions.length} questions
      </p>
    </div>
  );
}
