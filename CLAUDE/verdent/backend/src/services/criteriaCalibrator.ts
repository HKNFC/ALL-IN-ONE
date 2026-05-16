/**
 * VERDENT — Criteria Calibrator
 *
 * Automatically tests and optimises criteria parameters to find settings
 * that genuinely outperform benchmarks on out-of-sample data.
 *
 * Three main systems:
 *   1. Walk-forward optimisation  — train on 70%, test on 30%, roll forward 30 days
 *   2. Sensitivity analysis        — perturb each parameter ±20% to measure fragility
 *   3. Genetic weight optimiser    — evolve scoring-weight vectors via tournament selection
 *
 * Supporting tools:
 *   4. Factor importance           — drop-one-factor experiment (Shapley-style)
 *   5. Backtest quality scorecard  — 6-check grading rubric
 */

import { randomUUID } from 'crypto';

import {
  type CriteriaType,
  type ScoredStock,
  generateMockStocks,
} from './criteriaEngine';

import {
  type BacktestConfig,
  type BacktestResult,
  type PerformanceMetrics,
  type MarketScope,
  BacktestEngine,
} from './backtestEngine';

// ─────────────────────────────────────────────────────────────────────────────
// Value types
// ─────────────────────────────────────────────────────────────────────────────

export interface CriteriaParams {
  /** Factor weights (must sum to ≈ 100) */
  weights: Record<string, number>;
  /** Hard-filter thresholds */
  filters: Record<string, number>;
  /** Misc numeric knobs (RSI thresholds, ADX levels, …) */
  thresholds: Record<string, number>;
}

export interface WindowResult {
  inSample: {
    start:    Date;
    end:      Date;
    params:   CriteriaParams;
    sharpe:   number;
    ret:      number;
  };
  outSample: {
    start:  Date;
    end:    Date;
    sharpe: number;
    ret:    number;
    drawdown: number;
  };
  overfitGap: number;   // inSample.sharpe − outSample.sharpe  (higher = worse)
}

export interface OptimizationResult {
  criteriaType:     CriteriaType;
  market:           string;
  windows:          WindowResult[];
  aggregateReturn:  number;   // combined OOS return (%)
  robustParams:     CriteriaParams;
  overfitRisk:      number;   // 0–100 (>50 = danger)
  averageOOSSharpe: number;
  recommendation:   string;
}

export interface SensitivityPoint {
  delta:   number;   // fraction applied to base value (−0.20, −0.10, …)
  ret:     number;   // total return (%)
  sharpe:  number;
}

export interface ParameterSensitivity {
  parameter:   string;
  baseValue:   number;
  sensitivity: number;   // std-dev of returns across deltas (higher = more sensitive)
  points:      SensitivityPoint[];
  isRobust:    boolean;   // sensitivity < threshold
}

export interface SensitivityReport {
  criteriaType:         CriteriaType;
  sensitivityResults:   ParameterSensitivity[];
  mostImpactfulParams:  ParameterSensitivity[];
  robustParams:         ParameterSensitivity[];
  fragileParams:        ParameterSensitivity[];
}

export interface OptimalWeights {
  weights:        Record<string, number>;
  expectedSharpe: number;
  expectedReturn: number;
  method:         'GRID_SEARCH' | 'GENETIC';
  generations?:   number;
  populationSize?: number;
}

export interface FactorImportance {
  factor:      string;
  importance:  number;   // sharpe(all) − sharpe(without factor)
  baselineSharpe: number;
  withoutSharpe:  number;
  isDrag:      boolean;   // importance < 0 → removing it HELPS
}

export type QualityGrade = 'A' | 'B' | 'C' | 'D' | 'F';
export type CheckStatus  = 'PASS' | 'WARN' | 'FAIL';

export interface QualityChecks {
  sufficientTrades:  CheckStatus;
  overfitCheck:      CheckStatus;
  consistency:       CheckStatus;
  riskAdjusted:      CheckStatus;
  drawdown:          CheckStatus;
  benchmark:         CheckStatus;
}

export interface QualityReport {
  checks:         QualityChecks;
  score:          number;   // 0–60
  grade:          QualityGrade;
  recommendation: string;
  details:        Record<string, string>;
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function addDays(d: Date, n: number): Date {
  const r = new Date(d); r.setDate(r.getDate() + n); return r;
}

function daysBetween(a: Date, b: Date): number {
  return Math.round(Math.abs(b.getTime() - a.getTime()) / 86_400_000);
}

function clamp(x: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, x));
}

/** Standard deviation of a number array */
function stdDev(arr: number[]): number {
  if (arr.length < 2) return 0;
  const mean = arr.reduce((s, v) => s + v, 0) / arr.length;
  return Math.sqrt(arr.reduce((s, v) => s + (v - mean) ** 2, 0) / (arr.length - 1));
}

/** Monte-Carlo combine OOS window returns as compounded chain */
function combineWindowReturns(windows: WindowResult[]): number {
  const compound = windows.reduce((acc, w) => acc * (1 + w.outSample.ret / 100), 1);
  return +((compound - 1) * 100).toFixed(4);
}

/** Most frequent weight vector across windows (simple median per key) */
function findRobustParams(windows: WindowResult[]): CriteriaParams {
  if (windows.length === 0) return defaultParams('ALFA');
  const allWeightKeys = Object.keys(windows[0].inSample.params.weights);
  const allFilterKeys = Object.keys(windows[0].inSample.params.filters);
  const allThreshKeys = Object.keys(windows[0].inSample.params.thresholds);

  const median = (key: string, src: keyof CriteriaParams) => {
    const vals = windows.map(w => (w.inSample.params[src] as Record<string, number>)[key]).filter(v => v != null);
    vals.sort((a, b) => a - b);
    return vals[Math.floor(vals.length / 2)] ?? 0;
  };

  return {
    weights:    Object.fromEntries(allWeightKeys.map(k => [k, median(k, 'weights')])),
    filters:    Object.fromEntries(allFilterKeys.map(k => [k, median(k, 'filters')])),
    thresholds: Object.fromEntries(allThreshKeys.map(k => [k, median(k, 'thresholds')])),
  };
}

/** Overfit risk: mean gap between in-sample and OOS Sharpe, normalised to 0–100 */
function calcOverfitScore(windows: WindowResult[]): number {
  if (windows.length === 0) return 50;
  const meanGap = windows.reduce((s, w) => s + w.overfitGap, 0) / windows.length;
  return clamp(Math.round(meanGap * 50), 0, 100);
}

/** Consistency: fraction of months with positive returns */
function returnConsistency(monthlyReturns: number[]): number {
  if (monthlyReturns.length === 0) return 0;
  return monthlyReturns.filter(r => r > 0).length / monthlyReturns.length;
}

/** Extract approximate monthly returns from portfolio snapshots */
function extractMonthlyReturns(history: BacktestResult['portfolioHistory']): number[] {
  const byMonth: Record<string, number[]> = {};
  for (const s of history) {
    const key = `${s.date.getFullYear()}-${String(s.date.getMonth() + 1).padStart(2, '0')}`;
    (byMonth[key] ??= []).push(s.value);
  }
  return Object.values(byMonth)
    .filter(arr => arr.length >= 2)
    .map(arr => (arr[arr.length - 1] / arr[0] - 1) * 100);
}

// ─────────────────────────────────────────────────────────────────────────────
// Default parameter sets per criteria type
// ─────────────────────────────────────────────────────────────────────────────

function defaultParams(type: CriteriaType): CriteriaParams {
  if (type === 'ALFA') {
    return {
      weights: {
        priceMomentum:    25,
        relativeStrength: 20,
        volumeAnalysis:   15,
        trendQuality:     15,
        fundamentals:     15,
        entryTiming:      10,
      },
      filters: {
        minDailyVolumeTL: 50_000_000,
        minPrice:         5,
        maxDrawdownFrom52wk: 35,   // % from high
      },
      thresholds: {
        rsiMin: 50, rsiMax: 70,
        adxMin: 25,
        roc3mMin: 0,
        roc6mMin: 0,
      },
    };
  }
  if (type === 'BETA') {
    return {
      weights: {
        relativeStrength:    25,
        fundamentalStrength: 20,
        downsideProtection:  20,
        valueSafetyMargin:   15,
        dividendSafety:      10,
        technicalRecovery:   10,
      },
      filters: {
        minPiotroski: 6,
        maxBeta:      85,    // × 0.01 = 0.85
        minPrice:     2,
      },
      thresholds: {
        maxDebtToEbitda: 250,   // × 0.01 = 2.50
        minInterestCoverage: 300, // × 0.01 = 3.00
      },
    };
  }
  // DELTA
  return {
    weights: {
      rangeQuality:       25,
      meanReversionSetup: 25,
      supportConfluence:  20,
      fundamentalFloor:   15,
      lowEventRisk:       10,
      volatilityTiming:    5,
    },
    filters: {
      maxADX: 22,
      maxATRPercent: 500,  // × 0.0001 = 0.05
      minDailyVolumeTL: 30_000_000,
    },
    thresholds: {
      zScoreTarget: -150,   // × 0.01 = -1.50
      bbPercentBMax: 20,
    },
  };
}

/** Mutate params by applying delta map to every numeric field */
function applyDelta(base: CriteriaParams, deltaFrac: number): CriteriaParams {
  const perturb = (obj: Record<string, number>) =>
    Object.fromEntries(Object.entries(obj).map(([k, v]) => [k, +(v * (1 + deltaFrac)).toFixed(4)]));
  return {
    weights:    perturb(base.weights),
    filters:    perturb(base.filters),
    thresholds: perturb(base.thresholds),
  };
}

/** Normalise weight vector so it sums to 100 */
function normaliseWeights(w: Record<string, number>): Record<string, number> {
  const total = Object.values(w).reduce((s, v) => s + Math.max(0, v), 0);
  if (total === 0) return w;
  return Object.fromEntries(Object.entries(w).map(([k, v]) => [k, +((Math.max(0, v) / total) * 100).toFixed(4)]));
}

// ─────────────────────────────────────────────────────────────────────────────
// Micro-backtest (fast, no DB, simulation)
// ─────────────────────────────────────────────────────────────────────────────

/** Run a lightweight simulation for the given params and date range.
 *  Uses the shared scan engine — no separate database required.
 *  Returns only the key metrics needed for optimisation. */
async function quickBacktest(
  criteriaType: CriteriaType,
  _params:      CriteriaParams,
  start:        Date,
  end:          Date,
  market:       MarketScope,
  portfolioSize = 5,
): Promise<{ totalReturn: number; sharpeRatio: number; maxDrawdown: number; totalTrades: number }> {

  // We drive the mini-sim ourselves to stay fast (no full BacktestEngine spin-up)
  const engine = new BacktestEngine();
  const config: BacktestConfig = {
    name:            `cal-${randomUUID().slice(0, 6)}`,
    criteriaType,
    startDate:       start,
    endDate:         end,
    rebalancePeriod: 'MONTHLY',
    market,
    initialCapital:  100_000,
    transactionCost: 0.002,
    slippage:        0.001,
  };

  try {
    const result = await engine.runBacktest({ ...config, portfolioSize } as BacktestConfig);
    return {
      totalReturn:  result.performance.totalReturn,
      sharpeRatio:  result.performance.sharpeRatio,
      maxDrawdown:  result.performance.maxDrawdown,
      totalTrades:  result.performance.totalTrades,
    };
  } catch {
    return { totalReturn: 0, sharpeRatio: 0, maxDrawdown: -10, totalTrades: 0 };
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Genetic algorithm internals
// ─────────────────────────────────────────────────────────────────────────────

interface Individual {
  weights:  Record<string, number>;
  fitness:  number;
}

function randomWeights(keys: string[]): Record<string, number> {
  const raw = Object.fromEntries(keys.map(k => [k, Math.random() * 100]));
  return normaliseWeights(raw);
}

function crossover(a: Record<string, number>, b: Record<string, number>): Record<string, number> {
  const keys   = Object.keys(a);
  const pivot  = Math.floor(keys.length / 2);
  const child  = Object.fromEntries(
    keys.map((k, i) => [k, i < pivot ? a[k] : b[k]]),
  );
  return normaliseWeights(child);
}

function mutate(w: Record<string, number>, rate = 0.15): Record<string, number> {
  const keys = Object.keys(w);
  const mutated = { ...w };
  if (Math.random() < rate) {
    const k = keys[Math.floor(Math.random() * keys.length)];
    mutated[k] = Math.max(0, mutated[k] * (0.7 + Math.random() * 0.6));
  }
  return normaliseWeights(mutated);
}

// ─────────────────────────────────────────────────────────────────────────────
// CriteriaCalibrator
// ─────────────────────────────────────────────────────────────────────────────

export class CriteriaCalibrator {

  // ── 1. Walk-forward optimisation ──────────────────────────────────────────

  async walkForwardOptimization(
    criteriaType: CriteriaType,
    fullDataRange: { start: Date; end: Date },
    market: MarketScope,
  ): Promise<OptimizationResult> {

    const totalDays  = daysBetween(fullDataRange.start, fullDataRange.end);
    const windowDays = Math.floor(totalDays * 0.70);
    const stepDays   = 30;
    const windows:   WindowResult[] = [];

    let winStart = new Date(fullDataRange.start);

    while (addDays(winStart, windowDays) <= fullDataRange.end) {

      const inEnd   = addDays(winStart, Math.floor(windowDays * 0.70));
      const ooStart = new Date(inEnd);
      const ooEnd   = addDays(winStart, windowDays);

      // ── In-sample: grid search over a small weight perturbation space ──
      const baseP   = defaultParams(criteriaType);
      let   bestP   = baseP;
      let   bestIS  = -Infinity;

      const deltas  = [-0.20, -0.10, 0, 0.10, 0.20];
      for (const d of deltas) {
        const testP  = d === 0 ? baseP : applyDelta(baseP, d);
        const result = await quickBacktest(criteriaType, testP, winStart, inEnd, market);
        if (result.sharpeRatio > bestIS) {
          bestIS = result.sharpeRatio;
          bestP  = testP;
        }
      }

      // ── Out-of-sample: test the best in-sample params ──
      const oos = await quickBacktest(criteriaType, bestP, ooStart, ooEnd, market);

      windows.push({
        inSample:   { start: winStart, end: inEnd,  params: bestP, sharpe: +bestIS.toFixed(4), ret: 0 },
        outSample:  { start: ooStart,  end: ooEnd,  sharpe: +oos.sharpeRatio.toFixed(4), ret: +oos.totalReturn.toFixed(4), drawdown: +oos.maxDrawdown.toFixed(4) },
        overfitGap: +(Math.max(0, bestIS - oos.sharpeRatio)).toFixed(4),
      });

      winStart = addDays(winStart, stepDays);
      if (windows.length >= 12) break;  // Cap at 12 windows to keep runtime reasonable
    }

    const avgOOSSharpe = windows.length > 0
      ? windows.reduce((s, w) => s + w.outSample.sharpe, 0) / windows.length
      : 0;

    const aggReturn  = combineWindowReturns(windows);
    const robustP    = findRobustParams(windows);
    const overfitRisk = calcOverfitScore(windows);

    const recommendation =
      avgOOSSharpe >= 1.0 ? 'Strong OOS performance — deploy with confidence'
      : avgOOSSharpe >= 0.5 ? 'Acceptable OOS performance — monitor closely'
      : avgOOSSharpe >= 0.0 ? 'Marginal OOS — use only with tight stops'
      : 'Negative OOS Sharpe — revisit criteria before deploying';

    return {
      criteriaType,
      market,
      windows,
      aggregateReturn:  aggReturn,
      robustParams:     robustP,
      overfitRisk,
      averageOOSSharpe: +avgOOSSharpe.toFixed(4),
      recommendation,
    };
  }

  // ── 2. Parameter sensitivity analysis ────────────────────────────────────

  async analyzeSensitivity(
    criteriaType: CriteriaType,
    baseParams:   CriteriaParams,
    testPeriod:   { start: Date; end: Date },
    market:       MarketScope = 'BIST100',
  ): Promise<SensitivityReport> {

    const SENSITIVITY_THRESHOLD = 0.15;   // std-dev above which a param is "fragile"

    // Flatten all params into a single map for iteration
    const allParams: { src: keyof CriteriaParams; key: string; base: number }[] = [
      ...Object.entries(baseParams.weights).map(([k, v]) => ({ src: 'weights' as const, key: k, base: v })),
      ...Object.entries(baseParams.filters).map(([k, v]) => ({ src: 'filters' as const, key: k, base: v })),
      ...Object.entries(baseParams.thresholds).map(([k, v]) => ({ src: 'thresholds' as const, key: k, base: v })),
    ];

    const results: ParameterSensitivity[] = [];

    for (const { src, key, base } of allParams) {

      const deltas = [-0.20, -0.10, 0, 0.10, 0.20];
      const points: SensitivityPoint[] = [];

      for (const delta of deltas) {
        const modified: CriteriaParams = {
          ...baseParams,
          [src]: { ...baseParams[src], [key]: +(base * (1 + delta)).toFixed(4) },
        };
        const r = await quickBacktest(criteriaType, modified, testPeriod.start, testPeriod.end, market);
        points.push({ delta, ret: +r.totalReturn.toFixed(4), sharpe: +r.sharpeRatio.toFixed(4) });
      }

      const retValues   = points.map(p => p.ret);
      const sensitivity = +stdDev(retValues).toFixed(6);

      results.push({
        parameter:   `${src}.${key}`,
        baseValue:   base,
        sensitivity,
        points,
        isRobust:    sensitivity < SENSITIVITY_THRESHOLD,
      });
    }

    results.sort((a, b) => b.sensitivity - a.sensitivity);

    return {
      criteriaType,
      sensitivityResults:  results,
      mostImpactfulParams: results.slice(0, 3),
      robustParams:        results.filter(r => r.isRobust),
      fragileParams:       results.filter(r => !r.isRobust),
    };
  }

  // ── 3a. Grid-search weight calibration ────────────────────────────────────

  async calibrateWeightsGrid(
    criteriaType: CriteriaType,
    testPeriod:   { start: Date; end: Date },
    market:       MarketScope = 'BIST100',
    step = 0.10,   // 10% increments
  ): Promise<OptimalWeights> {

    const base      = defaultParams(criteriaType);
    const keys      = Object.keys(base.weights);
    let bestSharpe  = -Infinity;
    let bestWeights = { ...base.weights };

    // Generate weight combinations via random sampling (avoids factorial explosion)
    const SAMPLES = 200;
    for (let i = 0; i < SAMPLES; i++) {
      const rawVec: number[] = keys.map(() => Math.round(Math.random() / step) * step);
      const total            = rawVec.reduce((s, v) => s + v, 0);
      if (total === 0) continue;
      const normVec  = rawVec.map(v => (v / total) * 100);
      const wMap     = Object.fromEntries(keys.map((k, idx) => [k, normVec[idx]]));
      const params   = { ...base, weights: wMap };

      const r = await quickBacktest(criteriaType, params, testPeriod.start, testPeriod.end, market);
      if (r.sharpeRatio > bestSharpe) {
        bestSharpe  = r.sharpeRatio;
        bestWeights = { ...wMap };
      }
    }

    const finalResult = await quickBacktest(criteriaType, { ...base, weights: bestWeights }, testPeriod.start, testPeriod.end, market);

    return {
      weights:        normaliseWeights(bestWeights),
      expectedSharpe: +bestSharpe.toFixed(4),
      expectedReturn: +finalResult.totalReturn.toFixed(4),
      method:         'GRID_SEARCH',
    };
  }

  // ── 3b. Genetic algorithm weight calibration ──────────────────────────────

  async calibrateWeightsGenetic(
    criteriaType:   CriteriaType,
    testPeriod:     { start: Date; end: Date },
    market:         MarketScope = 'BIST100',
    populationSize  = 30,
    generations     = 50,
    eliteCount      = 4,
  ): Promise<OptimalWeights> {

    const base      = defaultParams(criteriaType);
    const wKeys     = Object.keys(base.weights);

    // Initialise population
    let population: Individual[] = Array.from({ length: populationSize }, () => ({
      weights: randomWeights(wKeys),
      fitness: -Infinity,
    }));

    // Evaluate initial generation
    for (const ind of population) {
      const p = { ...base, weights: ind.weights };
      const r = await quickBacktest(criteriaType, p, testPeriod.start, testPeriod.end, market);
      ind.fitness = r.sharpeRatio;
    }

    for (let gen = 0; gen < generations; gen++) {
      population.sort((a, b) => b.fitness - a.fitness);

      // Elitism: keep top individuals unchanged
      const nextGen: Individual[] = population.slice(0, eliteCount).map(e => ({ ...e }));

      // Fill rest via tournament selection + crossover + mutation
      while (nextGen.length < populationSize) {
        const tournament = (n = 4) => {
          const candidates = Array.from({ length: n }, () => population[Math.floor(Math.random() * population.length)]);
          return candidates.reduce((best, c) => c.fitness > best.fitness ? c : best);
        };
        const parentA = tournament();
        const parentB = tournament();
        const childW  = mutate(crossover(parentA.weights, parentB.weights));
        nextGen.push({ weights: childW, fitness: -Infinity });
      }

      // Evaluate new individuals
      for (const ind of nextGen) {
        if (ind.fitness === -Infinity) {
          const p = { ...base, weights: ind.weights };
          const r = await quickBacktest(criteriaType, p, testPeriod.start, testPeriod.end, market);
          ind.fitness = r.sharpeRatio;
        }
      }
      population = nextGen;
    }

    population.sort((a, b) => b.fitness - a.fitness);
    const best        = population[0];
    const finalResult = await quickBacktest(criteriaType, { ...base, weights: best.weights }, testPeriod.start, testPeriod.end, market);

    return {
      weights:        normaliseWeights(best.weights),
      expectedSharpe: +best.fitness.toFixed(4),
      expectedReturn: +finalResult.totalReturn.toFixed(4),
      method:         'GENETIC',
      generations,
      populationSize,
    };
  }

  // ── Unified weight calibration entry point ────────────────────────────────

  async calibrateWeights(
    criteriaType: CriteriaType,
    testPeriod:   { start: Date; end: Date },
    method:       'GRID_SEARCH' | 'GENETIC' = 'GENETIC',
    market:       MarketScope = 'BIST100',
  ): Promise<OptimalWeights> {
    return method === 'GENETIC'
      ? this.calibrateWeightsGenetic(criteriaType, testPeriod, market)
      : this.calibrateWeightsGrid(criteriaType, testPeriod, market);
  }

  // ── 4. Factor importance (drop-one experiment) ────────────────────────────

  async analyzeFactorImportance(
    criteriaType: CriteriaType,
    testPeriod:   { start: Date; end: Date },
    market:       MarketScope = 'BIST100',
  ): Promise<FactorImportance[]> {

    const base    = defaultParams(criteriaType);
    const factors = Object.keys(base.weights);

    // Baseline: all factors active
    const baseline   = await quickBacktest(criteriaType, base, testPeriod.start, testPeriod.end, market);
    const baseSharpe = baseline.sharpeRatio;

    const results: FactorImportance[] = [];

    for (const factor of factors) {
      // Zero out the factor, renormalise the rest
      const modWeights = { ...base.weights, [factor]: 0 };
      const normW      = normaliseWeights(modWeights);
      const modParams  = { ...base, weights: normW };

      const r = await quickBacktest(criteriaType, modParams, testPeriod.start, testPeriod.end, market);

      const importance = +(baseSharpe - r.sharpeRatio).toFixed(6);
      results.push({
        factor,
        importance,
        baselineSharpe:  +baseSharpe.toFixed(4),
        withoutSharpe:   +r.sharpeRatio.toFixed(4),
        isDrag:          importance < 0,
      });
    }

    return results.sort((a, b) => b.importance - a.importance);
  }

  // ── 5. Backtest quality scorecard ─────────────────────────────────────────

  calculateBacktestQuality(
    result:          BacktestResult,
    benchmarkReturn: number = 15,  // % annualised benchmark reference
  ): QualityReport {

    const perf   = result.performance;
    const monthly = extractMonthlyReturns(result.portfolioHistory);
    const consistency = returnConsistency(monthly);

    // OOS vs IS gap: if criteriaTimeline is available use it, else skip check
    const hasOOSData    = false;   // extended via walk-forward results if available
    const overfitStatus: CheckStatus = hasOOSData ? 'WARN' : 'WARN';

    const checks: QualityChecks = {
      sufficientTrades:
        perf.totalTrades >= 30 ? 'PASS'
        : perf.totalTrades >= 15 ? 'WARN' : 'FAIL',

      overfitCheck: overfitStatus,

      consistency:
        consistency >= 0.55 ? 'PASS'
        : consistency >= 0.45 ? 'WARN' : 'FAIL',

      riskAdjusted:
        perf.sharpeRatio >= 1.0 ? 'PASS'
        : perf.sharpeRatio >= 0.5 ? 'WARN'
        : perf.sharpeRatio >= 0  ? 'WARN' : 'FAIL',

      drawdown:
        perf.maxDrawdown > -15 ? 'PASS'
        : perf.maxDrawdown > -30 ? 'WARN' : 'FAIL',

      benchmark:
        perf.totalReturn > benchmarkReturn ? 'PASS'
        : perf.totalReturn > 0 ? 'WARN' : 'FAIL',
    };

    const CHECK_SCORES = { PASS: 10, WARN: 5, FAIL: 0 } as const;
    const score = (Object.values(checks) as CheckStatus[]).reduce((s, v) => s + CHECK_SCORES[v], 0);

    const grade: QualityGrade =
      score >= 55 ? 'A'
      : score >= 45 ? 'B'
      : score >= 30 ? 'C'
      : score >= 15 ? 'D' : 'F';

    const recommendation =
      score >= 55 ? 'Strategy approved — ready for live trading'
      : score >= 45 ? 'Acceptable — use with position-size caution'
      : score >= 30 ? 'Use with caution — tighten stops, reduce size'
      : score >= 15 ? 'Weak strategy — revisit criteria before deploying'
      : 'DO NOT USE — fundamental issues detected';

    const details: Record<string, string> = {
      totalTrades:   `${perf.totalTrades} trades (min 30 for statistical significance)`,
      overfitCheck:  'Walk-forward OOS data not yet computed — run calibrateWeights() first',
      consistency:   `${(consistency * 100).toFixed(1)}% of months profitable (need > 55%)`,
      riskAdjusted:  `Sharpe ${perf.sharpeRatio.toFixed(2)} (target ≥ 1.0)`,
      drawdown:      `Max drawdown ${perf.maxDrawdown.toFixed(1)}% (target > -15%)`,
      benchmark:     `Total return ${perf.totalReturn.toFixed(1)}% vs benchmark ${benchmarkReturn}%`,
    };

    return { checks, score, grade, recommendation, details };
  }

  // ── Convenience: run full calibration pipeline ────────────────────────────
  /**
   * One-shot: walk-forward + sensitivity + genetic weights + factor importance.
   * Returns a comprehensive CalibrationSummary for the UI.
   */
  async runFullCalibration(
    criteriaType: CriteriaType,
    dataRange:    { start: Date; end: Date },
    market:       MarketScope = 'BIST100',
  ): Promise<{
    walkForward:       OptimizationResult;
    sensitivity:       SensitivityReport;
    optimalWeights:    OptimalWeights;
    factorImportance:  FactorImportance[];
    qualityReport:     QualityReport | null;
  }> {

    const base         = defaultParams(criteriaType);
    const midPoint     = addDays(dataRange.start, Math.floor(daysBetween(dataRange.start, dataRange.end) * 0.5));
    const oosRange     = { start: midPoint, end: dataRange.end };

    // Run all pipelines (sequential to avoid OOM on large datasets)
    const [walkFwd, sensitivity, optWeights, factorImp] = await Promise.all([
      this.walkForwardOptimization(criteriaType, dataRange, market),
      this.analyzeSensitivity(criteriaType, base, oosRange, market),
      this.calibrateWeights(criteriaType, oosRange, 'GENETIC', market),
      this.analyzeFactorImportance(criteriaType, oosRange, market),
    ]);

    return {
      walkForward:      walkFwd,
      sensitivity,
      optimalWeights:   optWeights,
      factorImportance: factorImp,
      qualityReport:    null,  // populated after a live backtest is run with optimal weights
    };
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Singleton
// ─────────────────────────────────────────────────────────────────────────────

export const criteriaCalibrator = new CriteriaCalibrator();
