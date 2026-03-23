import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import axios from "axios";
import { analyzeNews } from "../api";
import type { AnalysisResult } from "../types";
import AnalysisModal from "./AnalysisModal";
import {
  RefreshCw, ExternalLink, Zap, TrendingUp, TrendingDown,
  Minus, BarChart2, Sparkles, ChevronRight, Clock
} from "lucide-react";

interface TopNewsItem {
  index: number;
  id: string;
  title: string;
  simple: string;
  light: "green" | "red" | "yellow";
  light_reason: string;
  impact_score: number;
  affected_tickers: string[];
  emoji_summary: string;
  url: string;
  source: string;
  published_at: string;
}

interface TopNewsData {
  top_news: TopNewsItem[];
  market_mood: string;
  mood_score: number;
}

async function fetchTopNews(): Promise<TopNewsData> {
  const { data } = await axios.get("http://localhost:8000/api/top-news");
  return data.data;
}

function timeAgo(isoDate: string): string {
  const diff = Date.now() - new Date(isoDate).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "Az önce";
  if (m < 60) return `${m}dk önce`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}sa önce`;
  return `${Math.floor(h / 24)}g önce`;
}

const LIGHT_CONFIG = {
  green: {
    bg: "bg-emerald-500",
    ring: "ring-emerald-400/40",
    glow: "shadow-emerald-500/50",
    border: "border-emerald-500/30",
    cardBg: "bg-emerald-500/5",
    text: "text-emerald-400",
    label: "Olumlu",
    icon: <TrendingUp className="w-4 h-4" />,
    badge: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  },
  red: {
    bg: "bg-red-500",
    ring: "ring-red-400/40",
    glow: "shadow-red-500/50",
    border: "border-red-500/30",
    cardBg: "bg-red-500/5",
    text: "text-red-400",
    label: "Olumsuz",
    icon: <TrendingDown className="w-4 h-4" />,
    badge: "bg-red-500/20 text-red-300 border-red-500/30",
  },
  yellow: {
    bg: "bg-amber-400",
    ring: "ring-amber-400/40",
    glow: "shadow-amber-400/50",
    border: "border-amber-400/30",
    cardBg: "bg-amber-400/5",
    text: "text-amber-400",
    label: "Belirsiz",
    icon: <Minus className="w-4 h-4" />,
    badge: "bg-amber-400/20 text-amber-300 border-amber-400/30",
  },
};

const moodConfig = (score: number) => {
  if (score >= 7) return { color: "text-emerald-400", bar: "bg-emerald-500", label: "Olumlu Seyir" };
  if (score >= 4) return { color: "text-amber-400", bar: "bg-amber-400", label: "Karışık Seyir" };
  return { color: "text-red-400", bar: "bg-red-500", label: "Olumsuz Seyir" };
};

export default function Dashboard() {
  const [analysisResult, setAnalysisResult] = useState<{ result: AnalysisResult; title: string } | null>(null);
  const [analyzingId, setAnalyzingId] = useState<string | null>(null);

  const { data, isLoading, refetch, isRefetching, error } = useQuery({
    queryKey: ["top-news"],
    queryFn: fetchTopNews,
    staleTime: 0,
    retry: 1,
  });

  const analyzeMutation = useMutation({
    mutationFn: ({ title, content }: { title: string; content: string }) =>
      analyzeNews(title, content),
    onSuccess: (result, vars) => {
      setAnalysisResult({ result, title: vars.title });
      setAnalyzingId(null);
    },
    onError: () => setAnalyzingId(null),
  });

  const handleAnalyze = (item: TopNewsItem) => {
    setAnalyzingId(item.id);
    analyzeMutation.mutate({ title: item.title, content: item.simple });
  };

  const mood = data ? moodConfig(data.mood_score) : null;
  const now = new Date();
  const greeting =
    now.getHours() < 12 ? "Günaydın" : now.getHours() < 18 ? "İyi günler" : "İyi akşamlar";

  return (
    <div className="space-y-6">
      <div className="relative overflow-hidden bg-gradient-to-br from-blue-900/40 via-slate-900 to-violet-900/30 border border-slate-700/60 rounded-2xl p-6">
        <div className="absolute top-0 right-0 w-64 h-64 bg-blue-500/5 rounded-full -translate-y-1/2 translate-x-1/4 pointer-events-none" />
        <div className="absolute bottom-0 left-0 w-48 h-48 bg-violet-500/5 rounded-full translate-y-1/2 -translate-x-1/4 pointer-events-none" />
        <div className="relative">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-slate-400 text-sm">{greeting}</p>
              <h2 className="text-white text-2xl font-bold mt-0.5">
                Korkma, Anlatıyorum
              </h2>
              <p className="text-slate-400 text-sm mt-1 max-w-lg">
                Bugünkü ekonomi haberlerini senin için sadeleştirdim. Her haberin yanındaki renkli ışık, hisse fiyatlarına olası etkisini gösteriyor.
              </p>
            </div>
            <div className="flex-shrink-0 hidden sm:flex flex-col items-center justify-center bg-slate-800/60 border border-slate-700 rounded-xl px-4 py-3 min-w-[110px]">
              <Sparkles className="w-5 h-5 text-blue-400 mb-1" />
              <span className="text-slate-400 text-xs text-center">AI Destekli</span>
              <span className="text-white text-xs font-semibold text-center">Anlık Analiz</span>
            </div>
          </div>

          <div className="flex items-center gap-3 mt-4 flex-wrap">
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 inline-block" />
              <span className="text-slate-400 text-xs">Olumlu = Hisse fiyatı yükselir</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-red-400 inline-block" />
              <span className="text-slate-400 text-xs">Olumsuz = Hisse fiyatı düşer</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-400 inline-block" />
              <span className="text-slate-400 text-xs">Belirsiz = Etki net değil</span>
            </div>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BarChart2 className="w-5 h-5 text-blue-400" />
          <h3 className="text-white font-semibold">Günün En Kritik 3 Haberi</h3>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isRefetching}
          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 px-3 py-1.5 rounded-lg transition-all"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isRefetching ? "animate-spin" : ""}`} />
          Yenile
        </button>
      </div>

      {isLoading && (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-slate-800/60 border border-slate-700 rounded-2xl p-5 animate-pulse">
              <div className="flex gap-4">
                <div className="w-14 h-14 rounded-xl bg-slate-700 flex-shrink-0" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 bg-slate-700 rounded w-3/4" />
                  <div className="h-3 bg-slate-700 rounded w-full" />
                  <div className="h-3 bg-slate-700 rounded w-1/2" />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-2xl p-5 text-center">
          <p className="text-amber-300 font-medium text-sm">Top haberler yüklenemedi</p>
          <p className="text-amber-400/60 text-xs mt-1">API anahtarının ayarlandığından emin olun</p>
        </div>
      )}

      {data && (
        <>
          {mood && (
            <div className="bg-slate-800/40 border border-slate-700 rounded-xl px-4 py-3 flex items-center gap-4">
              <div className="flex-1">
                <p className="text-slate-400 text-xs mb-1">Bugün Piyasa Havası</p>
                <p className={`text-sm font-medium ${mood.color}`}>{data.market_mood}</p>
              </div>
              <div className="flex flex-col items-end gap-1 flex-shrink-0">
                <span className={`text-xs font-semibold ${mood.color}`}>{mood.label}</span>
                <div className="w-24 bg-slate-700 rounded-full h-1.5">
                  <div
                    className={`h-1.5 rounded-full ${mood.bar}`}
                    style={{ width: `${(data.mood_score / 10) * 100}%` }}
                  />
                </div>
              </div>
            </div>
          )}

          <div className="space-y-4">
            {data.top_news.map((item, rank) => {
              const cfg = LIGHT_CONFIG[item.light];
              return (
                <div
                  key={item.id || rank}
                  className={`relative overflow-hidden border rounded-2xl p-5 transition-all group ${cfg.cardBg} ${cfg.border}`}
                >
                  <div className="flex gap-4">
                    <div className="flex-shrink-0 flex flex-col items-center gap-2">
                      <div className="relative">
                        <div className={`w-14 h-14 rounded-xl flex items-center justify-center text-2xl border ${cfg.border} bg-slate-900/60`}>
                          {item.emoji_summary}
                        </div>
                        <div className="absolute -bottom-1 -right-1 flex items-center justify-center">
                          <span className={`w-5 h-5 rounded-full ${cfg.bg} ring-2 ${cfg.ring} shadow-lg ${cfg.glow} flex items-center justify-center`}>
                            <span className="text-white" style={{ fontSize: "9px", fontWeight: 700 }}>
                              {rank + 1}
                            </span>
                          </span>
                        </div>
                      </div>
                      <div className="flex flex-col items-center">
                        <div className={`flex items-center gap-1 text-xs font-semibold ${cfg.text}`}>
                          {cfg.icon}
                          <span className="hidden sm:inline">{cfg.label}</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-start gap-2 mb-2 flex-wrap">
                        <span className="text-blue-400 text-xs bg-blue-400/10 border border-blue-400/20 px-2 py-0.5 rounded-full font-medium">
                          {item.source}
                        </span>
                        {item.published_at && (
                          <span className="flex items-center gap-1 text-xs text-slate-500">
                            <Clock className="w-3 h-3" />
                            {timeAgo(item.published_at)}
                          </span>
                        )}
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ml-auto ${cfg.badge}`}>
                          Etki: {item.impact_score}/10
                        </span>
                      </div>

                      <h4 className="text-white font-semibold text-sm leading-snug mb-2 line-clamp-2">
                        {item.title}
                      </h4>

                      <div className={`rounded-xl px-3 py-2 border mb-3 ${cfg.cardBg} ${cfg.border}`}>
                        <p className="text-slate-300 text-sm leading-relaxed">
                          <span className={`font-semibold ${cfg.text}`}>Ne anlama geliyor? </span>
                          {item.simple}
                        </p>
                      </div>

                      <div className="flex items-center gap-2 flex-wrap">
                        <div className={`flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border ${cfg.badge}`}>
                          {cfg.icon}
                          <span className="font-medium">{item.light_reason}</span>
                        </div>
                        {item.affected_tickers?.slice(0, 3).map((ticker) => (
                          <span key={ticker} className="text-xs font-bold text-slate-300 bg-slate-800 border border-slate-700 px-2 py-1 rounded-lg">
                            {ticker}
                          </span>
                        ))}
                      </div>

                      <div className="flex items-center gap-2 mt-3 pt-3 border-t border-slate-700/40">
                        <button
                          onClick={() => handleAnalyze(item)}
                          disabled={analyzingId === item.id}
                          className="flex items-center gap-1.5 text-xs font-medium bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-500 text-white px-3 py-1.5 rounded-lg transition-all"
                        >
                          <Zap className={`w-3.5 h-3.5 ${analyzingId === item.id ? "animate-pulse" : ""}`} />
                          {analyzingId === item.id ? "Analiz Ediliyor..." : "Detaylı Analiz"}
                        </button>
                        <a
                          href={item.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-1 text-xs text-slate-400 hover:text-white transition-colors"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                          Habere Git
                          <ChevronRight className="w-3 h-3" />
                        </a>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </>
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
