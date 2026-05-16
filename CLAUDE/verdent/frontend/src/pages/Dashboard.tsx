import { useState, useEffect, useCallback } from 'react';
import { useAppStore } from '../stores/appStore';
import { formatPercent } from '../utils';

// ─── Types ────────────────────────────────────────────────────────────────────

type MarketLabel = 'BULL' | 'BEAR' | 'SIDEWAYS';
type CriteriaLabel = 'ALFA' | 'BETA' | 'DELTA';
type MarketId = 'BIST' | 'US';

interface IndicatorGroup {
  label: string;
  score: number;
  details: { name: string; value: string; signal: 'up' | 'down' | 'neutral' }[];
}

interface MarketConditionResult {
  market: MarketId;
  condition: MarketLabel;
  score: number;
  confidence: number;
  trend: IndicatorGroup;
  momentum: IndicatorGroup;
  volatility: IndicatorGroup;
  breadth: IndicatorGroup;
  recommendedCriteria: CriteriaLabel;
  updatedAt: Date;
}

interface TopStock {
  rank: number;
  symbol: string;
  name: string;
  score: number;
  entry: number;
  target: number;
  stopLoss: number;
  rr: number;
  change: number;
  signals: string[];
}

// ─── Mock data ────────────────────────────────────────────────────────────────

function generateMarketCondition(market: MarketId): MarketConditionResult {
  const score = market === 'BIST'
    ? parseFloat((6.2 + (Math.random() - 0.5) * 1.2).toFixed(2))
    : parseFloat((-4.1 + (Math.random() - 0.5) * 1.4).toFixed(2));
  const condition: MarketLabel = score > 3 ? 'BULL' : score < -3 ? 'BEAR' : 'SIDEWAYS';
  const confidence = parseFloat(Math.min(98, Math.max(45, Math.abs(score) * 8 + 30 + (Math.random() - 0.5) * 10)).toFixed(1));
  const criteria: CriteriaLabel = condition === 'BULL' ? 'ALFA' : condition === 'BEAR' ? 'BETA' : 'DELTA';

  return {
    market, condition, score, confidence, recommendedCriteria: criteria, updatedAt: new Date(),
    trend: {
      label: 'Trend', score: market === 'BIST' ? parseFloat((7.8 + (Math.random()-0.5)).toFixed(2)) : parseFloat((-6.2 + (Math.random()-0.5)).toFixed(2)),
      details: market === 'BIST'
        ? [{ name: 'BIST100 vs 200 SMA', value: 'Üstünde', signal: 'up' }, { name: 'Golden Cross (50>200)', value: 'Aktif', signal: 'up' }, { name: 'HH & HL Yapısı', value: 'Devam', signal: 'up' }]
        : [{ name: 'SPY vs 200 SMA', value: 'Altında', signal: 'down' }, { name: 'Death Cross (50<200)', value: 'Aktif', signal: 'down' }, { name: 'LL & LH Yapısı', value: 'Devam', signal: 'down' }],
    },
    momentum: {
      label: 'Momentum', score: market === 'BIST' ? parseFloat((6.0 + (Math.random()-0.5)*1.5).toFixed(2)) : parseFloat((-3.8 + (Math.random()-0.5)*1.2).toFixed(2)),
      details: market === 'BIST'
        ? [{ name: 'RSI(14)', value: '58.4', signal: 'up' }, { name: 'MACD', value: 'Sinyal üstünde', signal: 'up' }, { name: 'ADX(14)', value: '31.2', signal: 'up' }]
        : [{ name: 'RSI(14)', value: '38.7', signal: 'down' }, { name: 'MACD', value: 'Sinyal altında', signal: 'down' }, { name: 'ADX(14)', value: '28.4', signal: 'neutral' }],
    },
    volatility: {
      label: 'Volatilite', score: market === 'BIST' ? parseFloat((4.5 + (Math.random()-0.5)*2).toFixed(2)) : parseFloat((-5.2 + (Math.random()-0.5)*1.5).toFixed(2)),
      details: market === 'BIST'
        ? [{ name: 'ATR%', value: '1.8% (Düşük)', signal: 'up' }, { name: 'BB Genişliği', value: 'Daralıyor', signal: 'neutral' }]
        : [{ name: 'VIX', value: '24.8 (Yüksek)', signal: 'down' }, { name: 'ATR%', value: '2.4%', signal: 'down' }],
    },
    breadth: {
      label: 'Piyasa Genişliği', score: market === 'BIST' ? parseFloat((5.5 + (Math.random()-0.5)*2).toFixed(2)) : parseFloat((-2.1 + (Math.random()-0.5)*2).toFixed(2)),
      details: market === 'BIST'
        ? [{ name: '200 SMA Üstü', value: '%68', signal: 'up' }, { name: 'A/D Oranı', value: '1.42', signal: 'up' }]
        : [{ name: '200 SMA Üstü', value: '%41', signal: 'down' }, { name: 'A/D Oranı', value: '0.78', signal: 'down' }],
    },
  };
}

const BIST_STOCKS: TopStock[] = [
  { rank: 1, symbol: 'THYAO', name: 'Türk Hava Yolları', score: 94, entry: 285.5, target: 312.0, stopLoss: 268.0, rr: 2.6, change: 2.34, signals: ['Golden Cross', 'RSI 62'] },
  { rank: 2, symbol: 'EREGL', name: 'Ereğli Demir Çelik', score: 89, entry: 45.2, target: 51.0, stopLoss: 42.0, rr: 1.8, change: 1.12, signals: ['200 EMA↑', 'MACD↑'] },
  { rank: 3, symbol: 'SISE',  name: 'Şişecam', score: 85, entry: 28.7, target: 33.0, stopLoss: 26.5, rr: 1.9, change: -0.42, signals: ['Hacim Onayı', '52H Yakın'] },
  { rank: 4, symbol: 'AKBNK', name: 'Akbank', score: 82, entry: 52.3, target: 58.0, stopLoss: 49.0, rr: 1.7, change: 0.87, signals: ['RSI 55', 'BB Ortası↑'] },
  { rank: 5, symbol: 'TUPRS', name: 'Tüpraş', score: 78, entry: 168.2, target: 190.0, stopLoss: 158.0, rr: 2.1, change: 1.65, signals: ['EMA50↑', 'Momentum↑'] },
];

const US_STOCKS: TopStock[] = [
  { rank: 1, symbol: 'XOM', name: 'Exxon Mobil', score: 81, entry: 112.4, target: 118.0, stopLoss: 108.0, rr: 1.3, change: -0.54, signals: ['Düşük Beta', 'Temettü %3.2'] },
  { rank: 2, symbol: 'JNJ', name: 'Johnson & Johnson', score: 78, entry: 148.2, target: 156.0, stopLoss: 143.5, rr: 1.6, change: 0.23, signals: ['Defansif', 'D/E 0.42'] },
  { rank: 3, symbol: 'PG',  name: 'Procter & Gamble', score: 74, entry: 163.8, target: 172.0, stopLoss: 159.0, rr: 1.7, change: 0.41, signals: ['Stoch <20', 'FCF+'] },
  { rank: 4, symbol: 'KO',  name: 'Coca-Cola', score: 71, entry: 61.4, target: 65.0, stopLoss: 59.5, rr: 1.9, change: -0.18, signals: ['P/B 1.2', 'Temettü %3.0'] },
  { rank: 5, symbol: 'VZ',  name: 'Verizon', score: 68, entry: 39.6, target: 43.0, stopLoss: 38.0, rr: 2.1, change: 0.62, signals: ['Aşırı Satım↑', 'P/E 8.4'] },
];

// ─── Sub-components ───────────────────────────────────────────────────────────

function ScoreGauge({ score }: { score: number }) {
  const pct = (score + 10) / 20;
  const angle = pct * 180 - 90;
  const rad = (angle * Math.PI) / 180;
  const cx = 60; const cy = 60; const r = 44;
  const nx = cx + r * 0.82 * Math.sin(rad);
  const ny = cy - r * 0.82 * Math.cos(rad);
  const color = score > 3 ? 'var(--accent)' : score < -3 ? 'var(--red)' : 'var(--yellow)';

  return (
    <svg width="120" height="70" viewBox="0 0 120 70" style={{ overflow: 'visible' }}>
      {[{ from: -90, to: -30, c: '#FF4757' }, { from: -30, to: 30, c: '#FFC700' }, { from: 30, to: 90, c: '#00D084' }].map((seg, i) => {
        const a1 = (seg.from * Math.PI) / 180;
        const a2 = (seg.to   * Math.PI) / 180;
        return (
          <path key={i}
            d={`M ${cx+r*Math.sin(a1)} ${cy-r*Math.cos(a1)} A ${r} ${r} 0 0 1 ${cx+r*Math.sin(a2)} ${cy-r*Math.cos(a2)}`}
            fill="none" stroke={seg.c} strokeWidth="5" strokeLinecap="round" opacity="0.35" />
        );
      })}
      <line x1={cx} y1={cy} x2={nx} y2={ny} stroke={color} strokeWidth="2.5" strokeLinecap="round"
        style={{ filter: `drop-shadow(0 0 4px ${color})` }} />
      <circle cx={cx} cy={cy} r="4" fill={color} />
      <text x={cx} y={cy+14} textAnchor="middle" fontSize="11" fontWeight="700"
        fill={color} fontFamily="'IBM Plex Mono', monospace">
        {score > 0 ? '+' : ''}{score.toFixed(1)}
      </text>
    </svg>
  );
}

function ConditionBadge({ condition }: { condition: MarketLabel }) {
  const cfg = {
    BULL:     { label: '🐂 BOĞA',  color: 'var(--accent)', bg: 'rgba(0,208,132,0.12)',  border: 'rgba(0,208,132,0.3)' },
    BEAR:     { label: '🐻 AYI',   color: 'var(--red)',    bg: 'rgba(255,71,87,0.12)',   border: 'rgba(255,71,87,0.3)' },
    SIDEWAYS: { label: '↔ YATAY', color: 'var(--yellow)', bg: 'rgba(255,199,0,0.12)',   border: 'rgba(255,199,0,0.3)' },
  }[condition];
  return (
    <span style={{ color: cfg.color, background: cfg.bg, border: `1px solid ${cfg.border}`,
      borderRadius: 5, padding: '3px 10px', fontSize: 12, fontWeight: 700, letterSpacing: '0.04em' }}>
      {cfg.label}
    </span>
  );
}

function MiniSparkline({ score, color }: { score: number; color: string }) {
  const pts: number[] = [];
  let v = 50;
  for (let i = 0; i < 20; i++) {
    v = Math.max(10, Math.min(90, v + (score / 10) * 1.2 + (Math.random() - 0.5) * 3));
    pts.push(v);
  }
  const w = 100; const h = 30;
  const d = pts.map((y, x) => `${(x/19)*w},${h-(y/100)*h}`).join(' L ');
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ overflow: 'visible' }}>
      <path d={`M ${d} L 100,${h} L 0,${h} Z`} fill={color} opacity="0.15" />
      <polyline points={d} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function MarketConditionCard({ data, active }: { data: MarketConditionResult; active: boolean }) {
  const condColor = data.condition === 'BULL' ? 'var(--accent)' : data.condition === 'BEAR' ? 'var(--red)' : 'var(--yellow)';
  const sparkColor = data.condition === 'BULL' ? '#00D084' : data.condition === 'BEAR' ? '#FF4757' : '#FFC700';

  return (
    <div style={{
      background: active ? 'var(--surface-el)' : 'var(--surface)',
      border: `1px solid ${active ? condColor : 'var(--border)'}`,
      borderRadius: 10, padding: '16px 18px', flex: 1,
      boxShadow: active ? `0 0 20px ${condColor}22` : 'none', transition: 'all 0.3s ease',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-2)', letterSpacing: '0.08em', marginBottom: 4 }}>
            {data.market === 'BIST' ? 'BIST 100' : 'S&P 500'}
          </div>
          <ConditionBadge condition={data.condition} />
        </div>
        <ScoreGauge score={data.score} />
      </div>

      <div style={{ marginBottom: 10 }}>
        <MiniSparkline score={data.score} color={sparkColor} />
      </div>

      <div style={{ marginBottom: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
          <span style={{ fontSize: 10, color: 'var(--text-2)' }}>GÜVENİLİRLİK</span>
          <span style={{ fontSize: 11, fontWeight: 700, color: condColor }}>{data.confidence.toFixed(0)}%</span>
        </div>
        <div style={{ height: 4, background: 'var(--border)', borderRadius: 2, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${data.confidence}%`, background: condColor, borderRadius: 2,
            boxShadow: `0 0 8px ${condColor}66`, transition: 'width 0.6s ease' }} />
        </div>
      </div>

      {[data.trend, data.momentum, data.volatility, data.breadth].map(g => {
        const pct = ((g.score + 10) / 20) * 100;
        const gColor = g.score > 2 ? 'var(--accent)' : g.score < -2 ? 'var(--red)' : 'var(--yellow)';
        return (
          <div key={g.label} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
            <span style={{ fontSize: 10, color: 'var(--text-2)', width: 90, flexShrink: 0 }}>{g.label}</span>
            <div style={{ flex: 1, height: 3, background: 'var(--border)', borderRadius: 2, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${Math.max(2, pct)}%`, background: gColor, borderRadius: 2 }} />
            </div>
            <span style={{ fontSize: 10, color: gColor, width: 34, textAlign: 'right', fontWeight: 600 }}>
              {g.score > 0 ? '+' : ''}{g.score.toFixed(1)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function CriteriaCard({ criteria, confidence, active }: { criteria: CriteriaLabel; confidence: number; active: boolean }) {
  const cfg = {
    ALFA:  { color: 'var(--accent)', label: 'ALFA KRİTERİ', sub: 'Momentum / Büyüme',  emoji: '🚀', market: 'Boğa Piyasası' },
    BETA:  { color: 'var(--red)',    label: 'BETA KRİTERİ', sub: 'Defansif / Değer',    emoji: '🛡️', market: 'Ayı Piyasası' },
    DELTA: { color: 'var(--yellow)', label: 'DELTA KRİTERİ', sub: 'Mean Reversion',     emoji: '🔄', market: 'Yatay Piyasa' },
  }[criteria];

  return (
    <div style={{
      border: `1px solid ${active ? cfg.color : 'var(--border)'}`,
      borderRadius: 8, padding: '12px 14px',
      background: active ? `${cfg.color}0f` : 'transparent',
      opacity: active ? 1 : 0.45, transition: 'all 0.3s ease', position: 'relative', overflow: 'hidden',
    }}>
      {active && (
        <div style={{
          position: 'absolute', top: 8, right: 10, fontSize: 9, fontWeight: 700, letterSpacing: '0.1em',
          color: cfg.color, background: `${cfg.color}20`, border: `1px solid ${cfg.color}40`,
          borderRadius: 4, padding: '2px 6px',
        }}>AKTİF</div>
      )}
      <div style={{ fontSize: 18, marginBottom: 4 }}>{cfg.emoji}</div>
      <div style={{ fontSize: 12, fontWeight: 700, color: active ? cfg.color : 'var(--text)', marginBottom: 2 }}>{cfg.label}</div>
      <div style={{ fontSize: 10, color: 'var(--text-2)', marginBottom: active ? 8 : 0 }}>{cfg.market} · {cfg.sub}</div>
      {active && <div style={{ fontSize: 10, color: cfg.color, fontWeight: 600 }}>Güvenilirlik: {confidence.toFixed(0)}%</div>}
    </div>
  );
}

function IndicatorsPanel({ data }: { data: MarketConditionResult }) {
  const groups = [data.trend, data.momentum, data.volatility, data.breadth];
  const icons = ['📈', '⚡', '🌊', '📊'];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10 }}>
      {groups.map((g, i) => {
        const color = g.score > 2 ? 'var(--accent)' : g.score < -2 ? 'var(--red)' : 'var(--yellow)';
        return (
          <div key={g.label} className="card" style={{ padding: '12px 14px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <div style={{ fontSize: 10, color: 'var(--text-2)', letterSpacing: '0.06em' }}>{icons[i]} {g.label.toUpperCase()}</div>
              <span style={{ fontSize: 12, fontWeight: 700, color }}>{g.score > 0 ? '+' : ''}{g.score.toFixed(1)}</span>
            </div>
            {g.details.map((d, j) => (
              <div key={j} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5, gap: 8 }}>
                <span style={{ fontSize: 10, color: 'var(--text-2)', flex: 1 }}>{d.name}</span>
                <span style={{ fontSize: 10, fontWeight: 600,
                  color: d.signal === 'up' ? 'var(--accent)' : d.signal === 'down' ? 'var(--red)' : 'var(--text-2)' }}>
                  {d.signal === 'up' ? '↑ ' : d.signal === 'down' ? '↓ ' : '→ '}{d.value}
                </span>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

function TopStocksTable({ stocks, criteria }: { stocks: TopStock[]; criteria: CriteriaLabel }) {
  const criteriaColor = criteria === 'ALFA' ? 'var(--accent)' : criteria === 'BETA' ? 'var(--red)' : 'var(--yellow)';
  const [hovered, setHovered] = useState<number | null>(null);

  return (
    <div className="card" style={{ overflow: 'hidden' }}>
      <div style={{
        display: 'grid', gridTemplateColumns: '36px 100px 1fr 80px 80px 80px 72px 80px 140px',
        padding: '10px 16px', borderBottom: '1px solid var(--border)',
        fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em', background: 'var(--surface-el)',
      }}>
        {['#', 'SEMBOL', 'ŞİRKET', 'SKOR', 'GİRİŞ', 'HEDEF', 'STOP', 'R/R', 'SİNYALLER'].map((h, i) => (
          <span key={h} style={{ textAlign: i >= 3 ? 'right' : 'left' }}>{h}</span>
        ))}
      </div>

      {stocks.map((s, i) => {
        const changeColor = s.change >= 0 ? 'var(--accent)' : 'var(--red)';
        const scoreColor = s.score >= 85 ? 'var(--accent)' : s.score >= 70 ? criteriaColor : 'var(--text-2)';
        return (
          <div key={s.symbol}
            onMouseEnter={() => setHovered(i)} onMouseLeave={() => setHovered(null)}
            style={{
              display: 'grid', gridTemplateColumns: '36px 100px 1fr 80px 80px 80px 72px 80px 140px',
              padding: '11px 16px', borderBottom: i < stocks.length-1 ? '1px solid var(--border)' : 'none',
              background: hovered === i ? 'var(--surface-el)' : 'transparent',
              transition: 'background 0.15s ease', alignItems: 'center', cursor: 'pointer',
            }}>
            <span style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 600 }}>{s.rank}</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{
                width: 28, height: 28, borderRadius: 6,
                background: `${criteriaColor}18`, border: `1px solid ${criteriaColor}30`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 9, fontWeight: 700, color: criteriaColor,
              }}>{s.symbol.slice(0, 2)}</div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text)' }}>{s.symbol}</div>
                <div style={{ fontSize: 9, color: changeColor }}>{s.change >= 0 ? '+' : ''}{s.change.toFixed(2)}%</div>
              </div>
            </div>
            <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{s.name}</span>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: scoreColor }}>{s.score}</div>
              <div style={{ height: 2, background: 'var(--border)', borderRadius: 1, marginTop: 3 }}>
                <div style={{ height: '100%', width: `${s.score}%`, background: scoreColor, borderRadius: 1 }} />
              </div>
            </div>
            <span style={{ fontSize: 11, textAlign: 'right', color: 'var(--text)' }}>{s.entry.toFixed(1)}</span>
            <span style={{ fontSize: 11, textAlign: 'right', color: 'var(--accent)', fontWeight: 600 }}>{s.target.toFixed(1)}</span>
            <span style={{ fontSize: 11, textAlign: 'right', color: 'var(--red)' }}>{s.stopLoss.toFixed(1)}</span>
            <span style={{ fontSize: 11, textAlign: 'right', fontWeight: 600, color: s.rr >= 2 ? 'var(--accent)' : 'var(--text-2)' }}>{s.rr.toFixed(1)}x</span>
            <div style={{ display: 'flex', gap: 3, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
              {s.signals.slice(0, 2).map(sig => (
                <span key={sig} style={{ fontSize: 9, padding: '2px 5px', borderRadius: 3,
                  background: `${criteriaColor}15`, color: criteriaColor, border: `1px solid ${criteriaColor}25` }}>
                  {sig}
                </span>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function RefreshTimer({ lastUpdate, onRefresh }: { lastUpdate: Date; onRefresh: () => void }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - lastUpdate.getTime()) / 1000)), 1000);
    return () => clearInterval(id);
  }, [lastUpdate]);

  const pct = Math.min(100, (elapsed / 300) * 100);
  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <svg width="22" height="22" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="9" fill="none" stroke="var(--border)" strokeWidth="2" />
        <circle cx="12" cy="12" r="9" fill="none" stroke="var(--accent)" strokeWidth="2"
          strokeDasharray={`${(1 - pct/100)*56.5} 56.5`} strokeLinecap="round"
          transform="rotate(-90 12 12)" style={{ transition: 'stroke-dasharray 1s linear' }} />
      </svg>
      <span style={{ fontSize: 10, color: 'var(--text-2)' }}>
        {mins > 0 ? `${mins}d ` : ''}{String(secs).padStart(2,'0')}s önce
      </span>
      <button onClick={onRefresh} style={{
        background: 'transparent', border: '1px solid var(--border)', borderRadius: 5,
        padding: '3px 9px', fontSize: 10, color: 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit',
      }}>↻ YENİLE</button>
    </div>
  );
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:4000';

async function fetchConditionFromAPI(market: MarketId): Promise<MarketConditionResult> {
  const endpoint = market === 'BIST' ? 'BIST' : 'US';
  const res = await fetch(`${API}/api/market/condition/${endpoint}`);
  if (!res.ok) throw new Error('API hatası');
  const json = await res.json();
  const d = json.data;
  const condition: MarketLabel = d.condition === 'BULL' ? 'BULL' : d.condition === 'BEAR' ? 'BEAR' : 'SIDEWAYS';
  const criteria: CriteriaLabel = condition === 'BULL' ? 'ALFA' : condition === 'BEAR' ? 'BETA' : 'DELTA';
  const ind = d.indicators ?? {};

  const mapDetails = (details: Record<string, string>) =>
    Object.entries(details).map(([name, val]) => {
      const v = String(val);
      const signal: 'up' | 'down' | 'neutral' =
        v.includes('above') || v.includes('golden') || v.includes('UPTREND') ? 'up' :
        v.includes('below') || v.includes('death')  || v.includes('DOWNTREND') ? 'down' : 'neutral';
      return { name, value: v, signal };
    });

  return {
    market,
    condition,
    score: d.score ?? 0,
    confidence: d.confidence ?? 0,
    recommendedCriteria: criteria,
    updatedAt: new Date(),
    trend:      { label: 'Trend',              score: ind.trend?.rawScore      ?? 0, details: mapDetails(ind.trend?.details      ?? {}) },
    momentum:   { label: 'Momentum',           score: ind.momentum?.rawScore   ?? 0, details: mapDetails(ind.momentum?.details   ?? {}) },
    volatility: { label: 'Volatilite',         score: ind.volatility?.rawScore ?? 0, details: mapDetails(ind.volatility?.details ?? {}) },
    breadth:    { label: 'Piyasa Genişliği',   score: ind.breadth?.rawScore    ?? 0, details: mapDetails(ind.breadth?.details    ?? {}) },
  };
}

export default function Dashboard() {
  const { market: marketData, fetchMarketData } = useAppStore();
  const [activeTab, setActiveTab] = useState<MarketId>('BIST');
  const [bistData, setBistData] = useState<MarketConditionResult>(() => generateMarketCondition('BIST'));
  const [usData,   setUsData]   = useState<MarketConditionResult>(() => generateMarketCondition('US'));
  const [loading, setLoading]   = useState(false);

  const loadConditions = useCallback(async () => {
    setLoading(true);
    try {
      const [bist, us] = await Promise.allSettled([
        fetchConditionFromAPI('BIST'),
        fetchConditionFromAPI('US'),
      ]);
      if (bist.status === 'fulfilled') setBistData(bist.value);
      if (us.status === 'fulfilled')   setUsData(us.value);
    } catch (_) { /* mock data stays */ }
    finally { setLoading(false); }
  }, []);

  // İlk yüklemede hem market ticker'larını hem condition'ları çek
  useEffect(() => {
    fetchMarketData();
    loadConditions();
    const tickerTimer    = setInterval(fetchMarketData,   60_000);
    const conditionTimer = setInterval(loadConditions,   300_000);
    return () => { clearInterval(tickerTimer); clearInterval(conditionTimer); };
  }, [fetchMarketData, loadConditions]);

  const currentData = activeTab === 'BIST' ? bistData : usData;
  const topStocks   = activeTab === 'BIST' ? BIST_STOCKS : US_STOCKS;

  const refresh = useCallback(() => { loadConditions(); fetchMarketData(); }, [loadConditions, fetchMarketData]);

  const sp500 = marketData.find(m => m.index === 'S&P 500');
  const vix   = marketData.find(m => m.index === 'VIX');

  return (
    <div style={{ padding: '20px 24px', height: '100%', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 18 }}>

      {/* Header */}
      <div className="fade-in" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, letterSpacing: '-0.02em' }}>Piyasa Koşul Analizi</h1>
          <p style={{ margin: '4px 0 0', fontSize: 11, color: 'var(--text-2)' }}>
            Otomatik kriter seçimi · ALFA / BETA / DELTA
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {sp500 && (
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 10, color: 'var(--text-3)', marginBottom: 1 }}>S&P 500</div>
              <div style={{ fontSize: 12, fontWeight: 700, color: sp500.changePct >= 0 ? 'var(--accent)' : 'var(--red)' }}>
                {sp500.value.toLocaleString('tr-TR')} {formatPercent(sp500.changePct)}
              </div>
            </div>
          )}
          {vix && (
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 10, color: 'var(--text-3)', marginBottom: 1 }}>VIX</div>
              <div style={{ fontSize: 12, fontWeight: 700, color: vix.value > 20 ? 'var(--red)' : 'var(--accent)' }}>
                {vix.value.toFixed(2)}
              </div>
            </div>
          )}
          <RefreshTimer lastUpdate={currentData.updatedAt} onRefresh={refresh} />
        </div>
      </div>

      {/* Market tabs */}
      <div className="fade-in-d1" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        {(['BIST', 'US'] as MarketId[]).map(tab => {
          const d = tab === 'BIST' ? bistData : usData;
          const dotColor = d.condition === 'BULL' ? 'var(--accent)' : d.condition === 'BEAR' ? 'var(--red)' : 'var(--yellow)';
          const isActive = activeTab === tab;
          return (
            <button key={tab} onClick={() => setActiveTab(tab)} style={{
              padding: '7px 18px', borderRadius: 7, cursor: 'pointer', fontFamily: 'inherit',
              fontSize: 12, fontWeight: isActive ? 700 : 500,
              background: isActive ? 'var(--surface-el)' : 'transparent',
              border: `1px solid ${isActive ? 'var(--border)' : 'transparent'}`,
              color: isActive ? 'var(--text)' : 'var(--text-2)',
              display: 'flex', alignItems: 'center', gap: 8, transition: 'all 0.15s ease',
            }}>
              <span className="pulse-dot" style={{ width: 7, height: 7, borderRadius: '50%',
                background: dotColor, boxShadow: `0 0 6px ${dotColor}` }} />
              {tab === 'BIST' ? 'BIST Piyasası' : 'US Piyasası'}
              <ConditionBadge condition={d.condition} />
            </button>
          );
        })}
        {loading && <span className="cursor-blink" style={{ fontSize: 10, color: 'var(--text-2)', marginLeft: 8 }}>Yükleniyor...</span>}
      </div>

      {/* 2-col: Condition card + Criteria */}
      <div className="fade-in-d2" style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 16 }}>
        <MarketConditionCard data={currentData} active={true} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 2 }}>ÖNERİLEN KRİTER</div>
          {(['ALFA', 'BETA', 'DELTA'] as CriteriaLabel[]).map(c => (
            <CriteriaCard key={c} criteria={c} confidence={currentData.confidence} active={currentData.recommendedCriteria === c} />
          ))}
        </div>
      </div>

      {/* Indicators panel */}
      <div className="fade-in-d3">
        <div style={{ fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 10 }}>─── PİYASA GÖSTERGE DETAYI</div>
        <IndicatorsPanel data={currentData} />
      </div>

      {/* Top stocks */}
      <div className="fade-in-d4">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <div>
            <span style={{ fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em' }}>─── BUGÜNÜN EN İYİ HİSSELERİ</span>
            <span style={{ marginLeft: 10, fontSize: 10, fontWeight: 700,
              color: currentData.recommendedCriteria === 'ALFA' ? 'var(--accent)' : currentData.recommendedCriteria === 'BETA' ? 'var(--red)' : 'var(--yellow)' }}>
              {currentData.recommendedCriteria} KRİTERİ ile seçildi
            </span>
          </div>
          <span style={{ fontSize: 10, color: 'var(--text-3)' }}>{activeTab === 'BIST' ? 'BIST 100' : 'NYSE / NASDAQ'} · TOP 5</span>
        </div>
        <TopStocksTable stocks={topStocks} criteria={currentData.recommendedCriteria} />
      </div>

      {/* Comparison row */}
      <div className="fade-in-d5" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, opacity: 0.7 }}>
        <div style={{ fontSize: 9, color: 'var(--text-3)', letterSpacing: '0.08em', gridColumn: '1/-1', marginBottom: 4 }}>─── KARŞILAŞTIRMA GÖRÜNÜŞİ</div>
        <MarketConditionCard data={bistData} active={activeTab === 'BIST'} />
        <MarketConditionCard data={usData}   active={activeTab === 'US'} />
      </div>

    </div>
  );
}
