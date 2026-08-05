import { useState } from "react";
import { Sparkles, Check, RefreshCw, Save, ShieldCheck, ShieldAlert } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { Progress } from "@/components/ui/progress";
import { topics } from "@/lib/mock-data";
import { cn } from "@/lib/utils";

const difficulties = ["Easy", "Medium", "Hard"] as const;

const generated = [
  {
    id: "g1",
    text: "Derive the relation between electric field and electric potential, and explain its physical significance.",
    marks: 8,
    bloom: "Analyze",
    similarity: 14,
  },
  {
    id: "g2",
    text: "A parallel plate capacitor is charged to a potential difference V. Determine the energy stored per unit volume in the electric field.",
    marks: 6,
    bloom: "Apply",
    similarity: 62,
  },
  {
    id: "g3",
    text: "Explain the concept of electric flux and state Gauss's law in integral form.",
    marks: 4,
    bloom: "Understand",
    similarity: 9,
  },
];

export function GeneratePage() {
  const [topic, setTopic] = useState(topics[2].name);
  const [difficulty, setDifficulty] = useState<(typeof difficulties)[number]>("Medium");
  const [showResults, setShowResults] = useState(true);

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      {/* Config panel */}
      <Card className="lg:col-span-1 h-fit lg:sticky lg:top-20">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <CardTitle>Question Parameters</CardTitle>
          </div>
          <CardDescription>Generation is grounded strictly in your uploaded content</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-foreground">Topic</label>
            <Select value={topic} onChange={(e) => setTopic(e.target.value)}>
              {topics.map((t) => (
                <option key={t.id} value={t.name}>
                  {t.name}
                </option>
              ))}
            </Select>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-foreground">Difficulty Level</label>
            <div className="grid grid-cols-3 gap-2">
              {difficulties.map((d) => (
                <button
                  key={d}
                  onClick={() => setDifficulty(d)}
                  className={cn(
                    "rounded-lg border px-2 py-2 text-xs font-medium transition-all duration-200",
                    difficulty === d
                      ? "border-primary bg-primary/5 text-primary"
                      : "border-border bg-white text-muted-foreground hover:border-primary/30"
                  )}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-foreground">Marks</label>
            <Select defaultValue="6">
              {[2, 4, 5, 6, 8, 10].map((m) => (
                <option key={m} value={m}>
                  {m} marks
                </option>
              ))}
            </Select>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-foreground">Bloom's Cognitive Level</label>
            <Select defaultValue="Apply">
              {["Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create"].map((b) => (
                <option key={b} value={b}>
                  {b}
                </option>
              ))}
            </Select>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-foreground">Number of Questions</label>
            <Select defaultValue="3">
              {[1, 3, 5, 10].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
          </div>

          <Button className="w-full" onClick={() => setShowResults(true)}>
            <Sparkles className="h-4 w-4" /> Generate Questions
          </Button>
        </CardContent>
      </Card>

      {/* Results */}
      <div className="space-y-4 lg:col-span-2">
        {!showResults ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-16 text-center">
              <Sparkles className="h-8 w-8 text-muted-foreground" />
              <p className="mt-3 text-sm font-medium text-foreground">No questions generated yet</p>
              <p className="mt-1 text-xs text-muted-foreground">Set your parameters and generate to see results here</p>
            </CardContent>
          </Card>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Generated <span className="font-medium text-foreground">3 questions</span> for{" "}
                <span className="font-medium text-foreground">{topic}</span>
              </p>
              <Button variant="ghost" size="sm">
                <RefreshCw className="h-3.5 w-3.5" /> Regenerate all
              </Button>
            </div>

            {generated.map((q) => {
              const isDuplicate = q.similarity > 50;
              return (
                <Card
                  key={q.id}
                  className={cn(isDuplicate && "border-warning/40 bg-warning/[0.03]")}
                >
                  <CardContent className="p-5">
                    <div className="flex items-start justify-between gap-4">
                      <p className="text-sm leading-relaxed text-foreground">{q.text}</p>
                    </div>

                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <Badge variant="secondary">{q.marks} marks</Badge>
                      <Badge variant="accent">{q.bloom}</Badge>
                      <Badge variant={isDuplicate ? "warning" : "success"}>
                        {isDuplicate ? <ShieldAlert className="h-3 w-3" /> : <ShieldCheck className="h-3 w-3" />}
                        {q.similarity}% similar to existing
                      </Badge>
                    </div>

                    {isDuplicate && (
                      <p className="mt-2 text-xs text-warning">
                        This question closely resembles one already in your bank. Review before saving.
                      </p>
                    )}

                    <div className="mt-4 flex items-center gap-2">
                      <Button size="sm" variant={isDuplicate ? "secondary" : "primary"}>
                        <Save className="h-3.5 w-3.5" /> Save to bank
                      </Button>
                      <Button size="sm" variant="ghost">
                        <RefreshCw className="h-3.5 w-3.5" /> Regenerate
                      </Button>
                      <Button size="sm" variant="ghost" className="text-muted-foreground">
                        Edit
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}
