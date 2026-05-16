/**
 * VERDENT — Stock Screening Criteria Engine
 *
 * Three market-regime criteria sets:
 *  ALFA  — bull-market momentum / growth
 *  BETA  — bear-market defensive / value
 *  DELTA — sideways mean-reversion / range
 *
 * Public API
 * ──────────────────────────────────────────────────────────────────────────
 *  screenStocks(criteria, date, market)   → Promise<ScoredStock[]>
 *  calculateScore(stock, config)          → number  (0–100)
 *  applyFilters(stocks, rules)            → StockData[]
 *  rankStocks(scored)                     → ScoredStock[]  (sorted, ranks set)
 *  getTop5Portfolio(criteria, date, market) → Promise<Portfolio>
 */

import type { PriceBar } from './marketConditionService';
import { alfaCriteriaV2 }   from './criteria/alfaCriteriaV2';
import { betaCriteriaV2 }   from './criteria/betaCriteriaV2';
import { deltaCriteriaV2 }  from './criteria/deltaCriteriaV2';

// ─────────────────────────────────────────────────────────────────────────────
// Domain types
// ─────────────────────────────────────────────────────────────────────────────

export type CriteriaType  = 'ALFA' | 'BETA' | 'DELTA';
export type UniverseType  = 'BISTTUM' | 'BIST100' | 'BIST100DISI' | 'BIST' | 'US';
export type SignalDir    = 'BULLISH' | 'BEARISH' | 'NEUTRAL';

export interface SignalDetail {
  name:        string;
  category:    'technical' | 'fundamental';
  value:       number | string | null;
  threshold:   number | string | null;
  passed:      boolean;
  direction:   SignalDir;
  weight:      number;
  contribution: number;   // weight * (passed ? 1 : 0)
  description: string;
}

export interface StockSignals {
  technical:   SignalDetail[];
  fundamental: SignalDetail[];
  passed:      string[];
  failed:      string[];
}

export interface ScoredStock {
  symbol:           string;
  name:             string;
  score:            number;    // 0–100
  rank:             number;
  signals:          StockSignals;
  entryPrice:       number;
  suggestedStopLoss: number;
  targetPrice:      number;
  riskRewardRatio:  number;
  passedFilterCount: number;
  totalFilterCount:  number;
  criteriaType:     CriteriaType;
}

export interface PortfolioPosition {
  symbol:      string;
  name:        string;
  weight:      number;     // % allocation (equal-weight within top-5)
  entryPrice:  number;
  stopLoss:    number;
  target:      number;
  score:       number;
  rank:        number;
  riskReward:  number;
}

export interface Portfolio {
  criteriaType:  CriteriaType;
  date:          Date;
  market:        string;
  positions:     PortfolioPosition[];
  portfolioScore: number;     // average score across positions
  expectedReturn: number;     // average risk/reward weighted return
}

// ─────────────────────────────────────────────────────────────────────────────
// Full stock data shape (combines StockPrice + Stock from DB)
// ─────────────────────────────────────────────────────────────────────────────

export interface StockData {
  // Identity
  symbol:    string;
  name:      string;
  market:    string;
  sector:    string;
  marketCap: number;

  // OHLCV (current bar)
  date:   Date;
  open:   number;
  high:   number;
  low:    number;
  close:  number;
  volume: number;

  // Recent series for rolling calculations
  series: PriceBar[];

  // Pre-computed technical indicators
  rsi14?:      number | null;
  macd?:       number | null;
  macdSignal?: number | null;
  macdHist?:   number | null;    // histogram = macd − signal
  macdHistPrev?: number | null;  // histogram 1 bar ago
  macdHistPrev2?: number | null; // histogram 2 bars ago
  ema20?:      number | null;
  ema50?:      number | null;
  ema200?:     number | null;
  sma50?:      number | null;
  sma200?:     number | null;
  atr14?:      number | null;
  obv?:        number | null;
  vwap?:       number | null;
  bbUpper?:    number | null;
  bbMiddle?:   number | null;
  bbLower?:    number | null;
  adx14?:      number | null;
  stochK?:     number | null;
  stochD?:     number | null;
  stochKPrev?: number | null;    // K line 1 bar ago (crossover detection)
  stochDPrev?: number | null;

  // Derived / computed on-the-fly
  high52w?:    number | null;
  vol20Avg?:   number | null;    // 20-day average volume
  beta?:       number | null;    // vs market index
  relStrength?: number | null;   // price vs index ratio change (1-month)
  dividendYield?: number | null;
  currentRatio?:  number | null;
  operatingMargin?: number | null;

  // Fundamental (updated quarterly)
  pe?:             number | null;
  pb?:             number | null;
  roe?:            number | null;
  debtEquity?:     number | null;
  revenueGrowth?:  number | null;
  earningsGrowth?: number | null;
  freeCashFlow?:   number | null;

  // Sector average PE for relative valuation
  sectorAvgPE?: number | null;

  // Cross-sectional benchmark returns (universe median at scan date)
  // Set by screenStocksSync before scoring to enable proper relative strength
  marketReturn3m?:  number | null;
  marketReturn6m?:  number | null;
  marketReturn12m?: number | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Filter rule descriptor
// ─────────────────────────────────────────────────────────────────────────────

export type FilterOperator = 'gt' | 'lt' | 'gte' | 'lte' | 'eq' | 'between' | 'custom';

export interface FilterRule {
  id:        string;
  label:     string;
  field?:    keyof StockData;
  operator:  FilterOperator;
  value?:    number;
  valueB?:   number;     // upper bound for 'between'
  // For custom multi-field rules supply a predicate
  predicate?: (s: StockData) => boolean;
  mandatory:  boolean;   // if true, a fail disqualifies the stock entirely
  category:  'technical' | 'fundamental';
}

// ─────────────────────────────────────────────────────────────────────────────
// Scoring weight map
// ─────────────────────────────────────────────────────────────────────────────

export type WeightMap = Record<string, number>;

export interface CriteriaConfig {
  type:    CriteriaType;
  filters: FilterRule[];
  weights: WeightMap;
}

// ─────────────────────────────────────────────────────────────────────────────
// ── Helpers ──────────────────────────────────────────────────────────────────
// ─────────────────────────────────────────────────────────────────────────────

function coalesce<T>(v: T | null | undefined, fallback: T): T {
  return v === null || v === undefined ? fallback : v;
}

/** Apply a simple binary operator */
function evalOp(actual: number, op: FilterOperator, a: number, b?: number): boolean {
  switch (op) {
    case 'gt':      return actual >  a;
    case 'gte':     return actual >= a;
    case 'lt':      return actual <  a;
    case 'lte':     return actual <= a;
    case 'eq':      return actual === a;
    case 'between': return actual >= a && actual <= (b ?? a);
    default:        return false;
  }
}

/** ATR-based stop-loss (1.5× ATR below entry) */
function atrStop(stock: StockData): number {
  const atr = coalesce(stock.atr14, stock.close * 0.02);
  return +(stock.close - 1.5 * atr).toFixed(2);
}

/** Risk/reward: (target − entry) / (entry − stop) */
function riskReward(entry: number, stop: number, target: number): number {
  const risk   = entry - stop;
  const reward = target - entry;
  if (risk <= 0) return 0;
  return +(reward / risk).toFixed(2);
}

/** Normalise weight map so values sum to 100 */
function normaliseWeights(w: WeightMap): WeightMap {
  const total = Object.values(w).reduce((s, v) => s + v, 0);
  if (total === 0) return w;
  const out: WeightMap = {};
  for (const [k, v] of Object.entries(w)) out[k] = (v / total) * 100;
  return out;
}

// ─────────────────────────────────────────────────────────────────────────────
// ── ALFA configuration ────────────────────────────────────────────────────────
// Bull-market momentum / growth
// ─────────────────────────────────────────────────────────────────────────────

const ALFA_WEIGHTS: WeightMap = normaliseWeights({
  priceAbove200EMA:   15,
  priceAbove50EMA:     8,
  goldenCross:        10,
  rsiOptimal:         10,
  macdBullish:        10,
  macdHistIncreasing: 5,
  volumeConfirmation: 10,
  adxStrength:         8,
  near52WeekHigh:      7,
  bbAboveMiddle:       2,
  revenueGrowth:      10,
  earningsGrowth:     10,
  roeStrength:         5,
  lowLeverage:         3,
  freeCashFlow:        5,
  valuationCheck:      2,
});

const ALFA_FILTERS: FilterRule[] = [
  // ── Technical ──────────────────────────────────────────────────────────
  {
    id: 'priceAbove200EMA',
    label: 'Price > 200 EMA',
    category: 'technical',
    operator: 'custom',
    predicate: s => coalesce(s.ema200, 0) > 0 && s.close > s.ema200!,
    mandatory: false,  // scoring factor only — mandatory blocks early-rally breakouts
  },
  {
    id: 'priceAbove50EMA',
    label: 'Price > 50 EMA',
    category: 'technical',
    operator: 'custom',
    predicate: s => coalesce(s.ema50, 0) > 0 && s.close > s.ema50!,
    mandatory: false,
  },
  {
    id: 'goldenCross',
    label: '50 EMA > 200 EMA (Golden Cross)',
    category: 'technical',
    operator: 'custom',
    predicate: s =>
      coalesce(s.ema50, 0) > 0 &&
      coalesce(s.ema200, 0) > 0 &&
      s.ema50! > s.ema200!,
    mandatory: false,
  },
  {
    id: 'rsiOptimal',
    label: 'RSI(14) between 50–70',
    category: 'technical',
    operator: 'between',
    field: 'rsi14',
    value: 50,
    valueB: 70,
    mandatory: false,
  },
  {
    id: 'macdBullish',
    label: 'MACD Line > Signal Line',
    category: 'technical',
    operator: 'custom',
    predicate: s =>
      s.macd !== null && s.macd !== undefined &&
      s.macdSignal !== null && s.macdSignal !== undefined &&
      s.macd > s.macdSignal,
    mandatory: false,
  },
  {
    id: 'macdHistIncreasing',
    label: 'MACD Histogram increasing (3 bars)',
    category: 'technical',
    operator: 'custom',
    predicate: s =>
      s.macdHist != null && s.macdHistPrev != null && s.macdHistPrev2 != null &&
      s.macdHist > s.macdHistPrev! && s.macdHistPrev! > s.macdHistPrev2!,
    mandatory: false,
  },
  {
    id: 'volumeConfirmation',
    label: 'Volume > 1.5× 20-day average',
    category: 'technical',
    operator: 'custom',
    predicate: s => coalesce(s.vol20Avg, 0) > 0 && s.volume > s.vol20Avg! * 1.5,
    mandatory: false,
  },
  {
    id: 'adxStrength',
    label: 'ADX(14) > 25',
    category: 'technical',
    field: 'adx14',
    operator: 'gt',
    value: 25,
    mandatory: false,
  },
  {
    id: 'near52WeekHigh',
    label: 'Price within 10% of 52-week high',
    category: 'technical',
    operator: 'custom',
    predicate: s => s.high52w != null && s.high52w > 0 && s.close >= s.high52w * 0.90,
    mandatory: false,
  },
  {
    id: 'bbAboveMiddle',
    label: 'Price above Bollinger middle band',
    category: 'technical',
    operator: 'custom',
    predicate: s => s.bbMiddle != null && s.close > s.bbMiddle,
    mandatory: false,
  },
  // ── Fundamental ────────────────────────────────────────────────────────
  {
    id: 'revenueGrowth',
    label: 'Revenue Growth YoY > 15%',
    category: 'fundamental',
    field: 'revenueGrowth',
    operator: 'gt',
    value: 15,
    mandatory: false,
  },
  {
    id: 'earningsGrowth',
    label: 'Earnings Growth YoY > 10%',
    category: 'fundamental',
    field: 'earningsGrowth',
    operator: 'gt',
    value: 10,
    mandatory: false,
  },
  {
    id: 'roeStrength',
    label: 'ROE > 15%',
    category: 'fundamental',
    field: 'roe',
    operator: 'gt',
    value: 15,
    mandatory: false,
  },
  {
    id: 'lowLeverage',
    label: 'Debt/Equity < 1.5',
    category: 'fundamental',
    field: 'debtEquity',
    operator: 'lt',
    value: 1.5,
    mandatory: false,
  },
  {
    id: 'freeCashFlow',
    label: 'Free Cash Flow positive',
    category: 'fundamental',
    operator: 'custom',
    predicate: s => s.freeCashFlow != null && s.freeCashFlow > 0,
    mandatory: false,
  },
  {
    id: 'valuationCheck',
    label: 'P/E < Sector Average × 1.5',
    category: 'fundamental',
    operator: 'custom',
    predicate: s => {
      if (s.pe == null || s.sectorAvgPE == null || s.sectorAvgPE <= 0) return true; // no data → pass
      return s.pe < s.sectorAvgPE * 1.5;
    },
    mandatory: false,
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// ── BETA configuration ───────────────────────────────────────────────────────
// Bear-market defensive / value
// ─────────────────────────────────────────────────────────────────────────────

const BETA_WEIGHTS: WeightMap = normaliseWeights({
  relativeStrength:    20,
  lowBeta:             10,
  rsiRecovery:         10,
  supportLevel:        10,
  volumeDecliningDown: 5,
  bbOversoldBounce:    5,
  stochasticOversold:  10,
  dividendYield:       10,
  valuationPE:          8,
  pbValue:              4,
  lowLeverage:          8,
  liquidityRatio:       7,
  stableEarnings:       7,
  operatingMargin:      4,
  roeStrength:          2,
});

const BETA_FILTERS: FilterRule[] = [
  // ── Technical ──────────────────────────────────────────────────────────
  {
    id: 'relativeStrength',
    label: 'Relative Strength vs Market > 1.0',
    category: 'technical',
    operator: 'custom',
    predicate: s => coalesce(s.relStrength, 0) > 1.0,
    mandatory: false,
  },
  {
    id: 'lowBeta',
    label: 'Beta < 0.8 (Defensive)',
    category: 'technical',
    field: 'beta',
    operator: 'lt',
    value: 0.8,
    mandatory: false,
  },
  {
    id: 'rsiRecovery',
    label: 'RSI(14) ≥ 30 (Not in freefall)',
    category: 'technical',
    field: 'rsi14',
    operator: 'gte',
    value: 30,
    mandatory: true,
  },
  {
    id: 'supportLevel',
    label: 'Price above 200 SMA support',
    category: 'technical',
    operator: 'custom',
    predicate: s => s.sma200 != null && s.close > s.sma200 * 0.98, // within 2%
    mandatory: false,
  },
  {
    id: 'volumeDecliningDown',
    label: 'Volume declining on down days',
    category: 'technical',
    operator: 'custom',
    // Down day with volume below average = selling pressure reducing
    predicate: s =>
      s.close <= s.open
        ? coalesce(s.vol20Avg, s.volume * 1.1) > s.volume
        : true,
    mandatory: false,
  },
  {
    id: 'bbOversoldBounce',
    label: 'Price near/above Bollinger lower band',
    category: 'technical',
    operator: 'custom',
    predicate: s => {
      if (s.bbLower == null || s.bbUpper == null) return false;
      const bandWidth = s.bbUpper - s.bbLower;
      // Price within bottom 30% of band (oversold territory)
      return s.close >= s.bbLower && s.close <= s.bbLower + bandWidth * 0.30;
    },
    mandatory: false,
  },
  {
    id: 'stochasticOversold',
    label: 'Stochastic < 20 and crossing up',
    category: 'technical',
    operator: 'custom',
    predicate: s =>
      s.stochK != null && s.stochD != null &&
      s.stochK < 20 &&
      s.stochKPrev != null && s.stochDPrev != null &&
      // K crossed above D (was below, now above)
      s.stochKPrev <= s.stochDPrev && s.stochK >= s.stochD!,
    mandatory: false,
  },
  // ── Fundamental ────────────────────────────────────────────────────────
  {
    id: 'dividendYield',
    label: 'Dividend Yield > 2%',
    category: 'fundamental',
    field: 'dividendYield',
    operator: 'gt',
    value: 2,
    mandatory: false,
  },
  {
    id: 'valuationPE',
    label: 'P/E < 15 (Value)',
    category: 'fundamental',
    field: 'pe',
    operator: 'custom',
    predicate: s => s.pe != null && s.pe > 0 && s.pe < 15,
    mandatory: false,
  },
  {
    id: 'pbValue',
    label: 'P/B < 1.5',
    category: 'fundamental',
    field: 'pb',
    operator: 'lt',
    value: 1.5,
    mandatory: false,
  },
  {
    id: 'lowLeverage',
    label: 'Debt/Equity < 0.5',
    category: 'fundamental',
    field: 'debtEquity',
    operator: 'lt',
    value: 0.5,
    mandatory: false,
  },
  {
    id: 'liquidityRatio',
    label: 'Current Ratio > 2.0',
    category: 'fundamental',
    field: 'currentRatio',
    operator: 'gt',
    value: 2.0,
    mandatory: false,
  },
  {
    id: 'roeStrength',
    label: 'ROE > 12%',
    category: 'fundamental',
    field: 'roe',
    operator: 'gt',
    value: 12,
    mandatory: false,
  },
  {
    id: 'stableEarnings',
    label: 'Earnings Growth ≥ 0% (Stable)',
    category: 'fundamental',
    field: 'earningsGrowth',
    operator: 'gte',
    value: 0,
    mandatory: false,
  },
  {
    id: 'operatingMargin',
    label: 'Operating Margin > 15%',
    category: 'fundamental',
    field: 'operatingMargin',
    operator: 'gt',
    value: 15,
    mandatory: false,
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// ── DELTA configuration ───────────────────────────────────────────────────────
// Sideways mean-reversion / range trading
// ─────────────────────────────────────────────────────────────────────────────

const DELTA_WEIGHTS: WeightMap = normaliseWeights({
  rangeBoundADX:        15,
  bollingerOversold:    15,
  rsiRecovery:          15,
  stochasticOversold:   10,
  supportLevel:         10,
  vwapProximity:        10,
  volumeCapitulation:   10,
  rangeBound:            5,
  fairValuation:        10,
  balanceSheetStrength:  5,
  consistentRevenue:     5,
});

const DELTA_FILTERS: FilterRule[] = [
  // ── Technical ──────────────────────────────────────────────────────────
  {
    id: 'rangeBoundADX',
    label: 'ADX(14) < 20 (Range-bound)',
    category: 'technical',
    field: 'adx14',
    operator: 'lt',
    value: 20,
    mandatory: true,
  },
  {
    id: 'bollingerOversold',
    label: 'Price near Bollinger Lower Band',
    category: 'technical',
    operator: 'custom',
    predicate: s => {
      if (s.bbLower == null || s.bbMiddle == null) return false;
      const midToLow = s.bbMiddle - s.bbLower;
      // Price within bottom 40% of lower half
      return s.close <= s.bbLower + midToLow * 0.40;
    },
    mandatory: false,
  },
  {
    id: 'rsiRecovery',
    label: 'RSI(14) between 30–45 (Oversold recovering)',
    category: 'technical',
    field: 'rsi14',
    operator: 'between',
    value: 30,
    valueB: 45,
    mandatory: false,
  },
  {
    id: 'stochasticOversold',
    label: 'Stochastic(14,3,3) < 30',
    category: 'technical',
    field: 'stochK',
    operator: 'lt',
    value: 30,
    mandatory: false,
  },
  {
    id: 'supportLevel',
    label: 'Price near key support (within 3% of SMA50)',
    category: 'technical',
    operator: 'custom',
    predicate: s => {
      if (s.sma50 == null) return false;
      return Math.abs(s.close - s.sma50) / s.sma50 <= 0.03;
    },
    mandatory: false,
  },
  {
    id: 'vwapProximity',
    label: 'Price below VWAP (trending toward it)',
    category: 'technical',
    operator: 'custom',
    predicate: s => s.vwap != null && s.close < s.vwap * 1.01, // at or below VWAP
    mandatory: false,
  },
  {
    id: 'volumeCapitulation',
    label: 'Volume spike on reversal day (Capitulation)',
    category: 'technical',
    operator: 'custom',
    // Down day with very high volume = capitulation
    predicate: s =>
      s.close < s.open &&
      coalesce(s.vol20Avg, 0) > 0 &&
      s.volume > s.vol20Avg! * 2.0,
    mandatory: false,
  },
  {
    id: 'rangeBound',
    label: 'Price within established range (SMA50 ± 15%)',
    category: 'technical',
    operator: 'custom',
    predicate: s => {
      if (s.sma50 == null) return false;
      return Math.abs(s.close - s.sma50) / s.sma50 <= 0.15;
    },
    mandatory: false,
  },
  // ── Fundamental ────────────────────────────────────────────────────────
  {
    id: 'fairValuation',
    label: 'P/E between 10–20 (Fair value)',
    category: 'fundamental',
    operator: 'custom',
    predicate: s => s.pe != null && s.pe >= 10 && s.pe <= 20,
    mandatory: false,
  },
  {
    id: 'balanceSheetStrength',
    label: 'ROE > 10% + Low debt',
    category: 'fundamental',
    operator: 'custom',
    predicate: s =>
      coalesce(s.roe, 0) > 10 &&
      coalesce(s.debtEquity, 999) < 1.0,
    mandatory: false,
  },
  {
    id: 'consistentRevenue',
    label: 'Revenue stable (Growth ≥ −5%)',
    category: 'fundamental',
    field: 'revenueGrowth',
    operator: 'gte',
    value: -5,
    mandatory: false,
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Config registry
// ─────────────────────────────────────────────────────────────────────────────

export const CRITERIA_CONFIGS: Record<CriteriaType, CriteriaConfig> = {
  ALFA:  { type: 'ALFA',  filters: ALFA_FILTERS,  weights: ALFA_WEIGHTS  },
  BETA:  { type: 'BETA',  filters: BETA_FILTERS,  weights: BETA_WEIGHTS  },
  DELTA: { type: 'DELTA', filters: DELTA_FILTERS, weights: DELTA_WEIGHTS },
};

// ─────────────────────────────────────────────────────────────────────────────
// ── Core functions ───────────────────────────────────────────────────────────
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Evaluate all filter rules for a single stock and produce a score 0–100.
 *
 * Score = Σ (weight_i × passed_i)  over all filters where weight_i is
 * already normalised to sum-to-100.
 *
 * Mandatory filter failure → score = 0 (hard disqualification).
 */
export function calculateScore(
  stock:    StockData,
  config:   CriteriaConfig,
): { score: number; signals: StockSignals } {

  // ── ALFA V2: institutional momentum engine ─────────────────────────────
  if (config.type === 'ALFA') {
    const v2 = alfaCriteriaV2.score(stock);
    return {
      score: v2.total,
      signals: {
        technical:   v2.signals.passed
          .filter(s => !s.startsWith('[F]'))
          .map(name => ({
            name, category: 'technical' as const, description: name,
            value: null, threshold: null,
            passed: true, direction: 'BULLISH' as const,
            weight: 1, contribution: 1,
          })),
        fundamental: v2.signals.passed
          .filter(s => s.startsWith('[F]'))
          .map(name => ({
            name, category: 'fundamental' as const, description: name,
            value: null, threshold: null,
            passed: true, direction: 'BULLISH' as const,
            weight: 1, contribution: 1,
          })),
        passed:   v2.signals.passed,
        failed:   [...v2.signals.failed, ...v2.signals.warnings],
      },
    };
  }

  // ── BETA V2: professional bear market defense engine ────────────────────
  if (config.type === 'BETA') {
    const v2 = betaCriteriaV2.score(stock);
    return {
      score: v2.total,
      signals: {
        technical:   v2.signals.passed
          .filter(s => !s.startsWith('[F]'))
          .map(name => ({
            name, category: 'technical' as const, description: name,
            value: null, threshold: null,
            passed: true, direction: 'BEARISH' as const,
            weight: 1, contribution: 1,
          })),
        fundamental: v2.signals.passed
          .filter(s => s.startsWith('[F]'))
          .map(name => ({
            name, category: 'fundamental' as const, description: name,
            value: null, threshold: null,
            passed: true, direction: 'BEARISH' as const,
            weight: 1, contribution: 1,
          })),
        passed: v2.signals.passed,
        failed: [...v2.signals.failed, ...v2.signals.warnings],
      },
    };
  }

  // ── DELTA V2: professional mean-reversion / range engine ───────────────
  if (config.type === 'DELTA') {
    const v2 = deltaCriteriaV2.score(stock);
    return {
      score: v2.total,
      signals: {
        technical:   v2.signals.passed
          .map(name => ({
            name, category: 'technical' as const, description: name,
            value: null, threshold: null,
            passed: true, direction: 'NEUTRAL' as const,
            weight: 1, contribution: 1,
          })),
        fundamental: v2.signals.passed
          .filter(s => s.startsWith('[F]'))
          .map(name => ({
            name, category: 'fundamental' as const, description: name,
            value: null, threshold: null,
            passed: true, direction: 'NEUTRAL' as const,
            weight: 1, contribution: 1,
          })),
        passed: v2.signals.passed,
        failed: [...v2.signals.failed, ...v2.signals.warnings],
      },
    };
  }

  const technical:   SignalDetail[] = [];
  const fundamental: SignalDetail[] = [];
  const passed:  string[] = [];
  const failed:  string[] = [];

  let totalScore   = 0;
  let disqualified = false;

  for (const rule of config.filters) {
    const weight = config.weights[rule.id] ?? 0;

    // Evaluate the rule
    let didPass = false;
    let actual: number | string | null = null;
    let threshold: number | string | null = rule.value ?? null;

    if (rule.predicate) {
      didPass = rule.predicate(stock);
      // Try to surface the relevant field value
      if (rule.field) actual = (stock[rule.field] as number | null) ?? null;
    } else if (rule.field) {
      const fieldVal = stock[rule.field];
      if (fieldVal === null || fieldVal === undefined) {
        didPass = false;  // missing data → fail
      } else {
        actual  = fieldVal as number;
        didPass = evalOp(actual as number, rule.operator, rule.value!, rule.valueB);
      }
      if (rule.operator === 'between' && rule.valueB !== undefined) {
        threshold = `${rule.value} – ${rule.valueB}`;
      }
    }

    if (rule.mandatory && !didPass) {
      disqualified = true;
    }

    const contribution = didPass ? weight : 0;
    totalScore += contribution;

    const detail: SignalDetail = {
      name:        rule.id,
      category:    rule.category,
      value:       actual,
      threshold,
      passed:      didPass,
      direction:   didPass ? 'BULLISH' : 'BEARISH',
      weight,
      contribution,
      description: rule.label,
    };

    if (rule.category === 'technical')   technical.push(detail);
    else                                 fundamental.push(detail);

    if (didPass) passed.push(rule.id);
    else         failed.push(rule.id);
  }

  const finalScore = disqualified ? 0 : Math.min(100, +totalScore.toFixed(2));

  return {
    score:   finalScore,
    signals: { technical, fundamental, passed, failed },
  };
}

/**
 * Hard-filter a stock list: remove stocks that fail any mandatory rule
 * or that score below a minimum threshold.
 */
export function applyFilters(
  stocks:  StockData[],
  rules:   FilterRule[],
  minScore = 0,
  config?: CriteriaConfig,
): StockData[] {
  return stocks.filter(stock => {
    // Check mandatory rules
    for (const rule of rules.filter(r => r.mandatory)) {
      const fail = rule.predicate
        ? !rule.predicate(stock)
        : rule.field
          ? (() => {
              const v = stock[rule.field!];
              if (v === null || v === undefined) return true;
              return !evalOp(v as number, rule.operator, rule.value!, rule.valueB);
            })()
          : false;
      if (fail) return false;
    }
    // Optionally apply minimum score
    if (config && minScore > 0) {
      const { score } = calculateScore(stock, config);
      return score >= minScore;
    }
    return true;
  });
}

/**
 * Sort a list of scored stocks by score descending and assign integer ranks.
 */
export function rankStocks(scoredStocks: ScoredStock[]): ScoredStock[] {
  const sorted = [...scoredStocks].sort((a, b) => b.score - a.score);
  return sorted.map((s, i) => ({ ...s, rank: i + 1 }));
}

// ─────────────────────────────────────────────────────────────────────────────
// Price targets (ATR-based)
// ─────────────────────────────────────────────────────────────────────────────

function computePriceTargets(
  stock:    StockData,
  criteria: CriteriaType,
): { stopLoss: number; target: number; rr: number } {
  const entry = stock.close;
  const atr   = coalesce(stock.atr14, entry * 0.02);

  let stopMultiplier: number;
  let targetMultiplier: number;

  switch (criteria) {
    case 'ALFA':  stopMultiplier = 1.5; targetMultiplier = 3.0;  break; // 1:2 RR (momentum)
    case 'BETA':  stopMultiplier = 1.0; targetMultiplier = 2.0;  break; // 1:2 RR (defensive)
    case 'DELTA': stopMultiplier = 1.0; targetMultiplier = 1.5;  break; // 1:1.5 RR (range)
  }

  const stop   = +(entry - stopMultiplier  * atr).toFixed(2);
  const target = +(entry + targetMultiplier * atr).toFixed(2);
  const rr     = riskReward(entry, stop, target);

  return { stopLoss: stop, target, rr };
}

// ─────────────────────────────────────────────────────────────────────────────
// Main screen function
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Screen a list of stocks against a criteria set.
 *
 * In production, replace the `stocks` parameter with a DB query that loads
 * `StockData` rows for the given market / date. The mock generator at the
 * bottom of this file produces realistic test data.
 */
export function screenStocksSync(
  stocks:   StockData[],
  criteria: CriteriaType,
): ScoredStock[] {
  const config      = CRITERIA_CONFIGS[criteria];
  const preFiltered = applyFilters(stocks, config.filters, 0, config);

  // ── Cross-sectional RS benchmark (universe median returns) ─────────────────
  // Compute median 3M/6M/12M return across universe using price series.
  // This gives RS a meaningful peer comparison instead of a fixed threshold.
  if (preFiltered.length > 4 && criteria === 'ALFA') {
    const getReturn = (s: StockData, bars: number): number => {
      const ser = s.series;
      if (!ser || ser.length < bars + 2) return 0;
      const end   = ser[ser.length - 1]?.close ?? 0;
      const start = ser[Math.max(0, ser.length - bars - 1)]?.close ?? end;
      return start > 0 ? (end - start) / start : 0;
    };
    const vals3m  = preFiltered.map(s => getReturn(s, 63));
    const vals6m  = preFiltered.map(s => getReturn(s, 126));
    const vals12m = preFiltered.map(s => getReturn(s, 252));
    const sortNum = (arr: number[]) => [...arr].sort((a, b) => a - b);
    const med = (arr: number[]) => {
      const s = sortNum(arr); return s[Math.floor(s.length / 2)] ?? 0;
    };
    const mktRet3m  = med(vals3m);
    const mktRet6m  = med(vals6m);
    const mktRet12m = med(vals12m);
    for (const s of preFiltered) {
      s.marketReturn3m  = mktRet3m;
      s.marketReturn6m  = mktRet6m;
      s.marketReturn12m = mktRet12m;
    }
  }

  const scored: ScoredStock[] = preFiltered.map(stock => {
    const { score, signals } = calculateScore(stock, config);
    const { stopLoss, target, rr } = computePriceTargets(stock, criteria);

    return {
      symbol:            stock.symbol,
      name:              stock.name,
      score,
      rank:              0,  // set by rankStocks
      signals,
      entryPrice:        stock.close,
      suggestedStopLoss: stopLoss,
      targetPrice:       target,
      riskRewardRatio:   rr,
      passedFilterCount: signals.passed.length,
      totalFilterCount:  config.filters.length,
      criteriaType:      criteria,
    };
  });

  return rankStocks(scored);
}

/**
 * Async wrapper — loads stocks from Prisma, then calls `screenStocksSync`.
 * Falls back to the mock generator when the DB is empty.
 */
export async function screenStocks(
  criteria: CriteriaType,
  date:     Date,
  market:   string,
): Promise<ScoredStock[]> {
  let stocks: StockData[];

  try {
    const { PrismaClient } = await import('@prisma/client');
    const prisma = new PrismaClient();

    try {
      const rows = await prisma.stock.findMany({
        where: { market },
        include: {
          prices: {
            where: { date: { lte: date } },
            orderBy: { date: 'desc' },
            take: 250,  // enough for 200-bar indicators
          },
        },
      });

      stocks = rows
        .filter(r => r.prices.length > 0)
        .map(r => {
          const latest = r.prices[0]!;
          const series: PriceBar[] = r.prices
            .slice()
            .reverse()
            .map(p => ({
              date:      p.date,
              open:      p.open,
              high:      p.high,
              low:       p.low,
              close:     p.close,
              volume:    p.volume,
              rsi14:     p.rsi14,
              macd:      p.macd,
              macdSignal: p.macdSignal,
              ema20:     p.ema20,
              ema50:     p.ema50,
              ema200:    p.ema200,
              sma50:     p.sma50,
              sma200:    p.sma200,
              atr14:     p.atr14,
              obv:       p.obv,
              vwap:      p.vwap,
              bbUpper:   p.bbUpper,
              bbMiddle:  p.bbMiddle,
              bbLower:   p.bbLower,
              adx14:     p.adx14,
              stochK:    p.stochK,
              stochD:    p.stochD,
            }));

          // MACD histogram values
          const prev1  = r.prices[1];
          const prev2  = r.prices[2];
          const macdH  = latest.macd != null && latest.macdSignal != null
            ? latest.macd - latest.macdSignal : null;
          const macdHP = prev1?.macd != null && prev1?.macdSignal != null
            ? prev1.macd - prev1.macdSignal : null;
          const macdHP2= prev2?.macd != null && prev2?.macdSignal != null
            ? prev2.macd - prev2.macdSignal : null;

          // 20-day avg volume
          const vol20Avg = series.length >= 20
            ? series.slice(-20).reduce((s, p) => s + p.volume, 0) / 20
            : null;

          // 52-week high
          const high52w = series.length > 0
            ? Math.max(...series.map(p => p.high))
            : null;

          return {
            symbol:    r.symbol,
            name:      r.name,
            market:    r.market,
            sector:    r.sector ?? 'Unknown',
            marketCap: r.marketCap ?? 0,
            date:      latest.date,
            open:      latest.open,
            high:      latest.high,
            low:       latest.low,
            close:     latest.close,
            volume:    latest.volume,
            series,
            rsi14:     latest.rsi14,
            macd:      latest.macd,
            macdSignal: latest.macdSignal,
            macdHist:  macdH,
            macdHistPrev: macdHP,
            macdHistPrev2: macdHP2,
            ema20:     latest.ema20,
            ema50:     latest.ema50,
            ema200:    latest.ema200,
            sma50:     latest.sma50,
            sma200:    latest.sma200,
            atr14:     latest.atr14,
            obv:       latest.obv,
            vwap:      latest.vwap,
            bbUpper:   latest.bbUpper,
            bbMiddle:  latest.bbMiddle,
            bbLower:   latest.bbLower,
            adx14:     latest.adx14,
            stochK:    latest.stochK,
            stochD:    latest.stochD,
            stochKPrev: prev1?.stochK ?? null,
            stochDPrev: prev1?.stochD ?? null,
            high52w,
            vol20Avg,
            pe:              latest.pe,
            pb:              latest.pb,
            roe:             latest.roe,
            debtEquity:      latest.debtEquity,
            revenueGrowth:   latest.revenueGrowth,
            earningsGrowth:  latest.earningsGrowth,
            freeCashFlow:    latest.freeCashFlow,
            // These fields aren't in DB yet — fall back to null
            beta:            null,
            relStrength:     null,
            dividendYield:   null,
            currentRatio:    null,
            operatingMargin: null,
            sectorAvgPE:     null,
          } satisfies StockData;
        });
    } finally {
      await prisma.$disconnect();
    }
  } catch {
    // DB unavailable → use mock data for development / demos
    stocks = generateMockStocks(30, market as 'US' | 'BIST');
  }

  if (stocks.length === 0) {
    stocks = generateMockStocks(30, market as 'US' | 'BIST');
  }

  return screenStocksSync(stocks, criteria);
}

// ─────────────────────────────────────────────────────────────────────────────
// Top-5 portfolio builder
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Run a full screen, take the top-5 results, and build an equal-weight
 * portfolio with entry/stop/target for each position.
 */
export async function getTop5Portfolio(
  criteria: CriteriaType,
  date:     Date,
  market:   string,
): Promise<Portfolio> {
  const ranked = await screenStocks(criteria, date, market);
  const top5   = ranked.slice(0, 5);

  const positions: PortfolioPosition[] = top5.map(s => ({
    symbol:    s.symbol,
    name:      s.name,
    weight:    20,              // equal-weight (100 / 5)
    entryPrice: s.entryPrice,
    stopLoss:  s.suggestedStopLoss,
    target:    s.targetPrice,
    score:     s.score,
    rank:      s.rank,
    riskReward: s.riskRewardRatio,
  }));

  const portfolioScore  = positions.length > 0
    ? +(positions.reduce((s, p) => s + p.score, 0) / positions.length).toFixed(2)
    : 0;

  const expectedReturn  = positions.length > 0
    ? +(positions.reduce((s, p) => s + p.riskReward, 0) / positions.length).toFixed(2)
    : 0;

  return { criteriaType: criteria, date, market, positions, portfolioScore, expectedReturn };
}

// ─────────────────────────────────────────────────────────────────────────────
// Persistence helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Upsert all scored stocks as `ScanResult` rows in the database.
 * Only persists stocks with score > 0.
 */
export async function saveScanResults(
  results:  ScoredStock[],
  criteria: CriteriaType,
  date:     Date,
  market:   string,
): Promise<void> {
  const { PrismaClient } = await import('@prisma/client');
  const prisma = new PrismaClient();

  try {
    // Resolve criteria record
    let criteriaRecord = await prisma.criteria.findFirst({
      where: { name: criteria, isActive: true },
    });

    if (!criteriaRecord) {
      // Auto-create if missing
      const config = CRITERIA_CONFIGS[criteria];
      criteriaRecord = await prisma.criteria.create({
        data: {
          name:           criteria,
          displayName:    criteria === 'ALFA' ? 'Momentum / Growth (Bull)'
                        : criteria === 'BETA' ? 'Defensive / Value (Bear)'
                        :                       'Mean Reversion (Sideways)',
          market:         criteria === 'ALFA' ? 'BULL'
                        : criteria === 'BETA' ? 'BEAR'
                        :                       'SIDEWAYS',
          description:    `Auto-generated ${criteria} criteria`,
          rules:          config.filters.map(f => ({
            id: f.id, label: f.label, mandatory: f.mandatory, category: f.category,
          })),
          scoringWeights: config.weights,
          isActive:       true,
        },
      });
    }

    // Resolve stock IDs
    const symbols     = results.map(r => r.symbol);
    const stockRows   = await prisma.stock.findMany({
      where: { symbol: { in: symbols }, market },
      select: { id: true, symbol: true },
    });
    const symbolToId = new Map(stockRows.map(s => [s.symbol, s.id]));

    // Upsert scan results (only scored stocks with a matching DB row)
    const toSave = results.filter(r => r.score > 0 && symbolToId.has(r.symbol));

    await Promise.all(
      toSave.map(r =>
        prisma.scanResult.upsert({
          where: {
            scanDate_criteriaId_stockId: {
              scanDate:   date,
              criteriaId: criteriaRecord!.id,
              stockId:    symbolToId.get(r.symbol)!,
            },
          },
          update: {
            score:       r.score,
            rank:        r.rank,
            signals:     r.signals as object,
            entryPrice:  r.entryPrice,
            targetPrice: r.targetPrice,
            stopLoss:    r.suggestedStopLoss,
          },
          create: {
            scanDate:    date,
            criteriaId:  criteriaRecord!.id,
            stockId:     symbolToId.get(r.symbol)!,
            score:       r.score,
            rank:        r.rank,
            signals:     r.signals as object,
            entryPrice:  r.entryPrice,
            targetPrice: r.targetPrice,
            stopLoss:    r.suggestedStopLoss,
          },
        }),
      ),
    );
  } finally {
    await prisma.$disconnect();
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Mock data generator — realistic stock universe for dev / testing
// ─────────────────────────────────────────────────────────────────────────────

// ── Stock universe pools — imported from single source of truth ───────────────
import {
  BIST100_LIST, BIST100DISI_LIST, BISTTUM_LIST, US_MARKET_LIST,
} from './stockUniverse';

function rand(min: number, max: number) {
  return min + Math.random() * (max - min);
}

function maybe<T>(v: T, pNull = 0.15): T | null {
  return Math.random() < pNull ? null : v;
}

export function generateMockStocks(
  count    = 30,
  market:  'US' | 'BIST' = 'US',
  universe?: UniverseType,
): StockData[] {
  // Shuffle deterministically enough by slicing — real randomisation handled below
  const rawPool =
    market === 'US'               ? US_MARKET_LIST :
    universe === 'BIST100DISI'    ? BIST100DISI_LIST :
    universe === 'BISTTUM'        ? BISTTUM_LIST :
                                    BIST100_LIST;

  // Pick a random window so repeated calls surface different stocks
  const total   = rawPool.length;
  const offset  = Math.floor(Math.random() * Math.max(1, total - count));
  const selected = rawPool.slice(offset, offset + Math.min(count, total));

  return selected.map(({ symbol, name, sector }) => {
    const price    = rand(50, 800);
    const atr      = price * rand(0.01, 0.03);
    const ema200   = maybe(price * rand(0.85, 1.05));
    const ema50    = ema200 != null ? ema200 * rand(0.95, 1.08) : null;
    const sma200   = ema200 != null ? ema200 * rand(0.98, 1.02) : null;
    const sma50    = ema50  != null ? ema50  * rand(0.97, 1.03) : null;
    const bbMiddle = sma50 ?? price;
    const bbWidth  = bbMiddle * rand(0.03, 0.08);
    const vol20Avg = rand(1_000_000, 50_000_000);

    // Synthesise a minimal 5-bar series
    let px = price * 0.95;
    const series: PriceBar[] = Array.from({ length: 250 }, (_, i) => {
      const close = Math.max(px * (1 + (Math.random() - 0.49) * 0.015), 1);
      const open  = px;
      const high  = Math.max(open, close) * (1 + Math.random() * 0.008);
      const low   = Math.min(open, close) * (1 - Math.random() * 0.008);
      px = close;
      return {
        date: new Date(Date.now() - (250 - i) * 86_400_000),
        open: +open.toFixed(2), high: +high.toFixed(2),
        low: +low.toFixed(2), close: +close.toFixed(2),
        volume: Math.floor(rand(vol20Avg * 0.5, vol20Avg * 2)),
      };
    });

    const macd      = maybe(rand(-2, 4));
    const macdSig   = macd != null ? macd * rand(0.6, 1.1) : null;
    const macdH     = macd != null && macdSig != null ? macd - macdSig : null;

    return {
      symbol, name, market, sector: sector ?? 'Unknown', marketCap: rand(1e9, 3e12),
      date: new Date(), open: price * rand(0.99, 1.01), high: price * rand(1.00, 1.02),
      low: price * rand(0.98, 1.00), close: price, volume: Math.floor(rand(vol20Avg * 0.5, vol20Avg * 3)),
      series,
      rsi14:        maybe(rand(25, 75)),
      macd,
      macdSignal:   macdSig,
      macdHist:     macdH,
      macdHistPrev: macdH != null ? macdH * rand(0.8, 1.2) : null,
      macdHistPrev2: macdH != null ? macdH * rand(0.7, 1.1) : null,
      ema20:        maybe(price * rand(0.97, 1.03)),
      ema50, ema200,
      sma50, sma200,
      atr14:        atr,
      obv:          maybe(rand(1e7, 1e9)),
      vwap:         maybe(price * rand(0.98, 1.02)),
      bbUpper:      bbMiddle + bbWidth,
      bbMiddle,
      bbLower:      bbMiddle - bbWidth,
      adx14:        maybe(rand(12, 45)),
      stochK:       maybe(rand(10, 90)),
      stochD:       maybe(rand(10, 90)),
      stochKPrev:   maybe(rand(10, 90)),
      stochDPrev:   maybe(rand(10, 90)),
      high52w:      price * rand(1.0, 1.5),
      vol20Avg,
      beta:         maybe(rand(0.3, 1.8)),
      relStrength:  maybe(rand(0.7, 1.5)),
      dividendYield: maybe(rand(0, 6)),
      currentRatio:  maybe(rand(0.8, 4.0)),
      operatingMargin: maybe(rand(5, 40)),
      pe:            maybe(rand(8, 45)),
      pb:            maybe(rand(0.5, 5.0)),
      roe:           maybe(rand(5, 40)),
      debtEquity:    maybe(rand(0.1, 2.5)),
      revenueGrowth: maybe(rand(-10, 35)),
      earningsGrowth: maybe(rand(-15, 40)),
      freeCashFlow:  maybe(rand(-1e9, 5e9)),
      sectorAvgPE:   rand(15, 30),
    } satisfies StockData;
  });
}
