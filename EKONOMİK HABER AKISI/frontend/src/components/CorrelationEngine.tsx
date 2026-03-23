import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import axios from "axios";
import {
  GitMerge, TrendingUp, TrendingDown, AlertTriangle,
  Shield, ChevronDown, Zap, Plus, X, Info
} from "lucide-react";

const MACRO_INDICATORS = [
  "Faiz Oranı (TCMB Politika Faizi)",
  "Enflasyon (TÜFE)",
  "Dolar/TL Kuru",
  "Euro/TL Kuru",
  "Altın Fiyatı",
  "Petrol Fiyatı (Brent)",
  "BIST-100 Endeksi",
  "Türkiye CDS Primi",
  "Cari Açık",
  "Büyüme Oranı (GSYİH)",
  "İşsizlik Oranı",
  "Bütçe Açığı",
  "Rezervler (TCMB)",
];

const DIRECTIONS = [
  { value: "artıyor / yükseliyor", label: "Artıyor / Yükseliyor", icon: <TrendingUp className="w-4 h-4 text-emerald-400" /> },
  { value: "azalıyor / düşüyor", label: "Azalıyor / Düşüyor", icon: <TrendingDown className="w-4 h-4 text-red-400" /> },
];

const riskColor = (level: string) => {
  if (level === "Yüksek") return "text-red-400 bg-red-400/10 border-red-400/20";
  if (level === "Orta") return "text-amber-400 bg-amber-400/10 border-amber-400/20";
  return "text-emerald-400 bg-emerald-400/10 border-emerald-400/20";
};

const actionColor = (action: string) => {
  if (action === "Sat") return "bg-red-500/20 text-red-300 border-red-500/30";
  if (action === "Azalt") return "bg-orange-500/20 text-orange-300 border-orange-500/30";
  if (action === "Artır") return "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
  return "bg-slate-500/20 text-slate-300 border-slate-500/30";
};

interface CorrelationResult {
  indicator_explanation: string;
  best_sectors: { sector: string; performance: string; reason: string }[];
  worst_sectors: { sector: string; performance: string; reason: string }[];
  portfolio_risks: { ticker: string; risk_level: string; reason: string; action: string }[];
  safe_havens: string[];
  summary: string;
}

async function runCorrelation(indicator: string, direction: string, portfolio: string[]): Promise<CorrelationResult> {
  const { data } = await axios.post("http://localhost:8000/api/correlation", {
    indicator, direction, portfolio
  });
  return data.data;
}

export default function CorrelationEngine() {
  const [indicator, setIndicator] = useState(MACRO_INDICATORS[0]);
  const [customIndicator, setCustomIndicator] = useState("");
  const [direction, setDirection] = useState(DIRECTIONS[0].value);
  const [tickerInput, setTickerInput] = useState("");
  const [portfolio, setPortfolio] = useState<string[]>([]);
  const [result, setResult] = useState<CorrelationResult | null>(null);

  const mutation = useMutation({
    mutationFn: () => runCorrelation(
      customIndicator.trim() || indicator,
      direction,
      portfolio
    ),
    onSuccess: (data) => setResult(data),
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Hata oluştu";
      alert(msg);
    },
  });

  const addTicker = () => {
    const t = tickerInput.trim().toUpperCase();
    if (t && !portfolio.includes(t)) {
      setPortfolio([...portfolio, t]);
    }
    setTickerInput("");
  };

  const removeTicker = (t: string) => setPortfolio(portfolio.filter((x) => x !== t));

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <GitMerge className="w-5 h-5 text-violet-400" />
        <h2 className="text-white font-semibold">Korelasyon Motoru</h2>
        <span className="text-xs bg-violet-500/20 text-violet-300 border border-violet-500/30 px-2 py-0.5 rounded-full">
          Makro → Hisse Projeksiyonu
        </span>
      </div>

      <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-5 space-y-5">
        <div className="bg-violet-500/10 border border-violet-500/20 rounded-xl p-3 flex items-start gap-2">
          <Info className="w-4 h-4 text-violet-400 flex-shrink-0 mt-0.5" />
          <p className="text-violet-300 text-xs leading-relaxed">
            Bir makro gösterge seçin, yönünü belirtin ve portföyünüzdeki hisseleri ekleyin.
            AI, tarihsel korelasyonlara dayanarak hangi sektörlerin kazanıp kaybedeceğini ve portföyünüzdeki riskleri analiz eder.
          </p>
        </div>

        <div>
          <label className="text-slate-400 text-xs font-medium uppercase tracking-wider mb-2 block">
            Makro Ekonomik Gösterge
          </label>
          <div className="relative">
            <select
              value={indicator}
              onChange={(e) => setIndicator(e.target.value)}
              className="w-full bg-slate-900 border border-slate-600 focus:border-violet-500 outline-none rounded-xl px-4 py-3 text-slate-200 text-sm appearance-none cursor-pointer"
            >
              {MACRO_INDICATORS.map((ind) => (
                <option key={ind} value={ind}>{ind}</option>
              ))}
            </select>
            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
          </div>
          <input
            value={customIndicator}
            onChange={(e) => setCustomIndicator(e.target.value)}
            placeholder="veya farklı bir gösterge yazın (örn: Konut Fiyat Endeksi)"
            className="mt-2 w-full bg-slate-900 border border-slate-600 focus:border-violet-500 outline-none rounded-xl px-4 py-2.5 text-slate-200 text-sm placeholder-slate-500"
          />
        </div>

        <div>
          <label className="text-slate-400 text-xs font-medium uppercase tracking-wider mb-2 block">
            Yön
          </label>
          <div className="grid grid-cols-2 gap-2">
            {DIRECTIONS.map((d) => (
              <button
                key={d.value}
                onClick={() => setDirection(d.value)}
                className={`flex items-center gap-2 px-4 py-3 rounded-xl border text-sm font-medium transition-all ${
                  direction === d.value
                    ? "bg-violet-600/30 border-violet-500 text-white"
                    : "bg-slate-900 border-slate-600 text-slate-400 hover:border-slate-500"
                }`}
              >
                {d.icon}
                {d.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="text-slate-400 text-xs font-medium uppercase tracking-wider mb-2 block">
            Portföyünüz (opsiyonel)
          </label>
          <div className="flex gap-2">
            <input
              value={tickerInput}
              onChange={(e) => setTickerInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addTicker()}
              placeholder="Hisse kodu girin (örn: THYAO)"
              className="flex-1 bg-slate-900 border border-slate-600 focus:border-violet-500 outline-none rounded-xl px-4 py-2.5 text-slate-200 text-sm placeholder-slate-500 uppercase"
            />
            <button
              onClick={addTicker}
              className="bg-slate-700 hover:bg-slate-600 border border-slate-600 text-white px-4 py-2.5 rounded-xl transition-all"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>
          {portfolio.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-2">
              {portfolio.map((t) => (
                <span key={t} className="flex items-center gap-1.5 bg-violet-500/20 border border-violet-500/30 text-violet-300 text-xs font-bold px-2.5 py-1 rounded-lg">
                  {t}
                  <button onClick={() => removeTicker(t)} className="hover:text-white">
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>

        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
          className="w-full flex items-center justify-center gap-2 bg-violet-600 hover:bg-violet-500 disabled:bg-slate-700 disabled:text-slate-500 text-white font-semibold py-3 rounded-xl transition-all"
        >
          <Zap className={`w-4 h-4 ${mutation.isPending ? "animate-pulse" : ""}`} />
          {mutation.isPending ? "Analiz Ediliyor..." : "Korelasyon Analizi Başlat"}
        </button>
      </div>

      {result && (
        <div className="mt-6 space-y-5">
          <div className="bg-violet-500/10 border border-violet-500/20 rounded-xl p-4">
            <p className="text-violet-300 text-sm leading-relaxed">{result.indicator_explanation}</p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <div className="flex items-center gap-2 mb-3">
                <TrendingUp className="w-4 h-4 text-emerald-400" />
                <span className="text-emerald-400 text-sm font-semibold">En İyi Performans Gösteren Sektörler</span>
              </div>
              <div className="space-y-2">
                {result.best_sectors.map((s, i) => (
                  <div key={i} className="bg-emerald-400/5 border border-emerald-400/20 rounded-xl p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-emerald-300 font-semibold text-sm">{s.sector}</span>
                      <span className="text-emerald-400 text-xs font-bold">{s.performance}</span>
                    </div>
                    <p className="text-slate-400 text-xs leading-relaxed">{s.reason}</p>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <div className="flex items-center gap-2 mb-3">
                <TrendingDown className="w-4 h-4 text-red-400" />
                <span className="text-red-400 text-sm font-semibold">En Kötü Performans Gösteren Sektörler</span>
              </div>
              <div className="space-y-2">
                {result.worst_sectors.map((s, i) => (
                  <div key={i} className="bg-red-400/5 border border-red-400/20 rounded-xl p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-red-300 font-semibold text-sm">{s.sector}</span>
                      <span className="text-red-400 text-xs font-bold">{s.performance}</span>
                    </div>
                    <p className="text-slate-400 text-xs leading-relaxed">{s.reason}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {result.portfolio_risks.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                <span className="text-amber-400 text-sm font-semibold">Portföy Risk Analizi</span>
              </div>
              <div className="space-y-2">
                {result.portfolio_risks.map((r, i) => (
                  <div key={i} className="bg-slate-800 border border-slate-700 rounded-xl p-4">
                    <div className="flex items-center gap-3 mb-2">
                      <span className="text-white font-bold text-sm bg-slate-700 px-2.5 py-1 rounded-lg">{r.ticker}</span>
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded-lg border ${riskColor(r.risk_level)}`}>
                        {r.risk_level} Risk
                      </span>
                      <span className={`text-xs font-bold px-2.5 py-0.5 rounded-lg border ml-auto ${actionColor(r.action)}`}>
                        {r.action}
                      </span>
                    </div>
                    <p className="text-slate-400 text-xs leading-relaxed">{r.reason}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div>
            <div className="flex items-center gap-2 mb-3">
              <Shield className="w-4 h-4 text-blue-400" />
              <span className="text-blue-400 text-sm font-semibold">Güvenli Liman Önerileri</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {result.safe_havens.map((h, i) => (
                <span key={i} className="bg-blue-500/10 border border-blue-500/20 text-blue-300 text-sm px-3 py-1.5 rounded-xl">
                  {h}
                </span>
              ))}
            </div>
          </div>

          <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
            <p className="text-slate-200 text-sm leading-relaxed">{result.summary}</p>
          </div>
        </div>
      )}
    </div>
  );
}
