import { useEffect, useRef, useState, useCallback } from 'react'
import {
  TrendingUp, TrendingDown, Minus, RefreshCw, Clock,
  ArrowUp, ArrowDown, Target, Shield, Zap,
  ChevronRight, AlertCircle,
} from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from 'recharts'
import { marketService, scannerService } from '../services/api'

// ── Types ─────────────────────────────────────────────────────────────────────

type Condition = 'BULL' | 'BEAR' | 'SIDEWAYS'
type Criteria  = 'ALFA' | 'BETA' | 'DELTA'
type MarketKey = 'BIST' | 'US'

interface IndicatorGroup {
  score: number
  details: Record<string, unknown>
}

interface MarketConditionData {
  condition:            Condition
  score:                number
  confidence:           number
  recommendedCriteria:  Criteria
  date:                 string
  market:               string
  indicators?: {
    trend?:      IndicatorGroup
    momentum?:   IndicatorGroup
    volatility?: IndicatorGroup
    breadth?:    IndicatorGroup
  }
}

interface ScoredStock {
  symbol:          string
  name:            string
  score:           number
  rank:            number
  entryPrice:      number
  targetPrice:     number
  suggestedStopLoss: number
  riskRewardRatio: number
  signals?: {
    passed?: string[]
    failed?: string[]
  }
}

// ── Mock fallback data ─────────────────────────────────────────────────────────

const MOCK_CONDITIONS: Record<MarketKey, MarketConditionData> = {
  BIST: {
    condition: 'BULL', score: 6.2, confidence: 78,
    recommendedCriteria: 'ALFA', date: new Date().toISOString(), market: 'BIST',
    indicators: {
      trend:      { score: 7.5, details: {} },
      momentum:   { score: 6.0, details: {} },
      volatility: { score: 5.5, details: {} },
      breadth:    { score: 4.0, details: {} },
    },
  },
  US: {
    condition: 'BEAR', score: -4.1, confidence: 65,
    recommendedCriteria: 'BETA', date: new Date().toISOString(), market: 'US',
    indicators: {
      trend:      { score: -6.0, details: {} },
      momentum:   { score: -3.5, details: {} },
      volatility: { score: -2.0, details: {} },
      breadth:    { score: -1.5, details: {} },
    },
  },
}

const MOCK_STOCKS: Record<MarketKey, ScoredStock[]> = {
  BIST: [
    { symbol: 'THYAO', name: 'Türk Hava Yolları', score: 94, rank: 1, entryPrice: 285.5, targetPrice: 312.0, suggestedStopLoss: 268.0, riskRewardRatio: 1.52 },
    { symbol: 'EREGL', name: 'Ereğli Demir Çelik', score: 89, rank: 2, entryPrice: 45.2, targetPrice: 51.0, suggestedStopLoss: 42.0, riskRewardRatio: 1.81 },
    { symbol: 'SISE',  name: 'Şişe Cam', score: 85, rank: 3, entryPrice: 28.7, targetPrice: 33.0, suggestedStopLoss: 26.5, riskRewardRatio: 1.95 },
    { symbol: 'AKBNK', name: 'Akbank', score: 82, rank: 4, entryPrice: 52.3, targetPrice: 58.0, suggestedStopLoss: 49.0, riskRewardRatio: 1.71 },
    { symbol: 'TUPRS', name: 'Tüpraş', score: 78, rank: 5, entryPrice: 168.2, targetPrice: 190.0, suggestedStopLoss: 158.0, riskRewardRatio: 2.14 },
  ],
  US: [
    { symbol: 'JNJ',  name: 'Johnson & Johnson', score: 91, rank: 1, entryPrice: 152.4, targetPrice: 165.0, suggestedStopLoss: 146.0, riskRewardRatio: 1.97 },
    { symbol: 'PG',   name: 'Procter & Gamble', score: 87, rank: 2, entryPrice: 148.2, targetPrice: 158.0, suggestedStopLoss: 143.0, riskRewardRatio: 1.92 },
    { symbol: 'KO',   name: 'Coca-Cola', score: 83, rank: 3, entryPrice: 61.8, targetPrice: 67.0, suggestedStopLoss: 59.5, riskRewardRatio: 2.26 },
    { symbol: 'VZ',   name: 'Verizon', score: 79, rank: 4, entryPrice: 40.2, targetPrice: 44.0, suggestedStopLoss: 38.5, riskRewardRatio: 2.24 },
    { symbol: 'MCD',  name: "McDonald's", score: 76, rank: 5, entryPrice: 285.0, targetPrice: 308.0, suggestedStopLoss: 274.0, riskRewardRatio: 2.09 },
  ],
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const CONDITION_CONFIG = {
  BULL: {
    label: 'BOĞA PİYASASI', emoji: '🐂',
    bg: 'rgba(0,208,132,0.08)', border: 'rgba(0,208,132,0.25)',
    color: 'var(--green)', icon: ArrowUp,
  },
  BEAR: {
    label: 'AYI PİYASASI', emoji: '🐻',
    bg: 'rgba(255,77,77,0.08)', border: 'rgba(255,77,77,0.25)',
    color: 'var(--red)', icon: ArrowDown,
  },
  SIDEWAYS: {
    label: 'YATAY PİYASA', emoji: '↔',
    bg: 'rgba(245,166,35,0.08)', border: 'rgba(245,166,35,0.25)',
    color: 'var(--yellow)', icon: Minus,
  },
}

const CRITERIA_CONFIG = {
  ALFA: {
    label: 'ALFA KRİTERİ', desc: 'Boğa Piyasası — Momentum/Büyüme',
    color: 'var(--green)', bg: 'rgba(0,208,132,0.08)', icon: Zap,
  },
  BETA: {
    label: 'BETA KRİTERİ', desc: 'Ayı Piyasası — Savunmacı/Değer',
    color: 'var(--red)', bg: 'rgba(255,77,77,0.08)', icon: Shield,
  },
  DELTA: {
    label: 'DELTA KRİTERİ', desc: 'Yatay Piyasa — Mean Reversion',
    color: 'var(--yellow)', bg: 'rgba(245,166,35,0.08)', icon: Target,
  },
}

function fmt(n: number, decimals = 1) {
  return n.toFixed(decimals)
}

function isMarketHours(): boolean {
  const now = new Date()
  const h   = now.getUTCHours()
  return h >= 14 && h < 21
}

// ── Sub-components ────────────────────────────────────────────────────────────

function ConditionGauge({ score }: { score: number }) {
  const pct    = ((score + 10) / 20) * 100
  const clamp  = Math.max(0, Math.min(100, pct))
  const color  = score > 3 ? 'var(--green)' : score < -3 ? 'var(--red)' : 'var(--yellow)'

  return (
    <div style={{ padding: '0 4px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px', fontSize: '10px', color: 'var(--text-muted)' }}>
        <span>-10 AYI</span>
        <span style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>Skor: {score > 0 ? '+' : ''}{fmt(score)}</span>
        <span>BOĞA +10</span>
      </div>
      <div style={{ position: 'relative', height: '8px', background: 'var(--bg-hover)', borderRadius: '4px', overflow: 'visible' }}>
        <div style={{
          position: 'absolute', left: 0, top: 0, bottom: 0,
          width: `${clamp}%`, borderRadius: '4px',
          background: `linear-gradient(90deg, var(--red), var(--yellow), var(--green))`,
          transition: 'width 0.6s ease',
        }} />
        <div style={{
          position: 'absolute', top: '-4px',
          left: `calc(${clamp}% - 8px)`,
          width: '16px', height: '16px',
          borderRadius: '50%', background: color,
          border: '2px solid var(--bg-card)',
          boxShadow: `0 0 8px ${color}`,
          transition: 'left 0.6s ease',
        }} />
      </div>
    </div>
  )
}

function MarketConditionCard({ data, market }: { data: MarketConditionData; market: MarketKey }) {
  const cfg   = CONDITION_CONFIG[data.condition]
  const Icon  = cfg.icon
  const pulse = data.condition === 'BULL'

  return (
    <div style={{
      background: cfg.bg,
      border: `1px solid ${cfg.border}`,
      borderRadius: '12px',
      padding: '20px',
      flex: 1,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
        <div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', letterSpacing: '1px', marginBottom: '4px' }}>
            {market === 'BIST' ? 'BIST 100' : 'S&P 500 / US'}
          </div>
          <div style={{ fontSize: '20px', fontWeight: 700, color: cfg.color, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span>{cfg.emoji}</span>
            <span>{data.condition}</span>
          </div>
        </div>
        <div style={{
          width: '40px', height: '40px', borderRadius: '10px',
          background: `${cfg.color}22`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          position: 'relative',
        }}>
          <Icon size={20} color={cfg.color} />
          {pulse && (
            <span style={{
              position: 'absolute', inset: 0, borderRadius: '10px',
              border: `2px solid ${cfg.color}`,
              animation: 'ping 1.5s cubic-bezier(0,0,0.2,1) infinite',
            }} />
          )}
        </div>
      </div>

      <ConditionGauge score={data.score} />

      <div style={{ display: 'flex', gap: '12px', marginTop: '14px' }}>
        <div style={{ flex: 1, background: 'rgba(0,0,0,0.2)', borderRadius: '8px', padding: '8px 10px', textAlign: 'center' }}>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '2px' }}>SKOR</div>
          <div style={{ fontSize: '16px', fontWeight: 700, color: cfg.color }}>
            {data.score > 0 ? '+' : ''}{fmt(data.score)}
          </div>
        </div>
        <div style={{ flex: 1, background: 'rgba(0,0,0,0.2)', borderRadius: '8px', padding: '8px 10px', textAlign: 'center' }}>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '2px' }}>GÜVENİLİRLİK</div>
          <div style={{ fontSize: '16px', fontWeight: 700, color: 'var(--text-primary)' }}>
            {fmt(data.confidence, 0)}%
          </div>
        </div>
      </div>
    </div>
  )
}

function CriteriaRecommendation({ recommended, active }: { recommended: Criteria; active: boolean }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {(Object.keys(CRITERIA_CONFIG) as Criteria[]).map((key) => {
        const cfg    = CRITERIA_CONFIG[key]
        const isRec  = key === recommended
        const Icon   = cfg.icon

        return (
          <div key={key} style={{
            border: `1px solid ${isRec ? cfg.color + '60' : 'var(--border)'}`,
            borderRadius: '10px',
            padding: '12px 14px',
            background: isRec ? cfg.bg : 'transparent',
            opacity: !active && !isRec ? 0.45 : 1,
            transition: 'all 0.2s ease',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{
                width: '32px', height: '32px', borderRadius: '8px',
                background: isRec ? `${cfg.color}22` : 'var(--bg-hover)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Icon size={16} color={isRec ? cfg.color : 'var(--text-muted)'} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: '13px', fontWeight: 600, color: isRec ? cfg.color : 'var(--text-secondary)' }}>
                  {cfg.label}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{cfg.desc}</div>
              </div>
              {isRec && (
                <div style={{
                  fontSize: '10px', fontWeight: 700, padding: '2px 8px',
                  borderRadius: '20px', background: cfg.color, color: '#000',
                }}>AKTİF</div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function MarketIndicatorsPanel({ data }: { data: MarketConditionData }) {
  const indicators = data.indicators ?? {}

  const groups = [
    { key: 'trend',      label: 'Trend',     weight: '40%' },
    { key: 'momentum',   label: 'Momentum',  weight: '30%' },
    { key: 'volatility', label: 'Volatilite', weight: '20%' },
    { key: 'breadth',    label: 'Genişlik',  weight: '10%' },
  ] as const

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
      {groups.map(({ key, label, weight }) => {
        const grp   = indicators[key]
        const score = grp?.score ?? 0
        const color = score > 2 ? 'var(--green)' : score < -2 ? 'var(--red)' : 'var(--yellow)'
        const pct   = Math.max(0, Math.min(100, ((score + 10) / 20) * 100))

        return (
          <div key={key} className="card" style={{ padding: '14px 16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600 }}>{label}</span>
              <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Ağırlık: {weight}</span>
            </div>
            <div style={{ fontSize: '22px', fontWeight: 700, color, marginBottom: '8px' }}>
              {score > 0 ? '+' : ''}{fmt(score)}
            </div>
            <div style={{ height: '4px', background: 'var(--bg-hover)', borderRadius: '2px', overflow: 'hidden' }}>
              <div style={{
                height: '100%', width: `${pct}%`, borderRadius: '2px',
                background: color, transition: 'width 0.5s ease',
              }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function TopStocksTable({ stocks, loading }: { stocks: ScoredStock[]; loading: boolean }) {
  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} style={{
            height: '52px', borderRadius: '8px',
            background: 'var(--bg-hover)',
            animation: 'pulse 1.5s ease-in-out infinite',
          }} />
        ))}
      </div>
    )
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <thead>
          <tr style={{ borderBottom: '1px solid var(--border)' }}>
            {['#', 'Sembol', 'Skor', 'Giriş Fiyatı', 'Hedef', 'Stop Loss', 'R/R'].map((h) => (
              <th key={h} style={{
                padding: '8px 12px', textAlign: h === '#' ? 'center' : 'left',
                fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600,
                letterSpacing: '0.5px', whiteSpace: 'nowrap',
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {stocks.map((s) => {
            const rr    = s.riskRewardRatio
            const rrClr = rr >= 2 ? 'var(--green)' : rr >= 1.5 ? 'var(--yellow)' : 'var(--text-secondary)'

            return (
              <tr key={s.symbol} style={{
                borderBottom: '1px solid rgba(30,45,69,0.5)',
                transition: 'background 0.1s ease',
                cursor: 'default',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-hover)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                <td style={{ padding: '12px', textAlign: 'center' }}>
                  <div style={{
                    width: '24px', height: '24px', borderRadius: '50%',
                    background: s.rank === 1 ? 'var(--primary)' : 'var(--bg-hover)',
                    color: s.rank === 1 ? '#000' : 'var(--text-secondary)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: '11px', fontWeight: 700, margin: '0 auto',
                  }}>{s.rank}</div>
                </td>
                <td style={{ padding: '12px 12px 12px 8px' }}>
                  <div style={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: '14px' }}>{s.symbol}</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '1px' }}>{s.name}</div>
                </td>
                <td style={{ padding: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{
                      height: '6px', width: '60px', background: 'var(--bg-hover)',
                      borderRadius: '3px', overflow: 'hidden',
                    }}>
                      <div style={{
                        height: '100%', width: `${s.score}%`,
                        background: `linear-gradient(90deg, var(--primary), var(--primary-light))`,
                        borderRadius: '3px',
                      }} />
                    </div>
                    <span style={{ fontWeight: 600, color: 'var(--primary)', fontSize: '13px' }}>{s.score}</span>
                  </div>
                </td>
                <td style={{ padding: '12px', fontWeight: 600 }}>{s.entryPrice.toFixed(2)}</td>
                <td style={{ padding: '12px', color: 'var(--green)', fontWeight: 600 }}>{s.targetPrice.toFixed(2)}</td>
                <td style={{ padding: '12px', color: 'var(--red)', fontWeight: 600 }}>{s.suggestedStopLoss.toFixed(2)}</td>
                <td style={{ padding: '12px' }}>
                  <span style={{
                    fontSize: '12px', fontWeight: 700, color: rrClr,
                    background: `${rrClr}18`, padding: '2px 8px', borderRadius: '20px',
                  }}>{fmt(rr)}x</span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function MiniTrendChart({ market, condition }: { market: MarketKey; condition: Condition }) {
  const color    = condition === 'BULL' ? '#00D084' : condition === 'BEAR' ? '#FF4D4D' : '#F5A623'
  const baseVal  = market === 'BIST' ? 8500 : 4800
  const trend    = condition === 'BULL' ? 1 : condition === 'BEAR' ? -1 : 0

  const data = Array.from({ length: 30 }, (_, i) => ({
    d: i,
    v: baseVal + trend * i * 15 + (Math.random() - 0.5) * 80,
  }))

  return (
    <ResponsiveContainer width="100%" height={80}>
      <AreaChart data={data} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id={`trendGrad-${market}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor={color} stopOpacity={0.3} />
            <stop offset="95%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area
          type="monotone" dataKey="v"
          stroke={color} strokeWidth={2}
          fill={`url(#trendGrad-${market})`}
          dot={false} activeDot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

// ── Market Tab Panel ──────────────────────────────────────────────────────────

function MarketPanel({ market, onScanCriteriaChange }: {
  market: MarketKey
  onScanCriteriaChange?: (c: Criteria) => void
}) {
  const [condData,   setCondData]   = useState<MarketConditionData | null>(null)
  const [stockData,  setStockData]  = useState<ScoredStock[]>([])
  const [loading,    setLoading]    = useState(true)
  const [stockLoad,  setStockLoad]  = useState(true)
  const [error,      setError]      = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchCondition = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const res  = await marketService.getCondition(market)
      const data = res.data as MarketConditionData
      setCondData(data)
      setLastUpdate(new Date())
      onScanCriteriaChange?.(data.recommendedCriteria)
    } catch {
      setCondData(MOCK_CONDITIONS[market])
      setLastUpdate(new Date())
      setError('Canlı veri alınamadı — örnek veri gösteriliyor')
      onScanCriteriaChange?.(MOCK_CONDITIONS[market].recommendedCriteria)
    } finally {
      setLoading(false)
    }
  }, [market, onScanCriteriaChange])

  const fetchStocks = useCallback(async (criteria: Criteria) => {
    try {
      setStockLoad(true)
      const res  = await scannerService.scan({ criteria, market })
      const list = (res.data?.stocks ?? []) as ScoredStock[]
      setStockData(list.slice(0, 5))
    } catch {
      setStockData(MOCK_STOCKS[market])
    } finally {
      setStockLoad(false)
    }
  }, [market])

  useEffect(() => {
    fetchCondition()
  }, [fetchCondition])

  useEffect(() => {
    if (!condData) return
    fetchStocks(condData.recommendedCriteria)
  }, [condData, fetchStocks])

  useEffect(() => {
    if (!isMarketHours()) return
    timerRef.current = setInterval(fetchCondition, 5 * 60 * 1000)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [fetchCondition])

  const data = condData ?? MOCK_CONDITIONS[market]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {error && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: '8px',
          padding: '10px 14px', borderRadius: '8px',
          background: 'rgba(245,166,35,0.1)', border: '1px solid rgba(245,166,35,0.25)',
          fontSize: '13px', color: 'var(--yellow)',
        }}>
          <AlertCircle size={15} />
          {error}
        </div>
      )}

      {/* Condition + Criteria row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        {/* Left: condition card + mini chart */}
        <div className="card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ margin: 0, fontSize: '13px', color: 'var(--text-secondary)', letterSpacing: '1px' }}>
              PİYASA KOŞULU
            </h3>
            <button
              onClick={fetchCondition}
              disabled={loading}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: 'var(--text-muted)', padding: '4px',
                opacity: loading ? 0.5 : 1,
              }}
            >
              <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
            </button>
          </div>

          <MarketConditionCard data={data} market={market} />
          <MiniTrendChart market={market} condition={data.condition} />

          {lastUpdate && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11px', color: 'var(--text-muted)' }}>
              <Clock size={11} />
              Son güncelleme: {lastUpdate.toLocaleTimeString('tr-TR')}
            </div>
          )}
        </div>

        {/* Right: recommended criteria */}
        <div className="card" style={{ padding: '20px' }}>
          <h3 style={{ margin: '0 0 16px', fontSize: '13px', color: 'var(--text-secondary)', letterSpacing: '1px' }}>
            ÖNERİLEN KRİTER
          </h3>
          <CriteriaRecommendation recommended={data.recommendedCriteria} active={!loading} />
          <div style={{
            marginTop: '14px', padding: '10px 14px', borderRadius: '8px',
            background: 'var(--bg-hover)', border: '1px solid var(--border)',
            fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5,
          }}>
            <strong style={{ color: 'var(--text-primary)' }}>Piyasa Skoru {data.score > 0 ? '+' : ''}{fmt(data.score)}</strong>
            {' '}→ {data.condition === 'BULL'
              ? 'Güçlü yukarı trend. Momentum ve büyüme hisselerine odaklan.'
              : data.condition === 'BEAR'
              ? 'Aşağı baskı var. Savunmacı ve değer hisselerini tercih et.'
              : 'Belirsiz yön. Kısa vadeli dönüşleri değerlendir.'}
          </div>
        </div>
      </div>

      {/* Indicators row */}
      <div>
        <h3 style={{ margin: '0 0 12px', fontSize: '13px', color: 'var(--text-secondary)', letterSpacing: '1px' }}>
          PİYASA KOŞUL GÖSTERGELERİ
        </h3>
        <MarketIndicatorsPanel data={data} />
      </div>

      {/* Top stocks */}
      <div className="card" style={{ padding: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700 }}>
              Bugünün En İyi Hisseleri
            </h3>
            <p style={{ margin: '4px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
              {CRITERIA_CONFIG[data.recommendedCriteria].label} bazlı sıralama
            </p>
          </div>
          <div style={{
            display: 'flex', alignItems: 'center', gap: '6px',
            padding: '5px 12px', borderRadius: '20px',
            background: CRITERIA_CONFIG[data.recommendedCriteria].bg,
            border: `1px solid ${CRITERIA_CONFIG[data.recommendedCriteria].color}40`,
            fontSize: '12px', fontWeight: 600,
            color: CRITERIA_CONFIG[data.recommendedCriteria].color,
          }}>
            {data.recommendedCriteria}
            <ChevronRight size={12} />
          </div>
        </div>
        <TopStocksTable stocks={stockData} loading={stockLoad} />
      </div>
    </div>
  )
}

// ── Market Condition History Chart ────────────────────────────────────────────

const CONDITION_COLORS: Record<string, string> = {
  BULL: '#00D084',
  BEAR: '#FF4757',
  SIDEWAYS: '#FFA502',
}

function MarketConditionHistory({ market }: { market: MarketKey }) {
  // Generate 12 months of mock historical market condition data
  const data = [
    { month: 'Mar 25', condition: 'SIDEWAYS', score: 1.2, index: 100 },
    { month: 'Apr 25', condition: 'BULL',     score: 4.5, index: 108 },
    { month: 'May 25', condition: 'BULL',     score: 5.8, index: 115 },
    { month: 'Jun 25', condition: 'BULL',     score: 6.2, index: 122 },
    { month: 'Jul 25', condition: 'SIDEWAYS', score: 2.1, index: 119 },
    { month: 'Aug 25', condition: 'BEAR',     score: -3.5, index: 112 },
    { month: 'Sep 25', condition: 'BEAR',     score: -5.1, index: 103 },
    { month: 'Oct 25', condition: 'SIDEWAYS', score: -1.8, index: 106 },
    { month: 'Nov 25', condition: 'BULL',     score: 3.4, index: 114 },
    { month: 'Dec 25', condition: 'BULL',     score: 4.8, index: 121 },
    { month: 'Jan 26', condition: 'BULL',     score: 6.0, index: 130 },
    { month: 'Feb 26', condition: 'SIDEWAYS', score: 1.5, index: 127 },
  ]

  return (
    <div className="card" style={{ padding: '20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
        <div>
          <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700 }}>
            {market} — Piyasa Koşulu Geçmişi (12 Ay)
          </h3>
          <p style={{ margin: '4px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
            BULL / BEAR / SIDEWAYS dönemleri ve endeks performansı
          </p>
        </div>
        <div style={{ display: 'flex', gap: '12px', fontSize: '11px' }}>
          {(['BULL','SIDEWAYS','BEAR'] as const).map((c) => (
            <div key={c} style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <div style={{ width: '10px', height: '10px', borderRadius: '2px', background: CONDITION_COLORS[c] }} />
              <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>{c}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Condition stripe timeline */}
      <div style={{ display: 'flex', gap: '2px', height: '24px', borderRadius: '8px', overflow: 'hidden', marginBottom: '12px' }}>
        {data.map((d) => (
          <div
            key={d.month}
            title={`${d.month}: ${d.condition} (score ${d.score > 0 ? '+' : ''}${d.score})`}
            style={{
              flex: 1,
              background: CONDITION_COLORS[d.condition],
              opacity: 0.75,
              transition: 'opacity 0.15s',
              cursor: 'default',
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.opacity = '1' }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.opacity = '0.75' }}
          />
        ))}
      </div>

      {/* Month labels */}
      <div style={{ display: 'flex', gap: '2px', marginBottom: '16px' }}>
        {data.map((d) => (
          <div key={d.month} style={{ flex: 1, textAlign: 'center', fontSize: '9px', color: 'var(--text-muted)' }}>
            {d.month}
          </div>
        ))}
      </div>

      {/* Index performance line chart */}
      <ResponsiveContainer width="100%" height={140}>
        <AreaChart data={data}>
          <defs>
            <linearGradient id="indexGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor="#4D9FFF" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#4D9FFF" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="month" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} />
          <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} domain={['dataMin - 5', 'dataMax + 5']} />
          <Tooltip
            contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '8px', fontSize: '12px' }}
            labelStyle={{ color: 'var(--text-primary)' }}
            formatter={(v) => [`${v}`, 'Endeks (Base 100)']}
          />
          <Area type="monotone" dataKey="index" stroke="#4D9FFF" fill="url(#indexGrad)" strokeWidth={2} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState<MarketKey>('BIST')
  const now = new Date()

  const tabStyle = (key: MarketKey) => ({
    padding: '8px 20px',
    borderRadius: '8px',
    border: 'none',
    cursor: 'pointer',
    fontSize: '13px',
    fontWeight: activeTab === key ? 700 : 500,
    background: activeTab === key ? 'var(--primary)' : 'var(--bg-hover)',
    color:      activeTab === key ? '#000' : 'var(--text-secondary)',
    transition: 'all 0.15s ease',
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* ── Page header ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '24px', fontWeight: 700 }}>Dashboard</h1>
          <p style={{ margin: '4px 0 0', fontSize: '13px', color: 'var(--text-secondary)' }}>
            {now.toLocaleDateString('tr-TR', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
            {' · '}
            <span style={{
              color: isMarketHours() ? 'var(--green)' : 'var(--text-muted)',
              fontWeight: 600,
            }}>
              {isMarketHours() ? '● Piyasa Açık' : '○ Piyasa Kapalı'}
            </span>
          </p>
        </div>
        {/* Market tabs */}
        <div style={{ display: 'flex', gap: '8px', background: 'var(--bg-card)', padding: '6px', borderRadius: '12px', border: '1px solid var(--border)' }}>
          <button style={tabStyle('BIST')} onClick={() => setActiveTab('BIST')}>
            🇹🇷 BIST
          </button>
          <button style={tabStyle('US')} onClick={() => setActiveTab('US')}>
            🇺🇸 US Market
          </button>
        </div>
      </div>

      {/* ── Market panel ── */}
      {activeTab === 'BIST' && <MarketPanel key="BIST" market="BIST" />}
      {activeTab === 'US'   && <MarketPanel key="US"   market="US" />}

      {/* ── Market Condition History Chart ── */}
      <MarketConditionHistory market={activeTab} />

      {/* keyframe styles */}
      <style>{`
        @keyframes spin  { to { transform: rotate(360deg); } }
        @keyframes ping  {
          0%   { transform: scale(1);   opacity: 1; }
          75%  { transform: scale(1.5); opacity: 0; }
          100% { transform: scale(1.5); opacity: 0; }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.4; }
        }
      `}</style>
    </div>
  )
}
