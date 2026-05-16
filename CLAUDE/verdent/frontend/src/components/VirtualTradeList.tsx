/**
 * VirtualTradeList — virtualised list of backtest trades.
 * Uses @tanstack/react-virtual for efficient rendering of 1 000+ rows.
 */
import { useRef, useMemo, useCallback } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { ArrowUpRight, ArrowDownRight } from 'lucide-react';

export interface Trade {
  id:       string;
  symbol:   string;
  action:   'BUY' | 'SELL';
  date:     string;
  price:    number;
  shares:   number;
  value:    number;
  reason:   string;
  pnl?:     number;
  pnlPct?:  number;
}

interface Props {
  trades:         Trade[];
  height?:        number;  // px, default 480
  filterSymbol?:  string;
  filterAction?:  'BUY' | 'SELL' | 'ALL';
  sortByPnl?:     boolean;
}

const ROW_HEIGHT = 44;

export function VirtualTradeList({
  trades,
  height = 480,
  filterSymbol,
  filterAction = 'ALL',
  sortByPnl = false,
}: Props) {
  const parentRef = useRef<HTMLDivElement>(null);

  // Memoised filtered + sorted list
  const filtered = useMemo(() => {
    let list = trades;
    if (filterSymbol) {
      const q = filterSymbol.toUpperCase();
      list = list.filter(t => t.symbol.includes(q));
    }
    if (filterAction !== 'ALL') {
      list = list.filter(t => t.action === filterAction);
    }
    if (sortByPnl) {
      list = [...list].sort((a, b) => (b.pnl ?? 0) - (a.pnl ?? 0));
    }
    return list;
  }, [trades, filterSymbol, filterAction, sortByPnl]);

  const virtualizer = useVirtualizer({
    count:          filtered.length,
    getScrollElement: () => parentRef.current,
    estimateSize:   useCallback(() => ROW_HEIGHT, []),
    overscan:       10,
  });

  if (filtered.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-gray-500 text-sm">
        İşlem bulunamadı
      </div>
    );
  }

  return (
    <div
      ref={parentRef}
      style={{ height, overflowY: 'auto' }}
      className="relative w-full rounded-lg border border-gray-800"
    >
      {/* Sticky header */}
      <div className="sticky top-0 z-10 grid grid-cols-7 gap-2 px-3 py-2 bg-gray-900 border-b border-gray-800 text-xs font-semibold text-gray-400 uppercase tracking-wide">
        <span>Tarih</span>
        <span>Sembol</span>
        <span>İşlem</span>
        <span className="text-right">Fiyat</span>
        <span className="text-right">Lot</span>
        <span className="text-right">Değer</span>
        <span className="text-right">K/Z</span>
      </div>

      {/* Virtual rows */}
      <div
        style={{ height: virtualizer.getTotalSize(), position: 'relative' }}
      >
        {virtualizer.getVirtualItems().map(vRow => {
          const t = filtered[vRow.index];
          const isBuy  = t.action === 'BUY';
          const pnlPos = (t.pnl ?? 0) >= 0;

          return (
            <div
              key={vRow.key}
              data-index={vRow.index}
              ref={virtualizer.measureElement}
              style={{
                position:  'absolute',
                top:       vRow.start,
                left:      0,
                right:     0,
                height:    ROW_HEIGHT,
              }}
              className={`grid grid-cols-7 gap-2 items-center px-3 text-sm border-b border-gray-800/50
                ${vRow.index % 2 === 0 ? 'bg-gray-950' : 'bg-gray-900/60'}
                hover:bg-gray-800/60 transition-colors`}
            >
              <span className="text-gray-400 text-xs">
                {new Date(t.date).toLocaleDateString('tr-TR')}
              </span>
              <span className="font-mono font-semibold text-white">{t.symbol}</span>
              <span className={`flex items-center gap-1 font-semibold text-xs
                ${isBuy ? 'text-emerald-400' : 'text-red-400'}`}>
                {isBuy
                  ? <ArrowUpRight size={12} />
                  : <ArrowDownRight size={12} />}
                {t.action}
              </span>
              <span className="text-right text-gray-200 font-mono text-xs">
                {t.price.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}
              </span>
              <span className="text-right text-gray-400 text-xs">
                {t.shares.toFixed(0)}
              </span>
              <span className="text-right text-gray-200 font-mono text-xs">
                {(t.value / 1000).toFixed(1)}K
              </span>
              <span className={`text-right font-mono text-xs font-semibold
                ${t.pnl !== undefined ? (pnlPos ? 'text-emerald-400' : 'text-red-400') : 'text-gray-600'}`}>
                {t.pnl !== undefined
                  ? `${pnlPos ? '+' : ''}${t.pnlPct?.toFixed(1) ?? '0.0'}%`
                  : '—'}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
