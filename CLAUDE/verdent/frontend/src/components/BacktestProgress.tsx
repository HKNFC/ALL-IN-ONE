/**
 * BacktestProgress — live progress card for a running backtest.
 * Subscribes to 'backtest:progress' WS events and displays stage + progress bar.
 */
import { useEffect, useState, useMemo } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { Loader2, CheckCircle2, XCircle } from 'lucide-react';

type Stage = 'scanning' | 'portfolio' | 'calculating';

interface ProgressPayload {
  id:          string;
  stage:       Stage;
  progress:    number;
  message:     string;
  currentDate?: string;
}

interface Props {
  backtestId: string;
  status:     'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
  onComplete?: () => void;
}

const STAGE_LABELS: Record<Stage, string> = {
  scanning:    'Hisse Taranıyor',
  portfolio:   'Portföy Yönetimi',
  calculating: 'Metrikler Hesaplanıyor',
};

const STAGE_ORDER: Stage[] = ['scanning', 'portfolio', 'calculating'];

export function BacktestProgress({ backtestId, status, onComplete }: Props) {
  const { lastMessage } = useWebSocket<ProgressPayload>('backtest:progress');
  const [progress, setProgress] = useState<ProgressPayload | null>(null);

  useEffect(() => {
    if (lastMessage?.payload.id === backtestId) {
      setProgress(lastMessage.payload);
      if (lastMessage.payload.progress >= 100) onComplete?.();
    }
  }, [lastMessage, backtestId, onComplete]);

  const currentStageIdx = useMemo(() => {
    if (!progress) return 0;
    return STAGE_ORDER.indexOf(progress.stage);
  }, [progress]);

  if (status === 'COMPLETED') {
    return (
      <div className="flex items-center gap-2 text-emerald-400 text-sm font-medium">
        <CheckCircle2 size={16} />
        Backtest tamamlandı
      </div>
    );
  }

  if (status === 'FAILED') {
    return (
      <div className="flex items-center gap-2 text-red-400 text-sm font-medium">
        <XCircle size={16} />
        Backtest başarısız
      </div>
    );
  }

  const pct = progress?.progress ?? 0;

  return (
    <div className="space-y-3 p-4 bg-gray-900 rounded-xl border border-gray-800">
      {/* Stage indicators */}
      <div className="flex items-center gap-1">
        {STAGE_ORDER.map((stage, idx) => (
          <div key={stage} className="flex items-center gap-1">
            <div className={`flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-full transition-colors
              ${idx < currentStageIdx  ? 'bg-emerald-500/20 text-emerald-400'
              : idx === currentStageIdx ? 'bg-[#00D084]/20 text-[#00D084]'
              : 'bg-gray-800 text-gray-500'}`}>
              {idx === currentStageIdx && (
                <Loader2 size={10} className="animate-spin" />
              )}
              {STAGE_LABELS[stage]}
            </div>
            {idx < STAGE_ORDER.length - 1 && (
              <div className={`h-px w-4 ${idx < currentStageIdx ? 'bg-emerald-500' : 'bg-gray-700'}`} />
            )}
          </div>
        ))}
      </div>

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="flex justify-between items-center text-xs text-gray-400">
          <span>{progress?.message ?? 'Başlatılıyor...'}</span>
          <span className="font-mono text-[#00D084]">{pct}%</span>
        </div>
        <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-[#00D084] to-emerald-400 rounded-full transition-all duration-300"
            style={{ width: `${pct}%` }}
          />
        </div>
        {progress?.currentDate && (
          <div className="text-xs text-gray-500">
            İşlenen tarih: {new Date(progress.currentDate).toLocaleDateString('tr-TR')}
          </div>
        )}
      </div>
    </div>
  );
}
