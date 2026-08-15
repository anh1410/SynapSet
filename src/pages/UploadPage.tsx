import { useEffect, useRef, useState } from "react";
import {
  UploadCloud,
  FileText,
  BookOpen,
  NotebookPen,
  ScrollText,
  CheckCircle2,
  Loader2,
  XCircle,
  Trash2,
  AlertCircle,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import {
  deleteDocument,
  fetchDocuments,
  formatBytes,
  ingestDocument,
  timeAgo,
  type DocumentCategory,
  type UploadedDocument,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const categories: { id: DocumentCategory; label: string; icon: typeof BookOpen; description: string }[] = [
  { id: "syllabus", label: "Syllabus", icon: BookOpen, description: "Course structure & learning outcomes" },
  { id: "notes", label: "Class Notes", icon: NotebookPen, description: "Lecture notes, slides, handouts" },
  { id: "papers", label: "Question Papers", icon: ScrollText, description: "Previous years' exam papers" },
];

const statusMap = {
  processed: { icon: CheckCircle2, variant: "success" as const, label: "Processed" },
  processing: { icon: Loader2, variant: "warning" as const, label: "Processing" },
  failed: { icon: XCircle, variant: "destructive" as const, label: "Failed" },
};

const categoryLabels: Record<DocumentCategory, string> = {
  syllabus: "Syllabus",
  notes: "Class Notes",
  papers: "Question Paper",
};

export function UploadPage() {
  const [dragOver, setDragOver] = useState<DocumentCategory | null>(null);
  const [documents, setDocuments] = useState<UploadedDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState<DocumentCategory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputs = useRef<Record<DocumentCategory, HTMLInputElement | null>>({
    syllabus: null,
    notes: null,
    papers: null,
  });

  const load = () => {
    fetchDocuments()
      .then(setDocuments)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const handleUpload = async (category: DocumentCategory, file: File) => {
    setUploading(category);
    setError(null);
    try {
      await ingestDocument(file, category);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(null);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteDocument(id);
      setDocuments((docs) => docs.filter((d) => d.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  };

  return (
    <div className="space-y-6">
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-2.5 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {categories.map((cat) => {
          const Icon = cat.icon;
          const isOver = dragOver === cat.id;
          const isUploading = uploading === cat.id;
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

                <input
                  ref={(el) => (fileInputs.current[cat.id] = el)}
                  type="file"
                  accept=".pdf,.docx,.pptx,.txt"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleUpload(cat.id, file);
                    e.target.value = "";
                  }}
                />

                <div
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragOver(cat.id);
                  }}
                  onDragLeave={() => setDragOver(null)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDragOver(null);
                    const file = e.dataTransfer.files?.[0];
                    if (file) handleUpload(cat.id, file);
                  }}
                  onClick={() => !isUploading && fileInputs.current[cat.id]?.click()}
                  className={cn(
                    "mt-4 flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-border bg-secondary/30 px-4 py-8 text-center transition-all duration-200",
                    isOver && "border-primary bg-primary/5",
                    isUploading && "pointer-events-none opacity-70"
                  )}
                >
                  {isUploading ? (
                    <>
                      <Loader2 className="h-6 w-6 animate-spin text-primary" />
                      <p className="mt-2 text-xs font-medium text-foreground">Processing...</p>
                    </>
                  ) : (
                    <>
                      <UploadCloud className={cn("h-6 w-6 text-muted-foreground", isOver && "text-primary")} />
                      <p className="mt-2 text-xs font-medium text-foreground">
                        Drop files or <span className="text-primary">browse</span>
                      </p>
                      <p className="mt-1 text-[11px] text-muted-foreground">PDF, DOCX, PPTX</p>
                    </>
                  )}
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
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="space-y-3 p-6">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : documents.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No documents yet"
              description="Upload a syllabus, notes, or a past question paper above to start building your knowledge graph."
              className="m-6"
            />
          ) : (
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
                  {documents.map((d) => {
                    const s = statusMap[d.status];
                    const StatusIcon = s.icon;
                    return (
                      <tr key={d.id} className="border-b border-border last:border-0 transition-colors duration-150 hover:bg-secondary/30">
                        <td className="px-6 py-3">
                          <div className="flex items-center gap-2.5">
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-secondary text-slate-500">
                              <FileText className="h-4 w-4" />
                            </div>
                            <span className="font-medium text-foreground">{d.filename}</span>
                          </div>
                          {d.status === "failed" && d.error_message && (
                            <p className="ml-10 mt-0.5 text-[11px] text-destructive">{d.error_message}</p>
                          )}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">{categoryLabels[d.category]}</td>
                        <td className="px-4 py-3 text-muted-foreground">{formatBytes(d.size_bytes)}</td>
                        <td className="px-4 py-3 text-muted-foreground">{timeAgo(d.uploaded_at)}</td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {d.topics_extracted > 0 ? d.topics_extracted : "—"}
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant={s.variant}>
                            <StatusIcon className={cn("h-3 w-3", d.status === "processing" && "animate-spin")} />
                            {s.label}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-destructive hover:text-destructive"
                            onClick={() => handleDelete(d.id)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
