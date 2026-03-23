import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import {
  Play, Trash2, Eye, TrendingUp, TrendingDown, BarChart2,
  Percent, DollarSign, Calendar, Download, ChevronLeft,
  RefreshCw, Clock, AlertCircle, CheckCircle2, Loader2,
  ArrowUpRight, ArrowDownRight, GitCompare, X,
} from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, BarChart, Bar, Cell,
  AreaChart, Area, Legend,
} from 'recharts'
import { backtestService } from '../services/api'

import BacktestAnalytics from '../components/BacktestAnalytics'

// ── Types ─────────────────────────────────────────────────────────────────────

type CriteriaType   = 'ALFA' | 'BETA' | 'DELTA' | 'HYBRID'
type RebalancePeriod = 'WEEKLY' | 'BIWEEKLY' | 'MONTHLY'
type MarketType     = 'BIST' | 'US' | 'BOTH'
type DetailTab      = 'performance' | 'portfolio' | 'trades' | 'signals' | 'diagnostic' | 'analytics'

interface BacktestConfig {
  name:            string
  criteriaType:    CriteriaType
  startDate:       string
  endDate:         string
  rebalancePeriod: RebalancePeriod
  market:          MarketType
  initialCapital:  number
  transactionCost: number
  slippage:        number
}

interface BacktestRow {
  id:              string
  name:            string
  criteriaType:    string
  market:          string
  startDate:       string
  endDate:         string
  rebalancePeriod: string
  status:          string
  totalReturn:     number | null
  annualizedReturn:number | null
  maxDrawdown:     number | null
  sharpeRatio:     number | null
  winRate:         number | null
  totalTrades:     number | null
  initialCapital:  number
  createdAt:       string
}

interface BacktestDetail extends BacktestRow {
  portfolioSnapshots: Array<{
    id:             string
    date:           string
    portfolioValue: number
    holdings:       Array<{ symbol: string; shares: number; price: number; value: number }>
    criteriaUsed:   string
    marketCondition:string
  }>
  trades: Array<{
    id:       string
    symbol:   string
    action:   string
    date:     string
    price:    number
    shares:   number
    value:    number
    reason:   string
  }>
}

interface RunningJob {
  jobId:    string
  progress: number
  status:   'RUNNING' | 'COMPLETED' | 'FAILED'
  error?:   string
}

// ── Constants ─────────────────────────────────────────────────────────────────

const CRITERIA_META: Record<CriteriaType, { label: string; color: string; bg: string; desc: string }> = {
  ALFA:   { label: 'ALFA',   color: 'var(--green)',  bg: 'rgba(0,208,132,0.12)',  desc: 'Boğa piyasası — Momentum' },
  BETA:   { label: 'BETA',   color: 'var(--red)',    bg: 'rgba(255,77,77,0.12)',  desc: 'Ayı piyasası — Savunmacı' },
  DELTA:  { label: 'DELTA',  color: 'var(--yellow)', bg: 'rgba(245,166,35,0.12)', desc: 'Yatay piyasa — Mean Rev.' },
  HYBRID: { label: 'HYBRID', color: 'var(--blue)',   bg: 'rgba(77,159,255,0.12)', desc: 'Piyasaya göre otomatik' },
}

const CONDITION_COLOR: Record<string, string> = {
  BULL:     'var(--green)',
  BEAR:     'var(--red)',
  SIDEWAYS: 'var(--yellow)',
}

// ── Mock fallback data ─────────────────────────────────────────────────────────

function buildMockList(): BacktestRow[] {
  return [
    { id: 'mock-1', name: 'ALFA Boğa Testi', criteriaType: 'ALFA', market: 'BIST',
      startDate: '2022-01-01', endDate: '2024-01-01', rebalancePeriod: 'MONTHLY',
      status: 'COMPLETED', totalReturn: 47.3, annualizedReturn: 21.4, maxDrawdown: -12.3,
      sharpeRatio: 1.82, winRate: 68.5, totalTrades: 48, initialCapital: 100000,
      createdAt: new Date(Date.now() - 86400000).toISOString() },
    { id: 'mock-2', name: 'HYBRID Q4', criteriaType: 'HYBRID', market: 'US',
      startDate: '2023-01-01', endDate: '2024-01-01', rebalancePeriod: 'WEEKLY',
      status: 'COMPLETED', totalReturn: 31.2, annualizedReturn: 31.2, maxDrawdown: -8.7,
      sharpeRatio: 2.14, winRate: 72.0, totalTrades: 62, initialCapital: 100000,
      createdAt: new Date(Date.now() - 172800000).toISOString() },
    { id: 'mock-3', name: 'BETA Ayı Testi', criteriaType: 'BETA', market: 'BIST',
      startDate: '2021-01-01', endDate: '2022-01-01', rebalancePeriod: 'MONTHLY',
      status: 'COMPLETED', totalReturn: 8.7, annualizedReturn: 8.7, maxDrawdown: -5.2,
      sharpeRatio: 0.94, winRate: 55.0, totalTrades: 28, initialCapital: 100000,
      createdAt: new Date(Date.now() - 259200000).toISOString() },
  ]
}

function buildMockDetail(row: BacktestRow): BacktestDetail {
  const startMs  = new Date(row.startDate).getTime()
  const endMs    = new Date(row.endDate).getTime()
  const months   = Math.round((endMs - startMs) / (30 * 86400000))
  const criteria: CriteriaType[] = ['ALFA', 'BETA', 'DELTA', 'HYBRID']
  const conditions                = ['BULL', 'BEAR', 'SIDEWAYS']
  const bistStocks                = ['THYAO', 'EREGL', 'SISE', 'AKBNK', 'TUPRS']
  const usStocks                  = ['AAPL', 'MSFT', 'AMZN', 'GOOGL', 'NVDA']
  const stocks                    = row.market === 'BIST' ? bistStocks : usStocks

  const snapshots = Array.from({ length: months }, (_, i) => {
    const d = new Date(startMs + i * 30 * 86400000)
    const v = row.initialCapital * (1 + (row.totalReturn ?? 0) / 100 * (i / months) + (Math.random() - 0.5) * 0.02)
    const c = row.criteriaType === 'HYBRID'
      ? criteria[i % 3] as CriteriaType
      : row.criteriaType as CriteriaType
    return {
      id: `snap-${i}`,
      date: d.toISOString(),
      portfolioValue: Math.round(v),
      criteriaUsed: c,
      marketCondition: conditions[i % 3],
      holdings: stocks.map((s) => ({ symbol: s, shares: 20, price: 100 + Math.random() * 50, value: 2000 + Math.random() * 1000 })),
    }
  })

  const trades = Array.from({ length: row.totalTrades ?? 10 }, (_, i) => {
    const sym  = stocks[i % stocks.length]
    const isBuy = i % 2 === 0
    return {
      id:     `trade-${i}`,
      symbol: sym,
      action: isBuy ? 'BUY' : 'SELL',
      date:   new Date(startMs + i * 14 * 86400000).toISOString(),
      price:  100 + Math.random() * 100,
      shares: 10 + Math.round(Math.random() * 20),
      value:  (100 + Math.random() * 100) * (10 + Math.round(Math.random() * 20)),
      reason: isBuy ? `${row.criteriaType} sinyali — skor > 80` : 'Portföy yenileme — daha iyi fırsat',
    }
  })

  return { ...row, portfolioSnapshots: snapshots, trades }
}

// ── Utility ───────────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined, dec = 1, prefix = '') {
  if (n == null) return '—'
  return `${prefix}${n.toFixed(dec)}`
}

function fmtPct(n: number | null | undefined) {
  if (n == null) return '—'
  return `${n > 0 ? '+' : ''}${n.toFixed(1)}%`
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('tr-TR', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

function exportToCSV(rows: BacktestRow[]) {
  const headers = ['Ad', 'Kriter', 'Piyasa', 'Başlangıç', 'Bitiş', 'Dönem', 'Durum', 'Toplam Getiri%', 'CAGR%', 'Maks. Drawdown%', 'Sharpe', 'Kazanma Oranı%', 'İşlem Sayısı']
  const lines   = [
    headers.join(','),
    ...rows.map((r) => [
      `"${r.name}"`, r.criteriaType, r.market,
      r.startDate, r.endDate, r.rebalancePeriod, r.status,
      r.totalReturn ?? '', r.annualizedReturn ?? '', r.maxDrawdown ?? '',
      r.sharpeRatio ?? '', r.winRate ?? '', r.totalTrades ?? '',
    ].join(',')),
  ]
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = `verdent_backtests_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

function exportDetailCSV(detail: BacktestDetail) {
  const headers = ['Tarih', 'Sembol', 'İşlem', 'Fiyat', 'Adet', 'Değer', 'Neden']
  const lines   = [
    headers.join(','),
    ...detail.trades.map((t) => [
      fmtDate(t.date), t.symbol, t.action,
      t.price.toFixed(2), t.shares, t.value.toFixed(2), `"${t.reason}"`,
    ].join(',')),
  ]
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = `${detail.name.replace(/\s+/g, '_')}_trades.csv`
  a.click()
  URL.revokeObjectURL(url)
}

// ── Sub-components ────────────────────────────────────────────────────────────

function CriteriaBadge({ type }: { type: string }) {
  const meta = CRITERIA_META[type as CriteriaType] ?? { color: 'var(--text-muted)', bg: 'var(--bg-hover)', label: type }
  return (
    <span style={{
      padding: '2px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: 700,
      color: meta.color, background: meta.bg, border: `1px solid ${meta.color}40`,
    }}>{meta.label}</span>
  )
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { color: string; bg: string; icon: React.ReactNode }> = {
    COMPLETED: { color: 'var(--green)',  bg: 'rgba(0,208,132,0.1)',  icon: <CheckCircle2 size={11} /> },
    RUNNING:   { color: 'var(--blue)',   bg: 'rgba(77,159,255,0.1)', icon: <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} /> },
    FAILED:    { color: 'var(--red)',    bg: 'rgba(255,77,77,0.1)',  icon: <AlertCircle size={11} /> },
  }
  const s = map[status] ?? map.FAILED
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '2px 8px', borderRadius: '20px', fontSize: '11px', fontWeight: 600, color: s.color, background: s.bg }}>
      {s.icon}{status}
    </span>
  )
}

function MetricCard({ label, value, positive, sub, icon }: {
  label: string; value: string; positive?: boolean; sub?: string; icon: React.ReactNode
}) {
  const color = positive == null ? 'var(--text-primary)' : positive ? 'var(--green)' : 'var(--red)'
  return (
    <div className="card" style={{ padding: '18px 20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '10px' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-muted)', letterSpacing: '0.5px', textTransform: 'uppercase' }}>{label}</span>
        <span style={{ color, opacity: 0.8 }}>{icon}</span>
      </div>
      <div style={{ fontSize: '22px', fontWeight: 700, color }}>{value}</div>
      {sub && <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>{sub}</div>}
    </div>
  )
}

function HybridTimeline({ snapshots }: { snapshots: BacktestDetail['portfolioSnapshots'] }) {
  if (!snapshots.length) return null
  return (
    <div className="card" style={{ padding: '20px' }}>
      <h4 style={{ margin: '0 0 14px', fontSize: '13px', color: 'var(--text-secondary)', letterSpacing: '1px' }}>
        HYBRID KRİTER ZAMANÇİZELGESİ
      </h4>
      <div style={{ display: 'flex', gap: '2px', flexWrap: 'wrap' }}>
        {snapshots.map((s, i) => {
          const meta = CRITERIA_META[s.criteriaUsed as CriteriaType]
          return (
            <div
              key={s.id}
              title={`${fmtDate(s.date)} — ${s.criteriaUsed} (${s.marketCondition})`}
              style={{
                width: '28px', height: '28px', borderRadius: '6px',
                background: meta?.bg ?? 'var(--bg-hover)',
                border: `1px solid ${meta?.color ?? 'var(--border)'}40`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '9px', fontWeight: 700,
                color: meta?.color ?? 'var(--text-muted)',
                cursor: 'default',
              }}
            >{i + 1}</div>
          )
        })}
      </div>
      <div style={{ display: 'flex', gap: '16px', marginTop: '12px', flexWrap: 'wrap' }}>
        {(Object.keys(CRITERIA_META) as CriteriaType[]).filter((k) => k !== 'HYBRID').map((k) => {
          const meta  = CRITERIA_META[k]
          const count = snapshots.filter((s) => s.criteriaUsed === k).length
          return (
            <div key={k} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
              <div style={{ width: '10px', height: '10px', borderRadius: '3px', background: meta.color }} />
              <span style={{ color: 'var(--text-secondary)' }}>{k}: <strong style={{ color: meta.color }}>{count}</strong> dönem</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Detail View ───────────────────────────────────────────────────────────────

function BacktestDetailView({ detail, onBack }: { detail: BacktestDetail; onBack: () => void }) {
  const [tab, setTab] = useState<DetailTab>('performance')

  const equityCurve = detail.portfolioSnapshots.map((s) => ({
    date:  fmtDate(s.date).slice(3),
    value: s.portfolioValue,
    criteria: s.criteriaUsed,
  }))

  const monthlyMap: Record<string, number> = {}
  for (let i = 1; i < equityCurve.length; i++) {
    const prev    = detail.portfolioSnapshots[i - 1].portfolioValue
    const curr    = detail.portfolioSnapshots[i].portfolioValue
    const mo      = equityCurve[i].date
    monthlyMap[mo] = ((curr - prev) / prev) * 100
  }
  const monthlyData = Object.entries(monthlyMap).map(([d, r]) => ({ d, r: +r.toFixed(2) }))

  const tabBtnStyle = (t: DetailTab) => ({
    padding: '8px 16px', borderRadius: '8px', border: 'none', cursor: 'pointer',
    fontSize: '13px', fontWeight: tab === t ? 600 : 400,
    background: tab === t ? 'var(--primary)' : 'var(--bg-hover)',
    color:      tab === t ? '#000' : 'var(--text-secondary)',
    transition: 'all 0.15s',
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button
            onClick={onBack}
            style={{ background: 'var(--bg-hover)', border: '1px solid var(--border)', borderRadius: '8px', padding: '6px 10px', cursor: 'pointer', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '13px' }}
          >
            <ChevronLeft size={14} /> Geri
          </button>
          <div>
            <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 700 }}>{detail.name}</h2>
            <div style={{ display: 'flex', gap: '8px', marginTop: '4px', alignItems: 'center' }}>
              <CriteriaBadge type={detail.criteriaType} />
              <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{fmtDate(detail.startDate)} – {fmtDate(detail.endDate)}</span>
              <StatusBadge status={detail.status} />
            </div>
          </div>
        </div>
        <button
          onClick={() => exportDetailCSV(detail)}
          style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 14px', background: 'var(--bg-hover)', border: '1px solid var(--border)', borderRadius: '8px', cursor: 'pointer', color: 'var(--text-secondary)', fontSize: '13px' }}
        >
          <Download size={14} /> CSV İndir
        </button>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '8px', background: 'var(--bg-card)', padding: '6px', borderRadius: '10px', border: '1px solid var(--border)', width: 'fit-content' }}>
        <button style={tabBtnStyle('performance')} onClick={() => setTab('performance')}>📊 Performans</button>
        <button style={tabBtnStyle('portfolio')}   onClick={() => setTab('portfolio')}>📈 Portföy Geçmişi</button>
        <button style={tabBtnStyle('trades')}      onClick={() => setTab('trades')}>🔄 İşlemler</button>
        <button style={tabBtnStyle('signals')}     onClick={() => setTab('signals')}>🎯 Sinyaller</button>
        <button style={tabBtnStyle('diagnostic')}  onClick={() => setTab('diagnostic')}>🔬 Tanılama</button>
        <button style={tabBtnStyle('analytics')}   onClick={() => setTab('analytics')}>📊 Analitik</button>
      </div>

      {/* ── Performance Tab ── */}
      {tab === 'performance' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '12px' }}>
            <MetricCard label="Toplam Getiri" value={fmtPct(detail.totalReturn)} positive={(detail.totalReturn ?? 0) > 0} icon={<TrendingUp size={16} />} />
            <MetricCard label="Yıllık Getiri (CAGR)" value={fmtPct(detail.annualizedReturn)} positive={(detail.annualizedReturn ?? 0) > 0} icon={<BarChart2 size={16} />} />
            <MetricCard label="Maks. Drawdown" value={fmtPct(detail.maxDrawdown)} positive={false} icon={<TrendingDown size={16} />} />
            <MetricCard label="Sharpe Oranı" value={fmt(detail.sharpeRatio)} positive={(detail.sharpeRatio ?? 0) > 1} icon={<BarChart2 size={16} />} />
            <MetricCard label="Kazanma Oranı" value={fmtPct(detail.winRate)} positive={(detail.winRate ?? 0) > 50} icon={<Percent size={16} />} />
            <MetricCard label="Toplam İşlem" value={String(detail.totalTrades ?? '—')} icon={<DollarSign size={16} />} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            {/* Equity curve */}
            <div className="card" style={{ padding: '20px' }}>
              <h4 style={{ margin: '0 0 14px', fontSize: '13px', color: 'var(--text-secondary)', letterSpacing: '1px' }}>PORTFÖY DEĞERİ</h4>
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={equityCurve}>
                  <defs>
                    <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#00D084" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#00D084" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(30,45,69,0.5)" />
                  <XAxis dataKey="date" tick={{ fill: '#8A9BBE', fontSize: 10 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                  <YAxis tick={{ fill: '#8A9BBE', fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                  <Tooltip
                    contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '8px', fontSize: '12px' }}
                    formatter={(v: number) => [`${v.toLocaleString('tr-TR')} ₺`, 'Değer']}
                  />
                  <ReferenceLine y={detail.initialCapital} stroke="rgba(138,155,190,0.35)" strokeDasharray="4 4" label={{ value: 'Başlangıç', fill: '#4A5A78', fontSize: 10 }} />
                  <Area type="monotone" dataKey="value" stroke="#00D084" strokeWidth={2} fill="url(#eqGrad)" dot={false} name="Strateji" />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {/* Monthly returns */}
            <div className="card" style={{ padding: '20px' }}>
              <h4 style={{ margin: '0 0 14px', fontSize: '13px', color: 'var(--text-secondary)', letterSpacing: '1px' }}>AYLIK GETİRİLER</h4>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={monthlyData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(30,45,69,0.5)" />
                  <XAxis dataKey="d" tick={{ fill: '#8A9BBE', fontSize: 10 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                  <YAxis tick={{ fill: '#8A9BBE', fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => `${v}%`} />
                  <Tooltip
                    contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '8px', fontSize: '12px' }}
                    formatter={(v: number) => [`${v.toFixed(2)}%`, 'Getiri']}
                  />
                  <ReferenceLine y={0} stroke="rgba(138,155,190,0.4)" />
                  <Bar dataKey="r" radius={[3, 3, 0, 0]} name="Getiri">
                    {monthlyData.map((entry, i) => (
                      <Cell key={i} fill={entry.r >= 0 ? 'var(--green)' : 'var(--red)'} fillOpacity={0.85} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* HYBRID timeline */}
          {detail.criteriaType === 'HYBRID' && <HybridTimeline snapshots={detail.portfolioSnapshots} />}
        </div>
      )}

      {/* ── Portfolio History Tab ── */}
      {tab === 'portfolio' && (
        <div className="card" style={{ padding: '20px' }}>
          <h4 style={{ margin: '0 0 16px', fontSize: '13px', color: 'var(--text-secondary)', letterSpacing: '1px' }}>PORTFÖY GEÇMİŞİ (yenileme dönemleri)</h4>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['Tarih', 'Kriter', 'Piyasa Koşulu', 'Portföy Değeri', 'Üst 5 Hisse'].map((h) => (
                    <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600, letterSpacing: '0.5px', whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {detail.portfolioSnapshots.map((s) => (
                  <tr key={s.id} style={{ borderBottom: '1px solid rgba(30,45,69,0.4)' }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-hover)')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                  >
                    <td style={{ padding: '10px 12px', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{fmtDate(s.date)}</td>
                    <td style={{ padding: '10px 12px' }}><CriteriaBadge type={s.criteriaUsed} /></td>
                    <td style={{ padding: '10px 12px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 600, color: CONDITION_COLOR[s.marketCondition] ?? 'var(--text-secondary)' }}>
                        {s.marketCondition}
                      </span>
                    </td>
                    <td style={{ padding: '10px 12px', fontWeight: 700, color: 'var(--primary)' }}>
                      {s.portfolioValue.toLocaleString('tr-TR')} ₺
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                        {s.holdings.slice(0, 5).map((h) => (
                          <span key={h.symbol} style={{ fontSize: '11px', fontWeight: 600, padding: '1px 6px', borderRadius: '4px', background: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>
                            {h.symbol}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Trades Tab ── */}
      {tab === 'trades' && (
        <div className="card" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h4 style={{ margin: 0, fontSize: '13px', color: 'var(--text-secondary)', letterSpacing: '1px' }}>
              TÜM İŞLEMLER ({detail.trades.length})
            </h4>
            <button
              onClick={() => exportDetailCSV(detail)}
              style={{ display: 'flex', alignItems: 'center', gap: '5px', padding: '6px 12px', background: 'var(--bg-hover)', border: '1px solid var(--border)', borderRadius: '7px', cursor: 'pointer', color: 'var(--text-secondary)', fontSize: '12px' }}
            >
              <Download size={12} /> Dışa Aktar
            </button>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['Tarih', 'Sembol', 'İşlem', 'Fiyat', 'Adet', 'Değer', 'Neden'].map((h) => (
                    <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600, letterSpacing: '0.5px', whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {detail.trades.map((t) => (
                  <tr key={t.id} style={{ borderBottom: '1px solid rgba(30,45,69,0.4)' }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-hover)')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                  >
                    <td style={{ padding: '10px 12px', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{fmtDate(t.date)}</td>
                    <td style={{ padding: '10px 12px', fontWeight: 700 }}>{t.symbol}</td>
                    <td style={{ padding: '10px 12px' }}>
                      <span style={{
                        fontSize: '11px', fontWeight: 700, padding: '2px 8px', borderRadius: '20px',
                        background: t.action === 'BUY' ? 'rgba(0,208,132,0.15)' : 'rgba(255,77,77,0.15)',
                        color:      t.action === 'BUY' ? 'var(--green)' : 'var(--red)',
                      }}>{t.action}</span>
                    </td>
                    <td style={{ padding: '10px 12px' }}>{t.price.toFixed(2)}</td>
                    <td style={{ padding: '10px 12px', color: 'var(--text-secondary)' }}>{t.shares}</td>
                    <td style={{ padding: '10px 12px', fontWeight: 600 }}>{t.value.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                    <td style={{ padding: '10px 12px', color: 'var(--text-muted)', fontSize: '12px', maxWidth: '220px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {t.reason}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Signals Tab ── */}
      {tab === 'signals' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
          <div className="card" style={{ padding: '20px' }}>
            <h4 style={{ margin: '0 0 14px', fontSize: '13px', color: 'var(--text-secondary)', letterSpacing: '1px' }}>KRİTER KULLANIMI</h4>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={(() => {
                const counts: Record<string, number> = {}
                detail.portfolioSnapshots.forEach((s) => {
                  counts[s.criteriaUsed] = (counts[s.criteriaUsed] ?? 0) + 1
                })
                return Object.entries(counts).map(([c, n]) => ({ c, n }))
              })()}>
                <XAxis dataKey="c" tick={{ fill: '#8A9BBE', fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#8A9BBE', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '8px', fontSize: '12px' }} />
                <Bar dataKey="n" radius={[4, 4, 0, 0]} name="Dönem Sayısı">
                  {(Object.keys(CRITERIA_META) as CriteriaType[]).map((k) => (
                    <Cell key={k} fill={CRITERIA_META[k].color} fillOpacity={0.8} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="card" style={{ padding: '20px' }}>
            <h4 style={{ margin: '0 0 14px', fontSize: '13px', color: 'var(--text-secondary)', letterSpacing: '1px' }}>PİYASA KOŞULU DAĞILIMI</h4>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={(() => {
                const counts: Record<string, number> = {}
                detail.portfolioSnapshots.forEach((s) => {
                  counts[s.marketCondition] = (counts[s.marketCondition] ?? 0) + 1
                })
                return Object.entries(counts).map(([c, n]) => ({ c, n }))
              })()}>
                <XAxis dataKey="c" tick={{ fill: '#8A9BBE', fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#8A9BBE', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '8px', fontSize: '12px' }} />
                <Bar dataKey="n" radius={[4, 4, 0, 0]} name="Dönem Sayısı">
                  {['BULL', 'BEAR', 'SIDEWAYS'].map((k) => (
                    <Cell key={k} fill={CONDITION_COLOR[k]} fillOpacity={0.8} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {detail.criteriaType === 'HYBRID' && (
            <div style={{ gridColumn: '1 / -1' }}>
              <HybridTimeline snapshots={detail.portfolioSnapshots} />
            </div>
          )}
        </div>
      )}

      {/* ── Diagnostic Tab ── */}
      {tab === 'diagnostic' && (
        <DiagnosticPanel backtestId={detail.id} market={detail.market} />
      )}

      {/* ── Analytics Tab ── */}
      {tab === 'analytics' && (
        <BacktestAnalytics backtest={{
          id:              detail.id,
          name:            detail.name,
          criteriaType:    detail.criteriaType,
          market:          detail.market,
          startDate:       detail.startDate,
          endDate:         detail.endDate,
          totalReturn:     detail.totalReturn,
          annualizedReturn:detail.annualizedReturn,
          maxDrawdown:     detail.maxDrawdown,
          sharpeRatio:     detail.sharpeRatio,
          winRate:         detail.winRate,
          totalTrades:     detail.totalTrades,
          initialCapital:  detail.initialCapital ?? 100000,
          portfolioSnapshots: (detail.portfolioSnapshots ?? []).map((s: any) => ({
            date:            typeof s.date === 'string' ? s.date : new Date(s.date).toISOString(),
            portfolioValue:  s.portfolioValue,
            criteriaUsed:    s.criteriaUsed,
            marketCondition: s.marketCondition ?? 'SIDEWAYS',
            holdings:        Array.isArray(s.holdings) ? s.holdings : [],
          })),
          trades: (detail.trades ?? []).map((t: any) => ({
            date:   typeof t.date === 'string' ? t.date : new Date(t.date).toISOString(),
            action: t.action,
            value:  t.value,
            reason: t.reason ?? '',
          })),
        }} />
      )}
    </div>
  )
}

// ── Configuration Form ────────────────────────────────────────────────────────

function ConfigForm({ onJobStarted }: { onJobStarted: (jobId: string, name: string) => void }) {
  const [cfg, setCfg] = useState<BacktestConfig>({
    name:            'Yeni Backtest',
    criteriaType:    'HYBRID',
    startDate:       '2022-01-01',
    endDate:         '2024-01-01',
    rebalancePeriod: 'MONTHLY',
    market:          'BIST',
    initialCapital:  100000,
    transactionCost: 0.001,
    slippage:        0.001,
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError]           = useState<string | null>(null)

  const set = <K extends keyof BacktestConfig>(k: K, v: BacktestConfig[K]) =>
    setCfg((p) => ({ ...p, [k]: v }))

  const handleRun = async () => {
    if (new Date(cfg.startDate) >= new Date(cfg.endDate)) {
      setError('Başlangıç tarihi bitiş tarihinden önce olmalı')
      return
    }
    try {
      setSubmitting(true)
      setError(null)
      const res = await backtestService.run({
        ...cfg,
        startDate: cfg.startDate,
        endDate:   cfg.endDate,
      })
      onJobStarted(res.data.jobId, cfg.name)
    } catch (err: any) {
      const msg =
        err?.response?.data?.error ||
        err?.response?.data?.message ||
        err?.message ||
        'Backtest başlatılamadı — sunucu bağlantısını kontrol edin'
      setError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  const inputStyle = {
    width: '100%', padding: '9px 12px', background: 'var(--bg-hover)',
    border: '1px solid var(--border)', borderRadius: '8px', color: 'var(--text-primary)',
    fontSize: '13px', outline: 'none', colorScheme: 'dark' as const,
  }

  const labelStyle = { display: 'block' as const, fontSize: '11px', color: 'var(--text-muted)', marginBottom: '6px', letterSpacing: '0.5px', textTransform: 'uppercase' as const }

  const radioGroup = <T extends string>(
    options: { value: T; label: string; desc?: string }[],
    current: T,
    onChange: (v: T) => void,
    colorMap?: Record<string, string>
  ) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      {options.map(({ value, label, desc }) => {
        const active = current === value
        const color  = colorMap?.[value] ?? 'var(--primary)'
        return (
          <label key={value} style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', padding: '8px 10px', borderRadius: '8px', cursor: 'pointer', background: active ? `${color}12` : 'var(--bg-hover)', border: `1px solid ${active ? color + '50' : 'var(--border)'}`, transition: 'all 0.15s' }}>
            <div style={{ width: '16px', height: '16px', borderRadius: '50%', border: `2px solid ${active ? color : 'var(--text-muted)'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', marginTop: '1px', flexShrink: 0 }}>
              {active && <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: color }} />}
            </div>
            <input type="radio" value={value} checked={active} onChange={() => onChange(value)} style={{ display: 'none' }} />
            <div>
              <div style={{ fontSize: '13px', fontWeight: active ? 700 : 500, color: active ? color : 'var(--text-secondary)' }}>{label}</div>
              {desc && <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '1px' }}>{desc}</div>}
            </div>
          </label>
        )
      })}
    </div>
  )

  return (
    <div className="card" style={{ padding: '24px' }}>
      <h3 style={{ margin: '0 0 20px', fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)' }}>
        Yeni Backtest Oluştur
      </h3>

      <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr 1fr 1fr', gap: '20px' }}>
        {/* Criteria */}
        <div>
          <span style={labelStyle}>Kriter Türü</span>
          {radioGroup(
            [
              { value: 'ALFA',   label: 'ALFA',   desc: 'Boğa / Momentum' },
              { value: 'BETA',   label: 'BETA',   desc: 'Ayı / Savunmacı' },
              { value: 'DELTA',  label: 'DELTA',  desc: 'Yatay / Mean Rev.' },
              { value: 'HYBRID', label: 'HYBRID', desc: 'Otomatik seçim' },
            ] as { value: CriteriaType; label: string; desc: string }[],
            cfg.criteriaType,
            (v) => set('criteriaType', v),
            { ALFA: 'var(--green)', BETA: 'var(--red)', DELTA: 'var(--yellow)', HYBRID: 'var(--blue)' }
          )}
        </div>

        {/* Dates + Name */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div>
            <label style={labelStyle}>Backtest Adı</label>
            <input style={inputStyle} value={cfg.name} onChange={(e) => set('name', e.target.value)} />
          </div>
          <div>
            <label style={labelStyle}><Calendar size={11} style={{ display: 'inline', marginRight: '4px' }} />Başlangıç Tarihi</label>
            <input type="date" style={inputStyle} value={cfg.startDate} onChange={(e) => set('startDate', e.target.value)} />
          </div>
          <div>
            <label style={labelStyle}><Calendar size={11} style={{ display: 'inline', marginRight: '4px' }} />Bitiş Tarihi</label>
            <input type="date" style={inputStyle} value={cfg.endDate} onChange={(e) => set('endDate', e.target.value)} />
          </div>
        </div>

        {/* Period + Capital */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div>
            <span style={labelStyle}>Yenileme Dönemi</span>
            {radioGroup(
              [
                { value: 'WEEKLY',   label: 'Haftalık (7 gün)' },
                { value: 'BIWEEKLY', label: '15 Günlük' },
                { value: 'MONTHLY',  label: 'Aylık (30 gün)' },
              ] as { value: RebalancePeriod; label: string }[],
              cfg.rebalancePeriod,
              (v) => set('rebalancePeriod', v)
            )}
          </div>
          <div>
            <label style={labelStyle}>Başlangıç Sermayesi (₺)</label>
            <input
              type="number" style={inputStyle}
              value={cfg.initialCapital}
              onChange={(e) => set('initialCapital', +e.target.value)}
            />
          </div>
        </div>

        {/* Market + advanced */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div>
            <span style={labelStyle}>Piyasa</span>
            {radioGroup(
              [
                { value: 'BIST', label: '🇹🇷 BIST' },
                { value: 'US',   label: '🇺🇸 US Market' },
                { value: 'BOTH', label: '🌍 Her İkisi' },
              ] as { value: MarketType; label: string }[],
              cfg.market,
              (v) => set('market', v)
            )}
          </div>
          <div>
            <label style={labelStyle}>İşlem Maliyeti (%)</label>
            <input type="number" style={inputStyle} step="0.0001" value={cfg.transactionCost} onChange={(e) => set('transactionCost', +e.target.value)} />
          </div>
        </div>
      </div>

      {error && (
        <div style={{ marginTop: '14px', display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 14px', borderRadius: '8px', background: 'rgba(245,166,35,0.1)', border: '1px solid rgba(245,166,35,0.2)', fontSize: '13px', color: 'var(--yellow)' }}>
          <AlertCircle size={14} />{error}
        </div>
      )}

      <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'flex-end' }}>
        <button
          className="btn-primary"
          onClick={handleRun}
          disabled={submitting}
          style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 24px', opacity: submitting ? 0.7 : 1 }}
        >
          {submitting ? <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> : <Play size={16} />}
          {submitting ? 'Başlatılıyor...' : 'Backtesti Çalıştır'}
        </button>
      </div>
    </div>
  )
}

// ── Progress Bar ──────────────────────────────────────────────────────────────

function RunningJobBanner({ job, onDone }: { job: RunningJob; onDone: () => void }) {
  const [progress, setProgress]   = useState(job.progress)
  const [status,   setStatus]     = useState(job.status)
  const intervalRef  = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollRef      = useRef<ReturnType<typeof setInterval> | null>(null)
  const doneCalledRef = useRef(false)

  // Animate progress bar up to 94%
  useEffect(() => {
    if (status !== 'RUNNING') return
    intervalRef.current = setInterval(() => {
      setProgress((p) => {
        if (p >= 94) { clearInterval(intervalRef.current!); return 94 }
        return p + 1 + Math.random() * 1.5
      })
    }, 400)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [status])

  // Poll backend every 3 seconds to detect COMPLETED / FAILED
  useEffect(() => {
    if (status !== 'RUNNING') return
    pollRef.current = setInterval(async () => {
      try {
        const res = await backtestService.getList({ limit: 1, offset: 0 })
        const latest = res.data?.backtests?.[0]
        if (latest?.status === 'COMPLETED' || latest?.status === 'FAILED') {
          clearInterval(pollRef.current!)
          clearInterval(intervalRef.current!)
          setStatus(latest.status)
          setProgress(100)
          if (!doneCalledRef.current) {
            doneCalledRef.current = true
            setTimeout(onDone, 1500)
          }
        }
      } catch { /* ignore poll errors */ }
    }, 3000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [status, onDone])

  // Handle already-completed job passed in
  useEffect(() => {
    if ((job.status === 'COMPLETED' || job.status === 'FAILED') && !doneCalledRef.current) {
      clearInterval(intervalRef.current!)
      clearInterval(pollRef.current!)
      setProgress(100)
      setStatus(job.status)
      doneCalledRef.current = true
      setTimeout(onDone, 1500)
    }
  }, [job.status, onDone])

  const pct   = Math.min(100, progress)
  const color = status === 'FAILED' ? 'var(--red)' : 'var(--primary)'

  return (
    <div style={{ padding: '14px 18px', borderRadius: '10px', background: 'rgba(77,159,255,0.08)', border: '1px solid rgba(77,159,255,0.25)', display: 'flex', flexDirection: 'column', gap: '10px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: 'var(--blue)', fontWeight: 600 }}>
          {status === 'RUNNING' ? <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> : status === 'COMPLETED' ? <CheckCircle2 size={14} color="var(--green)" /> : <AlertCircle size={14} color="var(--red)" />}
          {status === 'RUNNING' ? 'Backtest çalışıyor...' : status === 'COMPLETED' ? 'Tamamlandı!' : `Hata: ${job.error}`}
        </div>
        <span style={{ fontSize: '13px', fontWeight: 700, color }}>{pct.toFixed(0)}%</span>
      </div>
      <div style={{ height: '6px', background: 'var(--bg-hover)', borderRadius: '3px', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: '3px', transition: 'width 0.4s ease' }} />
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function Backtest() {
  const PAGE_SIZE = 10

  const [list,          setList]          = useState<BacktestRow[]>([])
  const [total,         setTotal]         = useState(0)
  const [page,          setPage]          = useState(0)
  const [loading,       setLoading]       = useState(true)
  const [detail,        setDetail]        = useState<BacktestDetail | null>(null)
  const [runningJob,    setRunningJob]    = useState<RunningJob | null>(null)
  const [useMock,       setUseMock]       = useState(false)
  const [compareIds,    setCompareIds]    = useState<string[]>([])
  const [showCompare,   setShowCompare]   = useState(false)

  const fetchList = useCallback(async (p = 0) => {
    try {
      setLoading(true)
      const res = await backtestService.getList({ limit: PAGE_SIZE, offset: p * PAGE_SIZE })
      const rows = (res.data?.backtests ?? []) as BacktestRow[]
      setList(rows)
      setTotal(res.data?.total ?? rows.length)
      setUseMock(false)
    } catch {
      setList(buildMockList())
      setTotal(buildMockList().length)
      setUseMock(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchList(page) }, [fetchList, page])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const toggleCompare = (id: string) => {
    setCompareIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id)
      if (prev.length >= 3) return prev
      return [...prev, id]
    })
  }

  const compareItems = useMemo(
    () => list.filter((r) => compareIds.includes(r.id)),
    [list, compareIds]
  )

  // Build normalised chart data for comparison (index = 100 at start)
  const compareChartData = useMemo(() => {
    if (compareItems.length < 2) return []
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    // Generate 12 mock normalised monthly points per backtest
    return months.map((m, i) => {
      const pt: Record<string, unknown> = { month: m }
      compareItems.forEach((item) => {
        const annualised = (item.annualizedReturn ?? 0) / 100
        pt[item.name] = parseFloat((100 * Math.pow(1 + annualised, (i + 1) / 12)).toFixed(2))
      })
      return pt
    })
  }, [compareItems])

  const handleView = async (row: BacktestRow) => {
    if (useMock) { setDetail(buildMockDetail(row)); return }
    try {
      const res = await backtestService.getById(row.id)
      setDetail(res.data as BacktestDetail)
    } catch {
      setDetail(buildMockDetail(row))
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Bu backtesti silmek istiyor musunuz?')) return
    try {
      await backtestService.deleteById(id)
    } catch { /* noop */ }
    setList((prev) => prev.filter((r) => r.id !== id))
    setTotal((t) => Math.max(0, t - 1))
  }

  const handleJobStarted = (jobId: string, _name: string) => {
    setRunningJob({ jobId, progress: 0, status: 'RUNNING' })
  }

  const handleJobDone = () => {
    setRunningJob(null)
    setPage(0)
    fetchList(0)
  }

  if (detail) return <BacktestDetailView detail={detail} onBack={() => setDetail(null)} />

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '24px', fontWeight: 700 }}>Backtest</h1>
          <p style={{ margin: '4px 0 0', fontSize: '13px', color: 'var(--text-secondary)' }}>
            ALFA / BETA / DELTA ve HYBRID stratejilerini geçmiş verilerle test edin
          </p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            onClick={() => exportToCSV(list)}
            disabled={list.length === 0}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 14px', background: 'var(--bg-hover)', border: '1px solid var(--border)', borderRadius: '8px', cursor: 'pointer', color: 'var(--text-secondary)', fontSize: '13px', opacity: list.length === 0 ? 0.5 : 1 }}
          >
            <Download size={14} /> CSV İndir
          </button>
          <button
            onClick={() => { setPage(0); fetchList(0) }}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 14px', background: 'var(--bg-hover)', border: '1px solid var(--border)', borderRadius: '8px', cursor: 'pointer', color: 'var(--text-secondary)', fontSize: '13px' }}
          >
            <RefreshCw size={14} /> Yenile
          </button>
        </div>
      </div>

      {/* Config form */}
      <ConfigForm onJobStarted={handleJobStarted} />

      {/* Running job banner */}
      {runningJob && <RunningJobBanner job={runningJob} onDone={handleJobDone} />}

      {/* Demo notice */}
      {useMock && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 14px', borderRadius: '8px', background: 'rgba(245,166,35,0.08)', border: '1px solid rgba(245,166,35,0.2)', fontSize: '13px', color: 'var(--yellow)' }}>
          <AlertCircle size={14} /> API bağlantısı yok — örnek veriler gösteriliyor
        </div>
      )}

      {/* History list */}
      <div className="card" style={{ padding: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700 }}>Backtest Geçmişi</h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Clock size={13} style={{ color: 'var(--text-muted)' }} />
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{total} kayıt · Sayfa {page + 1}/{totalPages}</span>
          </div>
        </div>

        {loading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {[1, 2, 3].map((i) => (
              <div key={i} style={{ height: '56px', borderRadius: '8px', background: 'var(--bg-hover)', animation: 'pulse 1.5s ease-in-out infinite' }} />
            ))}
          </div>
        ) : list.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--text-muted)' }}>
            <BarChart2 size={32} style={{ opacity: 0.3, margin: '0 auto 12px' }} />
            <p style={{ margin: 0, fontSize: '14px' }}>Henüz backtest yok. Yukarıdan yeni bir tane başlatın.</p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['#', 'Ad', 'Kriter', 'Piyasa', 'Tarih Aralığı', 'Dönem', 'Durum', 'Getiri', 'Maks. Drawdown', 'Sharpe', 'İşlemler'].map((h) => (
                    <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600, letterSpacing: '0.5px', whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {list.map((row, idx) => (
                  <tr key={row.id} style={{ borderBottom: '1px solid rgba(30,45,69,0.4)', transition: 'background 0.1s' }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-hover)')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                  >
                    <td style={{ padding: '12px', color: 'var(--text-muted)', fontSize: '12px' }}>{idx + 1}</td>
                    <td style={{ padding: '12px', fontWeight: 600, maxWidth: '140px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {row.name}
                    </td>
                    <td style={{ padding: '12px' }}><CriteriaBadge type={row.criteriaType} /></td>
                    <td style={{ padding: '12px', color: 'var(--text-secondary)', fontSize: '12px' }}>{row.market}</td>
                    <td style={{ padding: '12px', color: 'var(--text-muted)', fontSize: '12px', whiteSpace: 'nowrap' }}>
                      {fmtDate(row.startDate)} – {fmtDate(row.endDate)}
                    </td>
                    <td style={{ padding: '12px', color: 'var(--text-secondary)', fontSize: '12px' }}>{row.rebalancePeriod === 'WEEKLY' ? 'Haftalık' : row.rebalancePeriod === 'BIWEEKLY' ? '15 Günlük' : 'Aylık'}</td>
                    <td style={{ padding: '12px' }}><StatusBadge status={row.status} /></td>
                    <td style={{ padding: '12px', fontWeight: 700 }}>
                      {row.totalReturn != null ? (
                        <span style={{ color: row.totalReturn >= 0 ? 'var(--green)' : 'var(--red)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          {row.totalReturn >= 0 ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}
                          {fmtPct(row.totalReturn)}
                        </span>
                      ) : '—'}
                    </td>
                    <td style={{ padding: '12px', color: (row.maxDrawdown ?? 0) < -15 ? 'var(--red)' : 'var(--yellow)' }}>
                      {fmtPct(row.maxDrawdown)}
                    </td>
                    <td style={{ padding: '12px', color: 'var(--text-secondary)' }}>
                      {fmt(row.sharpeRatio)}
                    </td>
                    <td style={{ padding: '12px' }}>
                      <div style={{ display: 'flex', gap: '6px' }}>
                        <button
                          onClick={() => handleView(row)}
                          title="Detay Görüntüle"
                          style={{ padding: '5px 8px', background: 'var(--bg-hover)', border: '1px solid var(--border)', borderRadius: '6px', cursor: 'pointer', color: 'var(--blue)', display: 'flex', alignItems: 'center', transition: 'all 0.15s' }}
                          onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--blue)'; e.currentTarget.style.background = 'rgba(77,159,255,0.1)' }}
                          onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.background = 'var(--bg-hover)' }}
                        >
                          <Eye size={13} />
                        </button>
                        <button
                          onClick={() => toggleCompare(row.id)}
                          title={compareIds.includes(row.id) ? 'Karşılaştırmadan Çıkar' : 'Karşılaştırmaya Ekle (maks 3)'}
                          style={{ padding: '5px 8px', background: compareIds.includes(row.id) ? 'rgba(168,85,247,0.15)' : 'var(--bg-hover)', border: `1px solid ${compareIds.includes(row.id) ? 'rgba(168,85,247,0.5)' : 'var(--border)'}`, borderRadius: '6px', cursor: 'pointer', color: compareIds.includes(row.id) ? '#A855F7' : 'var(--text-secondary)', display: 'flex', alignItems: 'center', transition: 'all 0.15s' }}
                        >
                          <GitCompare size={13} />
                        </button>
                        <button
                          onClick={() => handleDelete(row.id)}
                          title="Sil"
                          style={{ padding: '5px 8px', background: 'var(--bg-hover)', border: '1px solid var(--border)', borderRadius: '6px', cursor: 'pointer', color: 'var(--red)', display: 'flex', alignItems: 'center', transition: 'all 0.15s' }}
                          onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--red)'; e.currentTarget.style.background = 'rgba(255,77,77,0.1)' }}
                          onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.background = 'var(--bg-hover)' }}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination controls */}
        {!loading && totalPages > 1 && (
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px', paddingTop: '16px', borderTop: '1px solid var(--border)' }}>
            <button
              disabled={page === 0}
              onClick={() => setPage((p) => { const np = p - 1; fetchList(np); return np })}
              style={{ padding: '6px 14px', borderRadius: '7px', border: '1px solid var(--border)', background: 'var(--bg-hover)', color: page === 0 ? 'var(--text-muted)' : 'var(--text-secondary)', cursor: page === 0 ? 'not-allowed' : 'pointer', fontSize: '13px', opacity: page === 0 ? 0.5 : 1 }}
            >← Önceki</button>

            {Array.from({ length: totalPages }, (_, i) => i).filter((i) => Math.abs(i - page) <= 2).map((i) => (
              <button
                key={i}
                onClick={() => { setPage(i); fetchList(i) }}
                style={{ width: '34px', height: '34px', borderRadius: '7px', border: `1px solid ${i === page ? 'var(--primary)' : 'var(--border)'}`, background: i === page ? 'var(--primary)' : 'var(--bg-hover)', color: i === page ? '#000' : 'var(--text-secondary)', cursor: 'pointer', fontSize: '13px', fontWeight: i === page ? 700 : 400 }}
              >{i + 1}</button>
            ))}

            <button
              disabled={page >= totalPages - 1}
              onClick={() => setPage((p) => { const np = p + 1; fetchList(np); return np })}
              style={{ padding: '6px 14px', borderRadius: '7px', border: '1px solid var(--border)', background: 'var(--bg-hover)', color: page >= totalPages - 1 ? 'var(--text-muted)' : 'var(--text-secondary)', cursor: page >= totalPages - 1 ? 'not-allowed' : 'pointer', fontSize: '13px', opacity: page >= totalPages - 1 ? 0.5 : 1 }}
            >Sonraki →</button>
          </div>
        )}
      </div>

      {/* ── Comparison Panel ──────────────────────────────────────────────── */}
      {compareIds.length >= 2 && (
        <div className="card" style={{ marginTop: '24px', padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <GitCompare size={18} color="var(--purple)" />
              <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700 }}>Backtest Karşılaştırma</h3>
              <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>({compareIds.length} seçili)</span>
            </div>
            <button onClick={() => setCompareIds([])} className="btn-secondary" style={{ padding: '5px 10px', fontSize: '12px' }}>
              <X size={13} /> Temizle
            </button>
          </div>

          {/* Metrics table */}
          <div style={{ overflowX: 'auto', marginBottom: '24px' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600 }}>METRİK</th>
                  {compareItems.map((item) => (
                    <th key={item.id} style={{ padding: '8px 12px', textAlign: 'right', fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600 }}>
                      {item.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { key: 'totalReturn',      label: 'Toplam Getiri',  fmt: (v: number | null) => v != null ? `${v >= 0 ? '+' : ''}${v.toFixed(1)}%` : '—', color: (v: number | null) => v == null ? 'var(--text-secondary)' : v >= 0 ? 'var(--green)' : 'var(--red)' },
                  { key: 'annualizedReturn', label: 'CAGR',           fmt: (v: number | null) => v != null ? `${v >= 0 ? '+' : ''}${v.toFixed(1)}%` : '—', color: (v: number | null) => v == null ? 'var(--text-secondary)' : v >= 0 ? 'var(--green)' : 'var(--red)' },
                  { key: 'maxDrawdown',      label: 'Maks. Drawdown', fmt: (v: number | null) => v != null ? `${v.toFixed(1)}%` : '—',                       color: (v: number | null) => v == null ? 'var(--text-secondary)' : (v ?? 0) < -20 ? 'var(--red)' : 'var(--yellow)' },
                  { key: 'sharpeRatio',      label: 'Sharpe Oranı',   fmt: (v: number | null) => v != null ? v.toFixed(2) : '—',                             color: (v: number | null) => v == null ? 'var(--text-secondary)' : (v ?? 0) >= 1 ? 'var(--green)' : 'var(--yellow)' },
                  { key: 'winRate',          label: 'Kazanma Oranı',  fmt: (v: number | null) => v != null ? `${v.toFixed(1)}%` : '—',                       color: (v: number | null) => v == null ? 'var(--text-secondary)' : (v ?? 0) >= 50 ? 'var(--green)' : 'var(--red)' },
                  { key: 'totalTrades',      label: 'Toplam İşlem',   fmt: (v: number | null) => v != null ? String(v) : '—',                                color: () => 'var(--text-primary)' },
                ].map(({ key, label, fmt: fmtFn, color }) => (
                  <tr key={key} style={{ borderBottom: '1px solid rgba(30,45,74,0.4)' }}>
                    <td style={{ padding: '10px 12px', color: 'var(--text-secondary)', fontSize: '12px' }}>{label}</td>
                    {compareItems.map((item) => {
                      const val = item[key as keyof BacktestRow] as number | null
                      return (
                        <td key={item.id} style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700, color: color(val) }}>
                          {fmtFn(val)}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Growth chart */}
          {compareChartData.length > 0 && (
            <div>
              <p style={{ margin: '0 0 12px', fontSize: '12px', color: 'var(--text-muted)' }}>Normalised büyüme (başlangıç = 100), yıllıklandırılmış getiriye göre tahmin</p>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={compareChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="month" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
                  <YAxis tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
                  <Tooltip
                    contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '8px', fontSize: '12px' }}
                    labelStyle={{ color: 'var(--text-primary)' }}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px' }} />
                  {compareItems.map((item, i) => (
                    <Line
                      key={item.id}
                      type="monotone"
                      dataKey={item.name}
                      stroke={['#00D084','#4D9FFF','#A855F7'][i]}
                      strokeWidth={2}
                      dot={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      <style>{`
        @keyframes spin  { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.4; } }
      `}</style>
    </div>
  )
}

// ── Diagnostic Panel ──────────────────────────────────────────────────────────

function DiagnosticPanel({ backtestId, market }: { backtestId: string; market: string }) {
  const [report, setReport]   = React.useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [error, setError]     = React.useState<string | null>(null)

  const run = async () => {
    setLoading(true); setError(null)
    try {
      const res = await backtestService.diagnostic(backtestId)
      setReport(res.data as Record<string, unknown>)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Tanılama başarısız')
    } finally {
      setLoading(false)
    }
  }

  const card = (label: string, value: string, sub?: string, color = 'var(--accent)') => (
    <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 10, padding: '14px 18px', minWidth: 160 }}>
      <div style={{ color: 'var(--text-secondary)', fontSize: 11, marginBottom: 4 }}>{label}</div>
      <div style={{ color, fontSize: 20, fontWeight: 700 }}>{value}</div>
      {sub && <div style={{ color: 'var(--text-secondary)', fontSize: 11, marginTop: 4 }}>{sub}</div>}
    </div>
  )

  const priorityColor = (p: string) => p === 'HIGH' ? '#FF4757' : p === 'MEDIUM' ? '#FFA502' : '#00D084'

  if (!report) return (
    <div style={{ padding: 32, textAlign: 'center' }}>
      <p style={{ color: 'var(--text-secondary)', marginBottom: 20 }}>
        Backtestin neden düşük/yüksek performans gösterdiğini analiz eder:
        look-ahead bias, işlem maliyetleri, benchmark karşılaştırması.
      </p>
      <button onClick={run} disabled={loading} style={{
        background: 'var(--accent)', color: '#000', border: 'none', borderRadius: 8,
        padding: '10px 28px', fontWeight: 700, cursor: 'pointer', fontSize: 14,
      }}>
        {loading ? '🔬 Analiz yapılıyor…' : '🔬 Tanılama Çalıştır'}
      </button>
      {error && <p style={{ color: '#FF4757', marginTop: 12 }}>{error}</p>}
    </div>
  )

  const r = report as {
    overallScore: number; generatedAt: string
    bias: { estimatedImpact: number; biasTypes: string[]; details: string[] }
    costs: { configuredRoundTrip: number; realisticRoundTrip: number; annualDragEstimate: number; market: string }
    timing: { avgSlippageFromSignal: number; timingScore: number; bestEntryWindow: string }
    benchmarks: Record<string, { backtestReturn: number; benchmarkReturn: number; alpha: number; isOutperforming: boolean }>
    criteriaComponents: { component: string; hitRate: number; avgReturnWhenTrue: number; contribution: number; recommendation: string }[]
    summary: { estimatedPerformanceInflation: number; topIssues: string[]; topFixes: { fix: string; estimatedGain: string; priority: string }[] }
  }

  const scoreColor = r.overallScore >= 70 ? '#00D084' : r.overallScore >= 50 ? '#FFA502' : '#FF4757'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Score row */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        {card('Güvenilirlik Skoru', `${r.overallScore}/100`, 'Yüksek = daha güvenilir', scoreColor)}
        {card('Tahmini Getiri Şişirmesi', `+${r.summary.estimatedPerformanceInflation}%`, 'Bias kaynaklı yapay getiri', '#FFA502')}
        {card('Giriş Zamanlaması', `${r.timing.timingScore}/100`, r.timing.bestEntryWindow)}
        {card('İşlem Maliyeti (RT)', `%${r.costs.realisticRoundTrip}`, `Yapılandırılan: %${r.costs.configuredRoundTrip}`)}
      </div>

      {/* Top Issues */}
      {r.summary.topIssues.length > 0 && (
        <div style={{ background: 'rgba(255,71,87,0.08)', border: '1px solid rgba(255,71,87,0.3)', borderRadius: 10, padding: 16 }}>
          <div style={{ color: '#FF4757', fontWeight: 700, marginBottom: 10 }}>⚠️ Tespit Edilen Sorunlar</div>
          {r.summary.topIssues.map((issue, i) => (
            <div key={i} style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 6 }}>• {issue}</div>
          ))}
        </div>
      )}

      {/* Bias details */}
      <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 10, padding: 16 }}>
        <div style={{ fontWeight: 700, marginBottom: 10 }}>🔍 Öngörü Hatası (Look-Ahead Bias) Analizi</div>
        {r.bias.biasTypes.map((bt, i) => (
          <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            <span style={{ background: 'rgba(255,165,2,0.15)', color: '#FFA502', borderRadius: 4, padding: '2px 8px', fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap' }}>{bt}</span>
            <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{r.bias.details[i]}</span>
          </div>
        ))}
      </div>

      {/* Benchmarks */}
      <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 10, padding: 16 }}>
        <div style={{ fontWeight: 700, marginBottom: 12 }}>📊 Benchmark Karşılaştırması</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10 }}>
          {Object.entries(r.benchmarks).map(([k, v]) => (
            <div key={k} style={{ background: 'var(--bg-primary)', borderRadius: 8, padding: '10px 14px', border: `1px solid ${v.isOutperforming ? 'rgba(0,208,132,0.3)' : 'rgba(255,71,87,0.3)'}` }}>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>{k.replace(/_/g, ' ')}</div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text)', fontSize: 13 }}>Biz: <b>{v.backtestReturn}%</b></span>
                <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>BM: {v.benchmarkReturn}%</span>
              </div>
              <div style={{ color: v.alpha >= 0 ? '#00D084' : '#FF4757', fontSize: 14, fontWeight: 700, marginTop: 4 }}>
                Alpha: {v.alpha >= 0 ? '+' : ''}{v.alpha}%
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Criteria components */}
      <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 10, padding: 16 }}>
        <div style={{ fontWeight: 700, marginBottom: 12 }}>🎯 Kriter Bileşen Analizi</div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ color: 'var(--text-secondary)', borderBottom: '1px solid var(--border)' }}>
                <th style={{ textAlign: 'left', padding: '6px 12px' }}>Bileşen</th>
                <th style={{ textAlign: 'right', padding: '6px 12px' }}>İsabet %</th>
                <th style={{ textAlign: 'right', padding: '6px 12px' }}>Ort. Getiri</th>
                <th style={{ textAlign: 'right', padding: '6px 12px' }}>Katkı</th>
                <th style={{ textAlign: 'left', padding: '6px 12px' }}>Öneri</th>
              </tr>
            </thead>
            <tbody>
              {r.criteriaComponents.map((c, i) => (
                <tr key={i} style={{ borderBottom: '1px solid rgba(30,45,74,0.5)' }}>
                  <td style={{ padding: '7px 12px', fontWeight: 600 }}>{c.component}</td>
                  <td style={{ padding: '7px 12px', textAlign: 'right', color: c.hitRate >= 55 ? '#00D084' : c.hitRate >= 45 ? '#FFA502' : '#FF4757' }}>{c.hitRate}%</td>
                  <td style={{ padding: '7px 12px', textAlign: 'right', color: c.avgReturnWhenTrue >= 0 ? '#00D084' : '#FF4757' }}>{c.avgReturnWhenTrue >= 0 ? '+' : ''}{c.avgReturnWhenTrue}%</td>
                  <td style={{ padding: '7px 12px', textAlign: 'right', color: 'var(--text-secondary)' }}>{c.contribution.toFixed(2)}</td>
                  <td style={{ padding: '7px 12px', color: 'var(--text-secondary)', fontSize: 11 }}>{c.recommendation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Fixes */}
      <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 10, padding: 16 }}>
        <div style={{ fontWeight: 700, marginBottom: 12 }}>🛠️ Önerilen İyileştirmeler</div>
        {r.summary.topFixes.map((f, i) => (
          <div key={i} style={{ display: 'flex', gap: 12, marginBottom: 12, alignItems: 'flex-start' }}>
            <span style={{ background: `${priorityColor(f.priority)}22`, color: priorityColor(f.priority), borderRadius: 4, padding: '2px 8px', fontSize: 11, fontWeight: 700, minWidth: 60, textAlign: 'center', flexShrink: 0 }}>{f.priority}</span>
            <div>
              <div style={{ fontSize: 13, marginBottom: 3 }}>{f.fix}</div>
              <div style={{ color: '#00D084', fontSize: 12 }}>→ {f.estimatedGain}</div>
            </div>
          </div>
        ))}
      </div>

      <div style={{ textAlign: 'right', color: 'var(--text-secondary)', fontSize: 11 }}>
        Oluşturuldu: {new Date(r.generatedAt).toLocaleString('tr-TR')}
        {' · '}
        <button onClick={run} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: 11 }}>Yenile</button>
      </div>
    </div>
  )
}
