'use client';
import { useMemo } from 'react';
import { ScoreRing } from './ScoreRing';
import { MiniSparkline } from './MiniSparkline';
import { useBreakoutStore } from '@/store/useBreakoutStore';
import type { BreakoutStock } from '@/lib/mockData';

function pctColor(v: number) { return v >= 0 ? 'var(--bull)' : 'var(--bear)'; }
function fmt(v: number) { return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`; }
function fmtVol(v: number) {
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)}B`;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(0)}M`;
  return `${(v / 1_000).toFixed(0)}K`;
}

function seedSparkline(sym: string, n = 20): number[] {
  let seed = sym.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  const vals: number[] = [100];
  for (let i = 1; i < n; i++) {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    vals.push(vals[i-1] * (1 + ((seed % 100) - 47) * 0.003));
  }
  return vals;
}

interface RowProps { stock: BreakoutStock; idx: number; isActive: boolean; onSelect: () => void; }

function StockRow({ stock: s, idx, isActive, onSelect }: RowProps) {
  const spark = useMemo(() => seedSparkline(s.symbol), [s.symbol]);
  const sparkColor = s.change1m >= 0 ? '#00D084' : '#FF4757';

  const GRID = '70px 160px 90px 70px 70px 70px 90px 70px 130px 60px 60px 80px 80px';

  return (
    <div
      onClick={onSelect}
      style={{
        display: 'grid', gridTemplateColumns: GRID,
        padding: '9px 12px', borderBottom: '1px solid var(--border)',
        cursor: 'pointer', alignItems: 'center',
        background: isActive ? 'rgba(0,208,132,0.06)' : idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)',
        borderLeft: `2px solid ${isActive ? 'var(--accent)' : 'transparent'}`,
        transition: 'background 0.12s ease',
      }}
    >
      <div><ScoreRing score={s.breakoutScore} size={36} /></div>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 12, fontWeight: 700, color: isActive ? 'var(--accent)' : 'var(--text)', fontFamily: 'var(--font-mono)' }}>{s.symbol}</span>
          {s.isBreakingOut && <span className="badge badge-bull" style={{ fontSize: 8, padding: '1px 5px' }}>⚡</span>}
        </div>
        <div style={{ fontSize: 9, color: 'var(--text-3)', marginTop: 1 }}>{s.sector}</div>
      </div>
      <div style={{ fontSize: 12, fontWeight: 600, fontFamily: 'var(--font-mono)' }}>{s.price.toFixed(2)}₺</div>
      {[s.change1d, s.change1w, s.change1m].map((c, i) => (
        <div key={i} style={{ fontSize: 11, fontWeight: 600, color: pctColor(c), fontFamily: 'var(--font-mono)' }}>{fmt(c)}</div>
      ))}
      <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)' }}>{fmtVol(s.volume)}</div>
      <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: s.volumeRatio > 2 ? 'var(--bull)' : s.volumeRatio > 1.5 ? 'var(--sideways)' : 'var(--text-2)', fontWeight: s.volumeRatio > 2 ? 700 : 400 }}>{s.volumeRatio.toFixed(1)}x</div>
      <div style={{ fontSize: 10, color: 'var(--blue)', padding: '2px 6px', background: 'rgba(74,158,255,0.08)', borderRadius: 4, display: 'inline-block', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 122, whiteSpace: 'nowrap' }}>{s.pattern}</div>
      <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: s.rsi > 70 ? 'var(--bear)' : s.rsi < 40 ? 'var(--blue)' : 'var(--text-2)' }}>{s.rsi.toFixed(0)}</div>
      <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: s.adx > 30 ? 'var(--bull)' : 'var(--text-2)', fontWeight: s.adx > 30 ? 700 : 400 }}>{s.adx.toFixed(0)}</div>
      <div style={{ display: 'flex', gap: 3 }}>
        <span style={{ fontSize: 8, padding: '1px 4px', borderRadius: 3, background: s.aboveEma50 ? 'rgba(0,208,132,0.12)' : 'rgba(255,71,87,0.12)', color: s.aboveEma50 ? 'var(--bull)' : 'var(--bear)', fontFamily: 'var(--font-mono)' }}>50</span>
        <span style={{ fontSize: 8, padding: '1px 4px', borderRadius: 3, background: s.aboveEma200 ? 'rgba(0,208,132,0.12)' : 'rgba(255,71,87,0.12)', color: s.aboveEma200 ? 'var(--bull)' : 'var(--bear)', fontFamily: 'var(--font-mono)' }}>200</span>
      </div>
      <div style={{ height: 28 }}>
        <MiniSparkline data={spark} color={sparkColor} height={28} />
      </div>
    </div>
  );
}

const COLS = ['SKOR','HİSSE','FİYAT','1G','1H','1A','HACİM','H.ORAN','PATTERN','RSI','ADX','EMA','20G'];
const GRID = '70px 160px 90px 70px 70px 70px 90px 70px 130px 60px 60px 80px 80px';

interface Props { stocks: BreakoutStock[]; onSelect: (s: BreakoutStock) => void; }

export function BreakoutTable({ stocks, onSelect }: Props) {
  const { selectedSymbol } = useBreakoutStore();
  return (
    <div className="card" style={{ overflow: 'hidden' }}>
      <div style={{ display: 'grid', gridTemplateColumns: GRID, padding: '8px 12px', background: 'var(--bg-elevated)', borderBottom: '1px solid var(--border)' }}>
        {COLS.map(c => (
          <div key={c} style={{ fontSize: 9, color: 'var(--text-3)', letterSpacing: '0.1em', fontFamily: 'var(--font-mono)' }}>{c}</div>
        ))}
      </div>
      <div style={{ maxHeight: 520, overflowY: 'auto' }}>
        {stocks.map((s, i) => (
          <StockRow key={s.symbol} stock={s} idx={i} isActive={selectedSymbol === s.symbol} onSelect={() => onSelect(s)} />
        ))}
        {stocks.length === 0 && (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-3)', fontSize: 12 }}>Filtre kriterlerine uyan hisse bulunamadı</div>
        )}
      </div>
    </div>
  );
}
