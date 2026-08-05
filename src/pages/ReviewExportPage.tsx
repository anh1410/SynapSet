import { useState } from "react";
import { FileCheck2, FileText, FileType, Pencil, RefreshCcw, Download, GripVertical } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { questions, examBlueprints } from "@/lib/mock-data";

const paper = questions.slice(0, 8);

export function ReviewExportPage() {
  const [tab, setTab] = useState<"preview" | "history">("preview");

  return (
    <div className="space-y-4">
      <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <TabsList>
            <TabsTrigger value="preview">Paper Preview</TabsTrigger>
            <TabsTrigger value="history">Export History</TabsTrigger>
          </TabsList>

          {tab === "preview" && (
            <div className="flex gap-2">
              <Button variant="outline" size="sm">
                <FileType className="h-3.5 w-3.5" /> Export Word
              </Button>
              <Button size="sm">
                <Download className="h-3.5 w-3.5" /> Export PDF
              </Button>
            </div>
          )}
        </div>

        <TabsContent value="preview" className="mt-4">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="space-y-4 lg:col-span-2">
              <Card>
                <CardContent className="p-8">
                  <div className="border-b border-border pb-4 text-center">
                    <p className="text-xs uppercase tracking-widest text-muted-foreground">Department of Engineering</p>
                    <h2 className="mt-1 text-lg font-semibold text-foreground">End-Semester Examination — Nov 2026</h2>
                    <div className="mt-2 flex justify-center gap-4 text-xs text-muted-foreground">
                      <span>Total Marks: 100</span>
                      <span>·</span>
                      <span>Duration: 180 min</span>
                    </div>
                  </div>

                  <div className="mt-6 space-y-5">
                    {paper.map((q, i) => (
                      <div key={q.id} className="group flex items-start gap-3">
                        <GripVertical className="mt-1 h-4 w-4 shrink-0 cursor-grab text-transparent transition-colors duration-150 group-hover:text-muted-foreground" />
                        <span className="mt-0.5 text-sm font-medium text-foreground">Q{i + 1}.</span>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm leading-relaxed text-foreground">{q.text}</p>
                        </div>
                        <span className="shrink-0 text-xs font-medium text-muted-foreground">[{q.marks}]</span>
                        <div className="flex shrink-0 gap-1 opacity-0 transition-opacity duration-150 group-hover:opacity-100">
                          <Button variant="ghost" size="icon" className="h-6 w-6">
                            <Pencil className="h-3 w-3" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-6 w-6">
                            <RefreshCcw className="h-3 w-3" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>

            <div className="space-y-4">
              <Card>
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <FileCheck2 className="h-4 w-4 text-primary" />
                    <CardTitle>Paper Summary</CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  {[
                    { label: "Total Questions", value: "8" },
                    { label: "Total Marks", value: "100" },
                    { label: "Duration", value: "180 min" },
                    { label: "Topics Covered", value: "5" },
                  ].map((row) => (
                    <div key={row.label} className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">{row.label}</span>
                      <span className="font-medium text-foreground">{row.value}</span>
                    </div>
                  ))}
                  <div className="border-t border-border pt-3">
                    <div className="flex gap-1.5">
                      <Badge variant="success">30% Easy</Badge>
                      <Badge variant="warning">45% Med</Badge>
                      <Badge variant="destructive">25% Hard</Badge>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Actions</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <Button variant="secondary" className="w-full justify-start">
                    <Pencil className="h-3.5 w-3.5" /> Edit questions
                  </Button>
                  <Button variant="secondary" className="w-full justify-start">
                    <RefreshCcw className="h-3.5 w-3.5" /> Replace flagged
                  </Button>
                  <Button variant="ghost" className="w-full justify-start text-muted-foreground">
                    Save as draft
                  </Button>
                </CardContent>
              </Card>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="history" className="mt-4">
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-y border-border bg-secondary/40 text-left text-xs text-muted-foreground">
                      <th className="px-6 py-2.5 font-medium">Paper Name</th>
                      <th className="px-4 py-2.5 font-medium">Marks</th>
                      <th className="px-4 py-2.5 font-medium">Duration</th>
                      <th className="px-4 py-2.5 font-medium">Questions</th>
                      <th className="px-4 py-2.5 font-medium">Status</th>
                      <th className="px-4 py-2.5 font-medium">Updated</th>
                      <th className="px-4 py-2.5"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {examBlueprints.map((e) => (
                      <tr key={e.id} className="border-b border-border last:border-0 transition-colors duration-150 hover:bg-secondary/30">
                        <td className="px-6 py-3">
                          <div className="flex items-center gap-2.5">
                            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary text-slate-500">
                              <FileText className="h-4 w-4" />
                            </div>
                            <span className="font-medium text-foreground">{e.name}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">{e.totalMarks}</td>
                        <td className="px-4 py-3 text-muted-foreground">{e.duration} min</td>
                        <td className="px-4 py-3 text-muted-foreground">{e.questionCount}</td>
                        <td className="px-4 py-3">
                          <Badge
                            variant={e.status === "Exported" ? "success" : e.status === "In Review" ? "warning" : "secondary"}
                          >
                            {e.status}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">{e.updatedAt}</td>
                        <td className="px-4 py-3 text-right">
                          <Button variant="ghost" size="sm">
                            <Download className="h-3.5 w-3.5" /> Export
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
