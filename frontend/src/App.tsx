import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAppStore } from "@/store/useAppStore";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Header } from "@/components/layout/Header";
import { Sidebar } from "@/components/layout/Sidebar";
import { Dashboard } from "@/pages/Dashboard";
import { FeaturePage } from "@/pages/FeaturePage";
import { HistoryPage } from "@/pages/HistoryPage";
import { LogsPage } from "@/pages/LogsPage";

export default function App() {
  const theme = useAppStore((s) => s.theme);
  const { data, isLoading } = useQuery({ queryKey: ["features"], queryFn: api.features });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  return (
    <TooltipProvider delayDuration={200}>
      {/* Full-height, no-overflow shell */}
      <div
        className="flex bg-canvas"
        style={{ height: "100dvh", overflow: "hidden" }}
      >
        {/* Sidebar — fixed width, never shrinks */}
        <Sidebar
          categories={data?.categories ?? []}
          features={data?.features ?? []}
          isLoading={isLoading}
        />

        {/* Main — takes the rest, clips overflow internally */}
        <div
          className="flex flex-col"
          style={{ flex: 1, minWidth: 0, overflow: "hidden" }}
        >
          <Header />
          <main style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
            <Routes>
              <Route path="/"                   element={<Dashboard />} />
              <Route path="/feature/:featureId" element={<FeaturePage />} />
              <Route path="/history"            element={<HistoryPage />} />
              <Route path="/logs"               element={<LogsPage />} />
              <Route path="*"                   element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </div>
    </TooltipProvider>
  );
}
