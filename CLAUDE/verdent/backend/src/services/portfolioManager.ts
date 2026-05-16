/**
 * VERDENT — Advanced Portfolio Manager
 *
 * Critical performance improvements over naive equal-weight + fixed rebalance:
 *
 *  1. Dynamic position sizing  (equal / score-weighted / vol-adjusted / Kelly)
 *  2. Momentum-based hold/sell logic  (don't sell winners just because date arrived)
 *  3. Trailing stop-loss         (lock in profits, never move stop down)
 *  4. Smart rebalancing          (skip when transaction cost > marginal alpha)
 *  5. Market-condition exposure  (go partial cash in BEAR / wrong-criteria combos)
 *  6. Sector diversification     (max N positions per sector)
 *  7. Portfolio drawdown circuit-breaker  (go to cash on deep drawdown)
 */

import type { ScoredStock, CriteriaType } from './criteriaEngine';
import type { PortfolioSnapshot } from './backtestEngine';

// ─────────────────────────────────────────────────────────────────────────────
// Value types
// ─────────────────────────────────────────────────────────────────────────────

export type SizingMethod = 'EQUAL' | 'SCORE_WEIGHTED' | 'VOLATILITY_ADJUSTED' | 'KELLY';

export interface PositionWeight {
  symbol: string;
  weight: number;   // 0–1 fraction of invested capital
}

export interface SellDecision {
  sell:    boolean;
  reason:  SellReason;
  urgency?: 'IMMEDIATE' | 'NEXT_OPEN' | 'NORMAL';
  score?:  number;
}

export type SellReason =
  | 'STOP_LOSS_HIT'
  | 'SCORE_DETERIORATED'
  | 'NOT_IN_CANDIDATES'
  | 'MOMENTUM_CONTINUE'
  | 'KEEP_HOLDING'
  | 'TRAILING_STOP_HIT';

export interface EnrichedHolding {
  // Core fields (mirrors backtestEngine.Holding)
  symbol:       string;
  name:         string;
  shares:       number;
  entryPrice:   number;
  currentPrice: number;
  value:        number;
  weight:       number;    // 0–100
  pnl:          number;
  pnlPct:       number;
  // Extended fields
  entryDate:          Date;
  stopLoss:           number;
  currentATR:         number;
  trailingActive:     boolean;
  sector:             string;
  historicalWinRate:  number;  // 0–1
  avgWinLossRatio:    number;  // > 1 is good
  volatility20d:      number;  // annualised fraction
}

export interface RebalanceConfig {
  transactionCost: number;    // per leg, e.g. 0.003
  minChangesToRebalance: number;  // default 2
  marketCondition:  string;
}

export interface RebalanceDecision {
  shouldRebalance: boolean;
  reason:          string;
  changesNeeded:   number;
  keepCurrent?:    boolean;
  urgency?:        'HIGH' | 'NORMAL' | 'LOW';
}

export interface ExposureConfig {
  maxPositions:    number;
  maxExposure:     number;       // 0–1 fraction of capital to invest
  cashBuffer:      number;       // 0–1 fraction to keep as cash
  positionSizing:  SizingMethod;
}

export interface CircuitBreakerStatus {
  triggered:        boolean;
  drawdown:         number;   // negative fraction
  action?:          'MOVE_TO_CASH' | 'REDUCE_EXPOSURE';
  resumeCondition?: string;
  recoveryTarget?:  number;   // portfolio value that resumes normal operation
}

export interface MarketConditionInput {
  condition: 'BULL' | 'BEAR' | 'SIDEWAYS';
  score:     number;
  confidence: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Math helpers
// ─────────────────────────────────────────────────────────────────────────────

function daysBetween(a: Date, b: Date): number {
  return Math.abs(b.getTime() - a.getTime()) / 86_400_000;
}

function clamp(x: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, x));
}

/**
 * Kelly fraction: f* = (p × b − q) / b
 *   p = win probability, b = avg win/loss ratio, q = 1 − p
 * Returns raw Kelly; caller should apply half-Kelly and cap.
 */
function kellyFraction(winRate: number, avgWinLoss: number): number {
  const p = clamp(winRate, 0.01, 0.99);
  const b = Math.max(avgWinLoss, 0.01);
  const q = 1 - p;
  return (p * b - q) / b;
}

// ─────────────────────────────────────────────────────────────────────────────
// AdvancedPortfolioManager
// ─────────────────────────────────────────────────────────────────────────────

export class AdvancedPortfolioManager {

  // ── 1. Dynamic position sizing ────────────────────────────────────────────

  calculatePositionWeights(
    stocks: ScoredStock[],
    method: SizingMethod,
    enriched?: EnrichedHolding[],
  ): PositionWeight[] {

    if (stocks.length === 0) return [];

    // ── EQUAL (baseline) ──────────────────────────────────────
    if (method === 'EQUAL') {
      const w = 1 / stocks.length;
      return stocks.map(s => ({ symbol: s.symbol, weight: +w.toFixed(6) }));
    }

    // ── SCORE_WEIGHTED ────────────────────────────────────────
    if (method === 'SCORE_WEIGHTED') {
      const total = stocks.reduce((s, x) => s + x.score, 0);
      if (total === 0) return this.calculatePositionWeights(stocks, 'EQUAL');
      return stocks.map(s => ({
        symbol: s.symbol,
        weight: +((s.score / total)).toFixed(6),
      }));
    }

    // ── VOLATILITY_ADJUSTED (risk parity) ────────────────────
    if (method === 'VOLATILITY_ADJUSTED') {
      const vols = stocks.map(s => {
        const e = enriched?.find(h => h.symbol === s.symbol);
        return e?.volatility20d ?? 0.25;   // default 25% annualised
      });
      const invVols = vols.map(v => 1 / Math.max(v, 0.01));
      const total   = invVols.reduce((a, b) => a + b, 0);
      return stocks.map((s, i) => ({
        symbol: s.symbol,
        weight: +(invVols[i] / total).toFixed(6),
      }));
    }

    // ── KELLY ─────────────────────────────────────────────────
    if (method === 'KELLY') {
      const raw = stocks.map(s => {
        const e   = enriched?.find(h => h.symbol === s.symbol);
        const wr  = e?.historicalWinRate  ?? 0.55;
        const awl = e?.avgWinLossRatio    ?? 1.5;
        const fk  = kellyFraction(wr, awl);
        return Math.max(0, fk * 0.5);   // half-Kelly
      });
      const total = raw.reduce((a, b) => a + b, 0);
      if (total === 0) return this.calculatePositionWeights(stocks, 'EQUAL');
      // Cap each position at 30%
      const capped  = raw.map(f => Math.min(f / total, 0.30));
      const capSum  = capped.reduce((a, b) => a + b, 0);
      return stocks.map((s, i) => ({
        symbol: s.symbol,
        weight: +(capSum > 0 ? capped[i] / capSum : 1 / stocks.length).toFixed(6),
      }));
    }

    return this.calculatePositionWeights(stocks, 'EQUAL');
  }

  // ── 2. Momentum-based hold/sell ───────────────────────────────────────────

  shouldSellStock(
    holding:         EnrichedHolding,
    currentPrice:    number,
    newScanResults:  ScoredStock[],
  ): SellDecision {

    // Trailing stop check (highest priority)
    if (holding.trailingActive && currentPrice <= holding.stopLoss) {
      return { sell: true, reason: 'TRAILING_STOP_HIT', urgency: 'IMMEDIATE' };
    }

    // Hard stop loss
    if (currentPrice <= holding.stopLoss) {
      return { sell: true, reason: 'STOP_LOSS_HIT', urgency: 'IMMEDIATE' };
    }

    const unrealizedReturn    = (currentPrice - holding.entryPrice) / holding.entryPrice;
    const isInTop10           = newScanResults.slice(0, 10).some(s => s.symbol === holding.symbol);
    const currentScore        = newScanResults.find(s => s.symbol === holding.symbol)?.score ?? 0;
    const isInTop20           = newScanResults.slice(0, 20).some(s => s.symbol === holding.symbol);
    const daysSinceEntry      = daysBetween(holding.entryDate, new Date());

    // Protect winners: up >15% and still in top 10 → keep riding
    if (unrealizedReturn > 0.15 && isInTop10) {
      return { sell: false, reason: 'MOMENTUM_CONTINUE' };
    }

    // Score collapsed → exit
    if (currentScore < 45 && currentScore > 0) {
      return { sell: true, reason: 'SCORE_DETERIORATED', score: currentScore, urgency: 'NORMAL' };
    }

    // Completely dropped off the radar (top 20)
    if (!isInTop20 && daysSinceEntry >= 5) {
      return { sell: true, reason: 'NOT_IN_CANDIDATES', urgency: 'NORMAL' };
    }

    return { sell: false, reason: 'KEEP_HOLDING', score: currentScore };
  }

  // ── 3. Trailing stop update ───────────────────────────────────────────────

  updateTrailingStops(
    holdings:      EnrichedHolding[],
    currentPrices: Record<string, number>,
  ): EnrichedHolding[] {

    return holdings.map(h => {
      const curPrice         = currentPrices[h.symbol] ?? h.currentPrice;
      const unrealizedReturn = (curPrice - h.entryPrice) / h.entryPrice;

      // Only activate trailing stop after 10% gain
      if (unrealizedReturn < 0.10) return h;

      const atrStop     = curPrice - h.currentATR * 2.5;
      const movedStop   = Math.max(h.stopLoss, atrStop);

      // Once up ≥ 20%, floor the stop at breakeven + 2% (never lose on this trade)
      const minStop     = unrealizedReturn >= 0.20
        ? h.entryPrice * 1.02
        : h.stopLoss;

      const updatedStop = Math.max(movedStop, minStop);

      return {
        ...h,
        stopLoss:       +updatedStop.toFixed(4),
        trailingActive: true,
      };
    });
  }

  // ── 4. Smart rebalance gate ───────────────────────────────────────────────

  shouldRebalance(
    currentPortfolio: { holdings: EnrichedHolding[]; marketCondition: string },
    newTopStocks:     ScoredStock[],
    config:           RebalanceConfig,
  ): RebalanceDecision {

    const curSymbols  = new Set(currentPortfolio.holdings.map(h => h.symbol));
    const newSymbols  = new Set(newTopStocks.slice(0, 5).map(s => s.symbol));
    const added       = [...newSymbols].filter(s => !curSymbols.has(s));
    const removed     = [...curSymbols].filter(s => !newSymbols.has(s));
    const changesNeeded = Math.max(added.length, removed.length);

    // Market condition regime change → always rebalance immediately
    const newCondition = (newTopStocks[0] as any)?.marketCondition as string | undefined;
    if (newCondition && newCondition !== currentPortfolio.marketCondition) {
      return {
        shouldRebalance: true,
        reason:          'MARKET_CONDITION_CHANGED',
        changesNeeded,
        urgency:         'HIGH',
      };
    }

    // Only 1 change: skip if round-trip cost > half the expected alpha
    if (changesNeeded === 1) {
      const roundTripCost    = 2 * config.transactionCost;
      const expectedAlpha    = 0.01;   // 1% per rebalance period
      if (roundTripCost > expectedAlpha * 0.5) {
        return {
          shouldRebalance: false,
          reason:          'TRANSACTION_COST_NOT_WORTH_IT',
          changesNeeded,
          keepCurrent:     true,
          urgency:         'LOW',
        };
      }
    }

    const minChanges = config.minChangesToRebalance ?? 2;
    return {
      shouldRebalance: changesNeeded >= minChanges,
      reason:          changesNeeded >= minChanges ? 'NORMAL_REBALANCE' : 'INSUFFICIENT_CHANGE',
      changesNeeded,
      urgency:         'NORMAL',
    };
  }

  // ── 5. Market-condition exposure ──────────────────────────────────────────

  calculateMarketExposure(
    marketCondition: MarketConditionInput,
    criteria:        CriteriaType | 'HYBRID',
    portfolioSize:   number = 5,
  ): ExposureConfig {

    const cond = marketCondition.condition;

    // Perfectly matched criteria → full deployment
    if (criteria === 'ALFA' && cond === 'BULL') {
      return {
        maxPositions:   portfolioSize,
        maxExposure:    1.00,
        cashBuffer:     0.00,
        positionSizing: 'SCORE_WEIGHTED',
      };
    }
    if (criteria === 'BETA' && cond === 'BEAR') {
      return {
        maxPositions:   portfolioSize,
        maxExposure:    0.70,   // 30% cash cushion
        cashBuffer:     0.30,
        positionSizing: 'VOLATILITY_ADJUSTED',
      };
    }
    if (criteria === 'DELTA' && cond === 'SIDEWAYS') {
      return {
        maxPositions:   portfolioSize,
        maxExposure:    0.85,
        cashBuffer:     0.15,
        positionSizing: 'EQUAL',
      };
    }
    // HYBRID adapts dynamically
    if (criteria === 'HYBRID') {
      const exposureMap: Record<string, number> = {
        BULL:     1.00,
        SIDEWAYS: 0.85,
        BEAR:     0.70,
      };
      return {
        maxPositions:   portfolioSize,
        maxExposure:    exposureMap[cond] ?? 0.80,
        cashBuffer:     1 - (exposureMap[cond] ?? 0.80),
        positionSizing: cond === 'BULL' ? 'SCORE_WEIGHTED'
                       : cond === 'BEAR' ? 'VOLATILITY_ADJUSTED'
                       : 'EQUAL',
      };
    }

    // Wrong criteria for current market → defensive posture
    return {
      maxPositions:   Math.min(3, portfolioSize),
      maxExposure:    0.50,
      cashBuffer:     0.50,
      positionSizing: 'EQUAL',
    };
  }

  // ── 6. Sector diversification ─────────────────────────────────────────────

  applySectorDiversification(
    candidates:   ScoredStock[],
    portfolioSize: number = 5,
    maxPerSector:  number = 2,
  ): ScoredStock[] {

    const selected:     ScoredStock[] = [];
    const sectorCount:  Map<string, number> = new Map();

    for (const stock of candidates) {
      const sector       = (stock as any).sector as string ?? 'UNKNOWN';
      const sectorN      = sectorCount.get(sector) ?? 0;

      if (sectorN < maxPerSector) {
        selected.push(stock);
        sectorCount.set(sector, sectorN + 1);
      }

      if (selected.length >= portfolioSize) break;
    }

    // If we couldn't fill the portfolio due to sector caps, relax and fill with best remaining
    if (selected.length < portfolioSize) {
      const selectedSymbols = new Set(selected.map(s => s.symbol));
      for (const stock of candidates) {
        if (!selectedSymbols.has(stock.symbol)) {
          selected.push(stock);
          if (selected.length >= portfolioSize) break;
        }
      }
    }

    return selected;
  }

  // ── 7. Portfolio drawdown circuit-breaker ────────────────────────────────

  checkCircuitBreaker(
    portfolioHistory: PortfolioSnapshot[],
    threshold:        number = 0.12,   // 12% peak-to-trough triggers
  ): CircuitBreakerStatus {

    if (portfolioHistory.length === 0) {
      return { triggered: false, drawdown: 0 };
    }

    const values  = portfolioHistory.map(s => s.value);
    const peak    = Math.max(...values);
    const current = values[values.length - 1];
    const drawdown = (current - peak) / peak;   // negative

    if (drawdown <= -threshold) {
      return {
        triggered:        true,
        drawdown,
        action:           drawdown <= -0.20 ? 'MOVE_TO_CASH' : 'REDUCE_EXPOSURE',
        resumeCondition:  'Portfolio recovers above 50% of drawdown AND market above 200-day SMA',
        recoveryTarget:   peak * (1 - threshold * 0.5),
      };
    }

    return { triggered: false, drawdown };
  }

  // ── Composite rebalance orchestrator ──────────────────────────────────────
  /**
   * Full decision pipeline: takes scan results + current state,
   * returns what to buy/sell with quantities.
   */
  orchestrateRebalance(params: {
    candidates:        ScoredStock[];
    currentHoldings:   EnrichedHolding[];
    currentPrices:     Record<string, number>;
    availableCapital:  number;
    marketCondition:   MarketConditionInput;
    criteria:          CriteriaType | 'HYBRID';
    portfolioSize:     number;
    rebalanceConfig:   RebalanceConfig;
    portfolioHistory:  PortfolioSnapshot[];
  }): {
    buys:         { symbol: string; weight: number; capital: number }[];
    sells:        { symbol: string; reason: SellReason }[];
    cashFraction: number;
    exposureConfig: ExposureConfig;
    circuitBreaker: CircuitBreakerStatus;
    rebalanceDecision: RebalanceDecision;
  } {

    const {
      candidates, currentHoldings, currentPrices, availableCapital,
      marketCondition, criteria, portfolioSize, rebalanceConfig, portfolioHistory,
    } = params;

    // Step 1: circuit-breaker check
    const cb = this.checkCircuitBreaker(portfolioHistory);
    if (cb.triggered && cb.action === 'MOVE_TO_CASH') {
      return {
        buys:              [],
        sells:             currentHoldings.map(h => ({ symbol: h.symbol, reason: 'STOP_LOSS_HIT' as SellReason })),
        cashFraction:      1.0,
        exposureConfig:    { maxPositions: 0, maxExposure: 0, cashBuffer: 1, positionSizing: 'EQUAL' },
        circuitBreaker:    cb,
        rebalanceDecision: { shouldRebalance: true, reason: 'CIRCUIT_BREAKER', changesNeeded: currentHoldings.length, urgency: 'HIGH' },
      };
    }

    // Step 2: update trailing stops on existing holdings
    const updatedHoldings = this.updateTrailingStops(currentHoldings, currentPrices);

    // Step 3: sell decisions for current holdings
    const sellList = updatedHoldings
      .map(h => ({ h, dec: this.shouldSellStock(h, currentPrices[h.symbol] ?? h.currentPrice, candidates) }))
      .filter(x => x.dec.sell)
      .map(x => ({ symbol: x.h.symbol, reason: x.dec.reason }));

    // Step 4: determine target exposure
    const exposure = this.calculateMarketExposure(marketCondition, criteria, portfolioSize);

    // Step 5: sector-diversified top candidates
    const diversified = this.applySectorDiversification(candidates, exposure.maxPositions);

    // Step 6: rebalance gate
    const holdingMap = new Map(updatedHoldings.map(h => [h.symbol, h]));
    const portfolio  = {
      holdings:         updatedHoldings,
      marketCondition:  marketCondition.condition,
    };
    const rebDec = this.shouldRebalance(portfolio, diversified, rebalanceConfig);

    if (!rebDec.shouldRebalance && sellList.length === 0) {
      return {
        buys:              [],
        sells:             [],
        cashFraction:      exposure.cashBuffer,
        exposureConfig:    exposure,
        circuitBreaker:    cb,
        rebalanceDecision: rebDec,
      };
    }

    // Step 7: build buy list (only new entries)
    const keepSymbols = new Set(
      updatedHoldings
        .filter(h => !sellList.some(s => s.symbol === h.symbol))
        .map(h => h.symbol),
    );

    const toBuy = diversified.filter(s => !keepSymbols.has(s.symbol));

    // Step 8: position weights for all final holdings
    const finalStocks = [
      ...diversified.filter(s => keepSymbols.has(s.symbol)),
      ...toBuy,
    ].slice(0, exposure.maxPositions);

    const weights = this.calculatePositionWeights(finalStocks, exposure.positionSizing, updatedHoldings);
    const investedCapital = availableCapital * exposure.maxExposure;

    const buys = toBuy
      .map(s => {
        const w = weights.find(pw => pw.symbol === s.symbol);
        return w ? { symbol: s.symbol, weight: w.weight, capital: +(investedCapital * w.weight).toFixed(2) } : null;
      })
      .filter(Boolean) as { symbol: string; weight: number; capital: number }[];

    return {
      buys,
      sells:             sellList,
      cashFraction:      exposure.cashBuffer,
      exposureConfig:    exposure,
      circuitBreaker:    cb,
      rebalanceDecision: rebDec,
    };
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Singleton
// ─────────────────────────────────────────────────────────────────────────────

export const advancedPortfolioManager = new AdvancedPortfolioManager();
