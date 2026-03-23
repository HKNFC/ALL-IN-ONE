/**
 * BETA Criteria V2 — Professional Bear Market Defense Strategy
 *
 * Research basis:
 *   - Fama-French Value Factor (HML): low P/B, cheap assets survive bear markets
 *   - Low Volatility Anomaly (Baker, Bradley, Wurgler 2011): low-beta stocks outperform
 *   - Piotroski F-Score (2000): 9-point fundamental quality scoring
 *   - Crisis Alpha: stocks that fall less ARE the winners in bear markets
 *
 * Core philosophy: CAPITAL PRESERVATION first, positive returns second.
 * A -5% result when the market falls -30% is exceptional alpha.
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

/** Return from `startBarsAgo` to `endBarsAgo` (0 = last bar). */
function periodReturn(prices: OHLCV[], startBarsAgo: number, endBarsAgo: number): number | null {
  const endIdx   = prices.length - 1 - endBarsAgo
  const startIdx = prices.length - 1 - startBarsAgo
  if (startIdx < 0 || endIdx < 0 || startIdx >= prices.length) return null
  const startClose = prices[startIdx].close
  const endClose   = prices[endIdx].close
  if (!Number.isFinite(startClose) || !Number.isFinite(endClose) || startClose <= 0) return null
  return (endClose - startClose) / startClose
}

/**
 * Maximum drawdown over last `window` bars (returns a negative number).
 * Defined as (trough - peak) / peak.
 */
function maxDrawdown(prices: OHLCV[], window: number): number {
  const slice = prices.slice(-window)
  if (slice.length < 2) return 0
  let peak = slice[0].close
  let mdd  = 0
  for (const bar of slice) {
    if (bar.close > peak) peak = bar.close
    const dd = (bar.close - peak) / peak
    if (dd < mdd) mdd = dd
  }
  return mdd
}

/**
 * Fraction of down-day volume that is below the 20-day average.
 * High ratio = selling is drying up (positive sign in bear market).
 */
function quietDownDayRatio(prices: OHLCV[], vol20avg: number[], window: number): number | null {
  const pSlice = prices.slice(-window)
  const vSlice = vol20avg.slice(-window)
  const downDays = pSlice.filter((p, i) => i > 0 && p.close < pSlice[i - 1].close)
  if (downDays.length === 0) return 1   // no down days = best case
  const avgVol = lastValid(vSlice) ?? 1
  const quietCount = downDays.filter((p) => p.volume < avgVol).length
  return quietCount / downDays.length
}

/**
 * ATR as percentage of close (normalised volatility).
 * Lower value = less volatile stock.
 */
function atrPct(prices: OHLCV[], atr14: number[]): number | null {
  const atr   = lastValid(atr14)
  const close = prices[prices.length - 1]?.close ?? 0
  if (atr === null || close <= 0) return null
  return atr / close
}

/**
 * Piotroski-proxy score (0–9) built from available fundamentals.
 * Uses the 9 checks achievable with our Fundamentals interface.
 */
function piotroskiProxy(s: StockData): number {
  const f = s.fundamentals
  let score = 0

  // PROFITABILITY (4 checks)
  if (f.roe !== null && f.roe > 0)                           score += 1  // ROE > 0 (proxy for ROA > 0)
  if (f.freeCashFlow !== null && f.freeCashFlow > 0)         score += 1  // Operating CF > 0
  if (f.earningsGrowth !== null && f.earningsGrowth > 0)     score += 1  // Earnings improving (ΔROA proxy)
  // Accruals < 0: FCF/NI > 1 means cash earnings exceed accrual earnings
  // We approximate: if earnings growth AND FCF positive, quality is real
  if (f.earningsGrowth !== null && f.earningsGrowth > 0 &&
      f.freeCashFlow   !== null && f.freeCashFlow > 0)       score += 1

  // LEVERAGE & LIQUIDITY (3 checks)
  if (f.debtEquity !== null && f.debtEquity < 0.8)          score += 1  // Low leverage
  if (f.pb !== null && f.pb > 0 && f.pb < 2.5)              score += 1  // Reasonable book (liquidity proxy)
  // No recent share issuance: approximate via low P/B + positive FCF
  if (f.pb !== null && f.freeCashFlow !== null &&
      f.pb < 2.0 && f.freeCashFlow > 0)                     score += 1

  // OPERATING EFFICIENCY (2 checks)
  if (f.revenueGrowth !== null && f.revenueGrowth > 0)      score += 1  // Revenue growing (margin proxy)
  if (f.roe !== null && f.roe > 0.10)                        score += 1  // Asset turnover proxy

  return score
}

// ── FACTOR 1: RELATIVE STRENGTH IN DECLINE (25 pts) ─────────────────────────
// In bear markets, the only stocks worth holding are those declining LESS.
// Recent RS is weighted more heavily (1M > 3M > 6M).

export const BETA_V2_RELATIVE_STRENGTH: FilterRule[] = [
  {
    name: 'rs1monthBear',
    weight: 12,
    check: (s) => {
      // Most recent 1-month RS vs stored relativeStrength (90-day ratio)
      const r1m = periodReturn(s.prices, 21, 0)
      const rs  = s.relativeStrength
      if (r1m === null) return { passed: false, value: null, description: 'RS 1M: insufficient data' }
      // Pass if either recent return is positive OR RS ratio > 1 (beating index)
      const passed = r1m > -0.03 || (rs !== null && rs > 1.0)
      return {
        passed,
        value: parseFloat((r1m * 100).toFixed(1)),
        description: `RS 1M: ${(r1m * 100).toFixed(1)}% | RS ratio: ${rs?.toFixed(2) ?? 'n/a'} — falling less than market`,
      }
    },
  },
  {
    name: 'rs3monthBear',
    weight: 8,
    check: (s) => {
      const r3m = periodReturn(s.prices, 63, 0)
      if (r3m === null) return { passed: false, value: null, description: 'RS 3M: insufficient data' }
      const rs  = s.relativeStrength
      const passed = r3m > -0.08 || (rs !== null && rs > 0.8)
      return {
        passed,
        value: parseFloat((r3m * 100).toFixed(1)),
        description: `RS 3M: ${(r3m * 100).toFixed(1)}% — need relative outperformance`,
      }
    },
  },
  {
    name: 'outperformingMarket',
    weight: 5,
    check: (s) => {
      const rs = s.relativeStrength
      if (rs === null) return { passed: false, value: null, description: 'Relative strength: no data' }
      const passed = rs > 1.0
      return {
        passed,
        value: parseFloat(rs.toFixed(2)),
        description: `Relative strength vs index: ${rs.toFixed(2)} — need > 1.0 (outperforming)`,
      }
    },
  },
]

// ── FACTOR 2: PIOTROSKI FUNDAMENTAL QUALITY (20 pts) ────────────────────────
// Quality gate: only hold financially strong companies in a bear market.

export const BETA_V2_PIOTROSKI: FilterRule[] = [
  {
    name: 'piotroskiScoreHigh',
    weight: 10,
    check: (s) => {
      const score  = piotroskiProxy(s)
      const passed = score >= 6
      return {
        passed,
        value: score,
        description: `Piotroski proxy score: ${score}/9 — need ≥6 (quality gate)`,
      }
    },
  },
  {
    name: 'profitabilityConfirmed',
    weight: 4,
    check: (s) => {
      const roe = s.fundamentals.roe
      const fcf = s.fundamentals.freeCashFlow
      const passed = roe !== null && roe > 0 && fcf !== null && fcf > 0
      return {
        passed,
        value: roe !== null ? parseFloat((roe * 100).toFixed(1)) : null,
        description: `ROE=${roe !== null ? (roe * 100).toFixed(1) + '%' : 'n/a'}, FCF=${fcf !== null ? (fcf > 0 ? 'positive' : 'negative') : 'n/a'}`,
      }
    },
  },
  {
    name: 'earningsQuality',
    weight: 3,
    check: (s) => {
      const eg  = s.fundamentals.earningsGrowth
      const rg  = s.fundamentals.revenueGrowth
      const passed = eg !== null && eg > 0 && rg !== null && rg > 0
      return {
        passed,
        value: eg !== null ? parseFloat((eg * 100).toFixed(1)) : null,
        description: `EPS growth: ${eg !== null ? (eg * 100).toFixed(1) + '%' : 'n/a'}, Rev growth: ${rg !== null ? (rg * 100).toFixed(1) + '%' : 'n/a'}`,
      }
    },
  },
  {
    name: 'noExcessiveLeverage',
    weight: 3,
    check: (s) => {
      const de     = s.fundamentals.debtEquity
      const passed = de !== null && de < 0.5
      return {
        passed,
        value: de !== null ? parseFloat(de.toFixed(2)) : null,
        description: `D/E ratio: ${de?.toFixed(2) ?? 'n/a'} — need < 0.5 (conservative for bear)`,
      }
    },
  },
]

// ── FACTOR 3: LOW VOLATILITY / DOWNSIDE PROTECTION (20 pts) ─────────────────
// Low Volatility Anomaly: the less risky stock outperforms in down markets.

export const BETA_V2_DOWNSIDE_PROTECTION: FilterRule[] = [
  {
    name: 'lowBeta',
    weight: 10,
    check: (s) => {
      const beta   = s.beta
      const passed = beta !== null && beta < 0.85
      return {
        passed,
        value: beta !== null ? parseFloat(beta.toFixed(2)) : null,
        description: `Beta: ${beta?.toFixed(2) ?? 'n/a'} — need < 0.85 (defensive)`,
      }
    },
  },
  {
    name: 'limitedDrawdown',
    weight: 6,
    check: (s) => {
      // Max drawdown over 6 months should be tolerable
      const mdd    = maxDrawdown(s.prices, 126)
      const passed = mdd >= -0.25    // at most 25% drawdown in 6 months
      return {
        passed,
        value: parseFloat((mdd * 100).toFixed(1)),
        description: `6M max drawdown: ${(mdd * 100).toFixed(1)}% — need > -25%`,
      }
    },
  },
  {
    name: 'lowNormalisedVolatility',
    weight: 4,
    check: (s) => {
      const atrP   = atrPct(s.prices, s.indicators.atr14)
      if (atrP === null) return { passed: false, value: null, description: 'ATR%: no data' }
      const passed = atrP < 0.025    // daily swing < 2.5% of price
      return {
        passed,
        value: parseFloat((atrP * 100).toFixed(2)),
        description: `ATR/Price: ${(atrP * 100).toFixed(2)}% — need < 2.5% (low daily volatility)`,
      }
    },
  },
]

// ── FACTOR 4: VALUE SAFETY MARGIN (15 pts) ───────────────────────────────────
// Graham-inspired: buy cheap assets that are hard to destroy further.

export const BETA_V2_VALUE: FilterRule[] = [
  {
    name: 'valuePE',
    weight: 6,
    check: (s) => {
      const pe     = s.fundamentals.pe
      const passed = pe !== null && pe > 0 && pe < 15
      return {
        passed,
        value: pe !== null ? parseFloat(pe.toFixed(1)) : null,
        description: `P/E: ${pe?.toFixed(1) ?? 'n/a'} — need < 15 (value, not growth trap)`,
      }
    },
  },
  {
    name: 'valuePB',
    weight: 5,
    check: (s) => {
      const pb     = s.fundamentals.pb
      const passed = pb !== null && pb > 0 && pb < 1.5
      return {
        passed,
        value: pb !== null ? parseFloat(pb.toFixed(2)) : null,
        description: `P/B: ${pb?.toFixed(2) ?? 'n/a'} — need < 1.5 (below tangible asset value)`,
      }
    },
  },
  {
    name: 'fcfYield',
    weight: 4,
    check: (s) => {
      const fcf = s.fundamentals.freeCashFlow
      const mc  = s.fundamentals.marketCap
      const passed = fcf !== null && mc !== null && mc > 0 && (fcf / mc) > 0.04
      const fcfYield = fcf !== null && mc !== null && mc > 0 ? fcf / mc : null
      return {
        passed,
        value: fcfYield !== null ? parseFloat((fcfYield * 100).toFixed(2)) : null,
        description: `FCF Yield: ${fcfYield !== null ? (fcfYield * 100).toFixed(2) + '%' : 'n/a'} — need > 4%`,
      }
    },
  },
]

// ── FACTOR 5: TECHNICAL OVERSOLD RECOVERY SIGNALS (10 pts) ──────────────────
// Entry timing: stock has already corrected, now stabilising.

export const BETA_V2_TECHNICAL_RECOVERY: FilterRule[] = [
  {
    name: 'rsiOversoldZone',
    weight: 4,
    check: (s) => {
      const rsi    = lastValid(s.indicators.rsi14)
      if (rsi === null) return { passed: false, value: null, description: 'RSI: no data' }
      // 30-50: corrected but not collapsing; not above 50 (still defensive zone)
      const passed = rsi >= 30 && rsi <= 50
      return {
        passed,
        value: parseFloat(rsi.toFixed(1)),
        description: `RSI(14): ${rsi.toFixed(1)} — target 30–50 (corrected but stable)`,
      }
    },
  },
  {
    name: 'stochasticOversoldCross',
    weight: 3,
    check: (s) => {
      const k    = lastValid(s.indicators.stochastic.k)
      const d    = lastValid(s.indicators.stochastic.d)
      const pk   = nthFromEnd(s.indicators.stochastic.k, 1)
      const pd   = nthFromEnd(s.indicators.stochastic.d, 1)
      if (k === null || d === null || pk === null || pd === null)
        return { passed: false, value: null, description: 'Stochastic: no data' }
      const oversold    = k < 30
      const crossingUp  = k > d && pk <= pd
      const passed      = oversold && crossingUp
      return {
        passed,
        value: parseFloat(k.toFixed(1)),
        description: `Stoch %K=${k.toFixed(1)} — ${passed ? 'oversold + bullish cross' : 'no oversold cross'}`,
      }
    },
  },
  {
    name: 'nearLowerBollinger',
    weight: 3,
    check: (s) => {
      const lower  = lastValid(s.indicators.bollinger.lower)
      const middle = lastValid(s.indicators.bollinger.middle)
      const close  = s.prices[s.prices.length - 1]?.close ?? 0
      if (lower === null || middle === null)
        return { passed: false, value: null, description: 'Bollinger: no data' }
      const bw   = middle - lower
      const dist = bw > 0 ? (close - lower) / bw : 1
      // Within bottom 30% of BB range (oversold bounce zone)
      const passed = dist >= 0 && dist <= 0.30
      return {
        passed,
        value: parseFloat((dist * 100).toFixed(1)),
        description: `Price at ${(dist * 100).toFixed(1)}% of lower-to-middle BB — need ≤30%`,
      }
    },
  },
]

// ── FACTOR 6: BEAR MARKET SELLING EXHAUSTION (10 pts) ───────────────────────
// Classic signs that panic selling is finishing.

export const BETA_V2_SELLING_EXHAUSTION: FilterRule[] = [
  {
    name: 'quietDownDays',
    weight: 5,
    check: (s) => {
      const ratio  = quietDownDayRatio(s.prices, s.indicators.volume20avg, 20)
      if (ratio === null) return { passed: false, value: null, description: 'Volume analysis: no data' }
      const passed = ratio >= 0.60
      return {
        passed,
        value: parseFloat((ratio * 100).toFixed(1)),
        description: `${(ratio * 100).toFixed(0)}% of down days had below-avg volume — need ≥60% (selling exhaustion)`,
      }
    },
  },
  {
    name: 'priceNotFreefall',
    weight: 3,
    check: (s) => {
      const rsi    = lastValid(s.indicators.rsi14)
      if (rsi === null) return { passed: false, value: null, description: 'RSI: no data' }
      // Reject stocks in freefall (RSI < 25 = panic selling, not yet bottom)
      const passed = rsi >= 25
      return {
        passed,
        value: parseFloat(rsi.toFixed(1)),
        description: `RSI(14): ${rsi.toFixed(1)} — must be ≥25 (not in freefall)`,
      }
    },
  },
  {
    name: 'fibonacciSupport',
    weight: 2,
    check: (s) => {
      const close  = s.prices[s.prices.length - 1]?.close ?? 0
      const fib618 = s.indicators.fibonacci.level618
      if (fib618 <= 0) return { passed: false, value: null, description: 'Fibonacci: no data' }
      const pct    = Math.abs(close - fib618) / fib618
      const passed = pct <= 0.04
      return {
        passed,
        value: parseFloat((pct * 100).toFixed(2)),
        description: `${(pct * 100).toFixed(2)}% from Fib 61.8% support (${fib618.toFixed(2)}) — need within 4%`,
      }
    },
  },
]

// ── HARD FILTERS ─────────────────────────────────────────────────────────────

export const BETA_V2_HARD_FILTERS: FilterRule[] = [
  {
    name: 'maxBetaGate',
    weight: 10,
    check: (s) => {
      const beta   = s.beta
      // Allow null beta through (data unavailable ≠ high beta)
      if (beta === null) return { passed: true, value: null, description: 'Beta: no data (allowed)' }
      const passed = beta < 0.90
      return {
        passed,
        value: parseFloat(beta.toFixed(2)),
        description: `Beta: ${beta.toFixed(2)} — hard cap < 0.90 (avoid high-beta in bear market)`,
      }
    },
  },
  {
    name: 'debtSafetyGate',
    weight: 8,
    check: (s) => {
      const de     = s.fundamentals.debtEquity
      if (de === null) return { passed: true, value: null, description: 'D/E: no data (allowed)' }
      const passed = de < 2.0
      return {
        passed,
        value: parseFloat(de.toFixed(2)),
        description: `D/E: ${de.toFixed(2)} — hard cap < 2.0 (avoid overleveraged in bear)`,
      }
    },
  },
  {
    name: 'positiveROEGate',
    weight: 6,
    check: (s) => {
      const roe    = s.fundamentals.roe
      if (roe === null) return { passed: true, value: null, description: 'ROE: no data (allowed)' }
      const passed = roe > 0
      return {
        passed,
        value: roe !== null ? parseFloat((roe * 100).toFixed(1)) : null,
        description: `ROE: ${roe !== null ? (roe * 100).toFixed(1) + '%' : 'n/a'} — must be positive (profitable)`,
      }
    },
  },
]

// ── Compose all rules ─────────────────────────────────────────────────────────

export const BETA_V2_TECHNICAL: FilterRule[] = [
  ...BETA_V2_HARD_FILTERS,
  ...BETA_V2_RELATIVE_STRENGTH,
  ...BETA_V2_DOWNSIDE_PROTECTION,
  ...BETA_V2_TECHNICAL_RECOVERY,
  ...BETA_V2_SELLING_EXHAUSTION,
]

export const BETA_V2_FUNDAMENTAL: FilterRule[] = [
  ...BETA_V2_PIOTROSKI,
  ...BETA_V2_VALUE,
]

export const BETA_V2_CONFIG: CriteriaConfig = {
  type:               'BETA',
  label:              'BETA V2 — Bear Market Defense (Piotroski / Low-Vol / Value)',
  technicalFilters:   BETA_V2_TECHNICAL,
  fundamentalFilters: BETA_V2_FUNDAMENTAL,
}

// ── Bear market stop-loss calculator ─────────────────────────────────────────

export interface BearStopLossResult {
  stopPrice:    number
  stopPercent:  number
  method:       string
}

/**
 * Tighter bear-market stop: maximum 5% allowed loss per position.
 * Uses the tighter of: ATR-based (1.5×) or 5% hard cap.
 */
export function calculateBearStopLoss(
  prices:     OHLCV[],
  atr14:      number[],
  entryPrice: number
): BearStopLossResult {
  const atr     = lastValid(atr14) ?? entryPrice * 0.015
  const atrStop = entryPrice - atr * 1.5          // tighter than bull market (1.5× vs 2.5×)
  const pctStop = entryPrice * 0.95               // 5% hard cap

  const stopPrice    = Math.max(atrStop, pctStop) // tightest (highest price)
  const stopPercent  = (entryPrice - stopPrice) / entryPrice

  return {
    stopPrice:   parseFloat(stopPrice.toFixed(4)),
    stopPercent: parseFloat(stopPercent.toFixed(4)),
    method:      'ATR1.5x+5%cap',
  }
}

/**
 * Cash threshold: if fewer than `minQualified` stocks clear score ≥ 55,
 * the bear strategy should hold cash instead of forcing positions.
 */
export function shouldHoldCash(
  scores:        number[],
  minScore:      number = 55,
  minQualified:  number = 3
): boolean {
  return scores.filter((s) => s >= minScore).length < minQualified
}
