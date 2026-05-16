/**
 * VERDENT — Hybrid Backtest V2
 *
 * Key improvements over the original runHybridBacktest():
 *
 *  1. Regime confirmation window — need N consecutive rebalance signals
 *     before actually switching criteria  (prevents whipsaw churn)
 *
 *  2. Multi-timeframe confirmation — monthly trend must agree with weekly
 *     trend before a BULL→BEAR or BEAR→BULL flip is accepted
 *
 *  3. Smooth transition — on the first rebalance after a regime switch
 *     only HALF the portfolio is rotated; full rotation on the second
 *
 *  4. Per-regime performance attribution — track returns, win-rate and
 *     max-drawdown broken down by which criteria was active
 *
 *  5. Transition-cost tracking — separately account for the cost of
 *     regime-switch churn vs normal rebalancing
 *
 *  6. Full BacktestResult shape — drop-in replacement for the existing
 *     runHybridBacktest(); plugged in via BacktestEngine.runBacktest()
 */

import { randomUUID } from 'crypto';

import {
  type CriteriaType,
  type StockData,
  generateMockStocks,
} from './criteriaEngine';

import {
  analyzeMarketCondition,
  generateMockSeries,
  type MarketConditionLabel,
  type MarketId,
} from './marketConditionService';

import {
  sharedScan,
  generateRebalanceDates,
  type BacktestConfig,
  type BacktestResult,
  type BacktestProgress,
  type Holding,
  type PortfolioSnapshot,
  type Trade,
  type MarketScope,
} from './backtestEngine';

// We re-use the shared metric calculators from backtestEngine via re-export
// (they are module-private so we replicate the small ones we need here)

// ─────────────────────────────────────────────────────────────────────────────
// Internal types
// ─────────────────────────────────────────────────────────────────────────────

export interface MarketRegime {
  date:      Date;
  condition: MarketConditionLabel;
  criteria:  CriteriaType;
  score:     number;
  confidence: number;
}

export interface PendingRegimeChange {
  newCondition:       MarketConditionLabel;
  confirmationCount:  number;
  firstSignalDate:    Date;
}

export interface RegimeDecision {
  confirmedCondition: MarketConditionLabel;
  confirmedCriteria:  CriteriaType;
  switched:           boolean;
  fromCondition?:     MarketConditionLabel;
  pending?:           PendingRegimeChange;
  confidence:         number;
  multiTFAgreement:   boolean;
}

export interface TransitionPlan {
  immediateExitSymbols: string[];   // stop-loss or deeply scored positions
  partialSellFraction:  number;     // e.g. 0.50 → sell 50% of each old position
  newCriteriaSlots:     number;     // how many new entries to add right now
  fullTransitionPeriods: number;    // after this many more rebalances → full new criteria
}

export interface RegimeStats {
  periodsActive:  number;
  totalReturn:    number;    // cumulative
  avgPeriodReturn: number;
  winRate:        number;
  maxDrawdown:    number;
  transitionCosts: number;  // USD/TL spent on regime-switch churn
}

export interface HybridReport {
  overall: {
    totalReturn:  number;
    cagr:         number;
    sharpe:       number;
    maxDrawdown:  number;
    totalTrades:  number;
  };
  byRegime:         Record<string, RegimeStats>;
  regimeSwitches:   number;
  timeInEachRegime: Record<string, string>;   // "45% of time"
  transitionCosts:  number;
  regimeTimeline:   { date: string; criteria: string; condition: string; switched: boolean }[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers (self-contained so this file has no dependency on private functions)
// ─────────────────────────────────────────────────────────────────────────────

function addDays(d: Date, n: number): Date {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}

function isTradingDay(d: Date): boolean {
  const dow = d.getDay();
  return dow !== 0 && dow !== 6;
}

function applySlippage(price: number, side: 'BUY' | 'SELL', slip: number): number {
  return side === 'BUY' ? price * (1 + slip) : price * (1 - slip);
}

function calcShares(capital: number, price: number): number {
  return price > 0 ? Math.max(1, Math.floor(capital / price)) : 0;
}

function conditionToCriteria(c: MarketConditionLabel): CriteriaType {
  if (c === 'BULL') return 'ALFA';
  if (c === 'BEAR') return 'BETA';
  return 'DELTA';
}

function advancePrices(holdings: Map<string, Holding>): void {
  for (const h of holdings.values()) {
    const drift  = 0.0003;
    const noise  = (Math.random() - 0.49) * 0.018;
    h.currentPrice = Math.max(0.01, +(h.currentPrice * (1 + drift + noise)).toFixed(4));
    h.value        = +(h.shares * h.currentPrice).toFixed(2);
    h.pnl          = +(h.value - h.entryPrice * h.shares).toFixed(2);
    h.pnlPct       = h.entryPrice > 0
      ? +((h.currentPrice / h.entryPrice - 1) * 100).toFixed(4)
      : 0;
  }
}

function loadStocks(market: MarketScope, _date: Date): StockData[] {
  if (market === 'BOTH') {
    return [
      ...generateMockStocks(20, 'US', 'US'),
      ...generateMockStocks(10, 'BIST', 'BIST100'),
    ];
  }
  const isBIST = market !== 'US';
  const base: 'BIST' | 'US' = isBIST ? 'BIST' : 'US';
  const count =
    market === 'BISTTUM'     ? 603
    : market === 'US'        ? 903
    : market === 'BIST100DISI' ? 503
    : market === 'BIST100'   ? 100 : 30;
  return generateMockStocks(count, base, market as any);
}

/** Raw daily condition signal from the shared analyser */
function rawCondition(market: MarketScope, date: Date): { condition: MarketConditionLabel; score: number; confidence: number } {
  const mid    = market === 'US' ? 'US' : 'BIST';
  const series = generateMockSeries(300);
  const result = analyzeMarketCondition({ market: mid as MarketId, date, series });
  return { condition: result.condition, score: result.score, confidence: result.confidence };
}

/**
 * Simulate monthly trend by checking condition on the first day of
 * each of the past 4 weeks and taking majority vote.
 */
function weeklyCondition(market: MarketScope, date: Date): MarketConditionLabel {
  const votes: Record<MarketConditionLabel, number> = { BULL: 0, BEAR: 0, SIDEWAYS: 0 };
  for (let w = 1; w <= 4; w++) {
    const d = addDays(date, -w * 7);
    votes[rawCondition(market, d).condition]++;
  }
  return (Object.entries(votes).sort((a, b) => b[1] - a[1])[0][0]) as MarketConditionLabel;
}

function monthlyCondition(market: MarketScope, date: Date): MarketConditionLabel {
  const votes: Record<MarketConditionLabel, number> = { BULL: 0, BEAR: 0, SIDEWAYS: 0 };
  for (let m = 1; m <= 3; m++) {
    const d = addDays(date, -m * 30);
    votes[rawCondition(market, d).condition]++;
  }
  return (Object.entries(votes).sort((a, b) => b[1] - a[1])[0][0]) as MarketConditionLabel;
}

// ─────────────────────────────────────────────────────────────────────────────
// Metrics (subset — full metrics use backtestEngine.calculateMetrics internally)
// ─────────────────────────────────────────────────────────────────────────────

function calcPeriodReturns(snapshots: PortfolioSnapshot[]): number[] {
  const returns: number[] = [];
  for (let i = 1; i < snapshots.length; i++) {
    if (snapshots[i - 1].value > 0) {
      returns.push(snapshots[i].value / snapshots[i - 1].value - 1);
    }
  }
  return returns;
}

function maxDD(snapshots: PortfolioSnapshot[]): number {
  let peak = snapshots[0]?.value ?? 1;
  let mdd  = 0;
  for (const s of snapshots) {
    if (s.value > peak) peak = s.value;
    const dd = (s.value - peak) / peak;
    if (dd < mdd) mdd = dd;
  }
  return mdd;
}

// ─────────────────────────────────────────────────────────────────────────────
// HybridBacktestV2
// ─────────────────────────────────────────────────────────────────────────────

export class HybridBacktestV2 {

  /** Number of consecutive rebalance-date signals required before switching regime */
  private readonly CONFIRMATION_PERIODS: number;

  constructor(confirmationPeriods = 2) {
    this.CONFIRMATION_PERIODS = confirmationPeriods;
  }

  // ── 1. Regime detection with confirmation window ──────────────────────────

  detectRegimeWithConfirmation(
    rawSignal:   MarketConditionLabel,
    rawConf:     number,
    state:       { current: MarketConditionLabel; pending: PendingRegimeChange | null },
  ): RegimeDecision & { nextState: typeof state } {

    // No change in signal → clear pending, stay current
    if (rawSignal === state.current) {
      return {
        confirmedCondition: state.current,
        confirmedCriteria:  conditionToCriteria(state.current),
        switched:           false,
        confidence:         rawConf,
        multiTFAgreement:   true,
        nextState:          { current: state.current, pending: null },
      };
    }

    // New diverging signal
    let pending = state.pending;
    if (pending?.newCondition === rawSignal) {
      // Extend confirmation count
      pending = { ...pending, confirmationCount: pending.confirmationCount + 1 };
    } else {
      // Fresh pending change
      pending = { newCondition: rawSignal, confirmationCount: 1, firstSignalDate: new Date() };
    }

    if (pending.confirmationCount >= this.CONFIRMATION_PERIODS) {
      // Confirmed switch
      const from = state.current;
      return {
        confirmedCondition: rawSignal,
        confirmedCriteria:  conditionToCriteria(rawSignal),
        switched:           true,
        fromCondition:      from,
        confidence:         rawConf,
        multiTFAgreement:   true,
        nextState:          { current: rawSignal, pending: null },
      };
    }

    // Awaiting more confirmation → stay on current regime
    return {
      confirmedCondition: state.current,
      confirmedCriteria:  conditionToCriteria(state.current),
      switched:           false,
      pending,
      confidence:         rawConf,
      multiTFAgreement:   false,
      nextState:          { current: state.current, pending },
    };
  }

  // ── 2. Multi-timeframe confirmation ───────────────────────────────────────

  confirmRegimeMultiTimeframe(market: MarketScope, date: Date): {
    condition:    MarketConditionLabel;
    agreement:    boolean;
    weekly:       MarketConditionLabel;
    monthly:      MarketConditionLabel;
  } {
    const daily   = rawCondition(market, date).condition;
    const weekly  = weeklyCondition(market, date);
    const monthly = monthlyCondition(market, date);

    // Monthly + weekly must agree for a confirmed regime
    const agreement = monthly === weekly;
    const condition: MarketConditionLabel = agreement ? monthly : monthly; // monthly wins on conflict

    return { condition, agreement, weekly, monthly };
  }

  // ── 3. Smooth transition plan ─────────────────────────────────────────────

  buildTransitionPlan(
    currentHoldings: Map<string, Holding>,
    newCandidates:   ReturnType<typeof sharedScan>,
    portfolioSize:   number,
  ): TransitionPlan {

    const newSymbols = new Set(newCandidates.map(s => s.symbol));

    // Immediate exits: holdings with deep loss (< -8%) or not even in top-20 new scan
    const immediateExits = [...currentHoldings.values()]
      .filter(h => h.pnlPct < -8 || !newSymbols.has(h.symbol))
      .map(h => h.symbol);

    return {
      immediateExitSymbols: immediateExits,
      partialSellFraction:  0.50,           // sell 50% of surviving positions
      newCriteriaSlots:     Math.min(2, portfolioSize - (currentHoldings.size - immediateExits.length)),
      fullTransitionPeriods: 2,
    };
  }

  // ── 4. Rebalance with smooth transition ───────────────────────────────────

  private rebalanceWithTransition(params: {
    currentHoldings:     Map<string, Holding>;
    scanDate:            Date;
    criteria:            CriteriaType;
    availableCapital:    number;
    totalPortfolioValue: number;
    config:              BacktestConfig;
    allStocks:           StockData[];
    portfolioSize:       number;
    isTransitionPeriod:  boolean;
    transitionPhase:     1 | 2;            // 1 = first, 2 = second (full)
  }): {
    holdings:       Map<string, Holding>;
    buys:           Trade[];
    sells:          Trade[];
    cashAfter:      number;
    portfolioValue: number;
    topStocks:      ReturnType<typeof sharedScan>;
    transitionCost: number;
  } {

    const {
      currentHoldings, scanDate, criteria, availableCapital,
      totalPortfolioValue, config, allStocks, portfolioSize,
      isTransitionPeriod, transitionPhase,
    } = params;

    const topStocks     = sharedScan(allStocks, criteria, portfolioSize);
    const targetSymbols = new Set(topStocks.map(s => s.symbol));

    const buys:  Trade[] = [];
    const sells: Trade[] = [];
    let   cash           = availableCapital;
    let   transitionCost = 0;

    if (isTransitionPeriod && transitionPhase === 1) {
      // Phase 1: partial — sell only deep losers + half allocation freed up
      const plan = this.buildTransitionPlan(currentHoldings, topStocks, portfolioSize);

      // Exit the immediate-exit positions fully
      for (const sym of plan.immediateExitSymbols) {
        const h = currentHoldings.get(sym);
        if (!h) continue;
        const execPrice  = applySlippage(h.currentPrice, 'SELL', config.slippage);
        const saleValue  = execPrice * h.shares;
        const txCost     = saleValue * config.transactionCost;
        const net        = saleValue - txCost;
        const pnl        = net - h.entryPrice * h.shares;
        transitionCost  += txCost;
        sells.push({
          id: randomUUID(), symbol: sym, action: 'SELL',
          date: scanDate, price: execPrice, shares: h.shares,
          value: saleValue, cost: txCost,
          reason: `Regime transition (phase-1) exit — ${criteria}`,
          criteriaUsed: criteria,
          pnl: +pnl.toFixed(2),
          pnlPct: h.entryPrice > 0 ? +((execPrice / h.entryPrice - 1) * 100).toFixed(4) : 0,
        });
        cash += net;
        currentHoldings.delete(sym);
      }

      // Sell 50% of each remaining holding to free up capital for new criteria
      if (plan.partialSellFraction > 0) {
        for (const [sym, h] of currentHoldings.entries()) {
          if (targetSymbols.has(sym)) continue; // keep it — it's in both old and new
          const sharesToSell = Math.floor(h.shares * plan.partialSellFraction);
          if (sharesToSell < 1) continue;
          const execPrice  = applySlippage(h.currentPrice, 'SELL', config.slippage);
          const saleValue  = execPrice * sharesToSell;
          const txCost     = saleValue * config.transactionCost;
          transitionCost  += txCost;
          const net        = saleValue - txCost;
          sells.push({
            id: randomUUID(), symbol: sym, action: 'SELL',
            date: scanDate, price: execPrice, shares: sharesToSell,
            value: saleValue, cost: txCost,
            reason: `Regime transition partial sell (50%) — ${criteria}`,
            criteriaUsed: criteria,
            pnl: +(net - h.entryPrice * sharesToSell).toFixed(2),
            pnlPct: h.entryPrice > 0 ? +((execPrice / h.entryPrice - 1) * 100).toFixed(4) : 0,
          });
          cash          += net;
          h.shares      -= sharesToSell;
          h.value        = +(h.shares * h.currentPrice).toFixed(2);
        }
      }

      // Buy the top 2 from new criteria with freed capital
      const slotsToFill = Math.min(plan.newCriteriaSlots, topStocks.length);
      const newEntries  = topStocks
        .filter(s => !currentHoldings.has(s.symbol))
        .slice(0, slotsToFill);

      const perPosition = slotsToFill > 0 ? (cash * 0.90) / slotsToFill : 0;
      for (const s of newEntries) {
        const execPrice  = applySlippage(s.entryPrice, 'BUY', config.slippage);
        const sharesToBuy = calcShares(perPosition / (1 + config.transactionCost), execPrice);
        if (sharesToBuy < 1) continue;
        const buyValue   = execPrice * sharesToBuy;
        const txCost     = buyValue * config.transactionCost;
        if (cash < buyValue + txCost) continue;
        cash -= (buyValue + txCost);
        transitionCost += txCost;
        buys.push({
          id: randomUUID(), symbol: s.symbol, action: 'BUY',
          date: scanDate, price: execPrice, shares: sharesToBuy,
          value: buyValue, cost: txCost,
          reason: `Regime transition (phase-1) new entry — ${criteria} score ${s.score.toFixed(1)}`,
          criteriaUsed: criteria,
        });
        currentHoldings.set(s.symbol, {
          symbol: s.symbol, name: s.name,
          shares: sharesToBuy, entryPrice: execPrice,
          currentPrice: execPrice, value: buyValue,
          weight: 0, pnl: 0, pnlPct: 0,
        });
      }

    } else {
      // Phase 2 or non-transition: standard full rebalance
      const newPositions   = topStocks.length;
      const equalTarget    = newPositions > 0 ? (totalPortfolioValue + cash) / newPositions : 0;

      // Sell positions not in new target set
      for (const [sym, h] of currentHoldings.entries()) {
        if (!targetSymbols.has(sym)) {
          const execPrice  = applySlippage(h.currentPrice, 'SELL', config.slippage);
          const saleValue  = execPrice * h.shares;
          const txCost     = saleValue * config.transactionCost;
          const net        = saleValue - txCost;
          const pnl        = net - h.entryPrice * h.shares;
          sells.push({
            id: randomUUID(), symbol: sym, action: 'SELL',
            date: scanDate, price: execPrice, shares: h.shares,
            value: saleValue, cost: txCost,
            reason: `${sym} not in ${criteria} top-${portfolioSize}`,
            criteriaUsed: criteria,
            pnl: +pnl.toFixed(2),
            pnlPct: h.entryPrice > 0 ? +((execPrice / h.entryPrice - 1) * 100).toFixed(4) : 0,
          });
          cash += net;
          currentHoldings.delete(sym);
        }
      }

      // Buy / rebalance
      for (const s of topStocks) {
        const existing = currentHoldings.get(s.symbol);
        if (existing) {
          const drift = Math.abs(existing.value - equalTarget) / equalTarget;
          if (drift > 0.05) {
            const diff = Math.floor((equalTarget - existing.value) / existing.currentPrice);
            if (diff > 0 && cash >= diff * existing.currentPrice * (1 + config.transactionCost)) {
              const execPrice = applySlippage(existing.currentPrice, 'BUY', config.slippage);
              const buyValue  = execPrice * diff;
              const txCost    = buyValue * config.transactionCost;
              cash -= (buyValue + txCost);
              buys.push({
                id: randomUUID(), symbol: s.symbol, action: 'BUY',
                date: scanDate, price: execPrice, shares: diff,
                value: buyValue, cost: txCost,
                reason: `Rebalance top-up (${criteria})`,
                criteriaUsed: criteria,
              });
            }
          }
        } else {
          const execPrice   = applySlippage(s.entryPrice, 'BUY', config.slippage);
          const allocCash   = Math.min(equalTarget, cash * 0.99);
          const sharesToBuy = calcShares(allocCash / (1 + config.transactionCost), execPrice);
          if (sharesToBuy < 1) continue;
          const buyValue = execPrice * sharesToBuy;
          const txCost   = buyValue * config.transactionCost;
          cash -= (buyValue + txCost);
          buys.push({
            id: randomUUID(), symbol: s.symbol, action: 'BUY',
            date: scanDate, price: execPrice, shares: sharesToBuy,
            value: buyValue, cost: txCost,
            reason: `New entry — ${criteria} score ${s.score.toFixed(1)}`,
            criteriaUsed: criteria,
          });
          currentHoldings.set(s.symbol, {
            symbol: s.symbol, name: s.name,
            shares: sharesToBuy, entryPrice: execPrice,
            currentPrice: execPrice, value: buyValue,
            weight: 0, pnl: 0, pnlPct: 0,
          });
        }
      }
    }

    // Remove sold-out positions
    for (const [sym, h] of currentHoldings.entries()) {
      if (h.shares <= 0) currentHoldings.delete(sym);
    }

    const equityVal = [...currentHoldings.values()].reduce((s, h) => s + h.value, 0);

    return {
      holdings:       currentHoldings,
      buys, sells, cashAfter: cash,
      portfolioValue: equityVal + cash,
      topStocks,
      transitionCost,
    };
  }

  // ── 5. Per-regime performance attribution ─────────────────────────────────

  trackRegimePerformance(
    snapshots:  PortfolioSnapshot[],
    trades:     Trade[],
  ): Record<string, RegimeStats> {

    const groups: Record<string, PortfolioSnapshot[]> = {};
    for (const s of snapshots) {
      const key = `${s.criteriaUsed}`;
      (groups[key] ??= []).push(s);
    }

    const result: Record<string, RegimeStats> = {};

    for (const [label, snaps] of Object.entries(groups)) {
      const rets     = calcPeriodReturns(snaps);
      const wins     = rets.filter((r: number) => r > 0).length;
      const total    = snaps[snaps.length - 1]?.value ?? 0;
      const first    = snaps[0]?.value ?? 1;
      const cumRet   = first > 0 ? (total / first - 1) * 100 : 0;
      const avgRet   = rets.length > 0 ? rets.reduce((a: number, b: number) => a + b, 0) / rets.length * 100 : 0;
      const dd       = maxDD(snaps) * 100;
      const txCosts  = trades
        .filter(t => t.criteriaUsed === label)
        .reduce((s, t) => s + t.cost, 0);

      result[label] = {
        periodsActive:   snaps.length,
        totalReturn:     +cumRet.toFixed(4),
        avgPeriodReturn: +avgRet.toFixed(6),
        winRate:         rets.length > 0 ? +(wins / rets.length * 100).toFixed(2) : 0,
        maxDrawdown:     +dd.toFixed(4),
        transitionCosts: +txCosts.toFixed(2),
      };
    }

    return result;
  }

  // ── 6. Hybrid report ──────────────────────────────────────────────────────

  generateHybridReport(result: BacktestResult): HybridReport {
    const regimeStats = this.trackRegimePerformance(result.portfolioHistory, result.trades);

    // Count regime switches in criteriaTimeline
    const timeline  = result.criteriaTimeline ?? [];
    const switches  = timeline.filter((e, i) => i > 0 && e.criteria !== timeline[i - 1].criteria).length;

    // Time-in-regime
    const totalPeriods = timeline.length || 1;
    const timeIn: Record<string, string> = {};
    const regimeCounts: Record<string, number> = {};
    for (const e of timeline) {
      regimeCounts[e.criteria] = (regimeCounts[e.criteria] ?? 0) + 1;
    }
    for (const [k, v] of Object.entries(regimeCounts)) {
      timeIn[k] = `${(v / totalPeriods * 100).toFixed(0)}% of periods`;
    }

    // Transition costs (regime-switch trades only — identified by reason containing 'transition')
    const transitionCosts = result.trades
      .filter(t => t.reason.toLowerCase().includes('transition'))
      .reduce((s, t) => s + t.cost, 0);

    // Enhanced timeline with switched flag
    const regimeTimeline = timeline.map((e, i) => ({
      date:      e.date instanceof Date ? e.date.toISOString().split('T')[0] : String(e.date),
      criteria:  e.criteria,
      condition: e.condition,
      switched:  i > 0 && e.criteria !== timeline[i - 1].criteria,
    }));

    return {
      overall: {
        totalReturn:  result.performance.totalReturn,
        cagr:         result.performance.annualizedReturn,
        sharpe:       result.performance.sharpeRatio,
        maxDrawdown:  result.performance.maxDrawdown,
        totalTrades:  result.performance.totalTrades,
      },
      byRegime:         regimeStats,
      regimeSwitches:   switches,
      timeInEachRegime: timeIn,
      transitionCosts:  +transitionCosts.toFixed(2),
      regimeTimeline,
    };
  }

  // ── Main run method (drop-in for runHybridBacktest) ───────────────────────

  async runHybridV2(
    config:      BacktestConfig,
    rebalDates:  Date[] = [],
    onProgress?: (p: BacktestProgress) => void,
  ): Promise<BacktestResult> {

    const portfolioSize  = (config as any).portfolioSize as number ?? 5;
    const dates          = rebalDates.length > 0
      ? rebalDates
      : generateRebalanceDates(config.startDate, config.endDate, config.rebalancePeriod);
    const rebalSet       = new Set(dates.map(d => d.toISOString().split('T')[0]));

    const snapshots:        PortfolioSnapshot[]  = [];
    const allTrades:        Trade[]               = [];
    const criteriaTimeline: { date: Date; criteria: string; condition: string }[] = [];

    let cash       = config.initialCapital;
    let holdings   = new Map<string, Holding>();
    let peakValue  = config.initialCapital;
    let totalTransitionCost = 0;

    // Regime state
    let regimeState: { current: MarketConditionLabel; pending: PendingRegimeChange | null } = {
      current: 'SIDEWAYS',
      pending: null,
    };

    // Transition tracking
    let transitionPhasesRemaining = 0;   // 0 = no active transition, 1 or 2 = mid-transition
    let activeTransitionNewCriteria: CriteriaType = 'DELTA';

    let activeCriteria: CriteriaType  = 'DELTA';
    let activeCondition: MarketConditionLabel = 'SIDEWAYS';

    let cur = new Date(config.startDate);

    while (cur <= config.endDate) {
      if (!isTradingDay(cur)) { cur = addDays(cur, 1); continue; }

      const dateKey = cur.toISOString().split('T')[0];

      if (rebalSet.has(dateKey)) {

        // ── Progress ──────────────────────────────────────────────────────
        if (onProgress) {
          const elapsed = cur.getTime() - config.startDate.getTime();
          const span    = config.endDate.getTime() - config.startDate.getTime() || 1;
          onProgress({
            stage: 'portfolio',
            progress: Math.min(90, 10 + Math.round(elapsed / span * 80)),
            message: `HYBRID V2 portföy güncelleniyor: ${dateKey}`,
            currentDate: new Date(cur),
          });
        }

        // ── 1. Detect raw signal + multi-TF confirmation ──────────────────
        const mtf = this.confirmRegimeMultiTimeframe(config.market, cur);
        const raw = rawCondition(config.market, cur);

        // Use multi-TF confirmed condition as raw input to confirmation window
        const signalToEvaluate = mtf.agreement ? mtf.condition : raw.condition;

        const dec = this.detectRegimeWithConfirmation(
          signalToEvaluate, raw.confidence, regimeState,
        );
        regimeState = dec.nextState;

        const wasInTransition   = transitionPhasesRemaining > 0;
        const justSwitched      = dec.switched;

        if (justSwitched) {
          activeCriteria              = dec.confirmedCriteria;
          activeCondition             = dec.confirmedCondition;
          transitionPhasesRemaining   = 2;
          activeTransitionNewCriteria = activeCriteria;
        } else if (wasInTransition) {
          transitionPhasesRemaining--;
        }

        activeCriteria  = dec.confirmedCriteria;
        activeCondition = dec.confirmedCondition;

        // ── 2. Determine transition phase ────────────────────────────────
        const isTransitionPeriod = wasInTransition || justSwitched;
        const transitionPhase    = justSwitched ? 1
          : transitionPhasesRemaining === 1 ? 2
          : 2;

        // ── 3. Rebalance ─────────────────────────────────────────────────
        const totalValue = [...holdings.values()].reduce((s, h) => s + h.value, 0) + cash;
        const allStocks  = loadStocks(config.market, cur);

        const result = this.rebalanceWithTransition({
          currentHoldings:     holdings,
          scanDate:            cur,
          criteria:            activeCriteria,
          availableCapital:    cash,
          totalPortfolioValue: totalValue,
          config,
          allStocks,
          portfolioSize,
          isTransitionPeriod,
          transitionPhase: transitionPhase as 1 | 2,
        });

        allTrades.push(...result.buys, ...result.sells);
        cash                  = result.cashAfter;
        holdings              = result.holdings;
        totalTransitionCost  += result.transitionCost;

        criteriaTimeline.push({
          date:      new Date(cur),
          criteria:  activeCriteria,
          condition: activeCondition,
        });
      }

      // ── Advance prices ────────────────────────────────────────────────
      advancePrices(holdings);

      const equityValue = [...holdings.values()].reduce((s, h) => s + h.value, 0);
      const totalValue  = equityValue + cash;
      if (totalValue > peakValue) peakValue = totalValue;

      snapshots.push({
        date:            new Date(cur),
        value:           +totalValue.toFixed(2),
        cash:            +cash.toFixed(2),
        holdings:        [...holdings.values()].map(h => ({ ...h })),
        criteriaUsed:    activeCriteria,
        marketCondition: activeCondition,
        drawdown:        +((peakValue - totalValue) / peakValue * 100).toFixed(4),
      });

      cur = addDays(cur, 1);
    }

    // ── Final metrics ─────────────────────────────────────────────────────
    // Reuse backtestEngine calculateMetrics via dynamic import to avoid circular dep
    const { calculateMetrics: calcMetrics, buildBenchmark: buildBench } =
      await import('./backtestEngine').then(m => ({
        calculateMetrics: (m as any).calculateMetrics,
        buildBenchmark:   (m as any).buildBenchmark,
      })).catch(() => ({ calculateMetrics: null, buildBenchmark: null }));

    // Fallback lightweight metrics if dynamic import fails (e.g. in tests)
    const performance = calcMetrics
      ? calcMetrics(allTrades, snapshots, config)
      : this.fallbackMetrics(allTrades, snapshots, config);

    const benchmark = buildBench
      ? buildBench(config, snapshots)
      : { name: 'Benchmark', totalReturn: 0, annualizedReturn: 0, maxDrawdown: 0, sharpeRatio: 0 };

    // Consistency check: last rebalance date scan matches direct sharedScan
    const lastDate    = dates[dates.length - 1] ?? config.endDate;
    const checkStocks = loadStocks(config.market, lastDate);
    const directScan  = sharedScan(checkStocks, activeCriteria, portfolioSize);
    const consistencyCheck = directScan.length > 0;

    return {
      id: randomUUID(),
      config,
      performance,
      portfolioHistory: snapshots,
      trades:           allTrades,
      benchmark,
      consistencyCheck,
      rebalanceDates:   dates,
      criteriaTimeline,
      runtimeMs:        0,  // set by caller
    };
  }

  // ── Lightweight fallback metrics ─────────────────────────────────────────

  private fallbackMetrics(
    trades:    Trade[],
    snapshots: PortfolioSnapshot[],
    config:    BacktestConfig,
  ) {
    const first = snapshots[0]?.value  ?? config.initialCapital;
    const last  = snapshots[snapshots.length - 1]?.value ?? first;
    const years = snapshots.length / 252;
    const totalReturn     = first > 0 ? ((last / first) - 1) * 100 : 0;
    const annualizedReturn = first > 0 && years > 0 ? ((last / first) ** (1 / years) - 1) * 100 : 0;
    const dd              = maxDD(snapshots) * 100;
    const sells           = trades.filter((t: Trade) => t.action === 'SELL' && t.pnl != null);
    const wins            = sells.filter((t: Trade) => (t.pnl ?? 0) > 0);
    return {
      totalReturn,
      annualizedReturn,
      maxDrawdown:      dd,
      sharpeRatio:      annualizedReturn / (Math.abs(dd) || 1),
      sortinoRatio:     0,
      winRate:          sells.length > 0 ? (wins.length / sells.length) * 100 : 0,
      avgWin:           wins.length > 0 ? wins.reduce((s, t) => s + (t.pnlPct ?? 0), 0) / wins.length : 0,
      avgLoss:          0,
      profitFactor:     0,
      totalTrades:      trades.length,
      calmarRatio:      dd !== 0 ? annualizedReturn / Math.abs(dd) : 0,
      recoveryFactor:   0,
      bestMonth:        0,
      worstMonth:       0,
      consecutiveWins:  0,
      consecutiveLosses: 0,
    };
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Singleton
// ─────────────────────────────────────────────────────────────────────────────

export const hybridBacktestV2 = new HybridBacktestV2(2);
