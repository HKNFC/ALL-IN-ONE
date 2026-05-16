/**
 * BacktestComparison — select 2-3 completed backtests, overlay equity curves,
 * and show a side-by-side metrics table.
 */
import { useState, useMemo } from 'react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend,
} from 'recharts';
import { Check, X } from 'lucide-react';

export interface BacktestSummary {
  id:               string;
  name:             string;
  criteriaType:     string;
  totalReturn:      number;
  annualizedReturn: number;
  maxDrawdown:      number;
  sharpeRatio:      number;
  winRate:          number;
  totalTrades:      number;
  portfolioHistory: { date: string; value: number }[];
}

interface Props {
  available: BacktestSummary[];
}

const PALETTE = ['#00D084', '#409CFF', '#FFC700', '#FF4757'];

const METRIC_ROWS: { key: keyof BacktestSummary; label: string; fmt: (v: number) => string; goodHigh: boolean }[] = [
  { key: 'totalReturn',      label: 'Toplam Getiri',   fmt: v => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`, goodHigh: true  },
  { key: 'annualizedReturn', label: 'Yıllık Getiri',   fmt: v => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`, goodHigh: true  },
  { key: 'maxDrawdown',      label: 'Maks. Drawdown',  fmt: v => `${v.toFixed(1)}%`,                     goodHigh: false },
  { key: 'sharpeRatio',      label: 'Sharpe Oranı',    fmt: v => v.toFixed(2),                           goodHigh: true  },
  { key: 'winRate',          label: 'Kazanma Oranı',   fmt: v => `${v.toFixed(1)}%`,                     goodHigh: true  },
  { key: 'totalTrades',      label: 'Toplam İşlem',    fmt: v => String(Math.round(v)),                  goodHigh: false },
];

export function BacktestComparison({ available }: Props) {
  const [selected, setSelected] = useState<string[]>([]);

  const toggle = (id: string) => {
    setSelected(prev =>
      prev.includes(id)
        ? prev.filter(x => x !== id)
        : prev.length < 3 ? [...prev, id] : prev,
    );
  };

  const items = useMemo(
    () => available.filter(b => selected.includes(b.id)),
    [available, selected],
  );

  // Normalise equity curves to start at 100
  const chartData = useMemo(() => {
    if (items.length === 0) return [];
    const maxLen = Math.max(...items.map(b => b.portfolioHistory.length));
    return Array.from({ length: maxLen }, (_, i) => {
      const row: Record<string, string | number> = {
        date: items[0]?.portfolioHistory[i]?.date ?? '',
      };
      items.forEach(b => {
        const h = b.portfolioHistory;
        if (i < h.length) {
          const base = h[0]?.value ?? 1;
          row[b.id] = +(h[i].value / base * 100).toFixed(2);
        }
      });
      return row;
    });
  }, [items]);

  // Best value per metric for highlighting
  const best = useMemo(() => {
    const res: Record<string, string> = {};
    METRIC_ROWS.forEach(({ key, goodHigh }) => {
      let bestId = '';
      let bestVal = goodHigh ? -Infinity : Infinity;
      items.forEach(b => {
        const v = b[key] as number;
        if (goodHigh ? v > bestVal : v < bestVal) { bestVal = v; bestId = b.id; }
      });
      res[key as string] = bestId;
    });
    return res;
  }, [items]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Selector */}
      <div>
        <div style={{ fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 8 }}>
          KARŞILAŞTIR (maks. 3)
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {available.map((b, i) => {
            const active = selected.includes(b.id);
            const color  = active ? PALETTE[selected.indexOf(b.id)] : 'var(--border)';
            return (
              <button key={b.id} onClick={() => toggle(b.id)} style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '5px 12px', borderRadius: 6, cursor: 'pointer',
                background: active ? `${color}15` : 'transparent',
                border: `1px solid ${color}`,
                color: active ? color : 'var(--text-2)',
                fontSize: 11, fontFamily: 'inherit', transition: 'all 0.15s',
              }}>
                {active ? <Check size={10} /> : <span style={{ width: 10, height: 10, borderRadius: '50%', background: PALETTE[i % 4], opacity: 0.4, display:'inline-block' }} />}
                {b.name}
                <span style={{ fontSize: 9, color: 'var(--text-3)' }}>{b.criteriaType}</span>
              </button>
            );
          })}
        </div>
      </div>

      {items.length < 2 && (
        <div style={{ color: 'var(--text-3)', fontSize: 12, padding: '20px 0' }}>
          En az 2 backtest seçin
        </div>
      )}

      {items.length >= 2 && (
        <>
          {/* Equity curve overlay */}
          <div className="card" style={{ padding: 16 }}>
            <div style={{ fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 12 }}>
              NORMALIZE EDİLMİŞ GETİRİ (başlangıç = 100)
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={chartData} margin={{ top: 4, right: 12, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                <XAxis dataKey="date" tick={{ fontSize: 9, fill: 'var(--text-3)' }} tickFormatter={d => d ? String(d).slice(2,7) : ''} />
                <YAxis tick={{ fontSize: 9, fill: 'var(--text-3)' }} tickFormatter={v => `${v}`} />
                <Tooltip
                  contentStyle={{ background:'var(--surface-el)', border:'1px solid var(--border)', borderRadius:6, fontSize:11 }}
                  formatter={(v: number, name: string) => {
                    const b = items.find(x => x.id === name);
                    return [`${v.toFixed(1)}`, b?.name ?? name];
                  }}
                />
                <Legend formatter={name => { const b = items.find(x => x.id === name); return b?.name ?? name; }} />
                {items.map((b, i) => (
                  <Line key={b.id} dataKey={b.id} stroke={PALETTE[i]} strokeWidth={1.5} dot={false} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Metrics comparison table */}
          <div className="card" style={{ overflow: 'hidden' }}>
            <div style={{
              display: 'grid', gridTemplateColumns: `160px repeat(${items.length}, 1fr)`,
              padding: '8px 14px', borderBottom: '1px solid var(--border)',
              fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.07em', background: 'var(--surface-el)',
            }}>
              <span>METRİK</span>
              {items.map((b, i) => (
                <span key={b.id} style={{ color: PALETTE[i], textAlign: 'center' }}>{b.name}</span>
              ))}
            </div>
            {METRIC_ROWS.map(({ key, label, fmt, goodHigh }, rowIdx) => (
              <div key={key as string} className={rowIdx % 2 === 0 ? 'table-row-even' : 'table-row-odd'} style={{
                display: 'grid', gridTemplateColumns: `160px repeat(${items.length}, 1fr)`,
                padding: '9px 14px', fontSize: 12, alignItems: 'center',
              }}>
                <span style={{ color: 'var(--text-2)' }}>{label}</span>
                {items.map((b, i) => {
                  const v    = b[key] as number;
                  const isBest = best[key as string] === b.id;
                  return (
                    <span key={b.id} style={{
                      textAlign: 'center', fontFamily: 'monospace', fontWeight: isBest ? 700 : 400,
                      color: isBest
                        ? PALETTE[i]
                        : key === 'maxDrawdown' ? '#FF4757'
                        : key === 'totalReturn' || key === 'annualizedReturn' ? (v >= 0 ? '#00D084' : '#FF4757')
                        : 'var(--text)',
                    }}>
                      {fmt(v)}
                      {isBest && <span style={{ fontSize: 8, marginLeft: 3, verticalAlign: 'super' }}>★</span>}
                    </span>
                  );
                })}
              </div>
            ))}
          </div>

          {/* Winner summary */}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {METRIC_ROWS.filter(m => best[m.key as string]).map(({ key, label, goodHigh }) => {
              const winner = items.find(b => b.id === best[key as string]);
              if (!winner) return null;
              const ci = selected.indexOf(winner.id);
              return (
                <div key={key as string} style={{
                  padding: '4px 10px', borderRadius: 6, fontSize: 10,
                  background: `${PALETTE[ci]}12`, border: `1px solid ${PALETTE[ci]}30`,
                  color: PALETTE[ci],
                }}>
                  {goodHigh ? '↑' : '↓'} {label}: <strong>{winner.name}</strong>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
