/**
 * VERDENT — Market Condition Analysis Engine
 *
 * Classifies a market as BULL / BEAR / SIDEWAYS using a four-pillar weighted
 * scoring model.
 *
 * Scoring summary
 * ──────────────────────────────────────────────────────────────────────────
 *  Pillar        Weight   Raw range   Weighted range
 *  ─────────────────────────────────────────────────
 *  Trend         40 %     −6 … +6     −2.40 … +2.40
 *  Momentum      30 %     −3 … +3     −0.90 … +0.90
 *  Volatility    20 %     −2 … +2     −0.40 … +0.40
 *  Breadth       10 %     −3 … +3     −0.30 … +0.30
 *  ─────────────────────────────────────────────────
 *  TOTAL                  −14… +14    −4.00 … +4.00
 *
 * Final score is linearly re-scaled to −10 … +10 for readability.
 * Thresholds:  score > 3  → BULL
 *              score < −3 → BEAR
 *              otherwise  → SIDEWAYS
 *
 * Confidence is the percentage of individual binary signals that agree with
 * the final condition label (0 – 100 %).
 */

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export type MarketConditionLabel = 'BULL' | 'BEAR' | 'SIDEWAYS';
export type CriteriaLabel = 'ALFA' | 'BETA' | 'DELTA';
export type MarketId = 'US' | 'BIST';

export interface PillarResult {
  /** Raw pillar score (before weight is applied) */
  rawScore: number;
  /** Weight-adjusted contribution */
  weightedScore: number;
  /** Human-readable breakdown of each signal within the pillar */
  details: Record<string, string | number>;
  /** Individual signal values (+1 / 0 / −1) used for confidence calc */
  signals: number[];
}

export interface MarketConditionIndicators {
  trend:      PillarResult;
  momentum:   PillarResult;
  volatility: PillarResult;
  breadth:    PillarResult;
}

export interface MarketConditionResult {
  condition:           MarketConditionLabel;
  /** Re-scaled to −10 … +10 */
  score:               number;
  /** 0 – 100 */
  confidence:          number;
  indicators:          MarketConditionIndicators;
  recommendedCriteria: CriteriaLabel;
  date:                Date;
  market:              MarketId;
}

// ─────────────────────────────────────────────────────────────────────────────
// Input shape for a single price bar + pre-computed indicators
// ─────────────────────────────────────────────────────────────────────────────

export interface PriceBar {
  date:   Date;
  open:   number;
  high:   number;
  low:    number;
  close:  number;
  volume: number;
  // Optional pre-computed indicators (the engine will derive them from the
  // series when they are not provided, or fall back to neutral if the series
  // is too short).
  sma50?:      number | null;
  sma200?:     number | null;
  ema20?:      number | null;
  ema50?:      number | null;
  ema200?:     number | null;
  rsi14?:      number | null;
  macd?:       number | null;
  macdSignal?: number | null;
  adx14?:      number | null;
  atr14?:      number | null;
  obv?:        number | null;
  bbUpper?:    number | null;
  bbLower?:    number | null;
  bbMiddle?:   number | null;
  stochK?:     number | null;
  stochD?:     number | null;
}

export interface BreadthSnapshot {
  advanceCount:        number;
  declineCount:        number;
  pctAbove200Sma:      number;  // 0 – 100
  newHighs:            number;
  newLows:             number;
}

export interface MarketAnalysisInput {
  market:   MarketId;
  date:     Date;
  /** Ordered oldest → newest, the last bar is "today" */
  series:   PriceBar[];
  vix?:     number | null;
  breadth?: BreadthSnapshot | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Pillar weights (must sum to 1)
// ─────────────────────────────────────────────────────────────────────────────

const WEIGHTS = {
  trend:      0.40,
  momentum:   0.30,
  volatility: 0.20,
  breadth:    0.10,
} as const;

// ─────────────────────────────────────────────────────────────────────────────
// Helper maths
// ─────────────────────────────────────────────────────────────────────────────

/** Simple Moving Average over the last `period` closes in `series` */
function sma(series: PriceBar[], period: number): number | null {
  if (series.length < period) return null;
  const slice = series.slice(-period);
  return slice.reduce((s, b) => s + b.close, 0) / period;
}

/** Exponential Moving Average (uses last `period` * 3 bars for stability) */
function ema(series: PriceBar[], period: number): number | null {
  if (series.length < period) return null;
  const k   = 2 / (period + 1);
  let value = series[0].close;
  for (let i = 1; i < series.length; i++) {
    value = series[i].close * k + value * (1 - k);
  }
  return value;
}

/** Wilders-smoothed RSI(14) */
function rsi(series: PriceBar[], period = 14): number | null {
  if (series.length < period + 1) return null;
  let gains = 0, losses = 0;
  for (let i = series.length - period; i < series.length; i++) {
    const delta = series[i].close - series[i - 1].close;
    if (delta >= 0) gains  += delta;
    else            losses -= delta;
  }
  const avgGain = gains  / period;
  const avgLoss = losses / period;
  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}

/** True Range → ATR(14), returned as % of close */
function atrPct(series: PriceBar[], period = 14): number | null {
  if (series.length < period + 1) return null;
  const trs: number[] = [];
  for (let i = series.length - period; i < series.length; i++) {
    const high  = series[i].high;
    const low   = series[i].low;
    const prev  = series[i - 1].close;
    trs.push(Math.max(high - low, Math.abs(high - prev), Math.abs(low - prev)));
  }
  const atr = trs.reduce((s, v) => s + v, 0) / period;
  const lastClose = series[series.length - 1].close;
  return lastClose > 0 ? (atr / lastClose) * 100 : null;
}

/** Detect Higher Highs + Higher Lows or Lower Highs + Lower Lows over lookback */
function swingStructure(
  series: PriceBar[],
  lookback = 20,
): 'UPTREND' | 'DOWNTREND' | 'MIXED' {
  if (series.length < lookback) return 'MIXED';
  const window = series.slice(-lookback);
  // Find local peaks and troughs (simple: compare with neighbours)
  const highs: number[] = [];
  const lows:  number[] = [];
  for (let i = 1; i < window.length - 1; i++) {
    if (window[i].high > window[i - 1].high && window[i].high > window[i + 1].high)
      highs.push(window[i].high);
    if (window[i].low < window[i - 1].low && window[i].low < window[i + 1].low)
      lows.push(window[i].low);
  }
  if (highs.length < 2 || lows.length < 2) return 'MIXED';
  const hhhl =
    highs[highs.length - 1] > highs[highs.length - 2] &&
    lows[lows.length - 1]   > lows[lows.length - 2];
  const lhll =
    highs[highs.length - 1] < highs[highs.length - 2] &&
    lows[lows.length - 1]   < lows[lows.length - 2];
  if (hhhl) return 'UPTREND';
  if (lhll) return 'DOWNTREND';
  return 'MIXED';
}

/** Clamp a value to [min, max] */
function clamp(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v));
}

/** Re-scale a weighted sum (range = wMin … wMax) to −10 … +10 */
function rescale(weighted: number, wMin: number, wMax: number): number {
  const normalised = (weighted - wMin) / (wMax - wMin); // 0 … 1
  return +(normalised * 20 - 10).toFixed(2);
}

// ─────────────────────────────────────────────────────────────────────────────
// Pillar scorers
// ─────────────────────────────────────────────────────────────────────────────

function scoreTrend(input: MarketAnalysisInput): PillarResult {
  const { series } = input;
  const last = series[series.length - 1];

  // Derive or use pre-computed values
  const sma50Val  = last.sma50  ?? sma(series, 50);
  const sma200Val = last.sma200 ?? sma(series, 200);
  const price     = last.close;

  const signals: number[] = [];
  const details: Record<string, string | number> = {};

  // ── Signal 1: Price vs 200 SMA ──────────────────────────────────────────
  let s1 = 0;
  if (sma200Val !== null) {
    s1 = price > sma200Val ? 2 : -2;
    details['price_vs_sma200'] = `${price.toFixed(2)} vs ${sma200Val.toFixed(2)} → ${s1 > 0 ? 'above' : 'below'}`;
  } else {
    details['price_vs_sma200'] = 'insufficient data';
  }
  signals.push(s1 > 0 ? 1 : s1 < 0 ? -1 : 0);

  // ── Signal 2: 50 SMA vs 200 SMA (Golden / Death Cross) ──────────────────
  let s2 = 0;
  if (sma50Val !== null && sma200Val !== null) {
    s2 = sma50Val > sma200Val ? 2 : -2;
    details['sma50_vs_sma200'] = `${sma50Val.toFixed(2)} vs ${sma200Val.toFixed(2)} → ${s2 > 0 ? 'golden cross' : 'death cross'}`;
  } else {
    details['sma50_vs_sma200'] = 'insufficient data';
  }
  signals.push(s2 > 0 ? 1 : s2 < 0 ? -1 : 0);

  // ── Signal 3: Higher Highs / Lower Lows structure ────────────────────────
  const structure = swingStructure(series, 30);
  let s3 = 0;
  if (structure === 'UPTREND')   s3 = 2;
  if (structure === 'DOWNTREND') s3 = -2;
  details['swing_structure'] = structure;
  signals.push(s3 > 0 ? 1 : s3 < 0 ? -1 : 0);

  const rawScore = clamp(s1 + s2 + s3, -6, 6);
  return {
    rawScore,
    weightedScore: rawScore * WEIGHTS.trend,
    details,
    signals,
  };
}

function scoreMomentum(input: MarketAnalysisInput): PillarResult {
  const { series } = input;
  const last = series[series.length - 1];

  const rsiVal  = last.rsi14      ?? rsi(series, 14);
  const macdVal = last.macd       ?? null;
  const sigVal  = last.macdSignal ?? null;
  const adxVal  = last.adx14      ?? null;

  const signals: number[] = [];
  const details: Record<string, string | number> = {};

  // ── Signal 1: RSI level ──────────────────────────────────────────────────
  let s1 = 0;
  if (rsiVal !== null) {
    if (rsiVal > 50)      s1 =  1;
    else if (rsiVal < 40) s1 = -1;
    details['rsi14'] = +rsiVal.toFixed(2);
  } else {
    details['rsi14'] = 'n/a';
  }
  signals.push(s1);

  // ── Signal 2: MACD vs Signal line ───────────────────────────────────────
  let s2 = 0;
  if (macdVal !== null && sigVal !== null) {
    s2 = macdVal > sigVal ? 1 : -1;
    details['macd']        = +macdVal.toFixed(4);
    details['macd_signal'] = +sigVal.toFixed(4);
    details['macd_status'] = s2 > 0 ? 'above signal' : 'below signal';
  } else {
    details['macd'] = 'n/a';
  }
  signals.push(s2);

  // ── Signal 3: ADX trend-strength ────────────────────────────────────────
  let s3 = 0;
  let adxNote = 'n/a';
  if (adxVal !== null) {
    if (adxVal > 25)      { adxNote = 'strong trend confirmed'; s3 = 0; }  // confirms direction
    else if (adxVal < 20) { adxNote = 'weak / sideways';        s3 = -1; }  // sideways penalty
    details['adx14'] = +adxVal.toFixed(2);
    details['adx_status'] = adxNote;
  } else {
    details['adx14'] = 'n/a';
  }
  signals.push(s3);

  const rawScore = clamp(s1 + s2 + s3, -3, 3);
  return {
    rawScore,
    weightedScore: rawScore * WEIGHTS.momentum,
    details,
    signals,
  };
}

function scoreVolatility(input: MarketAnalysisInput): PillarResult {
  const { series, vix } = input;
  const last = series[series.length - 1];

  const atrPctVal = atrPct(series, 14);
  const signals: number[] = [];
  const details: Record<string, string | number> = {};

  // ── Signal 1: VIX level (US only; BIST uses ATR-only proxy) ─────────────
  let s1 = 0;
  if (vix !== null && vix !== undefined) {
    if (vix < 15)        { s1 =  1; details['vix'] = `${vix} (low — bull signal)`; }
    else if (vix <= 25)  { s1 =  0; details['vix'] = `${vix} (elevated — neutral)`; }
    else                 { s1 = -1; details['vix'] = `${vix} (high — bear signal)`; }
  } else {
    details['vix'] = 'n/a — using ATR proxy';
    // BIST proxy: if ATR% is high, penalise volatility
    if (atrPctVal !== null) {
      s1 = atrPctVal > 3 ? -1 : atrPctVal < 1 ? 1 : 0;
    }
  }
  signals.push(s1);

  // ── Signal 2: ATR% trend ────────────────────────────────────────────────
  let s2 = 0;
  if (atrPctVal !== null) {
    details['atr_pct'] = +atrPctVal.toFixed(2) + '%';
    // Very low ATR = consolidation / sideways; high ATR = trending
    if (atrPctVal < 0.8) s2 = -1;  // ultra-low vol → sideways
    else                  s2 =  1;  // trending / directional
  } else {
    details['atr_pct'] = 'n/a';
  }
  signals.push(s2);

  // ── Bollinger Band width (additional context) ───────────────────────────
  if (last.bbUpper !== null && last.bbUpper !== undefined &&
      last.bbLower !== null && last.bbLower !== undefined &&
      last.bbMiddle !== null && last.bbMiddle !== undefined && last.bbMiddle > 0) {
    const bbWidth = (last.bbUpper - last.bbLower) / last.bbMiddle * 100;
    details['bb_width_pct'] = +bbWidth.toFixed(2) + '%';
  }

  const rawScore = clamp(s1 + s2, -2, 2);
  return {
    rawScore,
    weightedScore: rawScore * WEIGHTS.volatility,
    details,
    signals,
  };
}

function scoreBreadth(input: MarketAnalysisInput): PillarResult {
  const { breadth } = input;
  const signals: number[] = [];
  const details: Record<string, string | number> = {};

  if (!breadth) {
    details['note'] = 'no breadth data — pillar neutral';
    return { rawScore: 0, weightedScore: 0, details, signals: [0] };
  }

  const { advanceCount, declineCount, pctAbove200Sma, newHighs, newLows } = breadth;

  // ── Signal 1: Advance / Decline ratio ───────────────────────────────────
  let s1 = 0;
  const total = advanceCount + declineCount;
  if (total > 0) {
    const adRatio = advanceCount / total;
    s1 = adRatio > 0.55 ? 1 : adRatio < 0.45 ? -1 : 0;
    details['advance_decline_ratio'] = +adRatio.toFixed(3);
    details['advancing'] = advanceCount;
    details['declining']  = declineCount;
  }
  signals.push(s1);

  // ── Signal 2: % of stocks above 200 SMA ─────────────────────────────────
  let s2 = 0;
  if (pctAbove200Sma >= 60)      { s2 =  1; }
  else if (pctAbove200Sma <= 40) { s2 = -1; }
  details['pct_above_200sma'] = pctAbove200Sma.toFixed(1) + '%';
  signals.push(s2);

  // ── Signal 3: New Highs vs New Lows ─────────────────────────────────────
  let s3 = 0;
  const hlTotal = newHighs + newLows;
  if (hlTotal > 0) {
    const hlRatio = newHighs / hlTotal;
    s3 = hlRatio > 0.6 ? 1 : hlRatio < 0.4 ? -1 : 0;
    details['new_highs'] = newHighs;
    details['new_lows']  = newLows;
    details['nh_nl_ratio'] = +hlRatio.toFixed(3);
  }
  signals.push(s3);

  const rawScore = clamp(s1 + s2 + s3, -3, 3);
  return {
    rawScore,
    weightedScore: rawScore * WEIGHTS.breadth,
    details,
    signals,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Confidence calculator
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Returns 0 – 100.
 * Measures what fraction of individual binary signals point in the same
 * direction as the final `condition`.
 */
function calcConfidence(
  indicators: MarketConditionIndicators,
  condition:  MarketConditionLabel,
): number {
  const allSignals = [
    ...indicators.trend.signals,
    ...indicators.momentum.signals,
    ...indicators.volatility.signals,
    ...indicators.breadth.signals,
  ];

  const nonNeutral = allSignals.filter(s => s !== 0);
  if (nonNeutral.length === 0) return 50;

  let agreeing: number;
  if (condition === 'BULL') {
    agreeing = nonNeutral.filter(s => s > 0).length;
  } else if (condition === 'BEAR') {
    agreeing = nonNeutral.filter(s => s < 0).length;
  } else {
    // SIDEWAYS: neutral signals (0) agree; directional signals disagree
    const neutralCount = allSignals.filter(s => s === 0).length;
    const total        = allSignals.length;
    agreeing = neutralCount;
    return Math.round((agreeing / total) * 100);
  }

  return Math.round((agreeing / nonNeutral.length) * 100);
}

// ─────────────────────────────────────────────────────────────────────────────
// Criteria recommendation
// ─────────────────────────────────────────────────────────────────────────────

/**
 * ALFA → aggressive growth (BULL markets)
 * BETA → balanced / rotation (SIDEWAYS / uncertain)
 * DELTA → defensive / short-bias (BEAR markets)
 */
function recommendCriteria(
  condition:  MarketConditionLabel,
  confidence: number,
): CriteriaLabel {
  if (condition === 'BULL')    return confidence >= 60 ? 'ALFA' : 'BETA';
  if (condition === 'BEAR')    return confidence >= 60 ? 'DELTA' : 'BETA';
  return 'BETA';
}

// ─────────────────────────────────────────────────────────────────────────────
// Core analysis function
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Run all four pillars and produce a full `MarketConditionResult`.
 */
export function analyzeMarketCondition(
  input: MarketAnalysisInput,
): MarketConditionResult {
  if (input.series.length === 0) {
    throw new Error('analyzeMarketCondition: series must contain at least one bar');
  }

  const trend      = scoreTrend(input);
  const momentum   = scoreMomentum(input);
  const volatility = scoreVolatility(input);
  const breadth    = scoreBreadth(input);

  const indicators: MarketConditionIndicators = {
    trend, momentum, volatility, breadth,
  };

  // Total weighted score (−4 … +4 with current weights and raw ranges)
  const totalWeighted =
    trend.weightedScore +
    momentum.weightedScore +
    volatility.weightedScore +
    breadth.weightedScore;

  // Theoretical bounds:
  //   max = 6*0.4 + 3*0.3 + 2*0.2 + 3*0.1 = 2.4+0.9+0.4+0.3 = 4.0
  //   min = −4.0
  const W_MAX = 4.0;
  const W_MIN = -4.0;

  const score = rescale(totalWeighted, W_MIN, W_MAX); // −10 … +10

  const condition: MarketConditionLabel =
    score >  3 ? 'BULL' :
    score < -3 ? 'BEAR' :
                 'SIDEWAYS';

  const confidence = calcConfidence(indicators, condition);
  const recommendedCriteria = recommendCriteria(condition, confidence);

  return {
    condition,
    score,
    confidence,
    indicators,
    recommendedCriteria,
    date:   input.date,
    market: input.market,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Batch / historical analysis
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Walk through a historical price series day-by-day and return one
 * `MarketConditionResult` per date within [startDate, endDate].
 *
 * Each analysis uses all bars available up to and including that date
 * (expanding window), ensuring no look-ahead bias.
 */
export function getHistoricalMarketConditions(
  market:    MarketId,
  series:    PriceBar[],
  startDate: Date,
  endDate:   Date,
  vixSeries?: Map<string, number>,
  breadthSeries?: Map<string, BreadthSnapshot>,
): MarketConditionResult[] {
  const results: MarketConditionResult[] = [];

  const start = startDate.getTime();
  const end   = endDate.getTime();

  for (let i = 1; i <= series.length; i++) {
    const bar = series[i - 1];
    const t   = bar.date.getTime();

    if (t < start || t > end) continue;

    const dateKey = bar.date.toISOString().split('T')[0];
    const subSeries = series.slice(0, i);

    const result = analyzeMarketCondition({
      market,
      date: bar.date,
      series: subSeries,
      vix:     vixSeries?.get(dateKey) ?? null,
      breadth: breadthSeries?.get(dateKey) ?? null,
    });

    results.push(result);
  }

  return results;
}

// ─────────────────────────────────────────────────────────────────────────────
// "Current" — convenience wrapper using the last bar in a series
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Analyse the current (most recent) market condition from a live series.
 * Pass the full available history for best accuracy.
 */
export function getCurrentMarketCondition(
  market: MarketId,
  series: PriceBar[],
  vix?:    number | null,
  breadth?: BreadthSnapshot | null,
): MarketConditionResult {
  if (series.length === 0) {
    throw new Error('getCurrentMarketCondition: series is empty');
  }
  return analyzeMarketCondition({
    market,
    date: series[series.length - 1].date,
    series,
    vix:    vix    ?? null,
    breadth: breadth ?? null,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Database persistence  (Prisma)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Upsert a `MarketConditionResult` into the `market_conditions` table.
 *
 * Requires `@prisma/client` to be available.  Import is dynamic so the module
 * can be used / tested without a live database connection.
 */
export async function saveMarketCondition(
  result: MarketConditionResult,
): Promise<void> {
  // Dynamic import keeps the module usable in unit tests without a real DB.
  const { PrismaClient } = await import('@prisma/client');
  const prisma = new PrismaClient();

  try {
    // Normalise to midnight UTC so the @@unique(date) constraint works
    const dateKey = new Date(
      Date.UTC(
        result.date.getFullYear(),
        result.date.getMonth(),
        result.date.getDate(),
      ),
    );

    // Build the breadth index scalar (average of A/D ratio + pctAbove200SMA)
    const breadthDetails = result.indicators.breadth.details as Record<string, number | string>;
    const adRatio         = typeof breadthDetails['advance_decline_ratio'] === 'number'
      ? breadthDetails['advance_decline_ratio'] as number
      : null;
    const pctAbove        = typeof breadthDetails['pct_above_200sma'] === 'string'
      ? parseFloat(breadthDetails['pct_above_200sma'] as string)
      : null;
    const breadthIndex    =
      adRatio !== null && pctAbove !== null
        ? +((adRatio * 100 + pctAbove) / 2).toFixed(2)
        : null;

    // Derive VIX from volatility details
    const volDetails = result.indicators.volatility.details as Record<string, string | number>;
    const vixRaw     = volDetails['vix'];
    const vixLevel   =
      typeof vixRaw === 'number'
        ? vixRaw
        : typeof vixRaw === 'string' && !vixRaw.includes('n/a')
          ? parseFloat(vixRaw)
          : null;

    const sp500Trend = result.market === 'US'   ? result.condition : null;
    const bistTrend  = result.market === 'BIST' ? result.condition : null;

    await prisma.marketCondition.upsert({
      where:  { date: dateKey },
      update: {
        condition:    result.condition,
        confidence:   result.confidence,
        vixLevel,
        breadthIndex,
        sp500Trend,
        bistTrend,
        indicators:   result.indicators as object,
      },
      create: {
        date:         dateKey,
        market:       result.market,
        condition:    result.condition,
        confidence:   result.confidence,
        vixLevel,
        breadthIndex,
        sp500Trend,
        bistTrend,
        indicators:   result.indicators as object,
      },
    });
  } finally {
    await prisma.$disconnect();
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Load from DB  (convenience)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch all persisted `MarketCondition` rows for a given market and date range,
 * and rehydrate them as lightweight result objects (indicators come from the
 * stored JSON blob).
 */
export async function loadMarketConditions(
  market:    MarketId,
  startDate: Date,
  endDate:   Date,
): Promise<MarketConditionResult[]> {
  const { PrismaClient } = await import('@prisma/client');
  const prisma = new PrismaClient();

  try {
    const rows = await prisma.marketCondition.findMany({
      where: {
        market,
        date: { gte: startDate, lte: endDate },
      },
      orderBy: { date: 'asc' },
    });

    return rows.map(row => ({
      condition:           row.condition as MarketConditionLabel,
      score:               0, // not stored separately; recalculate if needed
      confidence:          row.confidence,
      indicators:          row.indicators as unknown as MarketConditionIndicators,
      recommendedCriteria: recommendCriteria(row.condition as MarketConditionLabel, row.confidence),
      date:                row.date,
      market:              row.market as MarketId,
    }));
  } finally {
    await prisma.$disconnect();
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Mock-data factory  (testing / demo)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Build a synthetic price series useful for unit-testing the engine without
 * real market data.
 *
 * @param days   Number of bars to generate (default 300)
 * @param regime Starting regime drives the random walk bias
 */
export function generateMockSeries(
  days   = 300,
  regime: 'BULL' | 'BEAR' | 'SIDEWAYS' = 'BULL',
): PriceBar[] {
  const bias =
    regime === 'BULL'     ?  0.0008 :
    regime === 'BEAR'     ? -0.0008 :
                             0.0001;

  const series: PriceBar[] = [];
  let price = 450;
  const now = Date.now();

  for (let i = days; i >= 0; i--) {
    const date   = new Date(now - i * 86_400_000);
    const change = (Math.random() - 0.5 + bias) * price * 0.018;
    const open   = price;
    const close  = Math.max(open + change, 1);
    const high   = Math.max(open, close) * (1 + Math.random() * 0.008);
    const low    = Math.min(open, close) * (1 - Math.random() * 0.008);
    const volume = Math.floor(Math.random() * 80_000_000 + 20_000_000);
    series.push({ date, open: +open.toFixed(2), high: +high.toFixed(2), low: +low.toFixed(2), close: +close.toFixed(2), volume });
    price = close;
  }
  return series;
}
