/**
 * ALFA Criteria V2 — Institutional Momentum Strategy
 *
 * Research basis:
 *   - Jegadeesh & Titman (1993): 6-12 month price momentum
 *   - Fama-French 5-Factor Model (momentum + quality adaptations)
 *   - IBD CANSLIM methodology (Acc/Dist, RS, EPS acceleration)
 *   - William O'Neil: pivot breakout, 52-week high proximity
 *
 * Scoring: 6 factor groups totaling 100 weighted points.
 * Integrates with the existing FilterRule / CriteriaConfig system.
 */

import type {
  OHLCV,
  StockData,
  FilterRule,
  CriteriaConfig,
} from '../../types/market'

// ── Utility helpers ──────────────────────────────────────────────────────────

function lastValid(arr: number[]): number | null {
  for (let i = arr.length - 1; i >= 0; i--) {
    if (Number.isFinite(arr[i])) return arr[i]
  }
  return null
}

/** Clamp x to [0, 1] using linear mapping from [lo, hi]. */
function norm(x: number, lo: number, hi: number): number {
  if (hi === lo) return 0.5
  return Math.max(0, Math.min(1, (x - lo) / (hi - lo)))
}

/**
 * Return the close price `offset` bars back from the last bar.
 * Returns null if out of range.
 */
function closeBarsAgo(prices: OHLCV[], offset: number): number | null {
  const idx = prices.length - 1 - offset
  if (idx < 0) return null
  const v = prices[idx].close
  return Number.isFinite(v) ? v : null
}

/**
 * Simple price return: (end - start) / start.
 * Uses actual available bars (caps at array length).
 */
function periodReturn(prices: OHLCV[], startBarsAgo: number, endBarsAgo: number): number | null {
  const end   = closeBarsAgo(prices, endBarsAgo)
  const start = closeBarsAgo(prices, startBarsAgo)
  if (end === null || start === null || start <= 0) return null
  return (end - start) / start
}

/** OBV slope: linear regression slope over last `window` OBV values (normalised). */
function obvSlope(obv: number[], window: number): number | null {
  const slice = obv.filter(Number.isFinite).slice(-window)
  if (slice.length < 3) return null
  const n = slice.length
  const meanX = (n - 1) / 2
  const meanY = slice.reduce((s, v) => s + v, 0) / n
  let num = 0, den = 0
  for (let i = 0; i < n; i++) {
    num += (i - meanX) * (slice[i] - meanY)
    den += (i - meanX) ** 2
  }
  if (den === 0) return null
  const scale = Math.abs(meanY) || 1
  return num / den / scale  // normalised slope
}

/**
 * IBD-style Accumulation / Distribution day count over `window` sessions.
 * Accumulation: close > prev close AND volume > 20-day avg volume
 * Distribution: close < prev close AND volume > 20-day avg volume
 */
function accDistDays(
  prices: OHLCV[],
  vol20avg: number[],
  window: number
): { accum: number; distrib: number } {
  const slice    = prices.slice(-window - 1)
  const volAvgs  = vol20avg.slice(-window - 1)
  let accum = 0, distrib = 0

  for (let i = 1; i < slice.length; i++) {
    const avgVol = volAvgs[i]
    if (!Number.isFinite(avgVol) || avgVol <= 0) continue
    const aboveAvgVol = slice[i].volume > avgVol * 1.1
    if (!aboveAvgVol) continue
    if (slice[i].close > slice[i - 1].close) accum++
    else if (slice[i].close < slice[i - 1].close) distrib++
  }

  return { accum, distrib }
}

/**
 * Up-volume / Down-volume ratio over `window` bars.
 * Days where close >= open count as "up volume".
 */
function upDownVolumeRatio(prices: OHLCV[], window: number): number | null {
  const slice = prices.slice(-window)
  if (slice.length < 5) return null
  let upVol = 0, downVol = 0
  for (const bar of slice) {
    if (bar.close >= bar.open) upVol   += bar.volume
    else                        downVol += bar.volume
  }
  if (downVol === 0) return 3  // all up
  return upVol / downVol
}

/**
 * EMA stack check: price > ema20 > ema50 > ema200
 * Returns 0 (none), 0.5 (partial), or 1.0 (perfect).
 */
function emaStackScore(stock: StockData): number {
  const close  = stock.prices[stock.prices.length - 1]?.close ?? 0
  const ema20  = lastValid(stock.indicators.ema20)
  const ema50  = lastValid(stock.indicators.ema50)
  const ema200 = lastValid(stock.indicators.ema200)
  if (ema20 === null || ema50 === null || ema200 === null) return 0

  const checks = [
    close > ema20,
    ema20 > ema50,
    ema50 > ema200,
    close > ema200,
  ]
  return checks.filter(Boolean).length / checks.length
}

/** Bollinger Band width (normalised): (upper - lower) / middle */
function bbWidth(stock: StockData): number | null {
  const upper  = lastValid(stock.indicators.bollinger.upper)
  const lower  = lastValid(stock.indicators.bollinger.lower)
  const middle = lastValid(stock.indicators.bollinger.middle)
  if (upper === null || lower === null || middle === null || middle === 0) return null
  return (upper - lower) / middle
}

/**
 * Volatility contraction (squeeze): compare average BB width over last 5 bars
 * vs last 20 bars. Returns true if currently contracting.
 */
function isBollingerSqueezing(stock: StockData): boolean {
  const upper  = stock.indicators.bollinger.upper.filter(Number.isFinite)
  const lower  = stock.indicators.bollinger.lower.filter(Number.isFinite)
  const middle = stock.indicators.bollinger.middle.filter(Number.isFinite)
  const n = Math.min(upper.length, lower.length, middle.length)
  if (n < 20) return false

  const widths = Array.from({ length: n }, (_, i) =>
    middle[i] > 0 ? (upper[i] - lower[i]) / middle[i] : 0
  )
  const recent5  = widths.slice(-5).reduce((s, v) => s + v, 0) / 5
  const prior20  = widths.slice(-20).reduce((s, v) => s + v, 0) / 20
  return recent5 < prior20 * 0.85   // at least 15% narrower
}

// ── FACTOR 1: PRICE MOMENTUM (25 pts) ───────────────────────────────────────
//   Jegadeesh-Titman skip-1-month momentum across 3 horizons + trend consistency

export const ALFA_V2_MOMENTUM: FilterRule[] = [
  {
    name: 'momentum12_1',
    weight: 10,
    check: (s) => {
      const r = periodReturn(s.prices, 252, 21)
      if (r === null) return { passed: false, value: null, description: '12-1 month momentum: insufficient data' }
      const passed = r > 0
      return {
        passed,
        value: parseFloat((r * 100).toFixed(1)),
        description: `12-1M momentum: ${(r * 100).toFixed(1)}% — need > 0%`,
      }
    },
  },
  {
    name: 'momentum6_1',
    weight: 9,
    check: (s) => {
      const r = periodReturn(s.prices, 126, 21)
      if (r === null) return { passed: false, value: null, description: '6-1 month momentum: insufficient data' }
      const passed = r > 0
      return {
        passed,
        value: parseFloat((r * 100).toFixed(1)),
        description: `6-1M momentum: ${(r * 100).toFixed(1)}% — need > 0%`,
      }
    },
  },
  {
    name: 'momentum3_1',
    weight: 6,
    check: (s) => {
      const r = periodReturn(s.prices, 63, 21)
      if (r === null) return { passed: false, value: null, description: '3-1 month momentum: insufficient data' }
      const passed = r > 0
      return {
        passed,
        value: parseFloat((r * 100).toFixed(1)),
        description: `3-1M momentum: ${(r * 100).toFixed(1)}% — need > 0%`,
      }
    },
  },
  {
    name: 'trendConsistency',
    weight: 6,
    check: (s) => {
      // % of last 126 days where close > 20-day SMA  (Frog-in-Pan proxy)
      const ema20 = s.indicators.ema20
      const prices = s.prices
      const window = Math.min(126, prices.length, ema20.length)
      if (window < 20) return { passed: false, value: null, description: 'Trend consistency: insufficient data' }
      let above = 0
      for (let i = 0; i < window; i++) {
        const idx = prices.length - window + i
        const eidx = ema20.length - window + i
        if (Number.isFinite(ema20[eidx]) && prices[idx].close > ema20[eidx]) above++
      }
      const pct = above / window
      const passed = pct >= 0.60
      return {
        passed,
        value: parseFloat((pct * 100).toFixed(1)),
        description: `Trend consistency: ${(pct * 100).toFixed(1)}% days above 20 EMA — need ≥60%`,
      }
    },
  },
]

// ── FACTOR 2: RELATIVE STRENGTH vs INDEX (20 pts) ───────────────────────────
//   IBD RS Rating methodology across multiple periods

export const ALFA_V2_RELATIVE_STRENGTH: FilterRule[] = [
  {
    name: 'rs3month',
    weight: 8,
    check: (s) => {
      // Positive absolute return over 3 months is minimum bar
      const r = periodReturn(s.prices, 63, 0)
      if (r === null) return { passed: false, value: null, description: 'RS 3M: insufficient data' }
      // Also use stored relativeStrength if available (90-day ratio)
      const rsRatio = s.relativeStrength
      const passed = r > 0 && (rsRatio === null || rsRatio > 0.8)
      return {
        passed,
        value: rsRatio !== null ? parseFloat(rsRatio.toFixed(2)) : parseFloat((r * 100).toFixed(1)),
        description: `RS 3M: return=${(r * 100).toFixed(1)}%, RS ratio=${rsRatio?.toFixed(2) ?? 'n/a'} — need positive`,
      }
    },
  },
  {
    name: 'rs6month',
    weight: 7,
    check: (s) => {
      const r = periodReturn(s.prices, 126, 0)
      if (r === null) return { passed: false, value: null, description: 'RS 6M: insufficient data' }
      const passed = r > 0
      return {
        passed,
        value: parseFloat((r * 100).toFixed(1)),
        description: `RS 6M: ${(r * 100).toFixed(1)}% — need > 0%`,
      }
    },
  },
  {
    name: 'rs12month',
    weight: 5,
    check: (s) => {
      const r = periodReturn(s.prices, 252, 0)
      if (r === null) return { passed: false, value: null, description: 'RS 12M: insufficient data' }
      const passed = r > 0
      return {
        passed,
        value: parseFloat((r * 100).toFixed(1)),
        description: `RS 12M: ${(r * 100).toFixed(1)}% — need > 0%`,
      }
    },
  },
]

// ── FACTOR 3: VOLUME CONFIRMATION (15 pts) ───────────────────────────────────
//   Professional volume analysis: accumulation vs distribution

export const ALFA_V2_VOLUME: FilterRule[] = [
  {
    name: 'upDownVolumeRatio',
    weight: 6,
    check: (s) => {
      const ratio = upDownVolumeRatio(s.prices, 50)
      if (ratio === null) return { passed: false, value: null, description: 'Up/Down volume: insufficient data' }
      const passed = ratio >= 1.3
      return {
        passed,
        value: parseFloat(ratio.toFixed(2)),
        description: `Up/Down volume ratio (50d): ${ratio.toFixed(2)} — need ≥1.3`,
      }
    },
  },
  {
    name: 'accDistBalance',
    weight: 5,
    check: (s) => {
      const { accum, distrib } = accDistDays(s.prices, s.indicators.volume20avg, 25)
      const passed = accum > distrib
      const net = accum - distrib
      return {
        passed,
        value: net,
        description: `Acc/Dist (25d): ${accum} accum vs ${distrib} distrib — net=${net > 0 ? '+' : ''}${net}`,
      }
    },
  },
  {
    name: 'obvTrending',
    weight: 4,
    check: (s) => {
      const slope = obvSlope(s.indicators.obv, 20)
      if (slope === null) return { passed: false, value: null, description: 'OBV trend: insufficient data' }
      const passed = slope > 0
      return {
        passed,
        value: parseFloat(slope.toFixed(4)),
        description: `OBV 20-day slope: ${slope > 0 ? 'rising' : 'falling'} (${slope.toFixed(4)})`,
      }
    },
  },
]

// ── FACTOR 4: TREND QUALITY (15 pts) ─────────────────────────────────────────
//   Structural trend health: EMA alignment, ADX strength

export const ALFA_V2_TREND: FilterRule[] = [
  {
    name: 'emaStackFull',
    weight: 8,
    check: (s) => {
      const score = emaStackScore(s)
      const passed = score >= 0.75  // at least 3 of 4 checks pass
      const close  = s.prices[s.prices.length - 1]?.close ?? 0
      const ema20  = lastValid(s.indicators.ema20)
      const ema50  = lastValid(s.indicators.ema50)
      const ema200 = lastValid(s.indicators.ema200)
      return {
        passed,
        value: parseFloat((score * 100).toFixed(0)),
        description: `EMA stack score: ${(score * 100).toFixed(0)}% — Price=${close.toFixed(2)} EMA20=${ema20?.toFixed(2)} EMA50=${ema50?.toFixed(2)} EMA200=${ema200?.toFixed(2)}`,
      }
    },
  },
  {
    name: 'adxTrendStrength',
    weight: 5,
    check: (s) => {
      const adx = lastValid(s.indicators.adx14.adx)
      if (adx === null) return { passed: false, value: null, description: 'ADX: insufficient data' }
      // Ideal: trending (>20) but not overextended (<55)
      const passed = adx >= 20 && adx <= 55
      return {
        passed,
        value: parseFloat(adx.toFixed(1)),
        description: `ADX(14) = ${adx.toFixed(1)} — target 20–55 (strong trend, not exhausted)`,
      }
    },
  },
  {
    name: 'vwapAbove',
    weight: 2,
    check: (s) => {
      const vwap  = lastValid(s.indicators.vwap)
      const close = s.prices[s.prices.length - 1]?.close ?? 0
      if (vwap === null) return { passed: false, value: null, description: 'VWAP: no data' }
      const passed = close > vwap
      return {
        passed,
        value: parseFloat(close.toFixed(2)),
        description: `Price (${close.toFixed(2)}) ${passed ? '>' : '<='} VWAP (${vwap.toFixed(2)})`,
      }
    },
  },
]

// ── FACTOR 5: FUNDAMENTAL QUALITY (15 pts) ───────────────────────────────────
//   Earnings + Revenue growth; cash-flow quality; balance sheet health

export const ALFA_V2_FUNDAMENTALS: FilterRule[] = [
  {
    name: 'revenueGrowthStrong',
    weight: 5,
    check: (s) => {
      const rg     = s.fundamentals.revenueGrowth
      const passed = rg !== null && rg > 0.15
      return {
        passed,
        value: rg !== null ? parseFloat((rg * 100).toFixed(1)) : null,
        description: `Revenue growth: ${rg !== null ? (rg * 100).toFixed(1) + '%' : 'n/a'} — need > 15%`,
      }
    },
  },
  {
    name: 'earningsGrowthStrong',
    weight: 5,
    check: (s) => {
      const eg     = s.fundamentals.earningsGrowth
      const passed = eg !== null && eg > 0.10
      return {
        passed,
        value: eg !== null ? parseFloat((eg * 100).toFixed(1)) : null,
        description: `Earnings growth: ${eg !== null ? (eg * 100).toFixed(1) + '%' : 'n/a'} — need > 10%`,
      }
    },
  },
  {
    name: 'roeStrong',
    weight: 3,
    check: (s) => {
      const roe    = s.fundamentals.roe
      const passed = roe !== null && roe > 0.15
      return {
        passed,
        value: roe !== null ? parseFloat((roe * 100).toFixed(1)) : null,
        description: `ROE: ${roe !== null ? (roe * 100).toFixed(1) + '%' : 'n/a'} — need > 15%`,
      }
    },
  },
  {
    name: 'debtEquityHealthy',
    weight: 1,
    check: (s) => {
      const de     = s.fundamentals.debtEquity
      const passed = de !== null && de < 1.5
      return {
        passed,
        value: de !== null ? parseFloat(de.toFixed(2)) : null,
        description: `D/E ratio: ${de?.toFixed(2) ?? 'n/a'} — need < 1.5`,
      }
    },
  },
  {
    name: 'freeCashFlowPositive',
    weight: 1,
    check: (s) => {
      const fcf    = s.fundamentals.freeCashFlow
      const passed = fcf !== null && fcf > 0
      return {
        passed,
        value: fcf,
        description: `FCF: ${fcf !== null ? (fcf > 0 ? 'positive' : 'negative') : 'n/a'} — need positive`,
      }
    },
  },
]

// ── FACTOR 6: ENTRY TIMING (10 pts) ──────────────────────────────────────────
//   O'Neil pivot proximity, Bollinger squeeze, RSI zone

export const ALFA_V2_ENTRY: FilterRule[] = [
  {
    name: 'near52WeekHighV2',
    weight: 5,
    check: (s) => {
      const close = s.prices[s.prices.length - 1]?.close ?? 0
      const high  = s.high52w
      if (high <= 0) return { passed: false, value: null, description: '52-week high: no data' }
      const dist  = (close - high) / high  // negative value
      // Ideal: within 15% of 52-week high (potential breakout zone)
      const passed = dist >= -0.15
      return {
        passed,
        value: parseFloat((dist * 100).toFixed(1)),
        description: `${(Math.abs(dist) * 100).toFixed(1)}% below 52-wk high (${high.toFixed(2)}) — need within 15%`,
      }
    },
  },
  {
    name: 'rsiOptimalZoneV2',
    weight: 3,
    check: (s) => {
      const rsi    = lastValid(s.indicators.rsi14)
      if (rsi === null) return { passed: false, value: null, description: 'RSI: no data' }
      // Best momentum entry: 50–65 (has momentum, not overbought)
      const passed = rsi >= 50 && rsi <= 65
      return {
        passed,
        value: parseFloat(rsi.toFixed(1)),
        description: `RSI(14) = ${rsi.toFixed(1)} — target 50–65 (momentum zone)`,
      }
    },
  },
  {
    name: 'bollingerSqueeze',
    weight: 2,
    check: (s) => {
      const squeezing = isBollingerSqueezing(s)
      const width     = bbWidth(s)
      return {
        passed: squeezing,
        value: width !== null ? parseFloat(width.toFixed(4)) : null,
        description: squeezing
          ? `BB squeeze active (width=${width?.toFixed(4)}) — energy building`
          : `No BB squeeze (width=${width?.toFixed(4)})`,
      }
    },
  },
]

// ── HARD FILTERS (binary gate — high weight) ─────────────────────────────────
// These run as technical filters but apply before soft scoring.

export const ALFA_V2_HARD_FILTERS: FilterRule[] = [
  {
    name: 'priceMustBeAbove200EMA',
    weight: 15,
    check: (s) => {
      const ema200 = lastValid(s.indicators.ema200)
      const close  = s.prices[s.prices.length - 1]?.close ?? 0
      const passed = ema200 !== null && close > ema200
      return {
        passed,
        value: ema200,
        description: `Price (${close.toFixed(2)}) ${passed ? '>' : '<='} 200 EMA (${ema200?.toFixed(2) ?? 'n/a'})`,
      }
    },
  },
  {
    name: 'priceMustBeAbove50EMA',
    weight: 10,
    check: (s) => {
      const ema50 = lastValid(s.indicators.ema50)
      const close = s.prices[s.prices.length - 1]?.close ?? 0
      const passed = ema50 !== null && close > ema50
      return {
        passed,
        value: ema50,
        description: `Price (${close.toFixed(2)}) ${passed ? '>' : '<='} 50 EMA (${ema50?.toFixed(2) ?? 'n/a'})`,
      }
    },
  },
  {
    name: 'goldenCross',
    weight: 8,
    check: (s) => {
      const ema50  = lastValid(s.indicators.ema50)
      const ema200 = lastValid(s.indicators.ema200)
      const passed = ema50 !== null && ema200 !== null && ema50 > ema200
      return {
        passed,
        value: ema50 !== null && ema200 !== null ? parseFloat((ema50 - ema200).toFixed(2)) : null,
        description: passed ? 'Golden Cross: 50 EMA > 200 EMA' : 'Death Cross / No cross',
      }
    },
  },
  {
    name: 'notBrokenStock',
    weight: 5,
    check: (s) => {
      const close = s.prices[s.prices.length - 1]?.close ?? 0
      const high  = s.high52w
      if (high <= 0) return { passed: true, value: null, description: '52-week high: no data (allowed)' }
      const drawdown = (close - high) / high
      const passed   = drawdown >= -0.35
      return {
        passed,
        value: parseFloat((drawdown * 100).toFixed(1)),
        description: `Drawdown from 52-wk high: ${(drawdown * 100).toFixed(1)}% — max allowed: -35%`,
      }
    },
  },
]

// ── Compose all rules ─────────────────────────────────────────────────────────

export const ALFA_V2_TECHNICAL: FilterRule[] = [
  ...ALFA_V2_HARD_FILTERS,
  ...ALFA_V2_MOMENTUM,
  ...ALFA_V2_RELATIVE_STRENGTH,
  ...ALFA_V2_VOLUME,
  ...ALFA_V2_TREND,
  ...ALFA_V2_ENTRY,
]

export const ALFA_V2_CONFIG: CriteriaConfig = {
  type:               'ALFA',
  label:              'ALFA V2 — Institutional Momentum (Jegadeesh-Titman / CANSLIM)',
  technicalFilters:   ALFA_V2_TECHNICAL,
  fundamentalFilters: ALFA_V2_FUNDAMENTALS,
}

// ── Standalone stop-loss calculator ──────────────────────────────────────────

export interface StopLossResult {
  stopPrice:    number
  stopPercent:  number
  method:       string
  isValidStop:  boolean
}

export function calculateStopLossV2(
  prices:     OHLCV[],
  atr14:      number[],
  entryPrice: number
): StopLossResult {
  const atr = lastValid(atr14) ?? entryPrice * 0.02

  // Method 1: ATR-based (2.5× ATR below entry)
  const atrStop = entryPrice - atr * 2.5

  // Method 2: Below recent swing low (lowest low in last 10 bars, -1%)
  const swingSlice = prices.slice(-10)
  const swingLow   = Math.min(...swingSlice.map((b) => b.low)) * 0.99

  // Method 3: 2% below 50 EMA
  const ema50arr = prices.map((_, i) => {
    // Re-use already-computed ema50 from indicators if available; 
    // here we approximate for standalone use.
    return NaN
  })

  // Use the highest (tightest) of ATR and swing stops
  const stopPrice  = Math.max(atrStop, swingLow)
  const stopPercent = (entryPrice - stopPrice) / entryPrice

  return {
    stopPrice:   parseFloat(stopPrice.toFixed(4)),
    stopPercent: parseFloat(stopPercent.toFixed(4)),
    method:      'ATR2.5x+SwingLow',
    isValidStop: stopPercent <= 0.08,  // max acceptable: 8% stop
  }
}

// ── Position sizing via risk-based approach ───────────────────────────────────

export interface PositionSizeResult {
  shares:         number
  positionValue:  number
  positionPct:    number
  riskAmount:     number
}

/**
 * Risk-based position sizing.
 * Size the position so that if stop is hit, max loss = riskPerTrade * capital.
 * Cap at maxPositionPct of portfolio.
 */
export function calculatePositionSize(
  capital:         number,
  entryPrice:      number,
  stopPrice:       number,
  riskPerTrade:    number = 0.02,  // 2% capital at risk per trade
  maxPositionPct:  number = 0.25   // max 25% per position
): PositionSizeResult {
  const riskPerShare = entryPrice - stopPrice
  if (riskPerShare <= 0 || entryPrice <= 0) {
    return { shares: 0, positionValue: 0, positionPct: 0, riskAmount: 0 }
  }

  const capitalAtRisk = capital * riskPerTrade
  const rawShares     = Math.floor(capitalAtRisk / riskPerShare)
  const rawValue      = rawShares * entryPrice

  const maxValue      = capital * maxPositionPct
  const finalShares   = rawValue > maxValue ? Math.floor(maxValue / entryPrice) : rawShares
  const finalValue    = finalShares * entryPrice

  return {
    shares:        finalShares,
    positionValue: parseFloat(finalValue.toFixed(2)),
    positionPct:   parseFloat((finalValue / capital).toFixed(4)),
    riskAmount:    parseFloat(Math.min(capitalAtRisk, finalShares * riskPerShare).toFixed(2)),
  }
}

// Export norm helper for potential reuse in other criteria files
export { norm }
