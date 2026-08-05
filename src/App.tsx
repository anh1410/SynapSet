import { useState } from "react";
import { Sidebar } from "@/components/Sidebar";
import { Topbar } from "@/components/Topbar";
import { OverviewPage } from "@/pages/OverviewPage";
import { UploadPage } from "@/pages/UploadPage";
import { AnalysisPage } from "@/pages/AnalysisPage";
import { GeneratePage } from "@/pages/GeneratePage";
import { BankPage } from "@/pages/BankPage";
import { ExamBuilderPage } from "@/pages/ExamBuilderPage";
import { ReviewExportPage } from "@/pages/ReviewExportPage";

export type Page =
  | "overview"
  | "upload"
  | "analysis"
  | "generate"
  | "bank"
  | "exam"
  | "review";

export default function App() {
  const [page, setPage] = useState<Page>("overview");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden bg-secondary/40">
      <Sidebar
        active={page}
        onNavigate={setPage}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar page={page} onMenuClick={() => setSidebarOpen(true)} />

        <main className="flex-1 overflow-y-auto scrollbar-thin">
          <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:py-8">
            {page === "overview" && <OverviewPage onNavigate={setPage} />}
            {page === "upload" && <UploadPage />}
            {page === "analysis" && <AnalysisPage />}
            {page === "generate" && <GeneratePage />}
            {page === "bank" && <BankPage />}
            {page === "exam" && <ExamBuilderPage />}
            {page === "review" && <ReviewExportPage />}
          </div>
        </main>
      </div>
    </div>
  );
}
