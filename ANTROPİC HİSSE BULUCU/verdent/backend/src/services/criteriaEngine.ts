import { prisma } from '../lib/prisma'
import { dataService } from './dataService'
import { calculateAllIndicators } from '../utils/indicators'
import { BETA_V2_CONFIG } from './criteria/betaCriteriaV2'
import { DELTA_V2_CONFIG } from './criteria/deltaCriteriaV2'
import type {
  OHLCV,
  StockData,
  ScoredStock,
  SignalDetail,
  Portfolio,
  CriteriaConfig,
  CriteriaType,
  FilterRule,
} from '../types/market'


// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

// Approximate beta: covariance(stock, index) / variance(index) over last 60 days
function approximateBeta(stockPrices: OHLCV[], indexPrices: OHLCV[]): number | null {
  const window = 60
  if (stockPrices.length < window + 1 || indexPrices.length < window + 1) return null

  const sReturns: number[] = []
  const iReturns: number[] = []
  const sSlice = stockPrices.slice(-window - 1)
  const iSlice = indexPrices.slice(-window - 1)

  for (let i = 1; i < sSlice.length; i++) {
    sReturns.push((sSlice[i].close - sSlice[i - 1].close) / sSlice[i - 1].close)
    iReturns.push((iSlice[i].close - iSlice[i - 1].close) / iSlice[i - 1].close)
  }

  const sAvg = sReturns.reduce((a, b) => a + b, 0) / sReturns.length
  const iAvg = iReturns.reduce((a, b) => a + b, 0) / iReturns.length

  let cov = 0
  let iVar = 0
  for (let i = 0; i < sReturns.length; i++) {
    cov  += (sReturns[i] - sAvg) * (iReturns[i] - iAvg)
    iVar += (iReturns[i] - iAvg) ** 2
  }

  return iVar === 0 ? null : cov / iVar
}

// Relative strength: stock return / index return over 90 days
function relativeStrength(stockPrices: OHLCV[], indexPrices: OHLCV[]): number | null {
  if (stockPrices.length < 90 || indexPrices.length < 90) return null
  const sStart = stockPrices[stockPrices.length - 90].close
  const sEnd   = stockPrices[stockPrices.length - 1].close
  const iStart = indexPrices[indexPrices.length - 90].close
  const iEnd   = indexPrices[indexPrices.length - 1].close
  const iReturn = (iEnd - iStart) / iStart
  if (iReturn === 0) return null
  const sReturn = (sEnd - sStart) / sStart
  return sReturn / Math.abs(iReturn)
}

// ATR-based stop-loss below last close
function stopLossFromATR(prices: OHLCV[], atr14: number[], multiplier = 2.0): number {
  const close = prices[prices.length - 1]?.close ?? 0
  const atr   = lastValid(atr14) ?? close * 0.02
  return parseFloat((close - multiplier * atr).toFixed(4))
}

// Target price: close + risk-reward * (close - stopLoss)
function targetFromRR(entry: number, stopLoss: number, rr = 2.5): number {
  const risk = entry - stopLoss
  return parseFloat((entry + rr * risk).toFixed(4))
}

// Normalise raw score (sum of weights of passing rules) to 0-100
function normaliseScore(rawPoints: number, maxPossible: number): number {
  if (maxPossible === 0) return 0
  return parseFloat(Math.min(100, Math.max(0, (rawPoints / maxPossible) * 100)).toFixed(1))
}

// ---------------------------------------------------------------------------
// ===  ALFA  === (Patlamaya Hazır — VCP / Minervini Momentum)
// 5 şart, her biri 20 puan. Toplam 100 üzerinden puanlama.
// ---------------------------------------------------------------------------
const ALFA_TECHNICAL: FilterRule[] = [
  // ── 1. RS Sırası ≥ 80 ──────────────────────────────────────────────────
  {
    name: 'rsRank',
    weight: 20,
    check: (s) => {
      const rank   = s.rsRank             // 0-100 percentile (post-assembly)
      const passed = rank >= 80
      return {
        passed,
        value: rank,
        description: `RS Sırası = ${rank.toFixed(0)} — ${passed ? '≥80 ✓ güçlü' : '<80 ✗ zayıf'} (piyasanın %${rank.toFixed(0)}'ndan güçlü)`,
      }
    },
  },
  // ── 2. VCP — Volatilite Daralması ──────────────────────────────────────
  {
    name: 'vcpContraction',
    weight: 20,
    check: (s) => {
      const vcp    = s.indicators.vcp
      const passed = vcp.isContracting && vcp.stages.length >= 3
      const last   = vcp.stages[vcp.stages.length - 1]
      const first  = vcp.stages[0]
      return {
        passed,
        value: parseFloat((vcp.score).toFixed(1)),
        description: `VCP ${passed ? '✓ Daralıyor' : '✗ Daralma yok'} — Aşamalar: ${vcp.stages.map((s) => (s * 100).toFixed(1) + '%').join(' → ')} | Pivot: ${vcp.pivot.toFixed(2)} | İlk→Son: ${first > 0 ? ((1 - last / first) * 100).toFixed(0) + '% daralma' : 'n/a'}`,
      }
    },
  },
  // ── 3. MFI > 60 — Para Akışı Pozitif ───────────────────────────────────
  {
    name: 'mfiPositive',
    weight: 20,
    check: (s) => {
      const mfi    = lastValid(s.indicators.mfi14)
      const passed = mfi !== null && mfi > 60
      return {
        passed,
        value: mfi,
        description: `MFI(14) = ${mfi?.toFixed(1) ?? 'n/a'} — ${passed ? '> 60 ✓ para akışı güçlü' : '≤ 60 ✗ para akışı zayıf'}`,
      }
    },
  },
  // ── 4. OBV Yükselen Trend (MA üzerinde) ────────────────────────────────
  {
    name: 'obvRising',
    weight: 20,
    check: (s) => {
      const obv     = lastValid(s.indicators.obv)
      const obvMA   = lastValid(s.indicators.obvMA20)
      const obvPrev = nthFromEnd(s.indicators.obv, 5)     // 5 bar önce
      const aboveMA = obv !== null && obvMA !== null && obv > obvMA
      const rising  = obv !== null && obvPrev !== null && obv > obvPrev
      const passed  = aboveMA && rising
      return {
        passed,
        value: obv !== null && obvMA !== null ? parseFloat(((obv - obvMA) / Math.abs(obvMA || 1) * 100).toFixed(1)) : null,
        description: `OBV ${aboveMA ? '> MA20 ✓' : '< MA20 ✗'} ve ${rising ? 'yükseliyor ✓' : 'düşüyor ✗'} — MA'nın ${obv !== null && obvMA !== null ? Math.abs(((obv - obvMA) / Math.abs(obvMA || 1)) * 100).toFixed(1) : 'n/a'}% ${aboveMA ? 'üzerinde' : 'altında'}`,
      }
    },
  },
  // ── 5. Pivot Kırılımı — Fiyat VCP Pivot'u Aşıyor, Hacim ≥1.5x ─────────
  {
    name: 'pivotBreakout',
    weight: 20,
    check: (s) => {
      const close    = s.prices[s.prices.length - 1]?.close ?? 0
      const pivot    = s.indicators.vcp.pivot
      const vol20avg = lastValid(s.indicators.volume20avg) ?? 0
      const lastVol  = s.prices[s.prices.length - 1]?.volume ?? 0
      const volRatio = vol20avg > 0 ? lastVol / vol20avg : 0

      const abovePivot = pivot > 0 && close > pivot
      const volOK      = volRatio >= 1.5
      const passed     = abovePivot && volOK

      // Partial credit: yakın kırılım (pivot'un %2 altında) + yüksek hacim
      const nearBreakout = pivot > 0 && close >= pivot * 0.98 && volRatio >= 1.2
      return {
        passed: passed || (nearBreakout && !passed ? false : passed),
        value: parseFloat((volRatio).toFixed(2)),
        description: `Pivot: ${pivot.toFixed(2)} | Fiyat: ${close.toFixed(2)} ${abovePivot ? '↑ KIRILIM ✓' : '≤ pivot ✗'} | Hacim: ${volRatio.toFixed(2)}x ort ${volOK ? '✓' : '✗ (<1.5x)'}`,
      }
    },
  },
]

// ALFA temel filtreler — VCP setinde minimal (trend konfirmasyonu)
const ALFA_FUNDAMENTAL: FilterRule[] = [
  {
    name: 'revenueGrowth', weight: 10,
    check: (s) => {
      const val    = s.fundamentals.revenueGrowth
      const passed = val !== null && val > 0.15
      return { passed, value: val !== null ? val * 100 : null, description: `Revenue growth ${val !== null ? (val * 100).toFixed(1) + '%' : 'n/a'} — need > 15%` }
    },
  },
  {
    name: 'earningsGrowth', weight: 10,
    check: (s) => {
      const val    = s.fundamentals.earningsGrowth
      const passed = val !== null && val > 0.10
      return { passed, value: val !== null ? val * 100 : null, description: `Earnings growth ${val !== null ? (val * 100).toFixed(1) + '%' : 'n/a'} — need > 10%` }
    },
  },
  {
    name: 'roeStrength', weight: 5,
    check: (s) => {
      const val    = s.fundamentals.roe
      const passed = val !== null && val > 0.15
      return { passed, value: val !== null ? val * 100 : null, description: `ROE ${val !== null ? (val * 100).toFixed(1) + '%' : 'n/a'} — need > 15%` }
    },
  },
  {
    name: 'lowDebt', weight: 5,
    check: (s) => {
      const val    = s.fundamentals.debtEquity
      const passed = val !== null && val < 1.5
      return { passed, value: val, description: `D/E ratio ${val?.toFixed(2) ?? 'n/a'} — need < 1.5` }
    },
  },
  {
    name: 'freeCashFlow', weight: 5,
    check: (s) => {
      const val    = s.fundamentals.freeCashFlow
      const passed = val !== null && val > 0
      return { passed, value: val, description: `FCF ${val !== null ? '$' + (val / 1e9).toFixed(2) + 'B' : 'n/a'} — must be positive` }
    },
  },
]

// ---------------------------------------------------------------------------
// ===  BETA  === (Bear — Defensive / Value)
// ---------------------------------------------------------------------------
const BETA_TECHNICAL: FilterRule[] = [
  {
    name: 'relativeStrength', weight: 20,
    check: (s) => {
      const rs     = s.relativeStrength
      const passed = rs !== null && rs > 1.0
      return { passed, value: rs, description: `Relative strength vs index = ${rs?.toFixed(2) ?? 'n/a'} — need > 1.0` }
    },
  },
  {
    name: 'lowBeta', weight: 10,
    check: (s) => {
      const beta   = s.beta
      const passed = beta !== null && beta < 0.8
      return { passed, value: beta, description: `Beta = ${beta?.toFixed(2) ?? 'n/a'} — need < 0.8 (defensive)` }
    },
  },
  {
    name: 'rsiNotInFreefall', weight: 10,
    check: (s) => {
      const rsi    = lastValid(s.indicators.rsi14)
      const passed = rsi !== null && rsi >= 30
      return { passed, value: rsi, description: `RSI(14) = ${rsi?.toFixed(1) ?? 'n/a'} — must not be below 30` }
    },
  },
  {
    name: 'supportLevel', weight: 10,
    check: (s) => {
      // Price within 3% of Fibonacci 61.8% support
      const fib    = s.indicators.fibonacci
      const close  = s.prices[s.prices.length - 1]?.close ?? 0
      const f618   = fib.level618
      const pctDiff = Math.abs(close - f618) / f618
      const passed  = pctDiff <= 0.03
      return { passed, value: parseFloat((pctDiff * 100).toFixed(2)), description: `Price ${(pctDiff * 100).toFixed(2)}% from Fib 61.8% support (${f618.toFixed(2)}) — need ≤3%` }
    },
  },
  {
    name: 'stochasticOversoldCrossing', weight: 10,
    check: (s) => {
      const k      = lastValid(s.indicators.stochastic.k)
      const d      = lastValid(s.indicators.stochastic.d)
      const prevK  = nthFromEnd(s.indicators.stochastic.k, 1)
      const prevD  = nthFromEnd(s.indicators.stochastic.d, 1)
      const isOversold = k !== null && k < 20
      const isCrossUp  = k !== null && d !== null && prevK !== null && prevD !== null && k > d && prevK <= prevD
      const passed = isOversold && isCrossUp
      return { passed, value: k, description: `Stoch %K=${k?.toFixed(1) ?? 'n/a'} — ${passed ? 'oversold+crossing up' : 'not oversold crossing up'}` }
    },
  },
  {
    name: 'bollingerLowerBand', weight: 8,
    check: (s) => {
      const lower = lastValid(s.indicators.bollinger.lower)
      const mid   = lastValid(s.indicators.bollinger.middle)
      const close = s.prices[s.prices.length - 1]?.close ?? 0
      if (lower === null || mid === null) return { passed: false, value: null, description: 'Bollinger data unavailable' }
      const bandWidth = mid - lower
      const distFromLower = close - lower
      const pct  = bandWidth > 0 ? distFromLower / bandWidth : 1
      const passed = pct >= 0 && pct <= 0.25  // within 25% of lower band
      return { passed, value: parseFloat((pct * 100).toFixed(1)), description: `Price at ${(pct * 100).toFixed(1)}% from lower to middle BB — need ≤25%` }
    },
  },
  {
    name: 'volumeDecliningOnDownDays', weight: 7,
    check: (s) => {
      // Check last 5 down days: are volumes below 20-day avg?
      const prices   = s.prices.slice(-20)
      const vol20avg = lastValid(s.indicators.volume20avg) ?? 1
      const downDays = prices.filter((p, i) => i > 0 && p.close < prices[i - 1].close)
      if (downDays.length === 0) return { passed: true, value: null, description: 'No recent down days' }
      const lowVolDownDays = downDays.filter((p) => p.volume < vol20avg)
      const ratio  = lowVolDownDays.length / downDays.length
      const passed = ratio >= 0.6
      return { passed, value: parseFloat((ratio * 100).toFixed(1)), description: `${(ratio * 100).toFixed(0)}% of down days had below-avg volume — need ≥60%` }
    },
  },
]

const BETA_FUNDAMENTAL: FilterRule[] = [
  {
    name: 'valuationPE', weight: 8,
    check: (s) => {
      const pe     = s.fundamentals.pe
      const passed = pe !== null && pe > 0 && pe < 15
      return { passed, value: pe, description: `P/E = ${pe?.toFixed(1) ?? 'n/a'} — need < 15 (value)` }
    },
  },
  {
    name: 'lowPB', weight: 5,
    check: (s) => {
      const pb     = s.fundamentals.pb
      const passed = pb !== null && pb < 1.5
      return { passed, value: pb, description: `P/B = ${pb?.toFixed(2) ?? 'n/a'} — need < 1.5` }
    },
  },
  {
    name: 'lowLeverage', weight: 8,
    check: (s) => {
      const de     = s.fundamentals.debtEquity
      const passed = de !== null && de < 0.5
      return { passed, value: de, description: `D/E = ${de?.toFixed(2) ?? 'n/a'} — need < 0.5 (conservative)` }
    },
  },
  {
    name: 'roeDefensive', weight: 7,
    check: (s) => {
      const roe    = s.fundamentals.roe
      const passed = roe !== null && roe > 0.12
      return { passed, value: roe !== null ? roe * 100 : null, description: `ROE = ${roe !== null ? (roe * 100).toFixed(1) + '%' : 'n/a'} — need > 12%` }
    },
  },
  {
    name: 'positiveFCF', weight: 7,
    check: (s) => {
      const fcf    = s.fundamentals.freeCashFlow
      const passed = fcf !== null && fcf > 0
      return { passed, value: fcf, description: `FCF ${fcf !== null ? (fcf > 0 ? 'positive' : 'negative') : 'n/a'} — must be positive` }
    },
  },
]

// ---------------------------------------------------------------------------
// ===  DELTA  === (Sideways — Mean Reversion / Range)
// ---------------------------------------------------------------------------
const DELTA_TECHNICAL: FilterRule[] = [
  {
    name: 'rangeBoundADX', weight: 15,
    check: (s) => {
      const adx    = lastValid(s.indicators.adx14.adx)
      const passed = adx !== null && adx < 20
      return { passed, value: adx, description: `ADX(14) = ${adx?.toFixed(1) ?? 'n/a'} — need < 20 (range-bound)` }
    },
  },
  {
    name: 'bollingerOversold', weight: 15,
    check: (s) => {
      const lower = lastValid(s.indicators.bollinger.lower)
      const close = s.prices[s.prices.length - 1]?.close ?? 0
      const mid   = lastValid(s.indicators.bollinger.middle)
      if (lower === null || mid === null) return { passed: false, value: null, description: 'Bollinger unavailable' }
      const bandWidth = mid - lower
      const distFromLower = close - lower
      const pct   = bandWidth > 0 ? distFromLower / bandWidth : 1
      const passed = pct >= 0 && pct <= 0.20
      return { passed, value: parseFloat((pct * 100).toFixed(1)), description: `Price at ${(pct * 100).toFixed(1)}% from lower BB — need ≤20%` }
    },
  },
  {
    name: 'rsiOversoldRecovery', weight: 15,
    check: (s) => {
      const rsi    = lastValid(s.indicators.rsi14)
      const passed = rsi !== null && rsi >= 30 && rsi <= 45
      return { passed, value: rsi, description: `RSI(14) = ${rsi?.toFixed(1) ?? 'n/a'} — target 30-45 (oversold recovery)` }
    },
  },
  {
    name: 'stochasticOversold', weight: 10,
    check: (s) => {
      const k      = lastValid(s.indicators.stochastic.k)
      const passed = k !== null && k < 30
      return { passed, value: k, description: `Stoch %K = ${k?.toFixed(1) ?? 'n/a'} — need < 30` }
    },
  },
  {
    name: 'supportLevel', weight: 10,
    check: (s) => {
      // Price within 2% of 52-week low support
      const close  = s.prices[s.prices.length - 1]?.close ?? 0
      const fib382 = s.indicators.fibonacci.level382
      const pct    = Math.abs(close - fib382) / fib382
      const passed = pct <= 0.04
      return { passed, value: parseFloat((pct * 100).toFixed(2)), description: `Price ${(pct * 100).toFixed(2)}% from Fib 38.2% (${fib382.toFixed(2)}) — need ≤4%` }
    },
  },
  {
    name: 'vwapProximity', weight: 10,
    check: (s) => {
      const vwap   = lastValid(s.indicators.vwap)
      const close  = s.prices[s.prices.length - 1]?.close ?? 0
      if (vwap === null) return { passed: false, value: null, description: 'VWAP unavailable' }
      const pct    = (vwap - close) / vwap  // positive = price below VWAP
      const passed = pct > 0 && pct <= 0.03  // below VWAP but within 3%
      return { passed, value: parseFloat((pct * 100).toFixed(2)), description: `Price ${pct > 0 ? (pct * 100).toFixed(2) + '% below' : 'above'} VWAP — need 0-3% below` }
    },
  },
  {
    name: 'volumeCapitulation', weight: 10,
    check: (s) => {
      // Most recent bar has volume ≥ 2× average (capitulation spike)
      const lastVol  = s.prices[s.prices.length - 1]?.volume ?? 0
      const vol20avg = lastValid(s.indicators.volume20avg) ?? 1
      const ratio    = lastVol / vol20avg
      const passed   = ratio >= 2.0
      return { passed, value: parseFloat(ratio.toFixed(2)), description: `Volume ${ratio.toFixed(2)}x 20-day avg — need ≥2x (capitulation)` }
    },
  },
]

const DELTA_FUNDAMENTAL: FilterRule[] = [
  {
    name: 'fairValuation', weight: 10,
    check: (s) => {
      const pe     = s.fundamentals.pe
      const passed = pe !== null && pe >= 10 && pe <= 20
      return { passed, value: pe, description: `P/E = ${pe?.toFixed(1) ?? 'n/a'} — target 10-20 (fair value)` }
    },
  },
  {
    name: 'roeSolid', weight: 5,
    check: (s) => {
      const roe    = s.fundamentals.roe
      const passed = roe !== null && roe > 0.10
      return { passed, value: roe !== null ? roe * 100 : null, description: `ROE = ${roe !== null ? (roe * 100).toFixed(1) + '%' : 'n/a'} — need > 10%` }
    },
  },
  {
    name: 'balanceSheetStrength', weight: 5,
    check: (s) => {
      const de     = s.fundamentals.debtEquity
      const fcf    = s.fundamentals.freeCashFlow
      const passed = de !== null && fcf !== null && de < 0.8 && fcf > 0
      return { passed, value: de, description: `D/E=${de?.toFixed(2) ?? 'n/a'}, FCF=${fcf !== null ? (fcf > 0 ? 'positive' : 'negative') : 'n/a'} — need D/E<0.8 & FCF>0` }
    },
  },
]

// ---------------------------------------------------------------------------
// Criteria config registry
// ---------------------------------------------------------------------------

// ALFA VCP config — built from lokal rules defined above
const ALFA_VCP_CONFIG: CriteriaConfig = {
  name:             'ALFA',
  description:      'Patlamaya Hazır — VCP / Minervini Momentum (RS Sırası, VCP Daralma, MFI, OBV, Pivot Kırılım)',
  marketCondition:  'BULL',
  technicalFilters: ALFA_TECHNICAL,
  fundamentalFilters: ALFA_FUNDAMENTAL,
  entryRules:       {
    minScore:       40,
    maxPositions:   5,
    positionSize:   0.20,
    stopLossPercent: 0.12,
  },
  exitRules: {
    takeProfit:    null,
    stopLoss:      0.12,
    rebalanceSell: true,
  },
}

export const CRITERIA_CONFIGS: Record<CriteriaType, CriteriaConfig> = {
  ALFA:  ALFA_VCP_CONFIG,
  BETA:  BETA_V2_CONFIG,
  DELTA: DELTA_V2_CONFIG,
}

// ---------------------------------------------------------------------------
// Core scoring
// ---------------------------------------------------------------------------
export function calculateScore(stock: StockData, config: CriteriaConfig): {
  score: number
  technicalSignals: SignalDetail[]
  fundamentalSignals: SignalDetail[]
} {
  const allRules = [...config.technicalFilters, ...config.fundamentalFilters]
  const maxPossible = allRules.reduce((s, r) => s + r.weight, 0)

  const evaluate = (rules: FilterRule[]): SignalDetail[] =>
    rules.map((rule) => {
      const { passed, value, description } = rule.check(stock)
      return {
        name:        rule.name,
        value,
        threshold:   null,
        passed,
        weight:      rule.weight,
        contribution: passed ? rule.weight : 0,
        description,
      }
    })

  const technicalSignals    = evaluate(config.technicalFilters)
  const fundamentalSignals  = evaluate(config.fundamentalFilters)
  const rawPoints           = [...technicalSignals, ...fundamentalSignals].reduce((s, d) => s + d.contribution, 0)

  return {
    score: normaliseScore(rawPoints, maxPossible),
    technicalSignals,
    fundamentalSignals,
  }
}

// ---------------------------------------------------------------------------
// Filter: hard-fail stocks that miss critical technical filters
// ---------------------------------------------------------------------------
export function applyFilters(stocks: StockData[], filters: FilterRule[], threshold = 0.50): StockData[] {
  // A stock passes if it meets >= threshold% of APPLICABLE filter weight.
  return stocks.filter((stock) => {
    let totalWeight   = 0
    let passingWeight = 0
    for (const f of filters) {
      const result = f.check(stock)
      if (result.value === null || result.value === undefined) continue
      totalWeight   += f.weight
      if (result.passed) passingWeight += f.weight
    }
    if (totalWeight === 0) return false
    return passingWeight / totalWeight >= threshold
  })
}

// ---------------------------------------------------------------------------
// Rank: sort descending by score, assign rank
// ---------------------------------------------------------------------------
export function rankStocks(scoredStocks: ScoredStock[]): ScoredStock[] {
  return scoredStocks
    .slice()
    .sort((a, b) => b.score - a.score)
    .map((s, i) => ({ ...s, rank: i + 1 }))
}

// ---------------------------------------------------------------------------
// Assemble full StockData bundle for a symbol
// ---------------------------------------------------------------------------
async function assembleStockData(
  symbol: string,
  name: string,
  market: string,
  indexPrices: OHLCV[],
  asOfDate?: Date
): Promise<StockData | null> {
  try {
    const endDate   = asOfDate ?? new Date()
    const startDate = new Date(endDate)
    startDate.setDate(startDate.getDate() - 430)

    const [prices, fundamentalsResult] = await Promise.all([
      dataService.fetchStockPrice(symbol, startDate, endDate, '1d'),
      dataService.fetchFundamentals(symbol).catch(() => null),
    ])

    // Compute 52wk H/L from already-fetched prices (no extra API call, no look-ahead bias)
    const last252 = prices.slice(-252)
    const hw = last252.length > 0
      ? { high: Math.max(...last252.map((p) => p.high)), low: Math.min(...last252.map((p) => p.low)) }
      : { high: 0, low: 0 }

    const fundamentals = fundamentalsResult ?? {
      symbol, pe: null, pb: null, roe: null, debtEquity: null,
      revenueGrowth: null, earningsGrowth: null, freeCashFlow: null,
      marketCap: null, updatedAt: new Date(),
    }

    if (prices.length < 50) {
      console.log(`[assembleStockData] ${symbol}: only ${prices.length} prices, skipping`)
      return null
    }

    const indicators = calculateAllIndicators(prices)
    const beta       = approximateBeta(prices, indexPrices)
    const rs         = relativeStrength(prices, indexPrices)

    return {
      symbol,
      name,
      market,
      prices,
      fundamentals,
      indicators,
      high52w: hw.high,
      low52w:  hw.low,
      relativeStrength: rs,
      rsRank: 0,   // filled in by screenStocks after all stocks are assembled
      beta,
    }
  } catch (err) {
    console.error(`[assembleStockData] ${symbol} error:`, (err as Error).message)
    return null
  }
}

// ---------------------------------------------------------------------------
// screenStocks
// ---------------------------------------------------------------------------
export async function screenStocks(
  criteriaType: CriteriaType,
  date: Date,
  market: string
): Promise<ScoredStock[]> {
  const config = CRITERIA_CONFIGS[criteriaType]

  // Fetch symbols from DB (fall back to constituent list)
  const dbStocks = await prisma.stock.findMany({
    where: { market: market.toUpperCase() },
    select: { symbol: true, name: true, market: true },
  })

  const symbolList = dbStocks.length >= 50
    ? dbStocks
    : (market === 'BIST'
        ? await dataService.getBIST100Constituents()
        : await dataService.getSP500Constituents()
      ).map((s) => ({ symbol: s, name: s, market }))

  // Fetch index prices once (shared across all beta/RS calculations)
  const indexSymbol = market === 'BIST' ? 'XU100.IS' : 'SPY'
  const idxEnd   = date ?? new Date()
  const idxStart = new Date(idxEnd)
  idxStart.setDate(idxStart.getDate() - 430)
  const indexPrices = await dataService.fetchStockPrice(indexSymbol, idxStart, idxEnd, '1d').catch(() => [] as OHLCV[])

  // Use full symbol list (prefetch store handles rate limiting during backtests)
  const limitedList = symbolList

  // Assemble data in batches — larger batches when prefetch is active (no API calls)
  const stockDataList: StockData[] = []
  const BATCH = 10
  for (let i = 0; i < limitedList.length; i += BATCH) {
    const batch = limitedList.slice(i, i + BATCH)
    const results = await Promise.allSettled(
      batch.map((s) => assembleStockData(s.symbol, s.name, s.market, indexPrices, date))
    )
    results.forEach((r) => {
      if (r.status === 'fulfilled' && r.value !== null) stockDataList.push(r.value)
      if (r.status === 'rejected') console.error('[screenStocks] assembleStockData error:', r.reason)
    })
    if (i + BATCH < limitedList.length) await new Promise((res) => setTimeout(res, 200))
  }

  // Compute RS Rank: percentile of each stock's relativeStrength among all assembled stocks
  const rsValues = stockDataList.map((s) => s.relativeStrength ?? -Infinity)
  stockDataList.forEach((stock) => {
    const myRS   = stock.relativeStrength ?? -Infinity
    const below  = rsValues.filter((v) => v < myRS).length
    stock.rsRank = rsValues.length > 1
      ? parseFloat(((below / (rsValues.length - 1)) * 100).toFixed(1))
      : 50
  })

  // ── STAGE 2 HARD PRE-FILTER (ALFA/HYBRID only) ──────────────────────────
  // Minervini: sadece Stage 2'deki hisseler satın alınır.
  // Tüm koşullar aynı anda sağlanmalı — biri bile tutmazsa elenir.
  let universe = stockDataList
  if (criteriaType === 'ALFA') {
    universe = stockDataList.filter((s) => {
      const close   = s.prices[s.prices.length - 1]?.close ?? 0
      const ema50   = lastValid(s.indicators.ema50)
      const ema150  = lastValid(s.indicators.ema150)
      const ema200  = lastValid(s.indicators.ema200)
      if (!close || !ema50 || !ema150 || !ema200) return false

      // 1. Fiyat tüm MA'ların üzerinde
      if (close < ema50 || close < ema150 || close < ema200) return false

      // 2. 150 EMA > 200 EMA (Stage 2 hizalama)
      if (ema150 <= ema200) return false

      // 3. 200 EMA yükseliyor: 1 ay (21 gün) veya en azından 2 ay (42 gün) öncesine göre
      const ema200_21ago = nthFromEnd(s.indicators.ema200, 21)
      const ema200_42ago = nthFromEnd(s.indicators.ema200, 42)
      const ema200Rising = (ema200_21ago && ema200 > ema200_21ago) ||
                           (ema200_42ago && ema200 > ema200_42ago)
      if (!ema200Rising) return false

      // 4. Fiyat 52 haftalık en yüksekten %30'dan fazla uzakta değil (önceki: %35)
      if (s.high52w > 0 && close < s.high52w * 0.70) return false

      // 5. Hisse gerçek bir hareket yaptı: 52w high ≥ 52w low × 1.25
      if (s.high52w > 0 && s.low52w > 0 && s.high52w < s.low52w * 1.25) return false

      return true
    })
    console.log(`[screenStocks] Stage 2 filtresi: ${stockDataList.length} hisseden ${universe.length} tanesi Stage 2'de`)
  }

  // Pre-filter: ALFA için %55, diğerleri için %50 eşiği
  const passThreshold = criteriaType === 'ALFA' ? 0.55 : 0.50
  const filtered = applyFilters(universe, config.technicalFilters, passThreshold)

  // Score all passing stocks
  const scored: ScoredStock[] = filtered.map((stock) => {
    const { score, technicalSignals, fundamentalSignals } = calculateScore(stock, config)
    const allSignals  = [...technicalSignals, ...fundamentalSignals]
    const entryPrice  = stock.prices[stock.prices.length - 1]?.close ?? 0
    const stopLoss    = stopLossFromATR(stock.prices, stock.indicators.atr14)
    const targetPrice = targetFromRR(entryPrice, stopLoss, 2.5)
    const rr          = entryPrice - stopLoss > 0 ? (targetPrice - entryPrice) / (entryPrice - stopLoss) : 0

    return {
      symbol: stock.symbol,
      name:   stock.name,
      score,
      rank:   0,
      signals: {
        technical:   technicalSignals,
        fundamental: fundamentalSignals,
        passed: allSignals.filter((d) => d.passed).map((d) => d.name),
        failed: allSignals.filter((d) => !d.passed).map((d) => d.name),
      },
      entryPrice,
      suggestedStopLoss: stopLoss,
      targetPrice,
      riskRewardRatio: parseFloat(rr.toFixed(2)),
    }
  })

  const ranked = rankStocks(scored)

  // Persist scan results to DB
  await persistScanResults(ranked, criteriaType, date, market).catch(() => {/* non-fatal */})

  return ranked
}

// ---------------------------------------------------------------------------
// getTop5Portfolio
// ---------------------------------------------------------------------------
export async function getTop5Portfolio(
  criteriaType: string,
  date: Date,
  market: string
): Promise<Portfolio> {
  const type    = criteriaType as CriteriaType
  const ranked  = await screenStocks(type, date, market)
  const top5    = ranked.slice(0, 5)
  const avgScore = top5.length > 0
    ? parseFloat((top5.reduce((s, x) => s + x.score, 0) / top5.length).toFixed(1))
    : 0

  return {
    criteria:    type,
    date,
    market,
    totalStocks: ranked.length,
    topHoldings: top5,
    avgScore,
    createdAt:   new Date(),
  }
}

// ---------------------------------------------------------------------------
// Persist scan results to DB
// ---------------------------------------------------------------------------
async function persistScanResults(
  ranked: ScoredStock[],
  criteriaType: CriteriaType,
  date: Date,
  market: string
): Promise<void> {
  // Find or create criteria record
  const criteriaRecord = await prisma.criteria.upsert({
    where: { id: `criteria_${criteriaType}` },
    create: {
      id:             `criteria_${criteriaType}`,
      name:           criteriaType,
      displayName:    CRITERIA_CONFIGS[criteriaType].label,
      market:         'ALL',
      description:    CRITERIA_CONFIGS[criteriaType].label,
      rules:          {},
      scoringWeights: {},
      isActive:       true,
    },
    update: {},
  })

  const dayStart = new Date(date)
  dayStart.setHours(0, 0, 0, 0)

  for (const stock of ranked.slice(0, 20)) {
    // Ensure stock record exists
    const stockRecord = await prisma.stock.upsert({
      where:  { symbol: stock.symbol },
      create: { symbol: stock.symbol, name: stock.name, market },
      update: {},
    })

    await prisma.scanResult.upsert({
      where: {
        scanDate_criteriaId_stockId: {
          scanDate:   dayStart,
          criteriaId: criteriaRecord.id,
          stockId:    stockRecord.id,
        },
      },
      create: {
        scanDate:    dayStart,
        criteriaId:  criteriaRecord.id,
        stockId:     stockRecord.id,
        score:       stock.score,
        rank:        stock.rank,
        signals:     stock.signals as object,
        entryPrice:  stock.entryPrice,
        targetPrice: stock.targetPrice,
        stopLoss:    stock.suggestedStopLoss,
      },
      update: {
        score:       stock.score,
        rank:        stock.rank,
        signals:     stock.signals as object,
        entryPrice:  stock.entryPrice,
        targetPrice: stock.targetPrice,
        stopLoss:    stock.suggestedStopLoss,
      },
    })
  }
}
