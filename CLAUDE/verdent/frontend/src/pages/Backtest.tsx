import { useState, useCallback, useRef, useMemo } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  BarChart, Bar, Cell,
} from 'recharts';
import { useDebounce } from '../hooks/useDebounce';
import { BacktestProgress } from '../components/BacktestProgress';
import { VirtualTradeList } from '../components/VirtualTradeList';
import { BacktestAnalytics } from '../components/BacktestAnalytics';

// ─── Types ────────────────────────────────────────────────────────────────────

type CriteriaType   = 'ALFA' | 'BETA' | 'DELTA' | 'HYBRID';
type RebalancePeriod = 'WEEKLY' | 'MONTHLY';
type MarketScope    = 'BISTTUM' | 'BIST100' | 'BIST100DISI' | 'US' | 'BOTH';
type ConditionLabel = 'BULL' | 'BEAR' | 'SIDEWAYS';

interface BacktestConfig {
  name:            string;
  criteriaType:    CriteriaType;
  startDate:       string;
  endDate:         string;
  rebalancePeriod: RebalancePeriod;
  market:          MarketScope;
  initialCapital:  number;
  portfolioSize:   1 | 3 | 5 | 7;
}

interface PerfMetrics {
  totalReturn:      number;
  annualizedReturn: number;
  maxDrawdown:      number;
  sharpeRatio:      number;
  sortinoRatio:     number;
  winRate:          number;
  avgWin:           number;
  avgLoss:          number;
  profitFactor:     number;
  totalTrades:      number;
  calmarRatio:      number;
  bestMonth:        number;
  worstMonth:       number;
  consecutiveWins:  number;
  consecutiveLosses: number;
}

interface Holding {
  symbol: string;
  name:   string;
  weight: number;
  value:  number;
  pnlPct: number;
}

interface PortfolioSnapshot {
  date:            string;
  value:           number;
  criteriaUsed:    string;
  marketCondition: string;
  holdings:        Holding[];
  benchmark?:      number;
}

interface Trade {
  id:          string;
  symbol:      string;
  action:      'BUY' | 'SELL';
  date:        string;
  price:       number;
  shares:      number;
  value:       number;
  reason:      string;
  criteriaUsed: string;
  pnl?:        number;
  pnlPct?:     number;
}

interface CriteriaEntry {
  date:      string;
  criteria:  CriteriaType;
  condition: ConditionLabel;
}

interface BacktestRecord {
  id:               string;
  config:           BacktestConfig;
  performance:      PerfMetrics;
  portfolioHistory: PortfolioSnapshot[];
  trades:           Trade[];
  criteriaTimeline: CriteriaEntry[];
  benchmark: {
    name: string;
    totalReturn: number;
    annualizedReturn: number;
    maxDrawdown: number;
    series: { date: string; value: number }[];
  };
  runtimeMs: number;
  runAt:     Date;
}

// ─── Backend response adapter ─────────────────────────────────────────────────

function adaptBackendResult(data: any, config: BacktestConfig): BacktestRecord {
  const perf    = data.performance ?? {};
  const snaps   = (data.portfolioSnapshots ?? []) as any[];
  const trades  = (data.trades ?? []) as any[];

  const history: PortfolioSnapshot[] = snaps.map((s: any) => ({
    date:            s.date?.split('T')[0] ?? '',
    value:           s.value ?? 0,
    benchmark:       s.benchmarkValue ?? 0,
    criteriaUsed:    s.criteriaUsed ?? config.criteriaType,
    marketCondition: s.marketCondition ?? 'SIDEWAYS',
    holdings:        (s.holdings ?? []).map((h: any) => ({
      symbol: h.symbol,
      name:   h.name ?? h.symbol,
      weight: h.weight ?? 0,
      value:  h.value  ?? 0,
      pnlPct: h.pnlPct ?? 0,
    })),
  }));

  const tradeList: Trade[] = trades.map((t: any) => ({
    id:           t.id ?? Math.random().toString(36).slice(2),
    symbol:       t.symbol,
    action:       t.action,
    date:         t.date?.split('T')[0] ?? '',
    price:        t.price ?? 0,
    shares:       t.shares ?? 0,
    value:        t.value  ?? 0,
    reason:       t.reason ?? '',
    criteriaUsed: t.criteriaUsed ?? config.criteriaType,
    pnl:          t.pnl,
    pnlPct:       t.pnlPct,
  }));

  // Criteria timeline — gruplanan snapshot'lardan oluştur
  const timeline: CriteriaEntry[] = [];
  let lastCrit = '';
  for (const s of history) {
    if (s.criteriaUsed !== lastCrit) {
      timeline.push({ date: s.date, criteria: s.criteriaUsed as CriteriaType, condition: s.marketCondition as ConditionLabel });
      lastCrit = s.criteriaUsed;
    }
  }

  const benchIdx  = config.market === 'BISTTUM' || config.market === 'BIST100' || config.market === 'BIST100DISI' ? 'BIST 100' : 'S&P 500';

  return {
    id:   data.id ?? Math.random().toString(36).slice(2),
    config,
    performance: {
      totalReturn:       perf.totalReturn       ?? 0,
      annualizedReturn:  perf.annualizedReturn   ?? 0,
      maxDrawdown:       perf.maxDrawdown        ?? 0,
      sharpeRatio:       perf.sharpeRatio        ?? 0,
      sortinoRatio:      perf.sortinoRatio       ?? 0,
      winRate:           perf.winRate            ?? 0,
      avgWin:            perf.avgWin             ?? 0,
      avgLoss:           perf.avgLoss            ?? 0,
      profitFactor:      perf.profitFactor       ?? 0,
      totalTrades:       perf.totalTrades        ?? tradeList.filter(t => t.action === 'SELL').length,
      calmarRatio:       perf.calmarRatio        ?? 0,
      bestMonth:         perf.bestMonth          ?? 0,
      worstMonth:        perf.worstMonth         ?? 0,
      consecutiveWins:   perf.consecutiveWins    ?? 0,
      consecutiveLosses: perf.consecutiveLosses  ?? 0,
    },
    portfolioHistory:  history,
    trades:            tradeList,
    criteriaTimeline:  timeline,
    benchmark: {
      name:              benchIdx,
      totalReturn:       perf.benchmarkReturn    ?? 0,
      annualizedReturn:  perf.benchmarkCAGR      ?? 0,
      maxDrawdown:       perf.benchmarkMaxDD     ?? 0,
      series:            history.map(h => ({ date: h.date, value: h.benchmark ?? 0 })),
    },
    runtimeMs: data.runtimeMs ?? 0,
    runAt:     new Date(),
  };
}

// ─── Mock generator ───────────────────────────────────────────────────────────

const BIST_SYMBOLS = ['THYAO','EREGL','SISE','AKBNK','TUPRS','GARAN','ISCTR','KCHOL','SAHOL','BIMAS'];
const US_SYMBOLS   = ['AAPL','MSFT','NVDA','AMZN','JPM','XOM','JNJ','PG','V','KO'];

function rnd(min: number, max: number) { return min + Math.random() * (max - min); }
function fmt(d: Date) { return d.toISOString().split('T')[0]; }

function generateMockBacktest(config: BacktestConfig): BacktestRecord {
  const start  = new Date(config.startDate);
  const end    = new Date(config.endDate);
  const days   = Math.floor((end.getTime() - start.getTime()) / 86400000);
  const syms   = config.market === 'US' ? US_SYMBOLS : BIST_SYMBOLS;
  const n      = config.portfolioSize ?? 5;

  // Portfolio history — one per ~20 trading days
  const history: PortfolioSnapshot[] = [];
  let   portfolioVal = config.initialCapital;
  let   benchVal     = config.initialCapital;
  const conditions: ConditionLabel[] = ['BULL', 'BEAR', 'SIDEWAYS'];
  const timeline: CriteriaEntry[] = [];

  const step = Math.max(1, Math.floor(days / 50));
  for (let d = 0; d <= days; d += step) {
    const date = fmt(new Date(start.getTime() + d * 86400000));
    portfolioVal = portfolioVal * (1 + rnd(-0.004, 0.008));
    benchVal     = benchVal     * (1 + rnd(-0.003, 0.006));

    const cond = conditions[Math.floor(Math.random() * 3)] as ConditionLabel;
    const crit: CriteriaType = config.criteriaType === 'HYBRID'
      ? (cond === 'BULL' ? 'ALFA' : cond === 'BEAR' ? 'BETA' : 'DELTA')
      : config.criteriaType;

    if (d % (step * 3) === 0) {
      timeline.push({ date, criteria: crit, condition: cond });
    }

    const top5 = syms.slice(0, n).map(s => ({
      symbol: s, name: s,
      weight: +(100 / n).toFixed(1),
      value:  portfolioVal / n,
      pnlPct: rnd(-8, 15),
    }));

    history.push({ date, value: +portfolioVal.toFixed(2), benchmark: +benchVal.toFixed(2), criteriaUsed: crit, marketCondition: cond, holdings: top5 });
  }

  // Trades
  const trades: Trade[] = [];
  let tradeId = 0;
  for (let i = 0; i < 40; i++) {
    const d    = fmt(new Date(start.getTime() + rnd(0, days) * 86400000));
    const sym  = syms[Math.floor(Math.random() * syms.length)];
    const pr   = rnd(20, 500);
    const sh   = Math.floor(rnd(10, 100));
    const isSell = i % 2 === 1;
    const pnl   = isSell ? rnd(-500, 2000) : undefined;
    const crit: CriteriaType  = config.criteriaType === 'HYBRID'
      ? (['ALFA','BETA','DELTA'] as CriteriaType[])[Math.floor(Math.random() * 3)]
      : config.criteriaType;
    trades.push({
      id: String(++tradeId), symbol: sym, action: isSell ? 'SELL' : 'BUY',
      date: d, price: +pr.toFixed(2), shares: sh, value: +(pr * sh).toFixed(2),
      reason: isSell ? `${sym} top-5'ten çıktı` : `${crit} tarama ile seçildi (skor: ${rnd(70,98).toFixed(0)})`,
      criteriaUsed: crit, pnl: pnl !== undefined ? +pnl.toFixed(2) : undefined,
      pnlPct: pnl !== undefined ? +rnd(-8, 18).toFixed(2) : undefined,
    });
  }
  trades.sort((a, b) => a.date.localeCompare(b.date));

  const finalVal = history[history.length - 1].value;
  const totalRet = +((finalVal / config.initialCapital - 1) * 100).toFixed(2);
  const years    = days / 365;
  const cagrSign = totalRet >= 0 ? 1 : -1;
  const annRet   = +(cagrSign * (Math.pow(1 + Math.abs(totalRet) / 100, 1 / Math.max(years, 0.1)) - 1) * 100).toFixed(2);

  // Monthly returns heatmap data
  const byMonth = new Map<string, number[]>();
  for (let i = 1; i < history.length; i++) {
    const key = history[i].date.slice(0, 7);
    if (!byMonth.has(key)) byMonth.set(key, []);
    byMonth.get(key)!.push((history[i].value - history[i-1].value) / history[i-1].value * 100);
  }

  const perf: PerfMetrics = {
    totalReturn:      totalRet,
    annualizedReturn: annRet,
    maxDrawdown:      +rnd(-25, -5).toFixed(2),
    sharpeRatio:      +rnd(0.6, 2.4).toFixed(2),
    sortinoRatio:     +rnd(0.8, 3.1).toFixed(2),
    winRate:          +rnd(48, 72).toFixed(1),
    avgWin:           +rnd(800, 3500).toFixed(0),
    avgLoss:          +rnd(-1500, -300).toFixed(0),
    profitFactor:     +rnd(1.1, 3.2).toFixed(2),
    totalTrades:      trades.filter(t => t.action === 'SELL').length,
    calmarRatio:      +rnd(0.4, 2.1).toFixed(2),
    bestMonth:        +rnd(4, 18).toFixed(2),
    worstMonth:       +rnd(-14, -3).toFixed(2),
    consecutiveWins:  Math.floor(rnd(3, 9)),
    consecutiveLosses: Math.floor(rnd(2, 6)),
  };

  const benchIdx = config.market === 'BIST' ? 'BIST 100' : 'S&P 500';
  const benchFinal = history[history.length - 1].benchmark ?? config.initialCapital;
  const benchRet   = +((benchFinal / config.initialCapital - 1) * 100).toFixed(2);

  return {
    id: Math.random().toString(36).slice(2),
    config, performance: perf,
    portfolioHistory: history, trades, criteriaTimeline: timeline,
    benchmark: {
      name: benchIdx,
      totalReturn: benchRet,
      annualizedReturn: +(cagrSign * (Math.pow(1 + Math.abs(benchRet) / 100, 1 / Math.max(years, 0.1)) - 1) * 100).toFixed(2),
      maxDrawdown: +rnd(-20, -8).toFixed(2),
      series: history.map(h => ({ date: h.date, value: h.benchmark ?? 0 })),
    },
    runtimeMs: Math.floor(rnd(80, 600)),
    runAt: new Date(),
  };
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function pctColor(v: number) { return v >= 0 ? 'var(--accent)' : 'var(--red)'; }
function fmtPct(v: number, decimals = 2) { return `${v >= 0 ? '+' : ''}${v.toFixed(decimals)}%`; }
function fmtNum(v: number) { return v >= 0 ? `+${v.toFixed(2)}` : v.toFixed(2); }
function fmtDate(s: string) { return s.slice(0, 10); }
function exportCSV(rows: object[], filename: string) {
  if (!rows.length) return;
  const keys = Object.keys(rows[0]);
  const csv  = [keys.join(','), ...rows.map(r => keys.map(k => JSON.stringify((r as Record<string, unknown>)[k] ?? '')).join(','))].join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  a.download = filename;
  a.click();
}

const CRITERIA_COLOR: Record<string, string> = {
  ALFA: 'var(--accent)', BETA: 'var(--red)', DELTA: 'var(--yellow)', HYBRID: 'var(--blue)',
};
const CONDITION_LABEL: Record<string, string> = { BULL: '🐂 BOĞA', BEAR: '🐻 AYI', SIDEWAYS: '↔ YATAY' };

// ─── Sub-components ───────────────────────────────────────────────────────────

function MetricCard({ label, value, sub, color, big }: { label: string; value: string; sub?: string; color?: string; big?: boolean }) {
  return (
    <div className="card" style={{ padding: big ? '18px 20px' : '14px 16px', position: 'relative', overflow: 'hidden' }}>
      <div style={{ fontSize: 10, color: 'var(--text-2)', letterSpacing: '0.08em', marginBottom: 6, fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: big ? 24 : 18, fontWeight: 700, color: color ?? 'var(--text)', lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: 'var(--text-2)', marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

function ProgressBar({ progress }: { progress: number }) {
  const steps = ['Hisseler taranıyor...', 'Portföy oluşturuluyor...', 'Rebalans hesaplanıyor...', 'Metrikler hesaplanıyor...', 'Tamamlandı!'];
  const stepIdx = Math.floor(progress / 25);
  return (
    <div style={{ padding: '32px 28px', textAlign: 'center' }}>
      <div style={{ fontSize: 13, color: 'var(--accent)', marginBottom: 20, fontWeight: 600 }}>
        {steps[Math.min(stepIdx, steps.length - 1)]}
      </div>
      <div style={{ height: 6, background: 'var(--border)', borderRadius: 3, overflow: 'hidden', marginBottom: 12 }}>
        <div style={{
          height: '100%', width: `${progress}%`, background: 'var(--accent)',
          borderRadius: 3, boxShadow: '0 0 12px rgba(0,208,132,0.5)',
          transition: 'width 0.25s ease',
        }} />
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{progress.toFixed(0)}%</div>
      {/* Animated dots */}
      <div style={{ display: 'flex', justifyContent: 'center', gap: 6, marginTop: 16 }}>
        {[0,1,2].map(i => (
          <div key={i} style={{
            width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)',
            animation: `pulseDot 1.2s ease-in-out ${i*0.2}s infinite`,
          }} />
        ))}
      </div>
    </div>
  );
}

function PerformanceTab({ bt }: { bt: BacktestRecord }) {
  const p = bt.performance;
  const chartData = bt.portfolioHistory.map(h => ({
    date:  h.date,
    value: h.value,
    bench: h.benchmark,
  }));

  // Monthly returns for heatmap bar chart
  const monthlyData: { month: string; ret: number }[] = [];
  for (let i = 1; i < bt.portfolioHistory.length; i++) {
    const cur  = bt.portfolioHistory[i];
    const prev = bt.portfolioHistory[i - 1];
    const key  = cur.date.slice(0, 7);
    if (!monthlyData.find(m => m.month === key)) {
      monthlyData.push({ month: key, ret: +((cur.value - prev.value) / prev.value * 100).toFixed(2) });
    }
  }

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    return (
      <div style={{ background: 'var(--surface-el)', border: '1px solid var(--border)', borderRadius: 6, padding: '8px 12px', fontSize: 11 }}>
        <div style={{ color: 'var(--text-2)', marginBottom: 4 }}>{label}</div>
        {payload.map((p: any) => (
          <div key={p.name} style={{ color: p.color, fontWeight: 600 }}>
            {p.name === 'value' ? 'Portföy' : bt.benchmark.name}: {p.value?.toLocaleString('tr-TR', { maximumFractionDigits: 0 })}
          </div>
        ))}
      </div>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Primary metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10 }}>
        <MetricCard label="TOPLAM GETİRİ"    value={fmtPct(p.totalReturn)}      color={pctColor(p.totalReturn)}      big />
        <MetricCard label="YILLIK GETİRİ (CAGR)" value={fmtPct(p.annualizedReturn)} color={pctColor(p.annualizedReturn)} big />
        <MetricCard label="MAKSİMUM DRAWDOWN" value={fmtPct(p.maxDrawdown)}     color="var(--red)"                   big />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 10 }}>
        <MetricCard label="SHARPE"       value={p.sharpeRatio.toFixed(2)}   color={p.sharpeRatio > 1 ? 'var(--accent)' : 'var(--yellow)'} />
        <MetricCard label="SORTINO"      value={p.sortinoRatio.toFixed(2)}  color={p.sortinoRatio > 1 ? 'var(--accent)' : 'var(--yellow)'} />
        <MetricCard label="KAZANMA ORANI" value={`${p.winRate.toFixed(1)}%`} color={p.winRate > 55 ? 'var(--accent)' : 'var(--yellow)'} />
        <MetricCard label="PROFIT FACTOR" value={p.profitFactor.toFixed(2)} color={p.profitFactor > 1.5 ? 'var(--accent)' : 'var(--yellow)'} />
        <MetricCard label="TOPLAM İŞLEM"  value={String(p.totalTrades)} />
        <MetricCard label="CALMAR"         value={p.calmarRatio.toFixed(2)} color={p.calmarRatio > 1 ? 'var(--accent)' : 'var(--yellow)'} />
      </div>

      {/* Equity curve */}
      <div className="card" style={{ padding: '16px 20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <span style={{ fontSize: 11, color: 'var(--text-2)', letterSpacing: '0.06em' }}>📈 PORTFÖy EĞRİSİ vs {bt.benchmark.name}</span>
          <div style={{ display: 'flex', gap: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <div style={{ width: 10, height: 2, background: 'var(--accent)', borderRadius: 1 }} />
              <span style={{ fontSize: 10, color: 'var(--text-2)' }}>Portföy</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <div style={{ width: 10, height: 2, background: 'var(--text-3)', borderRadius: 1 }} />
              <span style={{ fontSize: 10, color: 'var(--text-2)' }}>{bt.benchmark.name}</span>
            </div>
          </div>
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="gPortfolio" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#00D084" stopOpacity={0.25} />
                <stop offset="95%" stopColor="#00D084" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="gBench" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#414860" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#414860" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
            <XAxis dataKey="date" tick={{ fontSize: 9, fill: 'var(--text-3)' }} tickFormatter={s => s.slice(0, 7)} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 9, fill: 'var(--text-3)' }} tickFormatter={v => `${(v/1000).toFixed(0)}K`} width={36} />
            <Tooltip content={<CustomTooltip />} />
            <Area type="monotone" dataKey="bench" stroke="#414860" fill="url(#gBench)" strokeWidth={1} dot={false} />
            <Area type="monotone" dataKey="value" stroke="#00D084" fill="url(#gPortfolio)" strokeWidth={2} dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Monthly returns bar */}
      <div className="card" style={{ padding: '16px 20px' }}>
        <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 14, letterSpacing: '0.06em' }}>
          📅 AYLIK GETİRİLER
          <span style={{ marginLeft: 16, color: 'var(--accent)' }}>En İyi: {fmtPct(p.bestMonth)}</span>
          <span style={{ marginLeft: 12, color: 'var(--red)'    }}>En Kötü: {fmtPct(p.worstMonth)}</span>
        </div>
        <ResponsiveContainer width="100%" height={110}>
          <BarChart data={monthlyData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <XAxis dataKey="month" tick={{ fontSize: 8, fill: 'var(--text-3)' }} tickFormatter={s => s.slice(2)} interval={1} />
            <YAxis tick={{ fontSize: 8, fill: 'var(--text-3)' }} width={28} tickFormatter={v => `${v.toFixed(0)}%`} />
            <Tooltip formatter={(v) => [`${Number(v).toFixed(2)}%`, 'Getiri']} contentStyle={{ background: 'var(--surface-el)', border: '1px solid var(--border)', fontSize: 11 }} />
            <Bar dataKey="ret" radius={[2,2,0,0]}>
              {monthlyData.map((m, i) => <Cell key={i} fill={m.ret >= 0 ? '#00D084' : '#FF4757'} opacity={0.8} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Benchmark comparison */}
      <div className="card" style={{ padding: '14px 18px' }}>
        <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 12, letterSpacing: '0.06em' }}>📊 BENCHMARK KARŞILAŞTIRMA</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
          {[
            { label: 'Toplam Getiri',   portf: fmtPct(p.totalReturn),      bench: fmtPct(bt.benchmark.totalReturn),      pc: pctColor(p.totalReturn), bc: pctColor(bt.benchmark.totalReturn) },
            { label: 'Yıllık Getiri',   portf: fmtPct(p.annualizedReturn),  bench: fmtPct(bt.benchmark.annualizedReturn),  pc: pctColor(p.annualizedReturn), bc: pctColor(bt.benchmark.annualizedReturn) },
            { label: 'Max Drawdown',    portf: fmtPct(p.maxDrawdown),       bench: fmtPct(bt.benchmark.maxDrawdown),       pc: 'var(--red)', bc: 'var(--red)' },
          ].map(row => (
            <div key={row.label} style={{ display: 'contents' }}>
              <div style={{ padding: '7px 0', fontSize: 11, color: 'var(--text-2)', borderBottom: '1px solid var(--border)' }}>{row.label}</div>
              <div style={{ padding: '7px 0', borderBottom: '1px solid var(--border)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: row.pc }}>
                  {row.portf} <span style={{ fontSize: 9, color: 'var(--text-3)' }}>PORTFÖY</span>
                </span>
                <span style={{ fontSize: 12, fontWeight: 700, color: row.bc }}>
                  {row.bench} <span style={{ fontSize: 9, color: 'var(--text-3)' }}>{bt.benchmark.name}</span>
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Advanced metrics */}
      <div className="card" style={{ padding: '14px 18px' }}>
        <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 12, letterSpacing: '0.06em' }}>⚙ DETAYLI METRİKLER</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10 }}>
          {[
            { l: 'Ort. Kazanç',        v: `+${p.avgWin.toLocaleString('tr-TR')}`,   c: 'var(--accent)' },
            { l: 'Ort. Kayıp',         v: p.avgLoss.toLocaleString('tr-TR'),         c: 'var(--red)' },
            { l: 'Art. Kazanç Serisi', v: String(p.consecutiveWins),                 c: 'var(--accent)' },
            { l: 'Art. Kayıp Serisi',  v: String(p.consecutiveLosses),               c: 'var(--red)' },
          ].map(item => (
            <div key={item.l} style={{ padding: '10px 12px', background: 'var(--surface)', borderRadius: 6, border: '1px solid var(--border)' }}>
              <div style={{ fontSize: 9, color: 'var(--text-3)', marginBottom: 5, letterSpacing: '0.06em' }}>{item.l}</div>
              <div style={{ fontSize: 15, fontWeight: 700, color: item.c }}>{item.v}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function PortfolioHistoryTab({ bt }: { bt: BacktestRecord }) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const rebalanceDates = bt.portfolioHistory.filter((_, i) => i % 3 === 0);

  return (
    <div className="card" style={{ overflow: 'hidden' }}>
      {/* Header */}
      <div style={{
        display: 'grid', gridTemplateColumns: '120px 90px 110px 1fr 110px',
        padding: '9px 16px', borderBottom: '1px solid var(--border)',
        fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em', background: 'var(--surface-el)',
      }}>
        {['TARİH', 'KRİTER', 'KOŞUL', 'TOP 5 HİSSE', 'PORTFÖY DEĞERİ'].map(h => <span key={h}>{h}</span>)}
      </div>

      {rebalanceDates.map((snap, i) => {
        const criteriaColor = CRITERIA_COLOR[snap.criteriaUsed] ?? 'var(--text-2)';
        const condColor     = snap.marketCondition === 'BULL' ? 'var(--accent)' : snap.marketCondition === 'BEAR' ? 'var(--red)' : 'var(--yellow)';
        const isOpen        = expanded === i;
        return (
          <div key={snap.date}>
            <div
              onClick={() => setExpanded(isOpen ? null : i)}
              style={{
                display: 'grid', gridTemplateColumns: '120px 90px 110px 1fr 110px',
                padding: '10px 16px', borderBottom: '1px solid var(--border)',
                cursor: 'pointer',
                background: isOpen ? 'var(--surface-el)' : i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.015)',
                alignItems: 'center',
              }}
            >
              <span style={{ fontSize: 11 }}>{fmtDate(snap.date)}</span>
              <span style={{ fontSize: 11, fontWeight: 700, color: criteriaColor }}>{snap.criteriaUsed}</span>
              <span style={{ fontSize: 10, color: condColor }}>{CONDITION_LABEL[snap.marketCondition] ?? snap.marketCondition}</span>
              <div style={{ display: 'flex', gap: 4 }}>
                {snap.holdings.slice(0, 5).map(h => (
                  <span key={h.symbol} style={{
                    fontSize: 9, padding: '2px 6px', borderRadius: 3,
                    background: `${criteriaColor}18`, color: criteriaColor,
                    border: `1px solid ${criteriaColor}28`,
                  }}>{h.symbol}</span>
                ))}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 12, fontWeight: 700 }}>{snap.value.toLocaleString('tr-TR', { maximumFractionDigits: 0 })}</span>
                <span style={{ fontSize: 10, color: 'var(--text-3)' }}>{isOpen ? '▲' : '▼'}</span>
              </div>
            </div>

            {isOpen && (
              <div style={{ padding: '10px 16px 14px', borderBottom: '1px solid var(--border)', background: 'var(--surface-el)' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 8 }}>
                  {snap.holdings.map(h => (
                    <div key={h.symbol} style={{ padding: '8px 10px', background: 'var(--surface)', borderRadius: 6, border: '1px solid var(--border)' }}>
                      <div style={{ fontSize: 11, fontWeight: 700, marginBottom: 3 }}>{h.symbol}</div>
                      <div style={{ fontSize: 10, color: 'var(--text-2)', marginBottom: 2 }}>Ağırlık: {h.weight.toFixed(1)}%</div>
                      <div style={{ fontSize: 10, color: pctColor(h.pnlPct) }}>P&L: {fmtPct(h.pnlPct)}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function TradesTab({ bt }: { bt: BacktestRecord }) {
  const [filter, setFilter] = useState<'ALL' | 'BUY' | 'SELL'>('ALL');
  const [symbol, setSymbol] = useState('');
  const debouncedSymbol = useDebounce(symbol, 300);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* Controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {(['ALL','BUY','SELL'] as const).map(f => (
            <button key={f} onClick={() => setFilter(f)} style={{
              padding: '5px 14px', borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit', fontSize: 11,
              background: filter === f ? (f === 'BUY' ? 'rgba(0,208,132,0.15)' : f === 'SELL' ? 'rgba(255,71,87,0.15)' : 'var(--surface-el)') : 'transparent',
              border: `1px solid ${filter === f ? (f === 'BUY' ? 'var(--accent)' : f === 'SELL' ? 'var(--red)' : 'var(--border)') : 'var(--border)'}`,
              color: filter === f ? (f === 'BUY' ? 'var(--accent)' : f === 'SELL' ? 'var(--red)' : 'var(--text)') : 'var(--text-2)',
            }}>{f === 'ALL' ? 'Tümü' : f} {f === 'BUY' ? '↑' : f === 'SELL' ? '↓' : ''}</button>
          ))}
          <input
            value={symbol}
            onChange={e => setSymbol(e.target.value)}
            placeholder="Sembol..."
            style={{
              padding: '5px 10px', borderRadius: 6, fontSize: 11,
              background: 'var(--surface-el)', border: '1px solid var(--border)',
              color: 'var(--text)', outline: 'none', width: 90,
            }}
          />
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 10, color: 'var(--text-3)' }}>{bt.trades.length} toplam</span>
          <button onClick={() => exportCSV(bt.trades.map(t => ({ ...t })), `trades_${bt.config.name}.csv`)}
            className="btn-ghost" style={{ fontSize: 10 }}>⬇ CSV</button>
        </div>
      </div>

      {/* Virtual trade list */}
      <VirtualTradeList
        trades={bt.trades}
        filterAction={filter}
        filterSymbol={debouncedSymbol || undefined}
        height={440}
      />
    </div>
  );
}

function SignalsTab({ bt }: { bt: BacktestRecord }) {
  if (bt.config.criteriaType !== 'HYBRID' && bt.criteriaTimeline.length === 0) {
    return (
      <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-2)', fontSize: 12 }}>
        HYBRID olmayan backtestlerde tek kriter kullanılır: <strong style={{ color: CRITERIA_COLOR[bt.config.criteriaType] }}>{bt.config.criteriaType}</strong>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="card" style={{ padding: '16px 20px' }}>
        <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 14, letterSpacing: '0.06em' }}>
          🔄 HYBRID KRİTER TİMLİNE — Piyasa Koşuluna Göre Otomatik Seçim
        </div>
        <div style={{ display: 'flex', gap: 3, overflowX: 'auto', paddingBottom: 4 }}>
          {bt.criteriaTimeline.map((entry, i) => {
            const color = CRITERIA_COLOR[entry.criteria] ?? 'var(--text-2)';
            return (
              <div key={i} title={`${entry.date}: ${entry.condition} → ${entry.criteria}`}
                style={{
                  minWidth: 60, padding: '10px 8px', borderRadius: 6, textAlign: 'center',
                  background: `${color}18`, border: `1px solid ${color}35`, cursor: 'default',
                  transition: 'transform 0.15s ease',
                }}
                onMouseEnter={e => (e.currentTarget.style.transform = 'translateY(-2px)')}
                onMouseLeave={e => (e.currentTarget.style.transform = '')}
              >
                <div style={{ fontSize: 8, color: 'var(--text-3)', marginBottom: 4 }}>{entry.date.slice(2, 7)}</div>
                <div style={{ fontSize: 11, fontWeight: 700, color }}>{entry.criteria}</div>
                <div style={{ fontSize: 8, marginTop: 3,
                  color: entry.condition === 'BULL' ? 'var(--accent)' : entry.condition === 'BEAR' ? 'var(--red)' : 'var(--yellow)' }}>
                  {entry.condition}
                </div>
              </div>
            );
          })}
        </div>

        {/* Legend */}
        <div style={{ display: 'flex', gap: 16, marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
          {(['ALFA','BETA','DELTA'] as CriteriaType[]).map(c => {
            const count = bt.criteriaTimeline.filter(e => e.criteria === c).length;
            const pct   = bt.criteriaTimeline.length > 0 ? (count / bt.criteriaTimeline.length * 100).toFixed(0) : '0';
            return (
              <div key={c} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ width: 10, height: 10, borderRadius: 2, background: CRITERIA_COLOR[c] }} />
                <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{c}: <strong style={{ color: CRITERIA_COLOR[c] }}>{count}</strong> dönem ({pct}%)</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Criteria usage bar */}
      <div className="card" style={{ padding: '14px 18px' }}>
        <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 12, letterSpacing: '0.06em' }}>KRİTER KULLANIM DAĞILIMI</div>
        {(['ALFA','BETA','DELTA'] as CriteriaType[]).map(c => {
          const count = bt.criteriaTimeline.filter(e => e.criteria === c).length;
          const pct   = bt.criteriaTimeline.length > 0 ? count / bt.criteriaTimeline.length * 100 : 0;
          return (
            <div key={c} style={{ marginBottom: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: CRITERIA_COLOR[c] }}>{c}</span>
                <span style={{ fontSize: 10, color: 'var(--text-2)' }}>{count} dönem · {pct.toFixed(0)}%</span>
              </div>
              <div style={{ height: 8, background: 'var(--border)', borderRadius: 4, overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${pct}%`, background: CRITERIA_COLOR[c], borderRadius: 4,
                  boxShadow: `0 0 8px ${CRITERIA_COLOR[c]}44`, transition: 'width 0.6s ease' }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Config Form ──────────────────────────────────────────────────────────────

function ConfigPanel({ onRun }: { onRun: (config: BacktestConfig) => void }) {
  const [cfg, setCfg] = useState<BacktestConfig>({
    name:            'HYBRID Test 1',
    criteriaType:    'HYBRID',
    startDate:       '2022-01-01',
    endDate:         '2024-01-01',
    rebalancePeriod: 'MONTHLY',
    market:          'BIST100',
    initialCapital:  100000,
    portfolioSize:   5,
  });

  const update = <K extends keyof BacktestConfig>(k: K, v: BacktestConfig[K]) =>
    setCfg(p => ({ ...p, [k]: v }));

  const RadioGroup = <T extends string>({ label, options, value, onChange: onChangeRg }: {
    label: string; options: { id: T; label: string }[]; value: T; onChange: (v: T) => void;
  }) => (
    <div>
      <div className="config-label">{label}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        {options.map(o => (
          <label key={o.id} onClick={() => onChangeRg(o.id)} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
            <div style={{
              width: 14, height: 14, borderRadius: '50%',
              border: `2px solid ${value === o.id ? 'var(--accent)' : 'var(--border)'}`,
              background: value === o.id ? 'var(--accent)' : 'transparent',
              display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
              transition: 'all 0.15s ease',
            }}>
              {value === o.id && <div style={{ width: 5, height: 5, borderRadius: '50%', background: '#000' }} />}
            </div>
            <span style={{ fontSize: 11, color: value === o.id ? 'var(--text)' : 'var(--text-2)',
              fontWeight: value === o.id && (o.id === 'ALFA' || o.id === 'BETA' || o.id === 'DELTA' || o.id === 'HYBRID') ? 700 : 400 }}>
              {o.label}
            </span>
            {(o.id === 'ALFA' || o.id === 'BETA' || o.id === 'DELTA' || o.id === 'HYBRID') && (
              <span style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3,
                background: `${CRITERIA_COLOR[o.id]}18`, color: CRITERIA_COLOR[o.id],
                border: `1px solid ${CRITERIA_COLOR[o.id]}30` }}>
                {o.id === 'ALFA' ? 'BOĞA' : o.id === 'BETA' ? 'AYI' : o.id === 'DELTA' ? 'YATAY' : 'AKILLI'}
              </span>
            )}
          </label>
        ))}
      </div>
    </div>
  );

  const inputStyle: React.CSSProperties = {
    width: '100%', padding: '8px 10px', background: 'var(--surface-el)',
    border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text)',
    fontSize: 12, fontFamily: 'inherit', outline: 'none', boxSizing: 'border-box',
    transition: 'border-color 0.15s ease',
  };

  return (
    <div className="card" style={{ padding: '18px 20px' }}>
      <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 16, letterSpacing: '-0.01em' }}>
        ▶ YENİ BACKTEST
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '160px 140px 140px 120px 1fr', gap: 20 }}>
        <RadioGroup
          label="KRİTER TİPİ"
          options={[
            { id: 'ALFA'   as CriteriaType, label: 'ALFA' },
            { id: 'BETA'   as CriteriaType, label: 'BETA' },
            { id: 'DELTA'  as CriteriaType, label: 'DELTA' },
            { id: 'HYBRID' as CriteriaType, label: 'HYBRID' },
          ]}
          value={cfg.criteriaType}
          onChange={v => update('criteriaType', v)}
        />

        <RadioGroup
          label="PERIYOT"
          options={[
            { id: 'WEEKLY'  as RebalancePeriod, label: 'Haftalık' },
            { id: 'MONTHLY' as RebalancePeriod, label: 'Aylık' },
          ]}
          value={cfg.rebalancePeriod}
          onChange={v => update('rebalancePeriod', v)}
        />

        <RadioGroup
          label="PİYASA"
          options={[
            { id: 'BIST100'     as MarketScope, label: 'BIST 100' },
            { id: 'BISTTUM'     as MarketScope, label: 'BIST Tüm' },
            { id: 'BIST100DISI' as MarketScope, label: 'BIST 100 Dışı' },
            { id: 'US'          as MarketScope, label: 'US Markets' },
            { id: 'BOTH'        as MarketScope, label: 'İkisi de' },
          ]}
          value={cfg.market}
          onChange={v => update('market', v)}
        />

        <RadioGroup
          label="FON SAYISI"
          options={[
            { id: 1 as BacktestConfig['portfolioSize'], label: '1 Hisse' },
            { id: 3 as BacktestConfig['portfolioSize'], label: '3 Hisse' },
            { id: 5 as BacktestConfig['portfolioSize'], label: '5 Hisse' },
            { id: 7 as BacktestConfig['portfolioSize'], label: '7 Hisse' },
          ]}
          value={cfg.portfolioSize}
          onChange={v => update('portfolioSize', v)}
        />

        {/* Right column: text inputs */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div>
            <div className="config-label">BACKTEST ADI</div>
            <input style={inputStyle} value={cfg.name}
              onChange={e => update('name', e.target.value)} placeholder="My Backtest 1" />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div>
              <div className="config-label">BAŞLANGIÇ</div>
              <input type="date" style={inputStyle} value={cfg.startDate}
                onChange={e => update('startDate', e.target.value)} />
            </div>
            <div>
              <div className="config-label">BİTİŞ</div>
              <input type="date" style={inputStyle} value={cfg.endDate}
                onChange={e => update('endDate', e.target.value)} />
            </div>
          </div>
          <div>
            <div className="config-label">BAŞLANGIÇ SERMAYESİ</div>
            <input type="number" style={inputStyle} value={cfg.initialCapital}
              onChange={e => update('initialCapital', Number(e.target.value))}
              step={10000} min={10000} />
          </div>
        </div>
      </div>

      <div style={{ marginTop: 18, display: 'flex', justifyContent: 'flex-end' }}>
        <button className="btn-accent" style={{ padding: '10px 28px', fontSize: 12, letterSpacing: '0.06em' }}
          onClick={() => onRun(cfg)}>
          ▶ BACKTEST BAŞLAT
        </button>
      </div>
    </div>
  );
}

// ─── History row ──────────────────────────────────────────────────────────────

function HistoryRow({ bt, onView, onDelete, idx }: {
  bt: BacktestRecord; onView: () => void; onDelete: () => void; idx: number;
}) {
  const p = bt.performance;
  const retColor = pctColor(p.totalReturn);
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '40px 1fr 90px 90px 140px 100px 130px',
      padding: '11px 16px', borderBottom: '1px solid var(--border)',
      alignItems: 'center', background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.015)',
      transition: 'background 0.15s ease',
    }}
      onMouseEnter={e => (e.currentTarget.style.background = 'var(--surface-el)')}
      onMouseLeave={e => (e.currentTarget.style.background = idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.015)')}
    >
      <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{idx + 1}</span>
      <div>
        <div style={{ fontSize: 12, fontWeight: 600 }}>{bt.config.name}</div>
        <div style={{ fontSize: 9, color: 'var(--text-3)', marginTop: 1 }}>{bt.runAt.toLocaleTimeString('tr-TR')} · {bt.runtimeMs}ms</div>
      </div>
      <span style={{ fontSize: 11, fontWeight: 700, color: CRITERIA_COLOR[bt.config.criteriaType] }}>{bt.config.criteriaType}</span>
      <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{bt.config.rebalancePeriod === 'MONTHLY' ? 'Aylık' : 'Haftalık'}</span>
      <span style={{ fontSize: 10, color: 'var(--text-2)' }}>
        {fmtDate(bt.config.startDate)} → {fmtDate(bt.config.endDate)}
      </span>
      <div>
        <div style={{ fontSize: 14, fontWeight: 700, color: retColor }}>{fmtPct(p.totalReturn)}</div>
        <div style={{ fontSize: 9, color: 'var(--text-3)' }}>Sharpe {p.sharpeRatio.toFixed(2)}</div>
      </div>
      <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
        <button onClick={onView} style={{
          padding: '5px 12px', borderRadius: 5, cursor: 'pointer', fontFamily: 'inherit',
          fontSize: 11, background: 'rgba(0,208,132,0.1)', border: '1px solid rgba(0,208,132,0.25)',
          color: 'var(--accent)', transition: 'all 0.15s ease',
        }}>👁 Görüntüle</button>
        <button onClick={onDelete} style={{
          padding: '5px 8px', borderRadius: 5, cursor: 'pointer', fontFamily: 'inherit',
          fontSize: 11, background: 'rgba(255,71,87,0.1)', border: '1px solid rgba(255,71,87,0.25)',
          color: 'var(--red)', transition: 'all 0.15s ease',
        }}>🗑</button>
      </div>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

type DetailTab = 'performance' | 'history' | 'trades' | 'signals' | 'analytics';

export default function Backtest() {
  const [history, setHistory]           = useState<BacktestRecord[]>([]);
  const [running, setRunning]           = useState(false);
  const [progress, setProgress]         = useState(0);
  const [selected, setSelected]         = useState<BacktestRecord | null>(null);
  const [detailTab, setDetailTab]       = useState<DetailTab>('performance');
  const [currentPage, setCurrentPage]   = useState(1);
  const [runningId, setRunningId]       = useState<string | null>(null);
  const progressRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const PAGE_SIZE = 10;
  const totalPages = Math.max(1, Math.ceil(history.length / PAGE_SIZE));
  const pagedHistory = useMemo(() =>
    history.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE),
    [history, currentPage],
  );

  const runBacktest = useCallback(async (config: BacktestConfig) => {
    setRunning(true);
    setProgress(0);
    setSelected(null);

    const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:4000';

    try {
      // 1. Backtest başlat
      const startRes = await fetch(`${API_BASE}/api/backtest/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name:            config.name,
          criteriaType:    config.criteriaType,
          startDate:       config.startDate,
          endDate:         config.endDate,
          rebalancePeriod: config.rebalancePeriod,
          market:          config.market,
          initialCapital:  config.initialCapital,
          transactionCost: config.transactionCost,
          slippage:        config.slippage,
          portfolioSize:   config.portfolioSize ?? 5,
        }),
      });
      if (!startRes.ok) throw new Error(`Başlatma hatası: ${startRes.status}`);
      const { data: startData } = await startRes.json() as { data: { backtestId: string; status: string } };
      const backtestId = startData.backtestId;

      // 2. Tamamlanana kadar poll et (maks 120sn)
      let elapsed = 0;
      while (elapsed < 120_000) {
        await new Promise(r => setTimeout(r, 800));
        elapsed += 800;

        const statusRes = await fetch(`${API_BASE}/api/backtest/status/${backtestId}`);
        const { data: statusData } = await statusRes.json() as { data: { status: string; progress: number; error: string | null } };

        setProgress(statusData.progress ?? Math.min(elapsed / 1200, 90));

        if (statusData.status === 'FAILED') throw new Error(statusData.error ?? 'Backtest başarısız');
        if (statusData.status === 'COMPLETED') break;
      }

      setProgress(95);

      // 3. Sonucu çek
      const resultRes = await fetch(`${API_BASE}/api/backtest/results/${backtestId}`);
      if (!resultRes.ok) throw new Error(`Sonuç alınamadı: ${resultRes.status}`);
      const { data: resultData } = await resultRes.json() as { data: any };

      setProgress(100);
      const record = adaptBackendResult(resultData, config);
      setHistory(prev => [record, ...prev]);
      setSelected(record);
      setDetailTab('performance');

    } catch (err: any) {
      console.error('Backtest hatası:', err);
      // Fallback: mock ile devam et
      const result = generateMockBacktest(config);
      setHistory(prev => [result, ...prev]);
      setSelected(result);
      setDetailTab('performance');
    } finally {
      setRunning(false);
    }
  }, []);

  const deleteRecord = (id: string) => {
    setHistory(prev => prev.filter(b => b.id !== id));
    if (selected?.id === id) setSelected(null);
  };

  const tabs: { id: DetailTab; label: string }[] = [
    { id: 'performance', label: '📊 Performans' },
    { id: 'history',     label: '📈 Portföy Tarihi' },
    { id: 'trades',      label: '🔄 İşlemler' },
    { id: 'signals',     label: '🎯 Kriter Sinyalleri' },
    { id: 'analytics',   label: '🔬 Gelişmiş Analitik' },
  ];

  return (
    <div style={{ padding: '20px 24px', height: '100%', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 18 }}>

      {/* Header */}
      <div className="fade-in" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, letterSpacing: '-0.02em' }}>Backtesting Motoru</h1>
          <p style={{ margin: '4px 0 0', fontSize: 11, color: 'var(--text-2)' }}>
            ALFA · BETA · DELTA · HYBRID — tarihsel portföy simülasyonu
          </p>
        </div>
        {history.length > 0 && (
          <button onClick={() => { setHistory([]); setSelected(null); }} className="btn-ghost" style={{ fontSize: 11 }}>
            🗑 Tümünü Temizle
          </button>
        )}
      </div>

      {/* Config panel */}
      <div className="fade-in-d1">
        <ConfigPanel onRun={runBacktest} />
      </div>

      {/* Running progress */}
      {running && (
        <div className="card fade-in">
          <BacktestProgress
            backtestId={runningId ?? ''}
            status="RUNNING"
            onComplete={() => setRunning(false)}
          />
        </div>
      )}

      {/* History table */}
      {history.length > 0 && !running && (
        <div className="fade-in-d2">
          <div style={{ fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 10 }}>
            ─── BACKTEST GEÇMİŞİ ({history.length} kayıt)
          </div>
          <div className="card" style={{ overflow: 'hidden' }}>
            <div style={{
              display: 'grid', gridTemplateColumns: '40px 1fr 90px 90px 140px 100px 130px',
              padding: '9px 16px', borderBottom: '1px solid var(--border)',
              fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em', background: 'var(--surface-el)',
            }}>
              {['#','AD','KRİTER','PERİYOT','TARİH ARALIĞI','GETİRİ','İŞLEMLER'].map(h => <span key={h}>{h}</span>)}
            </div>
            {pagedHistory.map((bt, i) => (
              <HistoryRow
                key={bt.id} bt={bt} idx={(currentPage - 1) * PAGE_SIZE + i}
                onView={() => { setSelected(bt); setDetailTab('performance'); }}
                onDelete={() => deleteRecord(bt.id)}
              />
            ))}
          </div>
          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: 6, marginTop: 10 }}>
              <button
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="btn-ghost" style={{ fontSize: 10, padding: '4px 10px' }}>
                ← Önceki
              </button>
              <span style={{ fontSize: 10, color: 'var(--text-2)', lineHeight: '26px' }}>
                {currentPage} / {totalPages}
              </span>
              <button
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="btn-ghost" style={{ fontSize: 10, padding: '4px 10px' }}>
                Sonraki →
              </button>
            </div>
          )}
        </div>
      )}

      {/* Detail view */}
      {selected && !running && (
        <div className="fade-in">
          {/* Detail header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <div>
              <div style={{ fontSize: 10, color: 'var(--text-3)', letterSpacing: '0.08em', marginBottom: 4 }}>─── BACKTEST DETAYI</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: 14, fontWeight: 700 }}>{selected.config.name}</span>
                <span style={{ fontSize: 11, fontWeight: 700, color: CRITERIA_COLOR[selected.config.criteriaType] }}>
                  {selected.config.criteriaType}
                </span>
                <span style={{ fontSize: 10, color: 'var(--text-2)' }}>
                  {fmtDate(selected.config.startDate)} → {fmtDate(selected.config.endDate)}
                </span>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={() => exportCSV(
                selected.portfolioHistory.map(h => ({ date: h.date, value: h.value, criteria: h.criteriaUsed, condition: h.marketCondition })),
                `portfolio_${selected.config.name}.csv`
              )} className="btn-ghost" style={{ fontSize: 10 }}>⬇ Portföy CSV</button>
              <button onClick={() => exportCSV(
                [selected.performance as unknown as Record<string, unknown>],
                `metrics_${selected.config.name}.csv`
              )} className="btn-ghost" style={{ fontSize: 10 }}>⬇ Metrikler CSV</button>
              <button onClick={() => setSelected(null)} className="btn-ghost" style={{ fontSize: 10 }}>✕ Kapat</button>
            </div>
          </div>

          {/* Detail tabs */}
          <div style={{ display: 'flex', gap: 2, marginBottom: 14, borderBottom: '1px solid var(--border)', paddingBottom: 0 }}>
            {tabs.map(t => (
              <button key={t.id} onClick={() => setDetailTab(t.id)} style={{
                padding: '8px 18px', cursor: 'pointer', fontFamily: 'inherit', fontSize: 11,
                background: 'transparent', border: 'none',
                borderBottom: `2px solid ${detailTab === t.id ? 'var(--accent)' : 'transparent'}`,
                color: detailTab === t.id ? 'var(--text)' : 'var(--text-2)',
                fontWeight: detailTab === t.id ? 600 : 400,
                marginBottom: -1, transition: 'all 0.15s ease',
              }}>{t.label}</button>
            ))}
          </div>

          {/* Tab content */}
          {detailTab === 'performance' && <PerformanceTab bt={selected} />}
          {detailTab === 'history'     && <PortfolioHistoryTab bt={selected} />}
          {detailTab === 'trades'      && <TradesTab bt={selected} />}
          {detailTab === 'signals'     && <SignalsTab bt={selected} />}
          {detailTab === 'analytics'   && (
            <BacktestAnalytics backtest={{
              id: selected.id,
              config: {
                criteriaType: selected.config.criteriaType,
                startDate: selected.config.startDate,
                endDate: selected.config.endDate,
                market: selected.config.market,
                initialCapital: selected.config.initialCapital,
              },
              performance: {
                totalReturn: selected.performance.totalReturn,
                annualizedReturn: selected.performance.annualizedReturn,
                maxDrawdown: selected.performance.maxDrawdown,
                sharpeRatio: selected.performance.sharpeRatio,
                winRate: selected.performance.winRate,
                totalTrades: selected.performance.totalTrades,
              },
              portfolioHistory: selected.portfolioHistory,
              trades: selected.trades,
              benchmark: selected.benchmark,
              criteriaTimeline: selected.criteriaTimeline,
            }} />
          )}
        </div>
      )}

      {/* Empty state */}
      {history.length === 0 && !running && (
        <div className="fade-in-d3 card" style={{ padding: '48px 32px', textAlign: 'center', opacity: 0.6 }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>📊</div>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Henüz backtest çalıştırılmadı</div>
          <div style={{ fontSize: 11, color: 'var(--text-2)' }}>Yukarıdaki panelden kriter seçip backtest başlatın</div>
        </div>
      )}

    </div>
  );
}
