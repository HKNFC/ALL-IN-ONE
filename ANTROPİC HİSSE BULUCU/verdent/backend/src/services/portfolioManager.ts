/**
 * AdvancedPortfolioManager
 *
 * Plugs into backtestEngine.rebalancePortfolio() to replace the naive
 * equal-weight, always-rebalance strategy with seven intelligent improvements:
 *
 *   1. Dynamic position sizing  (EQUAL / SCORE_WEIGHTED / VOLATILITY_ADJUSTED / KELLY)
 *   2. Momentum-based hold/sell decisions
 *   3. Trailing stop-loss management
 *   4. Smart rebalance gating   (skip if transaction cost > expected alpha)
 *   5. Market-condition exposure overlay
 *   6. Sector diversification cap
 *   7. Drawdown circuit-breaker  (go-to-cash mode)
 */

import type { ScoredStock, Holding, BacktestConfig, PortfolioSnapshot } from '../types/market'

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

export type SizingMethod = 'EQUAL' | 'SCORE_WEIGHTED' | 'VOLATILITY_ADJUSTED' | 'KELLY' | 'RISK_BASED'

export interface PositionWeight {
  symbol: string
  weight: number   // 0-1
}

export interface SellDecision {
  sell:   boolean
  reason: 'MOMENTUM_CONTINUE' | 'STOP_LOSS_HIT' | 'SCORE_DETERIORATED' |
          'NOT_IN_CANDIDATES' | 'KEEP_HOLDING' | 'CIRCUIT_BREAKER'
  urgency?: 'IMMEDIATE' | 'NORMAL'
}

export interface RebalanceDecision {
  shouldRebalance: boolean
  reason:          string
  changesNeeded:   number
  urgency:         'HIGH' | 'NORMAL' | 'SKIP'
}

export interface ExposureConfig {
  maxPositions:  number
  maxExposure:   number     // 0-1  (1 = 100% invested)
  cashBuffer:    number     // 0-1
  sizingMethod:  SizingMethod
}

export interface CircuitBreakerStatus {
  triggered:        boolean
  drawdown:         number   // current drawdown from peak  (negative)
  action?:          'MOVE_TO_CASH'
  resumeCondition?: string
}

// Enriched holding used internally (adds stop-loss & trailing flag)
export interface ManagedHolding extends Holding {
  stopLoss:         number
  trailingActive:   boolean
  entryDate:        Date
  currentATR:       number   // last known ATR14
}

// ---------------------------------------------------------------------------
// Helper utilities
// ---------------------------------------------------------------------------

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v))
}

function daysBetween(a: Date, b: Date): number {
  return Math.abs(b.getTime() - a.getTime()) / 86_400_000
}

/** Annualised volatility from a price series (last N bars) */
function volatility(prices: number[], bars = 20): number {
  if (prices.length < 2) return 0.30   // fallback 30%
  const rets = prices.slice(-bars - 1).slice(1).map((p, i) => Math.log(p / prices[prices.length - bars - 1 + i] || 1))
  const mean = rets.reduce((a, b) => a + b, 0) / rets.length
  const variance = rets.reduce((a, b) => a + (b - mean) ** 2, 0) / rets.length
  return Math.sqrt(variance * 252)
}

// ---------------------------------------------------------------------------
// 1. Dynamic Position Sizing
// ---------------------------------------------------------------------------

/**
 * Calculate target weights for a list of candidates.
 *
 * @param stocks     Scored & ranked candidates (already top-N)
 * @param method     Sizing method
 * @param closePrices  Map symbol → recent close prices (for vol calc)
 */
export function calculatePositionWeights(
  stocks:      ScoredStock[],
  method:      SizingMethod,
  closePrices: Map<string, number[]> = new Map(),
): PositionWeight[] {

  if (stocks.length === 0) return []

  // ── EQUAL ────────────────────────────────────────────────────────────────
  if (method === 'EQUAL') {
    const w = 1 / stocks.length
    return stocks.map((s) => ({ symbol: s.symbol, weight: w }))
  }

  // ── SCORE_WEIGHTED ───────────────────────────────────────────────────────
  if (method === 'SCORE_WEIGHTED') {
    const total = stocks.reduce((s, x) => s + x.score, 0)
    if (total === 0) return calculatePositionWeights(stocks, 'EQUAL', closePrices)
    const raw = stocks.map((s) => ({ symbol: s.symbol, weight: s.score / total }))
    // Cap any single position at 35%
    return normalise(raw, 0.35)
  }

  // ── VOLATILITY_ADJUSTED (Risk Parity) ────────────────────────────────────
  if (method === 'VOLATILITY_ADJUSTED') {
    const invVols = stocks.map((s) => {
      const prices = closePrices.get(s.symbol) ?? []
      const vol    = prices.length >= 20 ? volatility(prices) : 0.25   // fallback
      return { symbol: s.symbol, invVol: vol > 0 ? 1 / vol : 1 }
    })
    const totalInv = invVols.reduce((s, x) => s + x.invVol, 0)
    if (totalInv === 0) return calculatePositionWeights(stocks, 'EQUAL', closePrices)
    const raw = invVols.map((x) => ({ symbol: x.symbol, weight: x.invVol / totalInv }))
    return normalise(raw, 0.40)
  }

  // ── KELLY (Half-Kelly) ────────────────────────────────────────────────────
  if (method === 'KELLY') {
    // We estimate win-rate from score: score 50 → p=0.50, score 100 → p=0.70
    const raw = stocks.map((s) => {
      const p = clamp(0.45 + (s.score / 100) * 0.25, 0.45, 0.70)
      const b = 1.5    // avg win/loss ratio assumption
      const q = 1 - p
      const kelly = (p * b - q) / b
      const halfKelly = clamp(kelly * 0.5, 0.05, 0.30)
      return { symbol: s.symbol, weight: halfKelly }
    })
    return normalise(raw, 0.30)
  }

  // ── RISK_BASED (Minervini — 2% risk/işlem) ────────────────────────────────
  if (method === 'RISK_BASED') {
    // Temporary portfolioValue proxy: çağrılan yerde mevcut değil, eşit ağırlık + stop mesafesi kullan
    const raw = stocks.map((s) => {
      const entry   = s.entryPrice
      const stop    = s.suggestedStopLoss ?? entry * 0.88
      const riskPct = entry > 0 ? (entry - stop) / entry : 0.12
      // Sıkı stop → büyük pozisyon, geniş stop → küçük pozisyon
      // Hedef: her pozisyon port. %2'sini riske etmeli → ağırlık = 0.02 / riskPct
      const weight  = riskPct > 0 ? clamp(0.02 / riskPct, 0.08, 0.30) : 1 / stocks.length
      return { symbol: s.symbol, weight }
    })
    return normalise(raw, 0.30)   // tek pozisyon max %30
  }

  return calculatePositionWeights(stocks, 'EQUAL', closePrices)
}

export function calculateRiskBasedWeights(
  stocks:         ScoredStock[],
  portfolioValue: number,
  riskPerTrade:   number = 0.02,   // portföyün %2'si
  maxWeight:      number = 0.25,   // tek pozisyon max %25
): PositionWeight[] {
  if (stocks.length === 0 || portfolioValue <= 0) return []

  const weights = stocks.map((s) => {
    const entry   = s.entryPrice
    const stop    = s.suggestedStopLoss ?? entry * 0.88
    const riskPer = entry - stop          // hisse başı risk (TL)
    if (riskPer <= 0) return { symbol: s.symbol, weight: 1 / stocks.length }

    const riskAmount = portfolioValue * riskPerTrade
    const shares     = Math.floor(riskAmount / riskPer)
    const posVal     = shares * entry
    const weight     = Math.min(posVal / portfolioValue, maxWeight)
    return { symbol: s.symbol, weight: Math.max(weight, 0.05) }
  })

  // Normalize so total ≤ 1.0 (kalan kısım nakit)
  const total = weights.reduce((s, w) => s + w.weight, 0)
  if (total > 1.0) {
    const scale = 1.0 / total
    return weights.map((w) => ({ ...w, weight: w.weight * scale }))
  }
  return weights
}

/** Normalise weights to sum=1, capping each at maxWeight, then re-normalise */
function normalise(raw: PositionWeight[], maxWeight: number): PositionWeight[] {
  // Iterative cap-and-redistribute
  let weights = raw.map((x) => ({ ...x }))
  for (let iter = 0; iter < 10; iter++) {
    const capped  = weights.map((x) => ({ ...x, weight: Math.min(x.weight, maxWeight) }))
    const total   = capped.reduce((s, x) => s + x.weight, 0)
    if (total <= 0) break
    weights = capped.map((x) => ({ ...x, weight: x.weight / total }))
    if (weights.every((x) => x.weight <= maxWeight + 1e-9)) break
  }
  return weights
}

// ---------------------------------------------------------------------------
// 2. Momentum-based hold/sell decisions
// ---------------------------------------------------------------------------

export function shouldSellStock(
  stock:           ManagedHolding,
  currentPrice:    number,
  newScanResults:  ScoredStock[],
): SellDecision {

  const unrealizedReturn = currentPrice > 0
    ? (currentPrice - stock.entryPrice) / stock.entryPrice
    : 0

  // ── Hard stop-loss ────────────────────────────────────────────────────────
  if (currentPrice <= stock.stopLoss) {
    return { sell: true, reason: 'STOP_LOSS_HIT', urgency: 'IMMEDIATE' }
  }

  // ── Momentum continuation override (keep winning stocks) ─────────────────
  const isStillInTop10 = newScanResults.slice(0, 10).some((s) => s.symbol === stock.symbol)
  if (unrealizedReturn > 0.10 && isStillInTop10) {
    return { sell: false, reason: 'MOMENTUM_CONTINUE' }
  }

  // ── Score-based exit — only sell if score is VERY low to reduce noise ─────
  const match = newScanResults.find((s) => s.symbol === stock.symbol)
  const currentScore = match?.score ?? 0

  // Don't sell if score dropped but stock is still profitable
  if (currentScore < 30 && unrealizedReturn < 0.05) {
    return { sell: true, reason: 'SCORE_DETERIORATED' }
  }

  // ── Not in top-20 candidates at all AND not profitable ───────────────────
  const inTop20 = newScanResults.slice(0, 20).some((s) => s.symbol === stock.symbol)
  if (!inTop20 && unrealizedReturn < -0.03) {
    return { sell: true, reason: 'NOT_IN_CANDIDATES' }
  }

  return { sell: false, reason: 'KEEP_HOLDING' }
}

// ---------------------------------------------------------------------------
// 3. Trailing stop-loss
// ---------------------------------------------------------------------------

export function updateTrailingStops(
  holdings:      ManagedHolding[],
  currentPrices: Map<string, number>,
): ManagedHolding[] {

  return holdings.map((h) => {
    const cp = currentPrices.get(h.symbol)
    if (!cp || cp <= 0) return h

    const unrealised = (cp - h.entryPrice) / h.entryPrice

    // Activate trailing stop once up ≥ 10%
    if (unrealised >= 0.10) {
      const atr        = h.currentATR > 0 ? h.currentATR : cp * 0.02   // 2% of price as fallback
      const trailStop  = cp - atr * 2.5
      // Breakeven floor once up ≥ 20%
      const beFl       = unrealised >= 0.20 ? h.entryPrice * 1.02 : h.stopLoss
      const newStop    = Math.max(h.stopLoss, trailStop, beFl)

      return { ...h, stopLoss: newStop, trailingActive: true }
    }

    return h
  })
}

// ---------------------------------------------------------------------------
// 4. Smart rebalance gating
// ---------------------------------------------------------------------------

export function shouldRebalance(
  currentHoldings: Holding[],
  newTopStocks:    ScoredStock[],
  config:          BacktestConfig,
): RebalanceDecision {

  const currentSymbols = new Set(currentHoldings.map((h) => h.symbol))
  const newSymbols     = new Set(newTopStocks.slice(0, 5).map((s) => s.symbol))

  const exits   = [...currentSymbols].filter((s) => !newSymbols.has(s)).length
  const entries = [...newSymbols].filter((s) => !currentSymbols.has(s)).length
  const changes = Math.max(exits, entries)

  // Full turnover (new scan completely different) → always rebalance
  if (changes >= 4) {
    return { shouldRebalance: true, reason: 'HIGH_TURNOVER', changesNeeded: changes, urgency: 'HIGH' }
  }

  // Always rebalance if there are any changes (simpler, avoids stale portfolios)
  return {
    shouldRebalance: changes >= 1,
    reason:          changes >= 1 ? 'NORMAL_REBALANCE' : 'NO_CHANGE',
    changesNeeded:   changes,
    urgency:         'NORMAL',
  }
}

// ---------------------------------------------------------------------------
// 5. Market-condition exposure overlay
// ---------------------------------------------------------------------------

export function calculateMarketExposure(
  condition:    'BULL' | 'BEAR' | 'SIDEWAYS',
  criteriaType: string,
): ExposureConfig {

  // Aligned: right criteria for the market regime
  if (criteriaType === 'ALFA' && condition === 'BULL') {
    return { maxPositions: 5, maxExposure: 1.00, cashBuffer: 0.00, sizingMethod: 'RISK_BASED' }
  }
  if (criteriaType === 'BETA' && condition === 'BEAR') {
    return { maxPositions: 5, maxExposure: 0.70, cashBuffer: 0.30, sizingMethod: 'VOLATILITY_ADJUSTED' }
  }
  if (criteriaType === 'DELTA' && condition === 'SIDEWAYS') {
    return { maxPositions: 5, maxExposure: 0.85, cashBuffer: 0.15, sizingMethod: 'EQUAL' }
  }

  // HYBRID adapts automatically — treat as aligned
  if (criteriaType === 'HYBRID') {
    const map: Record<string, ExposureConfig> = {
      BULL:     { maxPositions: 5, maxExposure: 1.00, cashBuffer: 0.00, sizingMethod: 'SCORE_WEIGHTED' },
      BEAR:     { maxPositions: 5, maxExposure: 0.70, cashBuffer: 0.30, sizingMethod: 'VOLATILITY_ADJUSTED' },
      SIDEWAYS: { maxPositions: 5, maxExposure: 0.85, cashBuffer: 0.15, sizingMethod: 'EQUAL' },
    }
    return map[condition] ?? { maxPositions: 5, maxExposure: 0.85, cashBuffer: 0.15, sizingMethod: 'EQUAL' }
  }

  // Misaligned but still invest — just use EQUAL sizing with slightly less exposure
  return { maxPositions: 5, maxExposure: 0.85, cashBuffer: 0.15, sizingMethod: 'EQUAL' }
}

// ---------------------------------------------------------------------------
// 6. Sector diversification
// ---------------------------------------------------------------------------

/**
 * Pick up to `limit` stocks while capping each sector at `maxPerSector`.
 * Falls back gracefully if sector info is missing.
 */
export function applySectorDiversification(
  candidates:   ScoredStock[],
  limit:        number = 5,
  maxPerSector: number = 2,
): ScoredStock[] {

  const selected:    ScoredStock[]         = []
  const sectorCount: Map<string, number>   = new Map()
  const overflow:    ScoredStock[]         = []   // rejected by sector cap

  for (const stock of candidates) {
    const sector = (stock as ScoredStock & { sector?: string }).sector ?? 'UNKNOWN'
    const count  = sectorCount.get(sector) ?? 0

    if (count < maxPerSector) {
      selected.push(stock)
      sectorCount.set(sector, count + 1)
      if (selected.length >= limit) break
    } else {
      overflow.push(stock)
    }
  }

  // If we couldn't fill limit due to sector caps, backfill from overflow
  if (selected.length < limit) {
    for (const stock of overflow) {
      selected.push(stock)
      if (selected.length >= limit) break
    }
  }

  return selected
}

// ---------------------------------------------------------------------------
// 7. Drawdown circuit-breaker
// ---------------------------------------------------------------------------

export function checkCircuitBreaker(
  snapshots: PortfolioSnapshot[],
  threshold = 0.20,   // 20% max drawdown before going to cash (12% was too tight for BIST volatility)
  recoveryThreshold = 0.10, // Resume when portfolio recovers 10% from trough
): CircuitBreakerStatus {

  if (snapshots.length < 2) return { triggered: false, drawdown: 0 }

  const values  = snapshots.map((s) => s.portfolioValue)
  const peak    = Math.max(...values)
  const current = values[values.length - 1]
  const dd      = peak > 0 ? (current - peak) / peak : 0

  if (dd <= -threshold) {
    // Check if portfolio has recovered enough from the trough to resume
    const trough = Math.min(...values.slice(values.findIndex(v => v === peak)))
    const recoveryFromTrough = trough > 0 ? (current - trough) / trough : 0

    if (recoveryFromTrough >= recoveryThreshold) {
      // Portfolio recovered 10%+ from trough — allow gradual re-entry
      return { triggered: false, drawdown: dd }
    }

    return {
      triggered:        true,
      drawdown:         dd,
      action:           'MOVE_TO_CASH',
      resumeCondition:  `Portfolio trough recovery ${(recoveryFromTrough * 100).toFixed(1)}% < required ${(recoveryThreshold * 100).toFixed(0)}%`,
    }
  }

  return { triggered: false, drawdown: dd }
}

// ---------------------------------------------------------------------------
// Orchestration helper — used by backtestEngine.rebalancePortfolio()
// ---------------------------------------------------------------------------

/**
 * Decide weights, exposure, and which stocks to use for the next rebalance.
 * Returns the final list of stocks to buy and their target weights.
 */
export function orchestrateRebalance(params: {
  scanResults:     ScoredStock[]
  currentHoldings: Holding[]
  snapshots:       PortfolioSnapshot[]
  condition:       'BULL' | 'BEAR' | 'SIDEWAYS'
  criteriaType:    string
  config:          BacktestConfig
  closePrices:     Map<string, number[]>
}): {
  stocks:            ScoredStock[]
  weights:           PositionWeight[]
  exposure:          ExposureConfig
  circuitBreaker:    CircuitBreakerStatus
  rebalanceDecision: RebalanceDecision
  skip:              boolean
} {
  const { scanResults, currentHoldings, snapshots, condition, criteriaType, config, closePrices } = params

  // ── 7. Circuit breaker check ──────────────────────────────────────────────
  const circuitBreaker = checkCircuitBreaker(snapshots)
  if (circuitBreaker.triggered) {
    return {
      stocks: [], weights: [], exposure: { maxPositions: 0, maxExposure: 0, cashBuffer: 1, sizingMethod: 'EQUAL' },
      circuitBreaker, rebalanceDecision: { shouldRebalance: true, reason: 'CIRCUIT_BREAKER', changesNeeded: currentHoldings.length, urgency: 'HIGH' },
      skip: false,
    }
  }

  // ── 5. Market exposure overlay ────────────────────────────────────────────
  const exposure = calculateMarketExposure(condition, criteriaType)

  // ── 6. Sector diversification ─────────────────────────────────────────────
  const diversified = applySectorDiversification(scanResults, exposure.maxPositions)

  // ── 4. Smart rebalance gating ─────────────────────────────────────────────
  const rebalanceDecision = shouldRebalance(currentHoldings, diversified, config)
  if (!rebalanceDecision.shouldRebalance) {
    return { stocks: [], weights: [], exposure, circuitBreaker, rebalanceDecision, skip: true }
  }

  // ── 1. Dynamic position sizing ────────────────────────────────────────────
  const weights = calculatePositionWeights(diversified, exposure.sizingMethod, closePrices)

  return { stocks: diversified, weights, exposure, circuitBreaker, rebalanceDecision, skip: false }
}
