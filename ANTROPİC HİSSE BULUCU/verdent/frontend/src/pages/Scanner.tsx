import { useState, useCallback, useMemo, useEffect } from 'react'
import {
  Search, Download, RefreshCw, ChevronDown, ChevronUp,
  CheckCircle2, AlertCircle, Loader2, BarChart2, Calendar,
  ArrowUpDown, ArrowUp, ArrowDown, Columns2, SlidersHorizontal,
} from 'lucide-react'
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer,
  Tooltip,
} from 'recharts'
import { scannerService, consistencyService } from '../services/api'

// ── Types ─────────────────────────────────────────────────────────────────────

type CriteriaType = 'ALFA' | 'BETA' | 'DELTA'
type MarketType   = 'BIST' | 'US'
type SortDir      = 'asc' | 'desc'

interface SignalDetail {
  name:   string
  passed: boolean
  points: number
  value?: string
}

interface ScoredStock {
  symbol:            string
  name:              string
  score:             number
  rank:              number
  entryPrice:        number
  targetPrice:       number
  suggestedStopLoss: number
  riskRewardRatio:   number
  signals?: {
    technical?:    SignalDetail[]
    fundamental?:  SignalDetail[]
    passed?:       string[]
    failed?:       string[]
  }
}

interface ScanResult {
  criteria:    string
  market:      string
  date:        string
  count:       number
  stocks:      ScoredStock[]
}

interface ConsistencyResult {
  isConsistent:   boolean | null
  message?:       string
  differences:    string[]
  backtestResult: { backtestId: string; backtestName: string; snapshotDate: string; portfolioValue: number } | null
}

// ── Mock data ─────────────────────────────────────────────────────────────────

const MOCK_BIST: ScoredStock[] = [
  { symbol: 'THYAO', name: 'Türk Hava Yolları', score: 94, rank: 1, entryPrice: 285.50, targetPrice: 312.00, suggestedStopLoss: 268.00, riskRewardRatio: 1.52,
    signals: { technical: [
      { name: 'Fiyat > 200 EMA', passed: true,  points: 15, value: '285.5 > 241.2' },
      { name: 'Golden Cross',    passed: true,  points: 10, value: '50 EMA > 200 EMA' },
      { name: 'RSI Optimal',     passed: true,  points: 10, value: 'RSI: 62' },
      { name: 'MACD Boğa',       passed: true,  points: 10, value: 'MACD üst sinyal' },
      { name: 'Hacim Onayı',     passed: true,  points: 10, value: '2.1x ort.' },
      { name: 'ADX Güçlü',       passed: true,  points: 8,  value: 'ADX: 31' },
      { name: '52H Yakın',       passed: true,  points: 7,  value: '%4.2 uzakta' },
    ], fundamental: [
      { name: 'Gelir Büyümesi',  passed: true,  points: 10, value: '+23% YoY' },
      { name: 'EPS Büyümesi',    passed: true,  points: 10, value: '+18% YoY' },
      { name: 'ROE',             passed: true,  points: 5,  value: '28%' },
      { name: 'Serbest Nakit',   passed: true,  points: 5,  value: 'Pozitif' },
      { name: 'Borç/Özkaynak',   passed: false, points: 0,  value: '1.8 (Yüksek)' },
    ]} },
  { symbol: 'EREGL', name: 'Ereğli Demir Çelik', score: 89, rank: 2, entryPrice: 45.20, targetPrice: 51.00, suggestedStopLoss: 42.00, riskRewardRatio: 1.81,
    signals: { technical: [
      { name: 'Fiyat > 200 EMA', passed: true,  points: 15, value: '45.2 > 38.1' },
      { name: 'Golden Cross',    passed: true,  points: 10, value: 'Aktif' },
      { name: 'RSI Optimal',     passed: true,  points: 10, value: 'RSI: 58' },
      { name: 'MACD Boğa',       passed: true,  points: 10, value: 'Aktif' },
      { name: 'Hacim Onayı',     passed: true,  points: 10, value: '1.8x ort.' },
      { name: 'ADX Güçlü',       passed: true,  points: 8,  value: 'ADX: 27' },
      { name: '52H Yakın',       passed: false, points: 0,  value: '%12 uzakta' },
    ], fundamental: [
      { name: 'Gelir Büyümesi',  passed: true,  points: 10, value: '+15% YoY' },
      { name: 'EPS Büyümesi',    passed: true,  points: 10, value: '+11% YoY' },
      { name: 'ROE',             passed: true,  points: 5,  value: '22%' },
      { name: 'Serbest Nakit',   passed: true,  points: 5,  value: 'Pozitif' },
      { name: 'Borç/Özkaynak',   passed: false, points: 0,  value: '0.9' },
    ]} },
  { symbol: 'SISE',  name: 'Şişe Cam',            score: 85, rank: 3, entryPrice: 28.70, targetPrice: 33.00, suggestedStopLoss: 26.50, riskRewardRatio: 1.95, signals: { technical: [], fundamental: [] } },
  { symbol: 'AKBNK', name: 'Akbank',               score: 82, rank: 4, entryPrice: 52.30, targetPrice: 58.00, suggestedStopLoss: 49.00, riskRewardRatio: 1.71, signals: { technical: [], fundamental: [] } },
  { symbol: 'TUPRS', name: 'Tüpraş',               score: 78, rank: 5, entryPrice: 168.20, targetPrice: 190.00, suggestedStopLoss: 158.00, riskRewardRatio: 2.14, signals: { technical: [], fundamental: [] } },
]

const MOCK_US: ScoredStock[] = [
  { symbol: 'JNJ',  name: 'Johnson & Johnson', score: 91, rank: 1, entryPrice: 152.40, targetPrice: 165.00, suggestedStopLoss: 146.00, riskRewardRatio: 1.97, signals: { technical: [], fundamental: [] } },
  { symbol: 'PG',   name: 'Procter & Gamble',  score: 87, rank: 2, entryPrice: 148.20, targetPrice: 158.00, suggestedStopLoss: 143.00, riskRewardRatio: 1.92, signals: { technical: [], fundamental: [] } },
  { symbol: 'KO',   name: 'Coca-Cola',          score: 83, rank: 3, entryPrice: 61.80,  targetPrice: 67.00,  suggestedStopLoss: 59.50,  riskRewardRatio: 2.26, signals: { technical: [], fundamental: [] } },
  { symbol: 'VZ',   name: 'Verizon',            score: 79, rank: 4, entryPrice: 40.20,  targetPrice: 44.00,  suggestedStopLoss: 38.50,  riskRewardRatio: 2.24, signals: { technical: [], fundamental: [] } },
  { symbol: 'MCD',  name: "McDonald's",         score: 76, rank: 5, entryPrice: 285.00, targetPrice: 308.00, suggestedStopLoss: 274.00, riskRewardRatio: 2.09, signals: { technical: [], fundamental: [] } },
]

const MOCK_CONDITION: Record<MarketType, { condition: string; score: number; confidence: number }> = {
  BIST: { condition: 'BULL', score: 5.8, confidence: 78 },
  US:   { condition: 'BEAR', score: -4.1, confidence: 65 },
}

const CONDITION_COLOR: Record<string, string> = {
  BULL: 'var(--green)', BEAR: 'var(--red)', SIDEWAYS: 'var(--yellow)',
}
const CONDITION_EMOJI: Record<string, string> = {
  BULL: '🐂', BEAR: '🐻', SIDEWAYS: '↔',
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function buildRadarData(stock: ScoredStock) {
  const tech = stock.signals?.technical ?? []
  const fund = stock.signals?.fundamental ?? []
  const maxTech = Math.max(...tech.map((s) => s.points), 1)
  const maxFund = Math.max(...fund.map((s) => s.points), 1)

  const techScore = tech.reduce((a, s) => a + (s.passed ? s.points : 0), 0)
  const techMax   = tech.reduce((a, s) => a + s.points, 0) || 1
  const fundScore = fund.reduce((a, s) => a + (s.passed ? s.points : 0), 0)
  const fundMax   = fund.reduce((a, s) => a + s.points, 0) || 1

  void maxTech; void maxFund

  return [
    { subject: 'Trend',     value: Math.round((techScore / techMax) * 100) },
    { subject: 'Momentum',  value: Math.round(stock.score * 0.9) },
    { subject: 'Hacim',     value: Math.round(stock.score * 0.85) },
    { subject: 'Temel',     value: Math.round((fundScore / fundMax) * 100) },
    { subject: 'R/R',       value: Math.min(100, Math.round(stock.riskRewardRatio * 40)) },
  ]
}

function exportToCSV(result: ScanResult) {
  const headers = ['Sıra', 'Sembol', 'Ad', 'Skor', 'Giriş', 'Hedef', 'Stop', 'R/R']
  const lines   = [
    headers.join(','),
    ...result.stocks.map((s) => [
      s.rank, s.symbol, `"${s.name}"`, s.score,
      s.entryPrice, s.targetPrice, s.suggestedStopLoss,
      s.riskRewardRatio.toFixed(2),
    ].join(',')),
  ]
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = `verdent_scan_${result.criteria}_${result.market}_${result.date}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

// ── Sub-components ────────────────────────────────────────────────────────────

function CriteriaBadge({ type }: { type: string }) {
  const MAP: Record<string, { color: string; bg: string }> = {
    ALFA:  { color: 'var(--green)',  bg: 'rgba(0,208,132,0.12)' },
    BETA:  { color: 'var(--red)',    bg: 'rgba(255,77,77,0.12)' },
    DELTA: { color: 'var(--yellow)', bg: 'rgba(245,166,35,0.12)' },
  }
  const m = MAP[type] ?? { color: 'var(--text-muted)', bg: 'var(--bg-hover)' }
  return (
    <span style={{ padding: '2px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: 700, color: m.color, background: m.bg, border: `1px solid ${m.color}40` }}>
      {type}
    </span>
  )
}

function ScoreBar({ score }: { score: number }) {
  const color = score >= 85 ? 'var(--green)' : score >= 70 ? 'var(--yellow)' : 'var(--red)'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <div style={{ width: '64px', height: '6px', background: 'var(--bg-hover)', borderRadius: '3px', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${score}%`, background: color, borderRadius: '3px' }} />
      </div>
      <span style={{ fontWeight: 700, fontSize: '13px', color }}>{score}</span>
    </div>
  )
}

function SignalRow({ sig }: { sig: SignalDetail }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '5px 0', borderBottom: '1px solid rgba(30,45,69,0.35)' }}>
      <span style={{ fontSize: '13px' }}>{sig.passed ? '✅' : '❌'}</span>
      <span style={{ flex: 1, fontSize: '12px', color: sig.passed ? 'var(--text-primary)' : 'var(--text-muted)' }}>{sig.name}</span>
      {sig.value && <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{sig.value}</span>}
      {sig.passed && sig.points > 0 && (
        <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--green)', minWidth: '42px', textAlign: 'right' }}>+{sig.points} pts</span>
      )}
    </div>
  )
}

function ExpandedDetail({ stock }: { stock: ScoredStock }) {
  const tech = stock.signals?.technical ?? []
  const fund = stock.signals?.fundamental ?? []
  const radarData = buildRadarData(stock)
  const rrColor = stock.riskRewardRatio >= 2 ? 'var(--green)' : stock.riskRewardRatio >= 1.5 ? 'var(--yellow)' : 'var(--text-secondary)'

  return (
    <tr>
      <td colSpan={8} style={{ padding: 0 }}>
        <div style={{ padding: '20px 16px 20px 52px', background: 'rgba(0,208,132,0.03)', borderBottom: '1px solid var(--border)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 200px', gap: '20px' }}>
            {/* Technical */}
            <div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', letterSpacing: '1px', marginBottom: '8px', fontWeight: 600 }}>TEKNİK SİNYALLER</div>
              {tech.length > 0 ? tech.map((s, i) => <SignalRow key={i} sig={s} />) : (
                <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: 0 }}>Sinyal verisi mevcut değil</p>
              )}
            </div>
            {/* Fundamental */}
            <div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', letterSpacing: '1px', marginBottom: '8px', fontWeight: 600 }}>TEMEL ANALİZ</div>
              {fund.length > 0 ? fund.map((s, i) => <SignalRow key={i} sig={s} />) : (
                <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: 0 }}>Temel veri mevcut değil</p>
              )}
              {/* Trade levels */}
              <div style={{ marginTop: '14px', padding: '12px 14px', background: 'var(--bg-hover)', borderRadius: '8px', border: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', gap: '16px', marginBottom: '6px', flexWrap: 'wrap' }}>
                  <span style={{ fontSize: '12px' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Giriş: </span>
                    <strong style={{ color: 'var(--text-primary)' }}>{stock.entryPrice.toFixed(2)}</strong>
                  </span>
                  <span style={{ fontSize: '12px' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Hedef: </span>
                    <strong style={{ color: 'var(--green)' }}>{stock.targetPrice.toFixed(2)}</strong>
                  </span>
                  <span style={{ fontSize: '12px' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Stop: </span>
                    <strong style={{ color: 'var(--red)' }}>{stock.suggestedStopLoss.toFixed(2)}</strong>
                  </span>
                </div>
                <div style={{ fontSize: '12px' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Risk/Ödül: </span>
                  <strong style={{ color: rrColor }}>1:{stock.riskRewardRatio.toFixed(2)}</strong>
                </div>
              </div>
            </div>
            {/* Radar */}
            <div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', letterSpacing: '1px', marginBottom: '4px', fontWeight: 600 }}>SKOR DAĞILIMI</div>
              <ResponsiveContainer width="100%" height={160}>
                <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="70%">
                  <PolarGrid stroke="rgba(30,45,69,0.8)" />
                  <PolarAngleAxis dataKey="subject" tick={{ fill: '#8A9BBE', fontSize: 10 }} />
                  <Radar dataKey="value" stroke="#00D084" fill="#00D084" fillOpacity={0.25} strokeWidth={2} />
                  <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '8px', fontSize: '11px' }} />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </td>
    </tr>
  )
}

function CompareView({ stocks }: { stocks: ScoredStock[] }) {
  const metrics: Array<{ label: string; key: keyof ScoredStock; fmt: (v: number) => string; higher: boolean }> = [
    { label: 'Skor',       key: 'score',             fmt: (v) => `${v}/100`,     higher: true },
    { label: 'Giriş',      key: 'entryPrice',         fmt: (v) => v.toFixed(2),   higher: false },
    { label: 'Hedef',      key: 'targetPrice',        fmt: (v) => v.toFixed(2),   higher: true },
    { label: 'Stop',       key: 'suggestedStopLoss',  fmt: (v) => v.toFixed(2),   higher: false },
    { label: 'R/R',        key: 'riskRewardRatio',    fmt: (v) => `${v.toFixed(2)}x`, higher: true },
  ]

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <thead>
          <tr style={{ borderBottom: '1px solid var(--border)' }}>
            <th style={{ padding: '10px 14px', textAlign: 'left', fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600 }}>METRİK</th>
            {stocks.map((s) => (
              <th key={s.symbol} style={{ padding: '10px 14px', textAlign: 'center', fontSize: '13px', fontWeight: 700, color: 'var(--primary)' }}>
                {s.symbol}
                <div style={{ fontSize: '10px', color: 'var(--text-muted)', fontWeight: 400 }}>{s.name}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metrics.map(({ label, key, fmt, higher }) => {
            const vals = stocks.map((s) => s[key] as number)
            const best = higher ? Math.max(...vals) : Math.min(...vals)
            return (
              <tr key={label} style={{ borderBottom: '1px solid rgba(30,45,69,0.4)' }}>
                <td style={{ padding: '10px 14px', fontSize: '12px', color: 'var(--text-muted)', fontWeight: 600 }}>{label}</td>
                {stocks.map((s) => {
                  const v     = s[key] as number
                  const isBest = v === best
                  return (
                    <td key={s.symbol} style={{ padding: '10px 14px', textAlign: 'center', fontWeight: isBest ? 700 : 400, color: isBest ? 'var(--green)' : 'var(--text-primary)' }}>
                      {fmt(v)}
                      {isBest && <span style={{ marginLeft: '4px', fontSize: '10px' }}>★</span>}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── useDebounce hook ──────────────────────────────────────────────────────────

function useDebounce<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState<T>(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(t)
  }, [value, delayMs])
  return debounced
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function Scanner() {
  const [criteria,    setCriteria]    = useState<CriteriaType>('ALFA')
  const [scanDate,    setScanDate]    = useState(() => new Date().toISOString().slice(0, 10))
  const [market,      setMarket]      = useState<MarketType>('BIST')
  const [scanning,    setScanning]    = useState(false)
  const [result,      setResult]      = useState<ScanResult | null>(null)
  const [useMock,     setUseMock]     = useState(false)
  const [expandedRow, setExpandedRow] = useState<string | null>(null)
  const [viewMode,    setViewMode]    = useState<'list' | 'compare'>('list')
  const [minScore,    setMinScore]    = useState(0)
  const [sortBy,      setSortBy]      = useState<'rank' | 'score' | 'riskRewardRatio'>('rank')
  const [sortDir,     setSortDir]     = useState<SortDir>('asc')
  const [consistency, setConsistency] = useState<ConsistencyResult | null>(null)
  const [checkingCons, setCheckingCons] = useState(false)

  const conditionInfo = useMock ? MOCK_CONDITION[market] : null

  // Debounce the min-score slider so filtering doesn't re-run on every keypress
  const debouncedMinScore = useDebounce(minScore, 200)

  const handleSort = (col: typeof sortBy) => {
    if (sortBy === col) setSortDir((d) => d === 'asc' ? 'desc' : 'asc')
    else { setSortBy(col); setSortDir('desc') }
  }

  const SortIcon = ({ col }: { col: typeof sortBy }) =>
    sortBy !== col ? <ArrowUpDown size={12} style={{ opacity: 0.4 }} /> :
    sortDir === 'asc' ? <ArrowUp size={12} style={{ color: 'var(--primary)' }} /> :
    <ArrowDown size={12} style={{ color: 'var(--primary)' }} />

  const checkConsistency = useCallback(async (crit: string, date: string, mkt: string) => {
    try {
      setCheckingCons(true)
      const res = await consistencyService.check({ criteria: crit, date, market: mkt })
      setConsistency(res.data as ConsistencyResult)
    } catch {
      setConsistency({ isConsistent: null, message: 'Tutarlılık kontrolü yapılamadı', differences: [], backtestResult: null })
    } finally {
      setCheckingCons(false)
    }
  }, [])

  const runScan = async () => {
    setScanning(true)
    setResult(null)
    setConsistency(null)
    setExpandedRow(null)

    try {
      const res    = await scannerService.scan({ criteria, date: scanDate, market })
      const stocks = (res.data?.stocks ?? []) as ScoredStock[]
      setResult({ criteria, market, date: scanDate, count: res.data?.count ?? stocks.length, stocks })
      setUseMock(false)
    } catch {
      const mockStocks = market === 'BIST' ? MOCK_BIST : MOCK_US
      setResult({ criteria, market, date: scanDate, count: mockStocks.length, stocks: mockStocks })
      setUseMock(true)
    } finally {
      setScanning(false)
    }

    await checkConsistency(criteria, scanDate, market)
  }

  // Memoised — only recalculates when stocks, sort config, or debounced score changes
  const displayedStocks = useMemo(
    () =>
      (result?.stocks ?? [])
        .filter((s) => s.score >= debouncedMinScore)
        .slice()
        .sort((a, b) => {
          const av = a[sortBy] as number
          const bv = b[sortBy] as number
          return sortDir === 'asc' ? av - bv : bv - av
        }),
    [result, debouncedMinScore, sortBy, sortDir],
  )

  const inputStyle = {
    width: '100%', padding: '9px 12px', background: 'var(--bg-hover)',
    border: '1px solid var(--border)', borderRadius: '8px', color: 'var(--text-primary)',
    fontSize: '13px', outline: 'none', colorScheme: 'dark' as const,
  }
  const labelStyle = {
    display: 'block' as const, fontSize: '11px', color: 'var(--text-muted)',
    marginBottom: '6px', letterSpacing: '0.5px', textTransform: 'uppercase' as const,
  }

  const criteriaOptions: CriteriaType[] = ['ALFA', 'BETA', 'DELTA']
  const CRITERIA_COLOR: Record<CriteriaType, string> = {
    ALFA: 'var(--green)', BETA: 'var(--red)', DELTA: 'var(--yellow)',
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* ── Header ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '24px', fontWeight: 700 }}>Hisse Tarama</h1>
          <p style={{ margin: '4px 0 0', fontSize: '13px', color: 'var(--text-secondary)' }}>
            ALFA / BETA / DELTA kriterleri ile hisse tarayın — geçmiş tarihler backtest ile tutarlıdır
          </p>
        </div>
        {result && (
          <button
            onClick={() => exportToCSV(result)}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 14px', background: 'var(--bg-hover)', border: '1px solid var(--border)', borderRadius: '8px', cursor: 'pointer', color: 'var(--text-secondary)', fontSize: '13px' }}
          >
            <Download size={14} /> CSV İndir
          </button>
        )}
      </div>

      {/* ── Config panel ── */}
      <div className="card" style={{ padding: '24px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: '20px', alignItems: 'end' }}>
          {/* Criteria */}
          <div>
            <label style={labelStyle}>Kriter Türü</label>
            <div style={{ display: 'flex', gap: '6px' }}>
              {criteriaOptions.map((c) => {
                const active = criteria === c
                const color  = CRITERIA_COLOR[c]
                return (
                  <button key={c} onClick={() => setCriteria(c)} style={{
                    flex: 1, padding: '9px 4px', borderRadius: '8px', border: `1px solid ${active ? color + '60' : 'var(--border)'}`,
                    background: active ? `${color}12` : 'var(--bg-hover)', cursor: 'pointer',
                    fontWeight: active ? 700 : 500, fontSize: '13px',
                    color: active ? color : 'var(--text-secondary)', transition: 'all 0.15s',
                  }}>{c}</button>
                )
              })}
            </div>
          </div>

          {/* Date */}
          <div>
            <label style={labelStyle}><Calendar size={11} style={{ display: 'inline', marginRight: '4px' }} />Tarama Tarihi</label>
            <input type="date" style={inputStyle} value={scanDate} onChange={(e) => setScanDate(e.target.value)} />
          </div>

          {/* Market */}
          <div>
            <label style={labelStyle}>Piyasa</label>
            <div style={{ display: 'flex', gap: '6px' }}>
              {(['BIST', 'US'] as MarketType[]).map((m) => {
                const active = market === m
                return (
                  <button key={m} onClick={() => setMarket(m)} style={{
                    flex: 1, padding: '9px 4px', borderRadius: '8px', border: `1px solid ${active ? 'var(--primary)60' : 'var(--border)'}`,
                    background: active ? 'rgba(0,208,132,0.1)' : 'var(--bg-hover)', cursor: 'pointer',
                    fontWeight: active ? 700 : 500, fontSize: '13px',
                    color: active ? 'var(--primary)' : 'var(--text-secondary)', transition: 'all 0.15s',
                  }}>{m === 'BIST' ? '🇹🇷 BIST' : '🇺🇸 US'}</button>
                )
              })}
            </div>
          </div>

          {/* Run button */}
          <button
            className="btn-primary"
            onClick={runScan}
            disabled={scanning}
            style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 24px', opacity: scanning ? 0.7 : 1, whiteSpace: 'nowrap' }}
          >
            {scanning ? <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> : <Search size={16} />}
            {scanning ? 'Taranıyor...' : 'Taramayı Başlat'}
          </button>
        </div>

        <div style={{ marginTop: '14px', padding: '10px 14px', borderRadius: '8px', background: 'rgba(77,159,255,0.07)', border: '1px solid rgba(77,159,255,0.2)', fontSize: '12px', color: 'var(--blue)', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <AlertCircle size={13} />
          Geçmiş tarihler için sonuçlar, aynı kriter/tarih kombinasyonundaki backtest ile tutarlıdır.
        </div>
      </div>

      {/* ── Consistency badge ── */}
      {(checkingCons || consistency) && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: '10px', padding: '12px 16px', borderRadius: '10px',
          background: consistency?.isConsistent === true  ? 'rgba(0,208,132,0.08)' :
                      consistency?.isConsistent === false ? 'rgba(255,77,77,0.08)' : 'rgba(77,159,255,0.08)',
          border: `1px solid ${consistency?.isConsistent === true ? 'rgba(0,208,132,0.25)' : consistency?.isConsistent === false ? 'rgba(255,77,77,0.25)' : 'rgba(77,159,255,0.25)'}`,
        }}>
          {checkingCons ? (
            <><Loader2 size={14} style={{ color: 'var(--blue)', animation: 'spin 1s linear infinite' }} />
            <span style={{ fontSize: '13px', color: 'var(--blue)' }}>Backtest tutarlılığı kontrol ediliyor...</span></>
          ) : consistency?.isConsistent === true ? (
            <><CheckCircle2 size={16} color="var(--green)" />
            <span style={{ fontSize: '13px', color: 'var(--green)', fontWeight: 600 }}>✅ Backtest Tutarlı</span>
            {consistency.backtestResult && <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>— {consistency.backtestResult.backtestName}</span>}</>
          ) : consistency?.isConsistent === false ? (
            <><AlertCircle size={16} color="var(--red)" />
            <span style={{ fontSize: '13px', color: 'var(--red)', fontWeight: 600 }}>⚠️ Tutarsızlık Tespit Edildi</span>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{consistency.differences.join(' · ')}</span></>
          ) : (
            <><AlertCircle size={14} color="var(--yellow)" />
            <span style={{ fontSize: '13px', color: 'var(--yellow)' }}>{consistency?.message ?? 'Eşleşen backtest bulunamadı'}</span></>
          )}
        </div>
      )}

      {/* ── Mock notice ── */}
      {useMock && result && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 14px', borderRadius: '8px', background: 'rgba(245,166,35,0.08)', border: '1px solid rgba(245,166,35,0.2)', fontSize: '13px', color: 'var(--yellow)' }}>
          <AlertCircle size={14} /> API bağlantısı yok — örnek veriler gösteriliyor
        </div>
      )}

      {/* ── Results ── */}
      {result && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Results header bar */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
              <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700 }}>
                Tarama Sonuçları
              </h3>
              <CriteriaBadge type={result.criteria} />
              <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{result.date} · {result.market}</span>
              {conditionInfo && (
                <span style={{ fontSize: '12px', fontWeight: 600, color: CONDITION_COLOR[conditionInfo.condition] }}>
                  {CONDITION_EMOJI[conditionInfo.condition]} {conditionInfo.condition} (Skor: {conditionInfo.score > 0 ? '+' : ''}{conditionInfo.score})
                </span>
              )}
            </div>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              {/* Score filter */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '6px 10px', background: 'var(--bg-hover)', border: '1px solid var(--border)', borderRadius: '8px' }}>
                <SlidersHorizontal size={13} color="var(--text-muted)" />
                <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Min skor:</span>
                <input
                  type="number" min={0} max={100} step={5} value={minScore}
                  onChange={(e) => setMinScore(+e.target.value)}
                  style={{ width: '44px', background: 'none', border: 'none', outline: 'none', color: 'var(--text-primary)', fontSize: '12px', fontWeight: 600 }}
                />
              </div>
              {/* View toggle */}
              <button
                onClick={() => setViewMode(viewMode === 'list' ? 'compare' : 'list')}
                style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '7px 12px', background: viewMode === 'compare' ? 'rgba(0,208,132,0.1)' : 'var(--bg-hover)', border: `1px solid ${viewMode === 'compare' ? 'rgba(0,208,132,0.3)' : 'var(--border)'}`, borderRadius: '8px', cursor: 'pointer', color: viewMode === 'compare' ? 'var(--primary)' : 'var(--text-secondary)', fontSize: '12px' }}
              >
                <Columns2 size={13} /> Karşılaştır
              </button>
              <button
                onClick={() => { setResult(null); setConsistency(null) }}
                style={{ display: 'flex', alignItems: 'center', gap: '5px', padding: '7px 12px', background: 'var(--bg-hover)', border: '1px solid var(--border)', borderRadius: '8px', cursor: 'pointer', color: 'var(--text-secondary)', fontSize: '12px' }}
              >
                <RefreshCw size={12} /> Temizle
              </button>
            </div>
          </div>

          {/* Stats row */}
          <div style={{ display: 'flex', gap: '12px' }}>
            {[
              { label: 'Taranan',   value: '500+', color: 'var(--text-secondary)' },
              { label: 'Geçen',     value: String(result.count),              color: 'var(--yellow)' },
              { label: 'Gösterilen', value: String(displayedStocks.length),   color: 'var(--primary)' },
            ].map(({ label, value, color }) => (
              <div key={label} style={{ padding: '8px 16px', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <BarChart2 size={13} color="var(--text-muted)" />
                <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{label}:</span>
                <span style={{ fontSize: '14px', fontWeight: 700, color }}>{value}</span>
              </div>
            ))}
          </div>

          {/* Compare view */}
          {viewMode === 'compare' && (
            <div className="card" style={{ padding: '20px' }}>
              <h4 style={{ margin: '0 0 14px', fontSize: '13px', color: 'var(--text-secondary)', letterSpacing: '1px' }}>KARŞILAŞTIRMA GÖRÜNÜMÜ — İlk 5 Hisse</h4>
              <CompareView stocks={displayedStocks.slice(0, 5)} />
            </div>
          )}

          {/* List view */}
          {viewMode === 'list' && (
            <div className="card" style={{ padding: '20px' }}>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border)' }}>
                      {[
                        { label: 'Sıra', col: 'rank'            as const },
                        { label: 'Sembol', col: null },
                        { label: 'Skor',   col: 'score'          as const },
                        { label: 'Giriş Fiyatı', col: null },
                        { label: 'Hedef', col: null },
                        { label: 'Stop', col: null },
                        { label: 'R/R',   col: 'riskRewardRatio' as const },
                        { label: 'Detay', col: null },
                      ].map(({ label, col }) => (
                        <th
                          key={label}
                          onClick={col ? () => handleSort(col) : undefined}
                          style={{ padding: '8px 12px', textAlign: 'left', fontSize: '11px', color: col && sortBy === col ? 'var(--primary)' : 'var(--text-muted)', fontWeight: 600, letterSpacing: '0.5px', whiteSpace: 'nowrap', cursor: col ? 'pointer' : 'default', userSelect: 'none' }}
                        >
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                            {label}
                            {col && <SortIcon col={col} />}
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {displayedStocks.map((s) => {
                      const expanded = expandedRow === s.symbol
                      const rrColor  = s.riskRewardRatio >= 2 ? 'var(--green)' : s.riskRewardRatio >= 1.5 ? 'var(--yellow)' : 'var(--text-secondary)'

                      return (
                        <>
                          <tr
                            key={s.symbol}
                            style={{ borderBottom: expanded ? 'none' : '1px solid rgba(30,45,69,0.4)', background: expanded ? 'rgba(0,208,132,0.04)' : 'transparent', transition: 'background 0.1s', cursor: 'default' }}
                            onMouseEnter={(e) => { if (!expanded) e.currentTarget.style.background = 'var(--bg-hover)' }}
                            onMouseLeave={(e) => { if (!expanded) e.currentTarget.style.background = 'transparent' }}
                          >
                            <td style={{ padding: '12px' }}>
                              <div style={{ width: '24px', height: '24px', borderRadius: '50%', background: s.rank === 1 ? 'var(--primary)' : s.rank <= 3 ? 'rgba(0,208,132,0.2)' : 'var(--bg-hover)', color: s.rank === 1 ? '#000' : 'var(--text-secondary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '11px', fontWeight: 700, margin: '0 auto' }}>{s.rank}</div>
                            </td>
                            <td style={{ padding: '12px' }}>
                              <div style={{ fontWeight: 700, fontSize: '14px' }}>{s.symbol}</div>
                              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '1px' }}>{s.name}</div>
                            </td>
                            <td style={{ padding: '12px' }}><ScoreBar score={s.score} /></td>
                            <td style={{ padding: '12px', fontWeight: 600 }}>{s.entryPrice.toFixed(2)}</td>
                            <td style={{ padding: '12px', color: 'var(--green)', fontWeight: 600 }}>{s.targetPrice.toFixed(2)}</td>
                            <td style={{ padding: '12px', color: 'var(--red)', fontWeight: 600 }}>{s.suggestedStopLoss.toFixed(2)}</td>
                            <td style={{ padding: '12px' }}>
                              <span style={{ fontSize: '12px', fontWeight: 700, color: rrColor, background: `${rrColor}18`, padding: '2px 8px', borderRadius: '20px' }}>{s.riskRewardRatio.toFixed(2)}x</span>
                            </td>
                            <td style={{ padding: '12px' }}>
                              <button
                                onClick={() => setExpandedRow(expanded ? null : s.symbol)}
                                style={{ display: 'flex', alignItems: 'center', gap: '4px', padding: '5px 10px', background: expanded ? 'rgba(0,208,132,0.1)' : 'var(--bg-hover)', border: `1px solid ${expanded ? 'rgba(0,208,132,0.3)' : 'var(--border)'}`, borderRadius: '6px', cursor: 'pointer', color: expanded ? 'var(--primary)' : 'var(--text-secondary)', fontSize: '12px', transition: 'all 0.15s' }}
                              >
                                Detay {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                              </button>
                            </td>
                          </tr>
                          {expanded && <ExpandedDetail key={`${s.symbol}-detail`} stock={s} />}
                        </>
                      )
                    })}
                    {displayedStocks.length === 0 && (
                      <tr>
                        <td colSpan={8} style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
                          <Search size={28} style={{ opacity: 0.3, margin: '0 auto 10px', display: 'block' }} />
                          Min skor filtresi sonuçları gizliyor. Filtreyi düşürün.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Empty state */}
      {!result && !scanning && (
        <div style={{ textAlign: 'center', padding: '64px 0', color: 'var(--text-muted)' }}>
          <Search size={40} style={{ opacity: 0.2, margin: '0 auto 16px', display: 'block' }} />
          <p style={{ margin: '0 0 4px', fontSize: '16px', color: 'var(--text-secondary)' }}>Taramaya hazır</p>
          <p style={{ margin: 0, fontSize: '13px' }}>Kriter ve tarih seçin, ardından taramayı başlatın.</p>
        </div>
      )}

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}
