import type { AnalysisResult } from "../types";
import { TrendingUp, TrendingDown, Minus, X, Brain, Clock, Building2, BarChart3, Zap, AlertTriangle, Lightbulb } from "lucide-react";

interface Props {
  result: AnalysisResult;
  newsTitle: string;
  onClose: () => void;
}

const impactColor = (impact: string) => {
  if (impact === "positive") return "text-emerald-400 bg-emerald-400/10 border-emerald-400/20";
  if (impact === "negative") return "text-red-400 bg-red-400/10 border-red-400/20";
  return "text-slate-400 bg-slate-400/10 border-slate-400/20";
};

const impactIcon = (impact: string) => {
  if (impact === "positive") return <TrendingUp className="w-4 h-4" />;
  if (impact === "negative") return <TrendingDown className="w-4 h-4" />;
  return <Minus className="w-4 h-4" />;
};

const sentimentColor = (score: number) => {
  if (score >= 5) return "text-emerald-400";
  if (score >= 1) return "text-green-400";
  if (score > -1) return "text-slate-400";
  if (score > -5) return "text-orange-400";
  return "text-red-400";
};

const sentimentBg = (score: number) => {
  if (score >= 5) return "from-emerald-500/20 to-emerald-900/10 border-emerald-500/30";
  if (score >= 1) return "from-green-500/20 to-green-900/10 border-green-500/30";
  if (score > -1) return "from-slate-500/20 to-slate-900/10 border-slate-500/30";
  if (score > -5) return "from-orange-500/20 to-orange-900/10 border-orange-500/30";
  return "from-red-500/20 to-red-900/10 border-red-500/30";
};

const actionConfig = (action: string) => {
  switch (action) {
    case "Al":
      return { bg: "bg-emerald-500", text: "text-white", border: "border-emerald-400", label: "AL" };
    case "Sat":
      return { bg: "bg-red-500", text: "text-white", border: "border-red-400", label: "SAT" };
    case "Dikkat":
      return { bg: "bg-orange-500", text: "text-white", border: "border-orange-400", label: "DİKKAT" };
    default:
      return { bg: "bg-slate-600", text: "text-white", border: "border-slate-500", label: "İZLE" };
  }
};

export default function AnalysisModal({ result, newsTitle, onClose }: Props) {
  const score = result.sentiment_score;
  const scorePercent = ((score + 10) / 20) * 100;
  const action = result.action_suggestion;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/70 backdrop-blur-sm overflow-y-auto py-6 px-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-3xl shadow-2xl">
        <div className="flex items-start justify-between p-6 border-b border-slate-700">
          <div className="flex-1 pr-4">
            <div className="flex items-center gap-2 mb-2">
              <Brain className="w-5 h-5 text-blue-400" />
              <span className="text-blue-400 text-sm font-medium">AI Analiz Sonucu</span>
            </div>
            <h2 className="text-white font-semibold text-base leading-snug line-clamp-2">{newsTitle}</h2>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors mt-1 flex-shrink-0">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl p-4">
            <span className="text-blue-400 text-xs font-semibold uppercase tracking-wider block mb-2">Basit Anlatım</span>
            <p className="text-slate-200 text-sm leading-relaxed">{result.simple_explanation}</p>
          </div>

          {action && (
            <div className="relative overflow-hidden rounded-2xl border border-violet-500/40 bg-gradient-to-br from-violet-900/30 via-slate-900 to-slate-900">
              <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-violet-500 via-blue-400 to-violet-500" />
              <div className="p-5">
                <div className="flex items-center gap-2 mb-3">
                  <div className="bg-violet-500/20 border border-violet-500/30 rounded-lg p-1.5">
                    <Zap className="w-4 h-4 text-violet-400" />
                  </div>
                  <span className="text-violet-300 text-sm font-bold uppercase tracking-wider">Aksiyon Önerisi</span>
                </div>

                <p className="text-white text-base font-semibold leading-snug mb-5">{action.headline}</p>

                <div className="space-y-2 mb-5">
                  {action.watch_list.map((item, i) => {
                    const cfg = actionConfig(item.action);
                    return (
                      <div key={i} className="flex items-start gap-3 bg-slate-800/70 border border-slate-700 rounded-xl p-3">
                        <div className="flex-shrink-0 flex flex-col items-center gap-1.5 pt-0.5">
                          <span className={`${cfg.bg} ${cfg.text} text-xs font-black px-2.5 py-1 rounded-lg min-w-[52px] text-center border ${cfg.border}`}>
                            {cfg.label}
                          </span>
                          <span className="text-slate-300 text-xs font-bold">{item.ticker}</span>
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-slate-200 text-sm font-medium leading-snug">{item.name}</p>
                          <p className="text-slate-400 text-xs mt-1 leading-relaxed">{item.reason}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-3">
                    <div className="flex items-center gap-1.5 mb-1.5">
                      <AlertTriangle className="w-3.5 h-3.5 text-red-400" />
                      <span className="text-red-400 text-xs font-semibold uppercase tracking-wider">Risk Uyarısı</span>
                    </div>
                    <p className="text-slate-300 text-xs leading-relaxed">{action.risk_warning}</p>
                  </div>
                  <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-3">
                    <div className="flex items-center gap-1.5 mb-1.5">
                      <Lightbulb className="w-3.5 h-3.5 text-emerald-400" />
                      <span className="text-emerald-400 text-xs font-semibold uppercase tracking-wider">Gizli Fırsat</span>
                    </div>
                    <p className="text-slate-300 text-xs leading-relaxed">{action.opportunity}</p>
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className={`bg-gradient-to-r ${sentimentBg(score)} border rounded-xl p-4`}>
            <div className="flex items-center justify-between mb-3">
              <span className="text-slate-300 text-xs font-semibold uppercase tracking-wider">Piyasa Duyarlılığı (Sentiment)</span>
              <span className={`text-2xl font-bold ${sentimentColor(score)}`}>
                {score > 0 ? "+" : ""}{score}
              </span>
            </div>
            <div className="w-full bg-slate-700 rounded-full h-2 mb-2">
              <div
                className="h-2 rounded-full transition-all duration-500"
                style={{
                  width: `${scorePercent}%`,
                  background: score >= 0 ? "linear-gradient(to right, #10b981, #34d399)" : "linear-gradient(to right, #ef4444, #f87171)"
                }}
              />
            </div>
            <div className="flex justify-between text-xs text-slate-500">
              <span>-10 (Çok Olumsuz)</span>
              <span className={`font-semibold ${sentimentColor(score)}`}>{result.sentiment_label}</span>
              <span>+10 (Çok Olumlu)</span>
            </div>
          </div>

          <div>
            <div className="flex items-center gap-2 mb-3">
              <Clock className="w-4 h-4 text-slate-400" />
              <span className="text-slate-300 text-sm font-semibold">Vadeli Etkiler</span>
            </div>
            <div className="grid gap-3">
              {[result.time_effects.short_term, result.time_effects.medium_term, result.time_effects.long_term].map((effect) => (
                <div key={effect.period} className={`border rounded-xl p-4 ${impactColor(effect.direction)}`}>
                  <div className="flex items-center gap-2 mb-1">
                    {impactIcon(effect.direction)}
                    <span className="font-semibold text-sm">{effect.period}</span>
                  </div>
                  <p className="text-sm opacity-90 leading-relaxed">{effect.effect}</p>
                </div>
              ))}
            </div>
          </div>

          <div>
            <div className="flex items-center gap-2 mb-3">
              <Building2 className="w-4 h-4 text-slate-400" />
              <span className="text-slate-300 text-sm font-semibold">Etkilenen Şirketler (BIST)</span>
            </div>
            <div className="space-y-2">
              {result.affected_companies.map((co, i) => (
                <div key={i} className="flex items-start gap-3 bg-slate-800 border border-slate-700 rounded-xl p-3">
                  <div className="flex-shrink-0">
                    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-bold border ${impactColor(co.impact)}`}>
                      {impactIcon(co.impact)}
                      {co.ticker}
                    </span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-slate-200 text-sm font-medium">{co.name}</p>
                    <p className="text-slate-400 text-xs mt-0.5 leading-relaxed">{co.reason}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <div className="flex items-center gap-2 mb-3">
              <BarChart3 className="w-4 h-4 text-slate-400" />
              <span className="text-slate-300 text-sm font-semibold">Etkilenen Sektörler</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {result.affected_sectors.map((sec, i) => (
                <div key={i} className={`border rounded-xl p-3 ${impactColor(sec.impact)}`}>
                  <div className="flex items-center gap-2 mb-1">
                    {impactIcon(sec.impact)}
                    <span className="font-semibold text-sm">{sec.name}</span>
                  </div>
                  <p className="text-xs opacity-80 leading-relaxed">{sec.reason}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
