/**
 * DELTA Criteria V2 — Professional Sideways / Mean-Reversion Strategy
 *
 * Research basis:
 *   - Poterba & Summers (1988): Mean reversion in equity prices
 *   - Statistical arbitrage: Z-score oversold entry signals
 *   - Bollinger Band %B + squeeze methodology (Bollinger)
 *   - Range-bound support confluence (Fibonacci + MA + swing lows)
 *
 * Core philosophy: sideways markets reward BUY NEAR SUPPORT, SELL NEAR RESISTANCE.
 * We enter only when multiple support levels align with oversold technicals.
 *
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

function nthFromEnd(arr: number[], n: number): number | null {
  for (let offset = n; offset < arr.length; offset++) {
    const idx = arr.length - 1 - offset
    if (idx >= 0 && Number.isFinite(arr[idx])) return arr[idx]
  }
  return null
}

/**
 * 20-day high and low of the close series.
 */
function range20(prices: OHLCV[]): { high: number; low: number; width: number } {
  const slice = prices.slice(-20)
  const highs = slice.map((p) => p.high)
  const lows  = slice.map((p) => p.low)
  const high  = Math.max(...highs)
  const low   = Math.min(...lows)
  return { high, low, width: low > 0 ? (high - low) / low : 0 }
}

/**
 * Price position within the 20-day range: 0 = at low, 1 = at high.
 */
function rangePosition(prices: OHLCV[]): number | null {
  const { high, low } = range20(prices)
  const close = prices[prices.length - 1]?.close ?? 0
  if (high === low) return null
  return (close - low) / (high - low)
}

/**
 * Count how many times in last `window` bars the price touched
 * within `tolerance` (fraction) of `level`.
 */
function touchCount(prices: OHLCV[], level: number, tolerance: number, window: number): number {
  return prices.slice(-window).filter((p) => Math.abs(p.close - level) / level <= tolerance).length
}

/**
 * Z-score of the last close vs its 20-day SMA / standard deviation.
 */
function zScore20(prices: OHLCV[]): number | null {
  if (prices.length < 20) return null
  const slice  = prices.slice(-20).map((p) => p.close)
  const mean   = slice.reduce((s, v) => s + v, 0) / slice.length
  const std    = Math.sqrt(slice.reduce((s, v) => s + (v - mean) ** 2, 0) / slice.length)
  if (std === 0) return null
  return (slice[slice.length - 1] - mean) / std
}

/**
 * Bollinger Band %B: 0 = at lower band, 1 = at upper band.
 */
function bollingerPctB(stock: StockData): number | null {
  const upper  = lastValid(stock.indicators.bollinger.upper)
  const lower  = lastValid(stock.indicators.bollinger.lower)
  const close  = stock.prices[stock.prices.length - 1]?.close ?? 0
  if (upper === null || lower === null || upper === lower) return null
  return (close - lower) / (upper - lower)
}

/**
 * Bollinger Band width (upper - lower) / middle.
 * Compare recent 5-bar average vs prior 20-bar average to detect squeeze.
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
  return recent5 < prior20 * 0.85
}

/**
 * Bullish RSI divergence over last `lookback` bars:
 * Price makes a new low but RSI does not → momentum bottoming.
 */
function hasBullishRSIDivergence(prices: OHLCV[], rsi14: number[], lookback: number): boolean {
  if (prices.length < lookback || rsi14.length < lookback) return false
  const pSlice = prices.slice(-lookback)
  const rSlice = rsi14.filter(Number.isFinite).slice(-lookback)
  if (rSlice.length < lookback) return false

  const priceMin1 = pSlice[pSlice.length - 1].close
  const priceMin2 = Math.min(...pSlice.slice(0, -1).map((p) => p.close))
  const rsiMin1   = rSlice[rSlice.length - 1]
  const rsiMin2   = Math.min(...rSlice.slice(0, -1))

  // Price making lower low, RSI making higher low = divergence
  return priceMin1 < priceMin2 && rsiMin1 > rsiMin2
}

/**
 * ATR as a percentage of close price.
 */
function atrPct(prices: OHLCV[], atr14: number[]): number | null {
  const atr   = lastValid(atr14)
  const close = prices[prices.length - 1]?.close ?? 0
  if (atr === null || close <= 0) return null
  return atr / close
}

/**
 * Historical 20-day close-to-close volatility (annualised).
 */
function historicalVol20(prices: OHLCV[]): number | null {
  if (prices.length < 22) return null
  const slice = prices.slice(-21)
  const returns: number[] = []
  for (let i = 1; i < slice.length; i++) {
    if (slice[i - 1].close > 0)
      returns.push(Math.log(slice[i].close / slice[i - 1].close))
  }
  if (returns.length < 5) return null
  const mean = returns.reduce((s, v) => s + v, 0) / returns.length
  const variance = returns.reduce((s, v) => s + (v - mean) ** 2, 0) / returns.length
  return Math.sqrt(variance * 252)
}

/**
 * Closest Fibonacci retracement level (from recent 60-bar swing).
 * Returns the nearest Fib price and its distance (fraction) from close.
 */
function nearestFibDistance(stock: StockData): number {
  const close  = stock.prices[stock.prices.length - 1]?.close ?? 0
  const fib    = stock.indicators.fibonacci
  const levels = [
    fib.level236, fib.level382, fib.level500, fib.level618, fib.level786,
  ].filter((v) => v > 0)
  if (levels.length === 0 || close <= 0) return 1
  return Math.min(...levels.map((l) => Math.abs(close - l) / close))
}

/**
 * Distance from the nearest round number (integer multiples of round base).
 */
function nearRoundNumber(close: number, tolerance: number = 0.015): boolean {
  if (close <= 0) return false
  const magnitude = Math.pow(10, Math.floor(Math.log10(close)))
  const roundBases = [magnitude, magnitude * 5, magnitude / 2]
  return roundBases.some((base) => {
    const nearest = Math.round(close / base) * base
    return nearest > 0 && Math.abs(close - nearest) / close <= tolerance
  })
}

// ── FACTOR 1: RANGE QUALITY (25 pts) ────────────────────────────────────────
// The stock must be genuinely range-bound with well-defined support/resistance.

export const DELTA_V2_RANGE_QUALITY: FilterRule[] = [
  {
    name: 'adxRangeBound',
    weight: 10,
    check: (s) => {
      const adx    = lastValid(s.indicators.adx14.adx)
      if (adx === null) return { passed: false, value: null, description: 'ADX: no data' }
      const passed = adx < 22
      return {
        passed,
        value: parseFloat(adx.toFixed(1)),
        description: `ADX(14): ${adx.toFixed(1)} — need < 22 (no meaningful trend)`,
      }
    },
  },
  {
    name: 'priceInLowerRange',
    weight: 10,
    check: (s) => {
      const pos = rangePosition(s.prices)
      if (pos === null) return { passed: false, value: null, description: 'Range position: insufficient data' }
      // Want to buy in lower 35% of 20-day range
      const passed = pos <= 0.35
      return {
        passed,
        value: parseFloat((pos * 100).toFixed(1)),
        description: `Price at ${(pos * 100).toFixed(1)}% of 20-day range — need ≤35% (near support)`,
      }
    },
  },
  {
    name: 'usableRangeWidth',
    weight: 5,
    check: (s) => {
      const { width } = range20(s.prices)
      // Optimal: 8–30% range width. Too narrow (< 5%) = no opportunity. Too wide (> 40%) = volatile.
      const passed = width >= 0.08 && width <= 0.40
      return {
        passed,
        value: parseFloat((width * 100).toFixed(1)),
        description: `20-day range width: ${(width * 100).toFixed(1)}% — need 8–40% (tradeable range)`,
      }
    },
  },
]

// ── FACTOR 2: MEAN-REVERSION SETUP (25 pts) ─────────────────────────────────
// Statistical measures: Z-score, Bollinger %B, stochastic, divergence.

export const DELTA_V2_MEAN_REVERSION: FilterRule[] = [
  {
    name: 'zScoreOversold',
    weight: 10,
    check: (s) => {
      const z = zScore20(s.prices)
      if (z === null) return { passed: false, value: null, description: 'Z-score: insufficient data' }
      // Oversold: z ≤ -1.0 (price ≥ 1 std dev below 20-day mean)
      const passed = z <= -1.0
      return {
        passed,
        value: parseFloat(z.toFixed(2)),
        description: `Z-score (20d): ${z.toFixed(2)} — need ≤-1.0 (statistically oversold)`,
      }
    },
  },
  {
    name: 'bollingerLow',
    weight: 8,
    check: (s) => {
      const pctB = bollingerPctB(s)
      if (pctB === null) return { passed: false, value: null, description: 'Bollinger %B: no data' }
      // Within bottom 25% of BB range
      const passed = pctB <= 0.25
      return {
        passed,
        value: parseFloat((pctB * 100).toFixed(1)),
        description: `Bollinger %B: ${(pctB * 100).toFixed(1)}% — need ≤25% (near lower band)`,
      }
    },
  },
  {
    name: 'rsiOversoldRecovery',
    weight: 4,
    check: (s) => {
      const rsi = lastValid(s.indicators.rsi14)
      if (rsi === null) return { passed: false, value: null, description: 'RSI: no data' }
      // 28–48: oversold territory with potential for bounce
      const passed = rsi >= 28 && rsi <= 48
      return {
        passed,
        value: parseFloat(rsi.toFixed(1)),
        description: `RSI(14): ${rsi.toFixed(1)} — target 28–48 (mean-reversion entry zone)`,
      }
    },
  },
  {
    name: 'stochasticOversoldCross',
    weight: 3,
    check: (s) => {
      const k   = lastValid(s.indicators.stochastic.k)
      const d   = lastValid(s.indicators.stochastic.d)
      const pk  = nthFromEnd(s.indicators.stochastic.k, 1)
      const pd  = nthFromEnd(s.indicators.stochastic.d, 1)
      if (k === null || d === null || pk === null || pd === null)
        return { passed: false, value: null, description: 'Stochastic: no data' }
      const oversold   = k < 30
      const crossingUp = k > d && pk <= pd
      const passed     = oversold && crossingUp
      return {
        passed,
        value: parseFloat(k.toFixed(1)),
        description: `Stoch %K=${k.toFixed(1)} D=${d.toFixed(1)} — ${passed ? 'oversold bullish cross' : 'no crossover'}`,
      }
    },
  },
  {
    name: 'bullishRSIDivergence',
    weight: 3,
    check: (s) => {
      // Use last 14 bars for divergence check
      const divergence = hasBullishRSIDivergence(s.prices, s.indicators.rsi14, 14)
      const rsi = lastValid(s.indicators.rsi14)
      return {
        passed: divergence,
        value: rsi !== null ? parseFloat(rsi.toFixed(1)) : null,
        description: divergence
          ? `Bullish RSI divergence detected — price lower low, RSI higher low`
          : 'No RSI divergence',
      }
    },
  },
]

// ── FACTOR 3: SUPPORT LEVEL CONFLUENCE (20 pts) ──────────────────────────────
// Multiple support layers aligned = higher probability of bounce.

export const DELTA_V2_SUPPORT_CONFLUENCE: FilterRule[] = [
  {
    name: 'nearFibonacciSupport',
    weight: 8,
    check: (s) => {
      const dist   = nearestFibDistance(s)
      const passed = dist <= 0.025  // within 2.5% of a Fib level
      const close  = s.prices[s.prices.length - 1]?.close ?? 0
      return {
        passed,
        value: parseFloat((dist * 100).toFixed(2)),
        description: `Nearest Fibonacci: ${(dist * 100).toFixed(2)}% away from price (${close.toFixed(2)}) — need ≤2.5%`,
      }
    },
  },
  {
    name: 'nearMovingAverageSupport',
    weight: 7,
    check: (s) => {
      const close  = s.prices[s.prices.length - 1]?.close ?? 0
      const ema50  = lastValid(s.indicators.ema50)
      const sma200 = lastValid(s.indicators.sma200)
      if (ema50 === null && sma200 === null)
        return { passed: false, value: null, description: 'MA support: no data' }
      const distEMA50  = ema50  ? Math.abs(close - ema50)  / close : 1
      const distSMA200 = sma200 ? Math.abs(close - sma200) / close : 1
      const minDist    = Math.min(distEMA50, distSMA200)
      const passed     = minDist <= 0.03
      return {
        passed,
        value: parseFloat((minDist * 100).toFixed(2)),
        description: `Nearest MA support: ${(minDist * 100).toFixed(2)}% away — need ≤3% (EMA50 or SMA200)`,
      }
    },
  },
  {
    name: 'rangeLowRetest',
    weight: 5,
    check: (s) => {
      const { low }  = range20(s.prices)
      const close    = s.prices[s.prices.length - 1]?.close ?? 0
      if (low <= 0)  return { passed: false, value: null, description: 'Range low: no data' }
      const dist     = (close - low) / low
      // Within 3% above range low = retesting support
      const passed   = dist >= 0 && dist <= 0.03
      return {
        passed,
        value: parseFloat((dist * 100).toFixed(2)),
        description: `${(dist * 100).toFixed(2)}% above 20-day range low (${low.toFixed(2)}) — need 0–3%`,
      }
    },
  },
]

// ── FACTOR 4: FUNDAMENTAL FLOOR (15 pts) ────────────────────────────────────
// Cheap enough that value investors provide a natural floor under the price.

export const DELTA_V2_FUNDAMENTAL_FLOOR: FilterRule[] = [
  {
    name: 'fairValuePE',
    weight: 5,
    check: (s) => {
      const pe     = s.fundamentals.pe
      const passed = pe !== null && pe > 0 && pe <= 20
      return {
        passed,
        value: pe !== null ? parseFloat(pe.toFixed(1)) : null,
        description: `P/E: ${pe?.toFixed(1) ?? 'n/a'} — need ≤20 (fair value, not a value trap)`,
      }
    },
  },
  {
    name: 'lowPBFloor',
    weight: 5,
    check: (s) => {
      const pb     = s.fundamentals.pb
      const passed = pb !== null && pb > 0 && pb < 2.5
      return {
        passed,
        value: pb !== null ? parseFloat(pb.toFixed(2)) : null,
        description: `P/B: ${pb?.toFixed(2) ?? 'n/a'} — need < 2.5 (asset value floor)`,
      }
    },
  },
  {
    name: 'positiveROE',
    weight: 3,
    check: (s) => {
      const roe    = s.fundamentals.roe
      const passed = roe !== null && roe > 0.08
      return {
        passed,
        value: roe !== null ? parseFloat((roe * 100).toFixed(1)) : null,
        description: `ROE: ${roe !== null ? (roe * 100).toFixed(1) + '%' : 'n/a'} — need > 8%`,
      }
    },
  },
  {
    name: 'positiveFCF',
    weight: 2,
    check: (s) => {
      const fcf    = s.fundamentals.freeCashFlow
      const passed = fcf !== null && fcf > 0
      return {
        passed,
        value: fcf,
        description: `FCF: ${fcf !== null ? (fcf > 0 ? 'positive' : 'negative') : 'n/a'} — must be positive`,
      }
    },
  },
]

// ── FACTOR 5: VOLATILITY TIMING (10 pts) ────────────────────────────────────
// We want low-volatility windows — quiet stocks bounce predictably.

export const DELTA_V2_VOLATILITY_TIMING: FilterRule[] = [
  {
    name: 'lowNormalisedATR',
    weight: 5,
    check: (s) => {
      const ap     = atrPct(s.prices, s.indicators.atr14)
      if (ap === null) return { passed: false, value: null, description: 'ATR%: no data' }
      // Max 4% ATR/price for range trading
      const passed = ap <= 0.04
      return {
        passed,
        value: parseFloat((ap * 100).toFixed(2)),
        description: `ATR/Price: ${(ap * 100).toFixed(2)}% — need ≤4% (not too volatile for range)`,
      }
    },
  },
  {
    name: 'bollingerSqueeze',
    weight: 3,
    check: (s) => {
      const squeezing = isBollingerSqueezing(s)
      const pctB      = bollingerPctB(s)
      return {
        passed: squeezing,
        value: pctB !== null ? parseFloat((pctB * 100).toFixed(1)) : null,
        description: squeezing
          ? 'BB squeeze active — consolidating before next move'
          : 'No BB squeeze',
      }
    },
  },
  {
    name: 'lowHistoricalVol',
    weight: 2,
    check: (s) => {
      const hv     = historicalVol20(s.prices)
      if (hv === null) return { passed: false, value: null, description: 'Historical vol: insufficient data' }
      // Annualised 20-day vol < 35%
      const passed = hv < 0.35
      return {
        passed,
        value: parseFloat((hv * 100).toFixed(1)),
        description: `20-day annualised vol: ${(hv * 100).toFixed(1)}% — need < 35%`,
      }
    },
  },
]

// ── FACTOR 6: RANGE TOUCH VALIDATION (5 pts) ────────────────────────────────
// A range is only reliable if price has bounced from its levels before.

export const DELTA_V2_RANGE_VALIDATION: FilterRule[] = [
  {
    name: 'rangeLowTouches',
    weight: 3,
    check: (s) => {
      const { low }  = range20(s.prices)
      const touches  = touchCount(s.prices, low, 0.015, 40)
      // At least 2 touches of the range low = validated support
      const passed   = touches >= 2
      return {
        passed,
        value: touches,
        description: `Range low (${low.toFixed(2)}) tested ${touches}x in last 40 bars — need ≥2 (valid support)`,
      }
    },
  },
  {
    name: 'nearRoundNumberSupport',
    weight: 2,
    check: (s) => {
      const close  = s.prices[s.prices.length - 1]?.close ?? 0
      const passed = nearRoundNumber(close, 0.02)
      return {
        passed,
        value: parseFloat(close.toFixed(2)),
        description: `Price ${close.toFixed(2)} — ${passed ? 'near psychological round number support' : 'no round number nearby'}`,
      }
    },
  },
]

// ── HARD FILTERS ─────────────────────────────────────────────────────────────

export const DELTA_V2_HARD_FILTERS: FilterRule[] = [
  {
    name: 'adxHardGate',
    weight: 8,
    check: (s) => {
      const adx    = lastValid(s.indicators.adx14.adx)
      if (adx === null) return { passed: true, value: null, description: 'ADX: no data (allowed)' }
      const passed = adx < 28
      return {
        passed,
        value: parseFloat(adx.toFixed(1)),
        description: `ADX hard gate: ${adx.toFixed(1)} — must be < 28 (no strong trend)`,
      }
    },
  },
  {
    name: 'notFallingKnife',
    weight: 5,
    check: (s) => {
      const close = s.prices[s.prices.length - 1]?.close ?? 0
      const high  = s.high52w
      if (high <= 0) return { passed: true, value: null, description: '52-week high: no data (allowed)' }
      const drawdown = (close - high) / high
      const passed   = drawdown >= -0.40
      return {
        passed,
        value: parseFloat((drawdown * 100).toFixed(1)),
        description: `Drawdown from 52-wk high: ${(drawdown * 100).toFixed(1)}% — must be ≥-40% (not a falling knife)`,
      }
    },
  },
  {
    name: 'atrHardGate',
    weight: 3,
    check: (s) => {
      const ap     = atrPct(s.prices, s.indicators.atr14)
      if (ap === null) return { passed: true, value: null, description: 'ATR%: no data (allowed)' }
      const passed = ap <= 0.05
      return {
        passed,
        value: parseFloat((ap * 100).toFixed(2)),
        description: `ATR/Price hard gate: ${(ap * 100).toFixed(2)}% — must be ≤5%`,
      }
    },
  },
]

// ── Compose all rules ─────────────────────────────────────────────────────────

export const DELTA_V2_TECHNICAL: FilterRule[] = [
  ...DELTA_V2_HARD_FILTERS,
  ...DELTA_V2_RANGE_QUALITY,
  ...DELTA_V2_MEAN_REVERSION,
  ...DELTA_V2_SUPPORT_CONFLUENCE,
  ...DELTA_V2_VOLATILITY_TIMING,
  ...DELTA_V2_RANGE_VALIDATION,
]

export const DELTA_V2_FUNDAMENTAL: FilterRule[] = [
  ...DELTA_V2_FUNDAMENTAL_FLOOR,
]

export const DELTA_V2_CONFIG: CriteriaConfig = {
  type:               'DELTA',
  label:              'DELTA V2 — Sideways Mean Reversion (Z-Score / Range / Confluence)',
  technicalFilters:   DELTA_V2_TECHNICAL,
  fundamentalFilters: DELTA_V2_FUNDAMENTAL,
}

// ── Range profit-taking calculator ───────────────────────────────────────────

export interface RangeTakeProfitConfig {
  target1:      number    // 50% position off at range midpoint
  target2:      number    // remaining near range high
  stopLoss:     number    // just below range low
  maxHoldDays:  number
  riskReward:   number
}

/**
 * For range trades: scale out at midpoint, full exit near range top.
 * Stop is placed just below the established range low.
 */
export function calculateRangeTakeProfit(
  entryPrice: number,
  rangeHigh:  number,
  rangeLow:   number
): RangeTakeProfitConfig {
  const rangeWidth = rangeHigh - rangeLow
  const target1    = entryPrice + rangeWidth * 0.45   // ~midpoint
  const target2    = rangeHigh * 0.97                 // 3% below range top
  const stopLoss   = rangeLow  * 0.985                // 1.5% below range low

  const avgTarget  = (target1 + target2) / 2
  const reward     = avgTarget - entryPrice
  const risk       = entryPrice - stopLoss
  const rr         = risk > 0 ? reward / risk : 0

  return {
    target1:     parseFloat(target1.toFixed(4)),
    target2:     parseFloat(target2.toFixed(4)),
    stopLoss:    parseFloat(stopLoss.toFixed(4)),
    maxHoldDays: 15,
    riskReward:  parseFloat(rr.toFixed(2)),
  }
}

/**
 * Extract the current 20-day range for a stock's price series.
 */
export function getCurrentRange(prices: OHLCV[]): { high: number; low: number; width: number } {
  return range20(prices)
}
