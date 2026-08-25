import { useState } from "react";
import { Sidebar } from "@/components/Sidebar";
import { Topbar } from "@/components/Topbar";
import { OverviewPage } from "@/pages/OverviewPage";
import { UploadPage } from "@/pages/UploadPage";
import { AnalysisPage } from "@/pages/AnalysisPage";
import { BankPage } from "@/pages/BankPage";
import { ExamBuilderPage } from "@/pages/ExamBuilderPage";
import { ExamsPage } from "@/pages/ExamsPage";
import { AuthPage } from "@/pages/AuthPage";
import { AuthProvider, useAuth } from "@/lib/AuthContext";

export type Page =
  | "overview"
  | "upload"
  | "analysis"
  | "bank"
  | "exam"
  | "exams";

function AppShell() {
  const [page, setPage] = useState<Page>("overview");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [examSeedIds, setExamSeedIds] = useState<string[]>([]);
  const [editExamId, setEditExamId] = useState<string | null>(null);
  const [bankSearch, setBankSearch] = useState<string | undefined>(undefined);

  const goToExamBuilder = (questionIds: string[]) => {
    setExamSeedIds(questionIds);
    setEditExamId(null);
    setPage("exam");
  };

  const goToNewExam = () => {
    setExamSeedIds([]);
    setEditExamId(null);
    setPage("exam");
  };

  const goToEditExam = (examId: string) => {
    setExamSeedIds([]);
    setEditExamId(examId);
    setPage("exam");
  };

  const goToExams = () => {
    setPage("exams");
  };

  const goToBankSearch = (query: string) => {
    setBankSearch(query);
    setPage("bank");
  };

  return (
    <div className="flex h-screen overflow-hidden bg-secondary/40">
      <Sidebar
        active={page}
        onNavigate={(p) => (p === "exam" ? goToNewExam() : setPage(p))}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar
          page={page}
          onMenuClick={() => setSidebarOpen(true)}
          onNavigate={(p) => (p === "exam" ? goToNewExam() : setPage(p))}
          onSelectQuestion={goToBankSearch}
        />

        <main className="flex-1 overflow-y-auto scrollbar-thin">
          <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:py-8">
            {page === "overview" && <OverviewPage onNavigate={(p) => (p === "exam" ? goToNewExam() : setPage(p))} />}
            {page === "upload" && <UploadPage />}
            {page === "analysis" && <AnalysisPage />}
            {page === "bank" && <BankPage onSendToExam={goToExamBuilder} initialSearch={bankSearch} />}
            {page === "exam" && (
              <ExamBuilderPage seedQuestionIds={examSeedIds} editExamId={editExamId} onSaved={goToExams} />
            )}
            {page === "exams" && <ExamsPage onEdit={goToEditExam} />}
          </div>
        </main>
      </div>
    </div>
  );
}

function Gate() {
  const { ready, teacher } = useAuth();
  if (!ready) {
    return <div className="flex min-h-screen items-center justify-center bg-secondary/40" />;
  }
  if (!teacher) {
    return <AuthPage />;
  }
  return <AppShell />;
}

export default function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  );
}
