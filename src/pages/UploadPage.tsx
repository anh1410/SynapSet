import { useState } from "react";
import {
  UploadCloud,
  FileText,
  BookOpen,
  NotebookPen,
  ScrollText,
  CheckCircle2,
  Loader2,
  XCircle,
  MoreHorizontal,
  Trash2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { uploadedDocuments } from "@/lib/mock-data";
import { cn } from "@/lib/utils";

const categories = [
  { id: "syllabus", label: "Syllabus", icon: BookOpen, description: "Course structure & learning outcomes" },
  { id: "notes", label: "Class Notes", icon: NotebookPen, description: "Lecture notes, slides, handouts" },
  { id: "papers", label: "Question Papers", icon: ScrollText, description: "Previous years' exam papers" },
];

const statusMap = {
  Processed: { icon: CheckCircle2, variant: "success" as const },
  Processing: { icon: Loader2, variant: "warning" as const },
  Failed: { icon: XCircle, variant: "destructive" as const },
};

export function UploadPage() {
  const [dragOver, setDragOver] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {categories.map((cat) => {
          const Icon = cat.icon;
          const isOver = dragOver === cat.id;
          return (
            <Card key={cat.id} className={cn(isOver && "ring-2 ring-primary border-primary")}>
              <CardContent className="p-5">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Icon className="h-4.5 w-4.5" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-foreground">{cat.label}</p>
                    <p className="text-[11px] text-muted-foreground">{cat.description}</p>
                  </div>
                </div>

                <div
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragOver(cat.id);
                  }}
                  onDragLeave={() => setDragOver(null)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDragOver(null);
                  }}
                  className={cn(
                    "mt-4 flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-border bg-secondary/30 px-4 py-8 text-center transition-all duration-200",
                    isOver && "border-primary bg-primary/5"
                  )}
                >
                  <UploadCloud className={cn("h-6 w-6 text-muted-foreground", isOver && "text-primary")} />
                  <p className="mt-2 text-xs font-medium text-foreground">
                    Drop files or <span className="text-primary">browse</span>
                  </p>
                  <p className="mt-1 text-[11px] text-muted-foreground">PDF, DOCX up to 25MB</p>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>Uploaded Documents</CardTitle>
            <CardDescription>Materials analyzed to extract topics and build the knowledge graph</CardDescription>
          </div>
          <Button size="sm" variant="outline">
            <UploadCloud className="h-3.5 w-3.5" /> Upload new
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-y border-border bg-secondary/40 text-left text-xs text-muted-foreground">
                  <th className="px-6 py-2.5 font-medium">Document</th>
                  <th className="px-4 py-2.5 font-medium">Type</th>
                  <th className="px-4 py-2.5 font-medium">Size</th>
                  <th className="px-4 py-2.5 font-medium">Uploaded</th>
                  <th className="px-4 py-2.5 font-medium">Topics</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                  <th className="px-4 py-2.5"></th>
                </tr>
              </thead>
              <tbody>
                {uploadedDocuments.map((d) => {
                  const s = statusMap[d.status];
                  const StatusIcon = s.icon;
                  return (
                    <tr key={d.id} className="border-b border-border last:border-0 transition-colors duration-150 hover:bg-secondary/30">
                      <td className="px-6 py-3">
                        <div className="flex items-center gap-2.5">
                          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-secondary text-slate-500">
                            <FileText className="h-4 w-4" />
                          </div>
                          <span className="font-medium text-foreground">{d.name}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{d.type}</td>
                      <td className="px-4 py-3 text-muted-foreground">{d.size}</td>
                      <td className="px-4 py-3 text-muted-foreground">{d.uploadedAt}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {d.topicsExtracted > 0 ? d.topicsExtracted : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={s.variant}>
                          <StatusIcon className={cn("h-3 w-3", d.status === "Processing" && "animate-spin")} />
                          {d.status}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex justify-end gap-1">
                          <Button variant="ghost" size="icon" className="h-7 w-7">
                            <MoreHorizontal className="h-3.5 w-3.5" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive hover:text-destructive">
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
