'use client';
import { useMemo } from 'react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

function generateIndexHistory(days: number, trend: number) {
  const data = [];
  let val = 9000 + Math.random() * 1000;
  for (let i = days; i >= 0; i--) {
    const d = new Date(Date.now() - i * 86400000);
    if (d.getDay() === 0 || d.getDay() === 6) continue;
    val = Math.max(1000, val * (1 + (Math.random() - 0.5 + trend) * 0.012));
    data.push({ date: d.toISOString().split('T')[0], value: +val.toFixed(2) });
  }
  return data;
}

const SECTORS = [
  { name: 'Bankacılık', change: 2.14, stocks: 12 },
  { name: 'Havacılık', change: 3.87, stocks: 4 },
  { name: 'Çelik', change: -1.23, stocks: 8 },
  { name: 'Enerji', change: 1.56, stocks: 6 },
  { name: 'Perakende', change: -0.45, stocks: 9 },
  { name: 'Teknoloji', change: 4.12, stocks: 5 },
  { name: 'Otomotiv', change: 0.78, stocks: 7 },
  { name: 'Savunma', change: 2.33, stocks: 3 },
  { name: 'Gıda', change: -0.89, stocks: 11 },
  { name: 'Cam', change: 1.44, stocks: 4 },
];

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ value: number }>;
  label?: string;
}

function CustomTooltip({ active, payload, label }: TooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: '#0F1629', border: '1px solid #1E2D4A', borderRadius: 6, padding: '8px 12px', fontSize: 11 }}>
      <div style={{ color: '#8899AA', marginBottom: 4 }}>{label}</div>
      <div style={{ color: '#00D084', fontWeight: 700, fontFamily: 'IBM Plex Mono' }}>{payload[0].value.toFixed(2)}</div>
    </div>
  );
}

export default function HomePage() {
  const bist100 = useMemo(() => generateIndexHistory(90, 0.002), []);
  const bist30  = useMemo(() => generateIndexHistory(90, 0.003), []);

  return (
    <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div className="fade-in">
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em' }}>Market Genel Bakış</h1>
        <p style={{ margin: '4px 0 0', fontSize: 11, color: 'var(--text-2)' }}>BIST piyasa durumu ve sektör performansı</p>
      </div>

      {/* Market condition badge */}
      <div className="fade-in-d1 card" style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ fontSize: 32 }}>🐂</div>
          <div>
            <div style={{ fontSize: 11, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 2 }}>PİYASA DURUMU</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--bull)' }}>BOĞA PİYASASI</div>
          </div>
        </div>
        <div style={{ width: 1, height: 48, background: 'var(--border)', marginLeft: 8 }} />
        {[
          { l: 'BIST 100 > EMA200', v: 'EVET', c: 'var(--bull)' },
          { l: 'Yükselen Hisse %', v: '67%', c: 'var(--bull)' },
          { l: 'Yeni 52H Zirve', v: '24 hisse', c: 'var(--accent)' },
          { l: 'Güç Oranı', v: '1.84', c: 'var(--bull)' },
        ].map(m => (
          <div key={m.l}>
            <div style={{ fontSize: 9, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 4 }}>{m.l}</div>
            <div style={{ fontSize: 15, fontWeight: 700, color: m.c, fontFamily: 'var(--font-mono)' }}>{m.v}</div>
          </div>
        ))}
      </div>

      {/* Index charts */}
      <div className="fade-in-d2" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        {[
          { name: 'BIST 100', data: bist100, color: '#00D084', value: bist100[bist100.length-1]?.value ?? 0 },
          { name: 'BIST 30',  data: bist30,  color: '#4A9EFF', value: bist30[bist30.length-1]?.value ?? 0 },
        ].map(idx => {
          const firstVal = idx.data[0]?.value ?? 1;
          const lastVal  = idx.data[idx.data.length-1]?.value ?? 1;
          const chg = ((lastVal - firstVal) / firstVal * 100).toFixed(2);
          return (
            <div key={idx.name} className="card" style={{ padding: '14px 16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                <div>
                  <div style={{ fontSize: 11, color: 'var(--text-2)', letterSpacing: '0.06em' }}>{idx.name}</div>
                  <div style={{ fontSize: 20, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{idx.value.toLocaleString('tr-TR', { maximumFractionDigits: 0 })}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: Number(chg) >= 0 ? 'var(--bull)' : 'var(--bear)', fontFamily: 'var(--font-mono)' }}>
                    {Number(chg) >= 0 ? '+' : ''}{chg}%
                  </div>
                  <div style={{ fontSize: 9, color: 'var(--text-3)' }}>90 günlük</div>
                </div>
              </div>
              <ResponsiveContainer width="100%" height={120}>
                <AreaChart data={idx.data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id={`g-${idx.name}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={idx.color} stopOpacity={0.2} />
                      <stop offset="95%" stopColor={idx.color} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#1E2D4A" strokeDasharray="3 3" />
                  <XAxis dataKey="date" tick={{ fontSize: 8, fill: '#4A5568' }} tickFormatter={(d: string) => d.slice(5)} interval={14} />
                  <YAxis tick={{ fontSize: 8, fill: '#4A5568' }} width={42} tickFormatter={(v: number) => `${(v/1000).toFixed(0)}K`} />
                  <Tooltip content={<CustomTooltip />} />
                  <Area type="monotone" dataKey="value" stroke={idx.color} fill={`url(#g-${idx.name})`} strokeWidth={2} dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          );
        })}
      </div>

      {/* Sector heatmap */}
      <div className="fade-in-d3">
        <div style={{ fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 10 }}>─── SEKTÖR PERFORMANSI (Bugün)</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 8 }}>
          {SECTORS.map(s => (
            <div key={s.name} style={{
              background: s.change >= 0 ? 'rgba(0,208,132,0.06)' : 'rgba(255,71,87,0.06)',
              border: `1px solid ${s.change >= 0 ? 'rgba(0,208,132,0.2)' : 'rgba(255,71,87,0.2)'}`,
              borderRadius: 6, padding: '12px 14px',
              transition: 'all 0.15s ease', cursor: 'default',
            }}>
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 6 }}>{s.name}</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: s.change >= 0 ? 'var(--bull)' : 'var(--bear)', fontFamily: 'var(--font-mono)' }}>
                {s.change >= 0 ? '+' : ''}{s.change.toFixed(2)}%
              </div>
              <div style={{ fontSize: 9, color: 'var(--text-3)', marginTop: 4 }}>{s.stocks} hisse</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
