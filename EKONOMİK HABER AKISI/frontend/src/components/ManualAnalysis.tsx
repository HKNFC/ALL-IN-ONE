import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { analyzeManual } from "../api";
import type { AnalysisResult } from "../types";
import AnalysisModal from "./AnalysisModal";
import { FileText, Zap } from "lucide-react";

export default function ManualAnalysis() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<{ data: AnalysisResult; title: string } | null>(null);

  const mutation = useMutation({
    mutationFn: analyzeManual,
    onSuccess: (data) => {
      const firstLine = text.split("\n")[0].slice(0, 100);
      setResult({ data, title: firstLine });
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Analiz sırasında hata oluştu";
      alert(msg);
    },
  });

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <FileText className="w-5 h-5 text-purple-400" />
        <h2 className="text-white font-semibold">Manuel Haber Analizi</h2>
      </div>
      <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-5">
        <p className="text-slate-400 text-sm mb-3">
          Herhangi bir yerden kopyaladığınız haber metnini buraya yapıştırın. AI analiz edecek.
        </p>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Haber metnini buraya yapıştırın..."
          rows={8}
          className="w-full bg-slate-900 border border-slate-600 focus:border-blue-500 outline-none rounded-xl p-4 text-slate-200 text-sm placeholder-slate-500 resize-none transition-colors"
        />
        <div className="flex items-center justify-between mt-3">
          <span className="text-slate-500 text-xs">{text.length} karakter</span>
          <button
            onClick={() => mutation.mutate(text)}
            disabled={mutation.isPending || text.trim().length < 20}
            className="flex items-center gap-2 bg-purple-600 hover:bg-purple-500 disabled:bg-slate-700 disabled:text-slate-500 text-white text-sm font-medium px-5 py-2 rounded-lg transition-all"
          >
            <Zap className={`w-4 h-4 ${mutation.isPending ? "animate-pulse" : ""}`} />
            {mutation.isPending ? "Analiz Ediliyor..." : "Analiz Et"}
          </button>
        </div>
      </div>

      {result && (
        <AnalysisModal
          result={result.data}
          newsTitle={result.title}
          onClose={() => setResult(null)}
        />
      )}
    </div>
  );
}
