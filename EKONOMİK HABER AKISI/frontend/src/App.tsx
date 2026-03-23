import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { checkHealth } from "./api";
import Dashboard from "./components/Dashboard";
import NewsFeed from "./components/NewsFeed";
import ManualAnalysis from "./components/ManualAnalysis";
import AnalystPanel from "./components/AnalystPanel";
import CorrelationEngine from "./components/CorrelationEngine";
import {
  TrendingUp, Newspaper, FileText, Users,
  AlertCircle, CheckCircle, GitMerge, LayoutDashboard
} from "lucide-react";

const queryClient = new QueryClient();

type Tab = "dashboard" | "news" | "manual" | "correlation" | "analysts";

function AppContent() {
  const [tab, setTab] = useState<Tab>("dashboard");

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: checkHealth,
    staleTime: 60 * 1000,
  });

  const tabs = [
    { id: "dashboard" as Tab, label: "Dashboard", icon: <LayoutDashboard className="w-4 h-4" /> },
    { id: "news" as Tab, label: "Tüm Haberler", icon: <Newspaper className="w-4 h-4" /> },
    { id: "manual" as Tab, label: "Manuel Analiz", icon: <FileText className="w-4 h-4" /> },
    { id: "correlation" as Tab, label: "Korelasyon", icon: <GitMerge className="w-4 h-4" /> },
    { id: "analysts" as Tab, label: "Analistler", icon: <Users className="w-4 h-4" /> },
  ];

  return (
    <div className="min-h-screen bg-slate-950">
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-sm sticky top-0 z-40">
        <div className="max-w-5xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="bg-blue-600 w-8 h-8 rounded-lg flex items-center justify-center">
                <TrendingUp className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-white font-bold text-base leading-none">Ekonomik Haber Akışı</h1>
                <p className="text-slate-500 text-xs mt-0.5">Yapay Zeka Destekli Yatırım Analiz Platformu</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {health ? (
                health.api_key_configured ? (
                  <span className="flex items-center gap-1.5 text-xs text-emerald-400">
                    <CheckCircle className="w-3.5 h-3.5" />
                    AI Hazır
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5 text-xs text-amber-400">
                    <AlertCircle className="w-3.5 h-3.5" />
                    API Key Eksik
                  </span>
                )
              ) : null}
            </div>
          </div>
          <div className="flex gap-1 mt-3 overflow-x-auto scrollbar-hide">
            {tabs.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-all whitespace-nowrap ${
                  tab === t.id
                    ? "bg-blue-600 text-white font-medium"
                    : "text-slate-400 hover:text-white hover:bg-slate-800"
                }`}
              >
                {t.icon}
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-6">
        {health && !health.api_key_configured && (
          <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-4 mb-6 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-amber-300 font-medium text-sm">API Anahtarı Yapılandırılmadı</p>
              <p className="text-amber-400/70 text-xs mt-1">
                Analiz özelliğini kullanmak için{" "}
                <code className="bg-amber-900/30 px-1 rounded">backend/.env</code> dosyasına{" "}
                <code className="bg-amber-900/30 px-1 rounded">ANTHROPIC_API_KEY</code> ekleyin.
              </p>
            </div>
          </div>
        )}

        {tab === "dashboard" && <Dashboard />}
        {tab === "news" && <NewsFeed />}
        {tab === "manual" && <ManualAnalysis />}
        {tab === "correlation" && <CorrelationEngine />}
        {tab === "analysts" && <AnalystPanel />}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppContent />
    </QueryClientProvider>
  );
}
