import { useState } from "react";
import { FileStack, Wand2, Clock, Hash, PieChart, ListChecks, Plus, Minus } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { topics, questions } from "@/lib/mock-data";

const difficultyMix = [
  { label: "Easy", value: 30, color: "bg-success" },
  { label: "Medium", value: 45, color: "bg-warning" },
  { label: "Hard", value: 25, color: "bg-destructive" },
];

export function ExamBuilderPage() {
  const [selectedTopics, setSelectedTopics] = useState<string[]>(topics.slice(0, 5).map((t) => t.name));
  const [generated, setGenerated] = useState(false);

  const toggleTopic = (name: string) =>
    setSelectedTopics((s) => (s.includes(name) ? s.filter((x) => x !== name) : [...s, name]));

  const selectedQuestions = questions.slice(0, 8);

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      {/* Constraints panel */}
      <Card className="lg:col-span-1 h-fit lg:sticky lg:top-20">
        <CardHeader>
          <div className="flex items-center gap-2">
            <FileStack className="h-4 w-4 text-primary" />
            <CardTitle>Paper Requirements</CardTitle>
          </div>
          <CardDescription>Define constraints for automatic question selection</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                <Hash className="h-3.5 w-3.5" /> Total Marks
              </label>
              <Input defaultValue="100" type="number" />
            </div>
            <div className="space-y-1.5">
              <label className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                <Clock className="h-3.5 w-3.5" /> Duration (min)
              </label>
              <Input defaultValue="180" type="number" />
            </div>
          </div>

          <div className="space-y-2.5">
            <label className="flex items-center gap-1.5 text-xs font-medium text-foreground">
              <PieChart className="h-3.5 w-3.5" /> Difficulty Mix
            </label>
            {difficultyMix.map((d) => (
              <div key={d.label} className="flex items-center gap-3">
                <span className="w-16 text-xs text-muted-foreground">{d.label}</span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary">
                  <div className={`h-full rounded-full ${d.color}`} style={{ width: `${d.value}%` }} />
                </div>
                <div className="flex items-center gap-1">
                  <button className="rounded p-0.5 text-muted-foreground hover:bg-secondary">
                    <Minus className="h-3 w-3" />
                  </button>
                  <span className="w-8 text-right text-xs font-medium text-foreground">{d.value}%</span>
                  <button className="rounded p-0.5 text-muted-foreground hover:bg-secondary">
                    <Plus className="h-3 w-3" />
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="space-y-2">
            <label className="flex items-center gap-1.5 text-xs font-medium text-foreground">
              <ListChecks className="h-3.5 w-3.5" /> Topic Coverage
            </label>
            <div className="max-h-48 space-y-1 overflow-y-auto rounded-lg border border-border p-2 scrollbar-thin">
              {topics.map((t) => (
                <label
                  key={t.id}
                  className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-xs transition-colors duration-150 hover:bg-secondary/60"
                >
                  <Checkbox
                    checked={selectedTopics.includes(t.name)}
                    onCheckedChange={() => toggleTopic(t.name)}
                  />
                  <span className="flex-1 text-foreground">{t.name}</span>
                  <span className="text-muted-foreground">{t.questions} avail.</span>
                </label>
              ))}
            </div>
          </div>

          <Button className="w-full" onClick={() => setGenerated(true)}>
            <Wand2 className="h-4 w-4" /> Auto-generate Paper
          </Button>
        </CardContent>
      </Card>

      {/* Generated paper preview */}
      <div className="space-y-4 lg:col-span-2">
        {!generated ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-16 text-center">
              <FileStack className="h-8 w-8 text-muted-foreground" />
              <p className="mt-3 text-sm font-medium text-foreground">No paper generated yet</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Set your requirements and click "Auto-generate Paper" to preview
              </p>
            </CardContent>
          </Card>
        ) : (
          <>
            <Card className="border-success/30 bg-success/[0.03]">
              <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div>
                  <p className="text-sm font-medium text-foreground">Constraints satisfied</p>
                  <p className="text-xs text-muted-foreground">
                    100 marks · 180 min · 8 questions · No repeated questions
                  </p>
                </div>
                <div className="flex gap-2">
                  <Badge variant="success">30% Easy</Badge>
                  <Badge variant="warning">45% Medium</Badge>
                  <Badge variant="destructive">25% Hard</Badge>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Selected Questions</CardTitle>
                <CardDescription>Best combination matching your constraints, ranked by relevance</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {selectedQuestions.map((q, i) => (
                  <div
                    key={q.id}
                    className="flex items-start gap-3 rounded-lg border border-border bg-white p-3.5 transition-all duration-200 hover:border-primary/30"
                  >
                    <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-secondary text-[11px] font-semibold text-muted-foreground">
                      {i + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-foreground">{q.text}</p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        <Badge variant="secondary">{q.topic}</Badge>
                        <Badge
                          variant={q.difficulty === "Easy" ? "success" : q.difficulty === "Medium" ? "warning" : "destructive"}
                        >
                          {q.difficulty}
                        </Badge>
                        <Badge variant="outline">{q.marks} marks</Badge>
                      </div>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
