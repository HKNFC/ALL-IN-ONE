'use client';
import { useMemo } from 'react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, BarChart, Bar, Cell, ReferenceLine } from 'recharts';
import { ScoreRing } from './ScoreRing';
import { generateMockPriceHistory } from '@/lib/mockData';
import type { BreakoutStock } from '@/lib/mockData';

interface Props { stock: BreakoutStock; onClose: () => void; }

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ value: number; color: string; name: string }>;
  label?: string;
}

function CustomTooltip({ active, payload, label }: TooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: '#0F1629', border: '1px solid #1E2D4A', borderRadius: 6, padding: '8px 12px', fontSize: 11 }}>
      <div style={{ color: '#8899AA', marginBottom: 4 }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color || '#fff', fontWeight: 600 }}>
          {p.name}: {typeof p.value === 'number' ? p.value.toFixed(2) : p.value}
        </div>
      ))}
    </div>
  );
}

export function StockDetailPanel({ stock: s, onClose }: Props) {
  const history = useMemo(() => generateMockPriceHistory(120), [s.symbol]);
  const chartData = history.map(h => ({ ...h, ma20: 0 }));

  // Calculate EMA20 for chart
  let ema = chartData[0]?.close ?? 0;
  for (const bar of chartData) {
    ema = bar.close * (2 / 21) + ema * (1 - 2 / 21);
    bar.ma20 = +ema.toFixed(2);
  }

  const firstClose = chartData[0]?.close ?? 1;
  const rebased = chartData.map(d => ({ ...d, pct: +((d.close - firstClose) / firstClose * 100).toFixed(2) }));

  const isPositive = s.change1m >= 0;
  const chartColor = isPositive ? '#00D084' : '#FF4757';

  // Score breakdown bars (deterministic based on symbol)
  const symSeed = s.symbol.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  const factors = [
    { name: 'Momentum', score: 40 + (symSeed * 7) % 60, color: 'var(--accent)' },
    { name: 'Hacim', score: 30 + (symSeed * 11) % 70, color: 'var(--blue)' },
    { name: 'Trend', score: 35 + (symSeed * 13) % 65, color: 'var(--sideways)' },
    { name: 'Pattern', score: 40 + (symSeed * 17) % 60, color: 'var(--purple)' },
    { name: 'Rölatif', score: 25 + (symSeed * 19) % 75, color: '#FF6B9D' },
  ];

  return (
    <div className="card fade-in" style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <ScoreRing score={s.breakoutScore} size={52} />
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 18, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{s.symbol}</span>
              {s.isBreakingOut && <span className="badge badge-bull">⚡ KIRILIM</span>}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 2 }}>{s.name} · {s.sector}</div>
          </div>
        </div>
        <button onClick={onClose} className="btn-ghost" style={{ fontSize: 16, padding: '4px 10px' }}>✕</button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 14 }}>

        {/* Price + key metrics row */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 8 }}>
          {[
            { l: 'FİYAT', v: `${s.price.toFixed(2)}₺`, c: 'var(--text)' },
            { l: '1G DEĞİŞİM', v: `${s.change1d >= 0 ? '+' : ''}${s.change1d.toFixed(2)}%`, c: s.change1d >= 0 ? 'var(--bull)' : 'var(--bear)' },
            { l: 'HEDEF', v: `${s.targetPrice?.toFixed(2)}₺`, c: 'var(--bull)' },
            { l: 'STOP', v: `${s.stopLoss?.toFixed(2)}₺`, c: 'var(--bear)' },
          ].map(m => (
            <div key={m.l} style={{ background: 'var(--bg-elevated)', borderRadius: 6, padding: '10px 12px', border: '1px solid var(--border)' }}>
              <div style={{ fontSize: 9, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 4 }}>{m.l}</div>
              <div style={{ fontSize: 15, fontWeight: 700, color: m.c, fontFamily: 'var(--font-mono)' }}>{m.v}</div>
            </div>
          ))}
        </div>

        {/* Price chart */}
        <div style={{ background: 'var(--bg-elevated)', borderRadius: 6, border: '1px solid var(--border)', padding: '12px 14px' }}>
          <div style={{ fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 10 }}>📈 FİYAT GRAFİĞİ (120 GÜN)</div>
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={rebased} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id={`grad-${s.symbol}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={chartColor} stopOpacity={0.2} />
                  <stop offset="95%" stopColor={chartColor} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#1E2D4A" strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fontSize: 8, fill: '#4A5568' }} tickFormatter={(d: string) => d.slice(5)} interval={14} />
              <YAxis tick={{ fontSize: 8, fill: '#4A5568' }} width={32} tickFormatter={(v: number) => `${v.toFixed(0)}%`} />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine y={0} stroke="#4A5568" strokeDasharray="4 2" />
              <Area type="monotone" dataKey="pct" stroke={chartColor} fill={`url(#grad-${s.symbol})`} strokeWidth={2} dot={false} name="Değişim %" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Volume chart */}
        <div style={{ background: 'var(--bg-elevated)', borderRadius: 6, border: '1px solid var(--border)', padding: '12px 14px' }}>
          <div style={{ fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 10 }}>
            📊 HACİM (Oran: <span style={{ color: s.volumeRatio > 2 ? 'var(--bull)' : 'var(--text-2)' }}>{s.volumeRatio.toFixed(1)}x ort.</span>)
          </div>
          <ResponsiveContainer width="100%" height={80}>
            <BarChart data={chartData.slice(-30)} margin={{ top: 2, right: 4, bottom: 0, left: 0 }}>
              <XAxis dataKey="date" tick={{ fontSize: 7, fill: '#4A5568' }} tickFormatter={(d: string) => d.slice(5)} interval={4} />
              <Tooltip formatter={(v) => [((Number(v) / 1_000_000)).toFixed(1)+'M', 'Hacim']} contentStyle={{ background: '#0F1629', border: '1px solid #1E2D4A', fontSize: 11 }} />
              <Bar dataKey="volume" radius={[2,2,0,0]}>
                {chartData.slice(-30).map((_, i) => (
                  <Cell key={i} fill={i >= 25 ? 'var(--accent)' : '#2A3F60'} opacity={0.8} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Score breakdown */}
        <div style={{ background: 'var(--bg-elevated)', borderRadius: 6, border: '1px solid var(--border)', padding: '12px 14px' }}>
          <div style={{ fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 12 }}>🎯 BREAKOUT SKOR DAĞILIMI</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {factors.map(f => (
              <div key={f.name}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontSize: 10, color: 'var(--text-2)' }}>{f.name}</span>
                  <span style={{ fontSize: 10, fontWeight: 600, color: f.color, fontFamily: 'var(--font-mono)' }}>{f.score}</span>
                </div>
                <div style={{ height: 4, background: 'var(--border)', borderRadius: 2, overflow: 'hidden' }}>
                  <div style={{
                    height: '100%', width: `${f.score}%`,
                    background: f.color, borderRadius: 2,
                    boxShadow: `0 0 6px ${f.color}66`,
                    transition: 'width 0.6s ease',
                  }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Technical indicators grid */}
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 8 }}>⚙ TEKNİK GÖSTERGELER</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
            {[
              { l: 'RSI(14)', v: s.rsi.toFixed(1), c: s.rsi > 70 ? 'var(--bear)' : s.rsi < 40 ? 'var(--blue)' : 'var(--text)' },
              { l: 'ADX(14)', v: s.adx.toFixed(1), c: s.adx > 30 ? 'var(--bull)' : 'var(--text)' },
              { l: '52H ZİRVE', v: `${s.distFrom52wHigh.toFixed(1)}%`, c: s.distFrom52wHigh > -5 ? 'var(--bull)' : 'var(--text-2)' },
              { l: 'EMA50', v: s.aboveEma50 ? 'ÜSTÜNDE' : 'ALTINDA', c: s.aboveEma50 ? 'var(--bull)' : 'var(--bear)' },
              { l: 'EMA200', v: s.aboveEma200 ? 'ÜSTÜNDE' : 'ALTINDA', c: s.aboveEma200 ? 'var(--bull)' : 'var(--bear)' },
              { l: 'HACİM', v: `${s.volumeRatio.toFixed(1)}x`, c: s.volumeRatio > 2 ? 'var(--bull)' : 'var(--text-2)' },
            ].map(item => (
              <div key={item.l} style={{ background: 'var(--bg-card)', borderRadius: 5, padding: '8px 10px', border: '1px solid var(--border)' }}>
                <div style={{ fontSize: 9, color: 'var(--text-3)', marginBottom: 3, letterSpacing: '0.06em' }}>{item.l}</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: item.c, fontFamily: 'var(--font-mono)' }}>{item.v}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
