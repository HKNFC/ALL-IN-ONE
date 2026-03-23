import type {
  OHLCV,
  MACDResult,
  BollingerResult,
  ADXResult,
  StochasticResult,
  FibonacciLevels,
  TechnicalIndicators,
} from '../types/market'

// Local type alias (mirrors VCPResult in market.ts — kept in sync)
interface VCPResult {
  stages: number[]
  pivot: number
  isContracting: boolean
  score: number
}

// ---------------------------------------------------------------------------
// EMA — Exponential Moving Average
// ---------------------------------------------------------------------------
export function calculateEMA(prices: OHLCV[], period: number): number[] {
  const closes = prices.map((p) => p.close)
  const result: number[] = new Array(closes.length).fill(NaN)
  if (closes.length < period) return result

  const k = 2 / (period + 1)

  // Seed with SMA of first `period` bars
  const seed = closes.slice(0, period).reduce((a, b) => a + b, 0) / period
  result[period - 1] = seed

  for (let i = period; i < closes.length; i++) {
    result[i] = closes[i] * k + result[i - 1] * (1 - k)
  }
  return result
}

// ---------------------------------------------------------------------------
// SMA — Simple Moving Average
// ---------------------------------------------------------------------------
export function calculateSMA(prices: OHLCV[], period: number): number[] {
  const closes = prices.map((p) => p.close)
  const result: number[] = new Array(closes.length).fill(NaN)

  for (let i = period - 1; i < closes.length; i++) {
    let sum = 0
    for (let j = 0; j < period; j++) sum += closes[i - j]
    result[i] = sum / period
  }
  return result
}

// ---------------------------------------------------------------------------
// RSI — Relative Strength Index (Wilder's smoothing)
// ---------------------------------------------------------------------------
export function calculateRSI(prices: OHLCV[], period: number = 14): number[] {
  const closes = prices.map((p) => p.close)
  const result: number[] = new Array(closes.length).fill(NaN)
  if (closes.length <= period) return result

  let avgGain = 0
  let avgLoss = 0

  // Initial average gain/loss over first `period` changes
  for (let i = 1; i <= period; i++) {
    const change = closes[i] - closes[i - 1]
    if (change > 0) avgGain += change
    else avgLoss += Math.abs(change)
  }
  avgGain /= period
  avgLoss /= period

  const rs = avgLoss === 0 ? 100 : avgGain / avgLoss
  result[period] = 100 - 100 / (1 + rs)

  // Wilder's smoothing for subsequent values
  for (let i = period + 1; i < closes.length; i++) {
    const change = closes[i] - closes[i - 1]
    const gain = change > 0 ? change : 0
    const loss = change < 0 ? Math.abs(change) : 0
    avgGain = (avgGain * (period - 1) + gain) / period
    avgLoss = (avgLoss * (period - 1) + loss) / period
    const rs2 = avgLoss === 0 ? 100 : avgGain / avgLoss
    result[i] = 100 - 100 / (1 + rs2)
  }
  return result
}

// ---------------------------------------------------------------------------
// MACD — Moving Average Convergence Divergence
// ---------------------------------------------------------------------------
export function calculateMACD(
  prices: OHLCV[],
  fastPeriod: number = 12,
  slowPeriod: number = 26,
  signalPeriod: number = 9
): MACDResult {
  const fastEMA = calculateEMA(prices, fastPeriod)
  const slowEMA = calculateEMA(prices, slowPeriod)
  const n = prices.length

  const macdLine: number[] = new Array(n).fill(NaN)
  for (let i = slowPeriod - 1; i < n; i++) {
    if (!isNaN(fastEMA[i]) && !isNaN(slowEMA[i])) {
      macdLine[i] = fastEMA[i] - slowEMA[i]
    }
  }

  // Signal = EMA of macdLine (using only valid values)
  const signalLine: number[] = new Array(n).fill(NaN)
  const histogram: number[] = new Array(n).fill(NaN)

  // Find first valid MACD index
  const firstValid = macdLine.findIndex((v) => !isNaN(v))
  if (firstValid === -1) return { macdLine, signalLine, histogram }

  const k = 2 / (signalPeriod + 1)

  // Seed signal with SMA of first `signalPeriod` MACD values
  let seedSum = 0
  let seedCount = 0
  let signalStart = -1

  for (let i = firstValid; i < n && seedCount < signalPeriod; i++) {
    if (!isNaN(macdLine[i])) {
      seedSum += macdLine[i]
      seedCount++
      if (seedCount === signalPeriod) {
        signalStart = i
        signalLine[i] = seedSum / signalPeriod
      }
    }
  }

  if (signalStart === -1) return { macdLine, signalLine, histogram }

  for (let i = signalStart + 1; i < n; i++) {
    if (!isNaN(macdLine[i])) {
      signalLine[i] = macdLine[i] * k + signalLine[i - 1] * (1 - k)
    }
  }

  for (let i = 0; i < n; i++) {
    if (!isNaN(macdLine[i]) && !isNaN(signalLine[i])) {
      histogram[i] = macdLine[i] - signalLine[i]
    }
  }

  return { macdLine, signalLine, histogram }
}

// ---------------------------------------------------------------------------
// Bollinger Bands
// ---------------------------------------------------------------------------
export function calculateBollinger(
  prices: OHLCV[],
  period: number = 20,
  stdDevMultiplier: number = 2
): BollingerResult {
  const closes = prices.map((p) => p.close)
  const n = closes.length
  const upper: number[] = new Array(n).fill(NaN)
  const middle: number[] = new Array(n).fill(NaN)
  const lower: number[] = new Array(n).fill(NaN)

  for (let i = period - 1; i < n; i++) {
    const slice = closes.slice(i - period + 1, i + 1)
    const avg = slice.reduce((a, b) => a + b, 0) / period
    const variance = slice.reduce((a, b) => a + (b - avg) ** 2, 0) / period
    const stdDev = Math.sqrt(variance)
    middle[i] = avg
    upper[i] = avg + stdDevMultiplier * stdDev
    lower[i] = avg - stdDevMultiplier * stdDev
  }

  return { upper, middle, lower }
}

// ---------------------------------------------------------------------------
// ATR — Average True Range (Wilder's smoothing)
// ---------------------------------------------------------------------------
export function calculateATR(prices: OHLCV[], period: number = 14): number[] {
  const n = prices.length
  const result: number[] = new Array(n).fill(NaN)
  if (n < period + 1) return result

  const trueRanges: number[] = [NaN]
  for (let i = 1; i < n; i++) {
    const hl = prices[i].high - prices[i].low
    const hc = Math.abs(prices[i].high - prices[i - 1].close)
    const lc = Math.abs(prices[i].low - prices[i - 1].close)
    trueRanges.push(Math.max(hl, hc, lc))
  }

  // Seed = SMA of first `period` TRs
  let seed = 0
  for (let i = 1; i <= period; i++) seed += trueRanges[i]
  seed /= period
  result[period] = seed

  for (let i = period + 1; i < n; i++) {
    result[i] = (result[i - 1] * (period - 1) + trueRanges[i]) / period
  }
  return result
}

// ---------------------------------------------------------------------------
// ADX — Average Directional Index with +DI / -DI (Wilder's smoothing)
// ---------------------------------------------------------------------------
export function calculateADX(prices: OHLCV[], period: number = 14): ADXResult {
  const n = prices.length
  const adx: number[] = new Array(n).fill(NaN)
  const plusDI: number[] = new Array(n).fill(NaN)
  const minusDI: number[] = new Array(n).fill(NaN)
  if (n < period * 2) return { adx, plusDI, minusDI }

  const plusDM: number[] = [NaN]
  const minusDM: number[] = [NaN]
  const tr: number[] = [NaN]

  for (let i = 1; i < n; i++) {
    const upMove = prices[i].high - prices[i - 1].high
    const downMove = prices[i - 1].low - prices[i].low
    plusDM.push(upMove > downMove && upMove > 0 ? upMove : 0)
    minusDM.push(downMove > upMove && downMove > 0 ? downMove : 0)
    tr.push(Math.max(
      prices[i].high - prices[i].low,
      Math.abs(prices[i].high - prices[i - 1].close),
      Math.abs(prices[i].low - prices[i - 1].close)
    ))
  }

  // Wilder smooth
  const smooth = (arr: number[], p: number): number[] => {
    const out: number[] = new Array(arr.length).fill(NaN)
    let seed = 0
    for (let i = 1; i <= p; i++) seed += arr[i]
    out[p] = seed
    for (let i = p + 1; i < arr.length; i++) {
      out[i] = out[i - 1] - out[i - 1] / p + arr[i]
    }
    return out
  }

  const smTR = smooth(tr, period)
  const smPDM = smooth(plusDM, period)
  const smMDM = smooth(minusDM, period)

  const dx: number[] = new Array(n).fill(NaN)
  for (let i = period; i < n; i++) {
    if (smTR[i] === 0) continue
    plusDI[i] = 100 * smPDM[i] / smTR[i]
    minusDI[i] = 100 * smMDM[i] / smTR[i]
    const diDiff = Math.abs(plusDI[i] - minusDI[i])
    const diSum = plusDI[i] + minusDI[i]
    dx[i] = diSum === 0 ? 0 : 100 * diDiff / diSum
  }

  // ADX = smoothed DX
  let adxSeed = 0
  let count = 0
  for (let i = period; i < n && count < period; i++) {
    if (!isNaN(dx[i])) { adxSeed += dx[i]; count++ }
  }
  if (count < period) return { adx, plusDI, minusDI }

  const adxStart = period + period - 1
  adx[adxStart] = adxSeed / period

  for (let i = adxStart + 1; i < n; i++) {
    if (!isNaN(dx[i])) {
      adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period
    }
  }

  return { adx, plusDI, minusDI }
}

// ---------------------------------------------------------------------------
// Stochastic Oscillator (%K and %D)
// ---------------------------------------------------------------------------
export function calculateStochastic(
  prices: OHLCV[],
  kPeriod: number = 14,
  kSmoothing: number = 3,
  dPeriod: number = 3
): StochasticResult {
  const n = prices.length
  const rawK: number[] = new Array(n).fill(NaN)
  const k: number[] = new Array(n).fill(NaN)
  const d: number[] = new Array(n).fill(NaN)

  for (let i = kPeriod - 1; i < n; i++) {
    const slice = prices.slice(i - kPeriod + 1, i + 1)
    const highestHigh = Math.max(...slice.map((p) => p.high))
    const lowestLow = Math.min(...slice.map((p) => p.low))
    const range = highestHigh - lowestLow
    rawK[i] = range === 0 ? 50 : ((prices[i].close - lowestLow) / range) * 100
  }

  // Smooth %K
  for (let i = kPeriod + kSmoothing - 2; i < n; i++) {
    let sum = 0
    let valid = 0
    for (let j = 0; j < kSmoothing; j++) {
      if (!isNaN(rawK[i - j])) { sum += rawK[i - j]; valid++ }
    }
    if (valid === kSmoothing) k[i] = sum / kSmoothing
  }

  // %D = SMA of smoothed %K
  for (let i = kPeriod + kSmoothing + dPeriod - 3; i < n; i++) {
    let sum = 0
    let valid = 0
    for (let j = 0; j < dPeriod; j++) {
      if (!isNaN(k[i - j])) { sum += k[i - j]; valid++ }
    }
    if (valid === dPeriod) d[i] = sum / dPeriod
  }

  return { k, d }
}

// ---------------------------------------------------------------------------
// OBV — On Balance Volume
// ---------------------------------------------------------------------------
export function calculateOBV(prices: OHLCV[]): number[] {
  const result: number[] = new Array(prices.length).fill(NaN)
  if (prices.length === 0) return result

  result[0] = prices[0].volume
  for (let i = 1; i < prices.length; i++) {
    if (prices[i].close > prices[i - 1].close) {
      result[i] = result[i - 1] + prices[i].volume
    } else if (prices[i].close < prices[i - 1].close) {
      result[i] = result[i - 1] - prices[i].volume
    } else {
      result[i] = result[i - 1]
    }
  }
  return result
}

// ---------------------------------------------------------------------------
// VWAP — Volume Weighted Average Price (rolling daily reset per bar)
// ---------------------------------------------------------------------------
export function calculateVWAP(prices: OHLCV[]): number[] {
  const result: number[] = []
  let cumulativeTPV = 0
  let cumulativeVolume = 0

  for (const bar of prices) {
    const typicalPrice = (bar.high + bar.low + bar.close) / 3
    cumulativeTPV += typicalPrice * bar.volume
    cumulativeVolume += bar.volume
    result.push(cumulativeVolume === 0 ? typicalPrice : cumulativeTPV / cumulativeVolume)
  }
  return result
}

// ---------------------------------------------------------------------------
// Volume Average
// ---------------------------------------------------------------------------
export function calculateVolumeAverage(prices: OHLCV[], period: number = 20): number[] {
  const n = prices.length
  const result: number[] = new Array(n).fill(NaN)
  for (let i = period - 1; i < n; i++) {
    let sum = 0
    for (let j = 0; j < period; j++) sum += prices[i - j].volume
    result[i] = sum / period
  }
  return result
}

// ---------------------------------------------------------------------------
// Fibonacci Retracement Levels
// ---------------------------------------------------------------------------
export function calculateFibonacci(prices: OHLCV[]): FibonacciLevels {
  const highs = prices.map((p) => p.high)
  const lows = prices.map((p) => p.low)
  const high = Math.max(...highs)
  const low = Math.min(...lows)
  const range = high - low

  return {
    high,
    low,
    level0: high,
    level236: high - range * 0.236,
    level382: high - range * 0.382,
    level500: high - range * 0.5,
    level618: high - range * 0.618,
    level786: high - range * 0.786,
    level1000: low,
  }
}

// ---------------------------------------------------------------------------
// MFI — Money Flow Index (period default 14)
// ---------------------------------------------------------------------------
export function calculateMFI(prices: OHLCV[], period: number = 14): number[] {
  const n = prices.length
  const result: number[] = new Array(n).fill(NaN)
  if (n < period + 1) return result

  const tp  = prices.map((p) => (p.high + p.low + p.close) / 3)
  const rmf = prices.map((p, i) => tp[i] * p.volume)   // raw money flow

  for (let i = period; i < n; i++) {
    let posFlow = 0
    let negFlow = 0
    for (let j = i - period + 1; j <= i; j++) {
      if (tp[j] > tp[j - 1]) posFlow += rmf[j]
      else                    negFlow += rmf[j]
    }
    result[i] = negFlow === 0 ? 100 : 100 - 100 / (1 + posFlow / negFlow)
  }
  return result
}

// ---------------------------------------------------------------------------
// OBV Moving Average
// ---------------------------------------------------------------------------
export function calculateOBVMA(obv: number[], period: number = 20): number[] {
  const n = obv.length
  const result: number[] = new Array(n).fill(NaN)
  for (let i = period - 1; i < n; i++) {
    let sum = 0, count = 0
    for (let j = i - period + 1; j <= i; j++) {
      if (!isNaN(obv[j])) { sum += obv[j]; count++ }
    }
    if (count > 0) result[i] = sum / count
  }
  return result
}

// ---------------------------------------------------------------------------
// VCP — Volatility Contraction Pattern (Minervini)
// Returns: weekly range % per stage, pivot price, contraction flag
// ---------------------------------------------------------------------------
export function calculateVCP(prices: OHLCV[], weeks: number = 4): VCPResult {
  const barsPerWeek = 5
  const needed = weeks * barsPerWeek
  const empty: VCPResult = { stages: [], pivot: 0, isContracting: false, score: 0 }
  if (prices.length < needed) return empty

  const window = prices.slice(-needed)
  const stages: number[] = []

  for (let w = 0; w < weeks; w++) {
    const segment = window.slice(w * barsPerWeek, (w + 1) * barsPerWeek)
    const hi = Math.max(...segment.map((p) => p.high))
    const lo = Math.min(...segment.map((p) => p.low))
    stages.push(lo > 0 ? (hi - lo) / lo : 0)
  }

  // Pivot = highest high of the LAST (tightest) stage
  const lastSeg = window.slice(-barsPerWeek)
  const pivot = Math.max(...lastSeg.map((p) => p.high))

  // Check monotone contraction
  let contracting = true
  for (let i = 1; i < stages.length; i++) {
    if (stages[i] >= stages[i - 1]) { contracting = false; break }
  }

  // Score: how much did volatility shrink? ideal: >=50% reduction from first to last
  const shrinkage = stages[0] > 0 ? 1 - stages[stages.length - 1] / stages[0] : 0
  const score = contracting ? Math.min(100, shrinkage * 120) : Math.max(0, shrinkage * 40)

  return { stages, pivot, isContracting: contracting, score }
}

// ---------------------------------------------------------------------------
// Master calculator — runs all indicators in one pass
// ---------------------------------------------------------------------------
export function calculateAllIndicators(prices: OHLCV[]): TechnicalIndicators {
  const obv = calculateOBV(prices)
  return {
    ema20: calculateEMA(prices, 20),
    ema50: calculateEMA(prices, 50),
    ema150: calculateEMA(prices, 150),
    ema200: calculateEMA(prices, 200),
    sma50: calculateSMA(prices, 50),
    sma200: calculateSMA(prices, 200),
    rsi14: calculateRSI(prices, 14),
    macd: calculateMACD(prices, 12, 26, 9),
    bollinger: calculateBollinger(prices, 20, 2),
    atr14: calculateATR(prices, 14),
    adx14: calculateADX(prices, 14),
    stochastic: calculateStochastic(prices, 14, 3, 3),
    obv,
    obvMA20: calculateOBVMA(obv, 20),
    mfi14: calculateMFI(prices, 14),
    vwap: calculateVWAP(prices),
    volume20avg: calculateVolumeAverage(prices, 20),
    fibonacci: calculateFibonacci(prices),
    vcp: calculateVCP(prices, 4),
  }
}
