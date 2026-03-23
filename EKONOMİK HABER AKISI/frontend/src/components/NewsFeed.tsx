import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { fetchNews, analyzeNews } from "../api";
import type { NewsItem, AnalysisResult } from "../types";
import AnalysisModal from "./AnalysisModal";
import { RefreshCw, ExternalLink, Zap, Clock, Newspaper } from "lucide-react";

function timeAgo(isoDate: string): string {
  const diff = Date.now() - new Date(isoDate).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "Az önce";
  if (m < 60) return `${m}dk önce`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}sa önce`;
  return `${Math.floor(h / 24)}g önce`;
}

export default function NewsFeed() {
  const [analyzing, setAnalyzing] = useState<string | null>(null);
  const [analysisResult, setAnalysisResult] = useState<{ result: AnalysisResult; title: string } | null>(null);

  const { data: news, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["news"],
    queryFn: () => fetchNews(60),
    staleTime: 5 * 60 * 1000,
  });

  const analyzeMutation = useMutation({
    mutationFn: ({ title, content }: { title: string; content: string }) =>
      analyzeNews(title, content),
    onSuccess: (data, variables) => {
      setAnalysisResult({ result: data, title: variables.title });
      setAnalyzing(null);
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Analiz sırasında hata oluştu";
      alert(msg);
      setAnalyzing(null);
    },
  });

  const handleAnalyze = (item: NewsItem) => {
    setAnalyzing(item.id);
    analyzeMutation.mutate({ title: item.title, content: item.summary || item.title });
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Newspaper className="w-5 h-5 text-blue-400" />
          <h2 className="text-white font-semibold">Son Haberler</h2>
          {news && <span className="bg-slate-700 text-slate-400 text-xs px-2 py-0.5 rounded-full">{news.length}</span>}
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 px-3 py-1.5 rounded-lg transition-all"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? "animate-spin" : ""}`} />
          Yenile
        </button>
      </div>

      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="bg-slate-800 border border-slate-700 rounded-xl p-4 animate-pulse">
              <div className="h-4 bg-slate-700 rounded w-3/4 mb-2" />
              <div className="h-3 bg-slate-700 rounded w-1/2" />
            </div>
          ))}
        </div>
      )}

      {news && (
        <div className="space-y-2">
          {news.map((item) => (
            <div
              key={item.id}
              className="bg-slate-800/60 border border-slate-700 hover:border-slate-600 rounded-xl p-4 transition-all group"
            >
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-xs font-medium text-blue-400 bg-blue-400/10 px-2 py-0.5 rounded-full border border-blue-400/20">
                      {item.source}
                    </span>
                    <span className="flex items-center gap-1 text-xs text-slate-500">
                      <Clock className="w-3 h-3" />
                      {timeAgo(item.published_at)}
                    </span>
                  </div>
                  <h3 className="text-slate-100 text-sm font-medium leading-snug line-clamp-2 mb-1">
                    {item.title}
                  </h3>
                  {item.summary && (
                    <p className="text-slate-500 text-xs leading-relaxed line-clamp-2">{item.summary}</p>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2 mt-3 pt-3 border-t border-slate-700/50">
                <button
                  onClick={() => handleAnalyze(item)}
                  disabled={analyzing === item.id}
                  className="flex items-center gap-1.5 text-xs font-medium bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-500 text-white px-3 py-1.5 rounded-lg transition-all"
                >
                  <Zap className={`w-3.5 h-3.5 ${analyzing === item.id ? "animate-pulse" : ""}`} />
                  {analyzing === item.id ? "Analiz Ediliyor..." : "AI ile Analiz Et"}
                </button>
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white px-3 py-1.5 rounded-lg border border-slate-700 hover:border-slate-600 transition-all"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  Habere Git
                </a>
              </div>
            </div>
          ))}
        </div>
      )}

      {analysisResult && (
        <AnalysisModal
          result={analysisResult.result}
          newsTitle={analysisResult.title}
          onClose={() => setAnalysisResult(null)}
        />
      )}
    </div>
  );
}
