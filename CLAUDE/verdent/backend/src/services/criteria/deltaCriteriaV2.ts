/**
 * VERDENT — DELTA Criteria V2
 * Professional Sideways Market / Mean-Reversion Strategy
 *
 * Research basis:
 *   • Poterba & Summers (1988)   — Mean reversion in equity prices
 *   • Bollinger Band methodology  — Statistical range / volatility bands
 *   • Statistical arbitrage       — Z-score deviation & reversion
 *   • Volume Profile (TPO)        — High-volume node as support
 *   • Fibonacci confluence        — Multi-level support clustering
 *
 * Primary objective   : Profit from range-bound mean-reversion setups
 * Secondary objective : Capital preservation via tight range stops
 * Benchmark           : Beat risk-free rate in sideways conditions
 *
 * Architecture:
 *   Phase 1 — Hard Filters  (all must pass)
 *   Phase 2 — Scoring       (6 factor buckets, 100 pts total)
 *   Phase 3 — Trade Plan    (range-based entry / take-profit / stop)
 */

import type { StockData } from '../criteriaEngine';
import type { PriceBar }  from '../marketConditionService';

// ─────────────────────────────────────────────────────────────────────────────
// Value types
// ─────────────────────────────────────────────────────────────────────────────

export interface OHLCV {
  date:   Date;
  open:   number;
  high:   number;
  low:    number;
  close:  number;
  volume: number;
}

export interface HardFilterResult {
  passed:   boolean;
  failedOn: string[];
}

export interface FactorScore {
  raw:        number;   // 0–1
  weighted:   number;   // raw × max_pts
  components: { name: string; value: number | string; score: number; weight: number }[];
}

export interface TakeProfitConfig {
  target1:     number;   // 50% partial at range midpoint
  target2:     number;   // remainder near range top
  stopLoss:    number;   // just below range low
  maxHoldDays: number;
  rangeHigh:   number;
  rangeLow:    number;
  rangeWidth:  number;   // fraction
}

export interface DeltaV2Score {
  total:            number;       // 0–100
  grade:            'A+' | 'A' | 'B' | 'C' | 'D' | 'F';
  hardFilterPassed: boolean;
  hardFilterResult: HardFilterResult;
  factors: {
    rangeQuality:       FactorScore;
    meanReversionSetup: FactorScore;
    supportConfluence:  FactorScore;
    fundamentalFloor:   FactorScore;
    lowEventRisk:       FactorScore;
    volatilityTiming:   FactorScore;
  };
  tradePlan:  TakeProfitConfig;
  stopLoss:   number;
  stopPercent: number;
  targetPrice: number;
  riskRewardRatio: number;
  signals: {
    passed:   string[];
    failed:   string[];
    warnings: string[];
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Math / indicator helpers
// ─────────────────────────────────────────────────────────────────────────────

function normalizeScore(x: number, lo: number, hi: number): number {
  if (hi === lo) return 0;
  return Math.max(0, Math.min(1, (x - lo) / (hi - lo)));
}

function closes(bars: OHLCV[]): number[] { return bars.map(b => b.close); }

function sma(bars: OHLCV[], period: number): number {
  const src = closes(bars);
  if (src.length < period) return src[src.length - 1] ?? 0;
  const slice = src.slice(-period);
  return slice.reduce((a, b) => a + b, 0) / period;
}

function ema(bars: OHLCV[], period: number): number {
  const src = closes(bars);
  if (src.length < period) return src[src.length - 1] ?? 0;
  const k   = 2 / (period + 1);
  let   val = src.slice(0, period).reduce((a, b) => a + b, 0) / period;
  for (let i = period; i < src.length; i++) val = src[i] * k + val * (1 - k);
  return val;
}

function stdDev(bars: OHLCV[], period: number): number {
  const src  = closes(bars).slice(-period);
  if (src.length < 2) return 0;
  const mean = src.reduce((a, b) => a + b, 0) / src.length;
  const variance = src.reduce((a, b) => a + (b - mean) ** 2, 0) / src.length;
  return Math.sqrt(variance);
}

function bollinger(bars: OHLCV[], period = 20, mult = 2): { upper: number; middle: number; lower: number; width: number } {
  const mid   = sma(bars, period);
  const sd    = stdDev(bars, period);
  const upper = mid + mult * sd;
  const lower = mid - mult * sd;
  return { upper, middle: mid, lower, width: mid > 0 ? (upper - lower) / mid : 0 };
}

function adx(bars: OHLCV[], period = 14): number {
  if (bars.length < period * 2) return 20;
  const dmPlus: number[]  = [];
  const dmMinus: number[] = [];
  const trArr: number[]   = [];
  for (let i = 1; i < bars.length; i++) {
    const hi = bars[i].high, lo = bars[i].low, pc = bars[i - 1].close;
    const ph = bars[i - 1].high, pl = bars[i - 1].low;
    trArr.push(Math.max(hi - lo, Math.abs(hi - pc), Math.abs(lo - pc)));
    const upMove = hi - ph, downMove = pl - lo;
    dmPlus.push(upMove > downMove && upMove > 0 ? upMove : 0);
    dmMinus.push(downMove > upMove && downMove > 0 ? downMove : 0);
  }
  const smoothed = (arr: number[]) => {
    let s = arr.slice(0, period).reduce((a, b) => a + b, 0);
    const out = [s];
    for (let i = period; i < arr.length; i++) {
      s = s - s / period + arr[i];
      out.push(s);
    }
    return out;
  };
  const sTR  = smoothed(trArr);
  const sDP  = smoothed(dmPlus);
  const sDM  = smoothed(dmMinus);
  const last = sTR.length - 1;
  if (sTR[last] === 0) return 0;
  const diP = (sDP[last] / sTR[last]) * 100;
  const diM = (sDM[last] / sTR[last]) * 100;
  const dx  = Math.abs(diP - diM) / (diP + diM + 1e-10) * 100;
  return dx;
}

function rsi(bars: OHLCV[], period = 14): number {
  const src = closes(bars);
  if (src.length < period + 1) return 50;
  let gains = 0, losses = 0;
  for (let i = src.length - period; i < src.length; i++) {
    const d = src[i] - src[i - 1];
    if (d >= 0) gains += d; else losses -= d;
  }
  const avgG = gains / period, avgL = losses / period;
  if (avgL === 0) return 100;
  return 100 - 100 / (1 + avgG / avgL);
}

function stochastic(bars: OHLCV[], kPeriod = 14, dPeriod = 3): { k: number; d: number; kPrev: number } {
  if (bars.length < kPeriod + dPeriod) return { k: 50, d: 50, kPrev: 50 };
  const rawK: number[] = [];
  for (let i = kPeriod - 1; i < bars.length; i++) {
    const window = bars.slice(i - kPeriod + 1, i + 1);
    const hi = window.reduce((m, b) => Math.max(m, b.high), 0);
    const lo = window.reduce((m, b) => Math.min(m, b.low), Infinity);
    rawK.push(hi === lo ? 50 : (bars[i].close - lo) / (hi - lo) * 100);
  }
  const kLine = rawK.map((_, i, a) =>
    i < dPeriod - 1 ? NaN : a.slice(i - dPeriod + 1, i + 1).reduce((s, v) => s + v, 0) / dPeriod);
  const dLine = kLine.map((_, i, a) => {
    const valid = a.slice(Math.max(0, i - dPeriod + 1), i + 1).filter(v => !isNaN(v));
    return valid.length === dPeriod ? valid.reduce((s, v) => s + v, 0) / dPeriod : NaN;
  });
  const last = kLine.length - 1;
  return {
    k:     isNaN(kLine[last])     ? 50 : kLine[last],
    d:     isNaN(dLine[last])     ? 50 : dLine[last],
    kPrev: isNaN(kLine[last - 1]) ? 50 : kLine[last - 1],
  };
}

function atr(bars: OHLCV[], period = 14): number {
  if (bars.length < 2) return (bars[0]?.close ?? 50) * 0.02;
  const trs: number[] = [];
  for (let i = 1; i < bars.length; i++) {
    const h = bars[i].high, l = bars[i].low, pc = bars[i - 1].close;
    trs.push(Math.max(h - l, Math.abs(h - pc), Math.abs(l - pc)));
  }
  return trs.slice(-period).reduce((a, b) => a + b, 0) / Math.min(trs.length, period);
}

/** Rolling historical volatility (annualised) */
function historicalVol(bars: OHLCV[], period = 20): number {
  const src  = closes(bars).slice(-period - 1);
  if (src.length < 2) return 0.20;
  const rets = src.slice(1).map((c, i) => Math.log(c / src[i]));
  const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
  const variance = rets.reduce((a, b) => a + (b - mean) ** 2, 0) / (rets.length - 1);
  return Math.sqrt(variance * 252);
}

/** Volatility percentile (current HV rank over lookback) */
function volPercentile(bars: OHLCV[], lookback = 252): number {
  if (bars.length < lookback + 21) return 0.50;
  const hvs: number[] = [];
  for (let i = 21; i <= lookback; i++) hvs.push(historicalVol(bars.slice(0, bars.length - lookback + i)));
  const cur = historicalVol(bars);
  const below = hvs.filter(v => v <= cur).length;
  return below / hvs.length;
}

/** Count how many times price tested range boundaries (within tolerance) */
function countRangeTouches(bars: OHLCV[], rangeHigh: number, rangeLow: number, period: number): number {
  const recent = bars.slice(-period);
  let touches = 0;
  const tol = (rangeHigh - rangeLow) * 0.03;
  for (const b of recent) {
    if (Math.abs(b.high - rangeHigh) < tol) touches++;
    if (Math.abs(b.low  - rangeLow)  < tol) touches++;
  }
  return touches;
}

/** Detect simple bullish RSI divergence: price lower low but RSI higher low */
function detectRSIDivergence(bars: OHLCV[], rsiPeriod = 14, lookback = 10): boolean {
  if (bars.length < lookback + rsiPeriod + 5) return false;
  const recent     = bars.slice(-lookback);
  const priorBars  = bars.slice(-(lookback * 2), -lookback);
  if (priorBars.length < 5) return false;
  const recentLow  = Math.min(...recent.map(b => b.close));
  const priorLow   = Math.min(...priorBars.map(b => b.close));
  const recentRSI  = rsi(bars, rsiPeriod);
  const priorRSI   = rsi(bars.slice(0, -lookback), rsiPeriod);
  return recentLow < priorLow && recentRSI > priorRSI;
}

/** Fibonacci retracement levels from recent swing high/low */
function fibonacciLevels(bars: OHLCV[], lookback = 60): number[] {
  const recent = bars.slice(-lookback);
  const hi     = Math.max(...recent.map(b => b.high));
  const lo     = Math.min(...recent.map(b => b.low));
  const diff   = hi - lo;
  return [0.236, 0.382, 0.500, 0.618, 0.786].map(r => lo + diff * r);
}

/** Approximate volume profile: 10 price buckets → top 3 high-volume nodes */
function volumeProfileNodes(bars: OHLCV[], lookback = 60): number[] {
  const recent = bars.slice(-lookback);
  const lo     = Math.min(...recent.map(b => b.low));
  const hi     = Math.max(...recent.map(b => b.high));
  const buckets = 10;
  const width   = (hi - lo) / buckets;
  if (width === 0) return [lo];
  const volByBucket = Array(buckets).fill(0);
  for (const b of recent) {
    const idx = Math.min(Math.floor((b.close - lo) / width), buckets - 1);
    volByBucket[idx] += b.volume;
  }
  return volByBucket
    .map((v, i) => ({ v, price: lo + (i + 0.5) * width }))
    .sort((a, b) => b.v - a.v)
    .slice(0, 3)
    .map(x => x.price);
}

/** Most significant recent swing low in lookback bars */
function recentSwingLow(bars: OHLCV[], lookback = 30): number {
  const recent = bars.slice(-lookback);
  let   best   = Infinity, bestIdx = 0;
  for (let i = 1; i < recent.length - 1; i++) {
    if (recent[i].low < recent[i - 1].low && recent[i].low < recent[i + 1].low) {
      if (recent[i].low < best) { best = recent[i].low; bestIdx = i; }
    }
  }
  return bestIdx > 0 ? best : Math.min(...recent.map(b => b.low));
}

/** Check if price is near a round number (e.g., 100, 50, 200) within tolerance */
function nearRoundNumber(price: number, tol = 0.015): boolean {
  const magnitudes = [1, 5, 10, 25, 50, 100, 200, 500, 1000];
  return magnitudes.some(m => {
    const nearest = Math.round(price / m) * m;
    return nearest > 0 && Math.abs(price - nearest) / price < tol;
  });
}

/** Historical range behaviour score: fraction of time in consolidation */
function historicalRangeBehavior(bars: OHLCV[], lookback = 252): number {
  const recent    = bars.slice(-lookback);
  if (recent.length < 40) return 0.5;
  let   rangeDays = 0;
  const window    = 20;
  for (let i = window; i < recent.length; i++) {
    const slice = recent.slice(i - window, i);
    const adxV  = adx({ ...slice } as unknown as OHLCV[], 14);
    if (adxV < 22) rangeDays++;
  }
  return rangeDays / (recent.length - window);
}

function toOHLCV(series: PriceBar[]): OHLCV[] {
  return series.map(b => ({
    date:   new Date(b.date),
    open:   b.open   ?? b.close,
    high:   b.high   ?? b.close,
    low:    b.low    ?? b.close,
    close:  b.close,
    volume: b.volume ?? 0,
  }));
}

// ─────────────────────────────────────────────────────────────────────────────
// Hard filter config
// ─────────────────────────────────────────────────────────────────────────────

export interface DeltaHardFilterConfig {
  maxADX:                number;
  minRangeDays:          number;
  minDailyVolumeTL:      number;
  maxDeclineFrom52wkHigh: number;   // negative fraction, e.g. -0.40
  maxATRPercent:         number;    // fraction of price, e.g. 0.05
  minPrice:              number;
}

export const DEFAULT_DELTA_FILTERS: DeltaHardFilterConfig = {
  maxADX:                 22,
  minRangeDays:           20,
  minDailyVolumeTL:       30_000_000,
  maxDeclineFrom52wkHigh: -0.40,
  maxATRPercent:          0.05,
  minPrice:               2,
};

// ─────────────────────────────────────────────────────────────────────────────
// DELTA V2 main class
// ─────────────────────────────────────────────────────────────────────────────

export class DeltaCriteriaV2 {

  constructor(
    private readonly hardFilters: DeltaHardFilterConfig = DEFAULT_DELTA_FILTERS,
  ) {}

  // ── Convert StockData series to OHLCV ──────────────────────────────────────

  private toBars(stock: StockData): OHLCV[] {
    if (stock.series && stock.series.length >= 20) return toOHLCV(stock.series);
    return this.syntheticSidewaysBars(stock);
  }

  // ── Hard filters ─────────────────────────────────────────────────────────

  applyHardFilters(stock: StockData, bars: OHLCV[]): HardFilterResult {
    const failed: string[] = [];

    if (stock.close < this.hardFilters.minPrice) {
      failed.push(`MIN_PRICE: ${stock.close} < ${this.hardFilters.minPrice}`);
    }

    const vol20     = bars.slice(-20).reduce((s, b) => s + b.volume, 0) / 20;
    const turnover  = vol20 * stock.close;
    if (turnover < this.hardFilters.minDailyVolumeTL) {
      failed.push(`MIN_LIQUIDITY: ${(turnover / 1e6).toFixed(1)}M TL < ${(this.hardFilters.minDailyVolumeTL / 1e6)}M`);
    }

    const adxVal = stock.adx14 ?? adx(bars, 14);
    if (adxVal > this.hardFilters.maxADX) {
      failed.push(`MAX_ADX: ${adxVal.toFixed(1)} > ${this.hardFilters.maxADX} (stock is trending, not sideways)`);
    }

    const atrVal    = stock.atr14 ?? atr(bars, 14);
    const atrPct    = atrVal / stock.close;
    if (atrPct > this.hardFilters.maxATRPercent) {
      failed.push(`MAX_ATR_PCT: ${(atrPct * 100).toFixed(1)}% > ${(this.hardFilters.maxATRPercent * 100).toFixed(0)}% (too volatile)`);
    }

    const high52w = stock.high52w ?? Math.max(...bars.slice(-252).map(b => b.high));
    const declineFromHigh = (stock.close - high52w) / high52w;
    if (declineFromHigh < this.hardFilters.maxDeclineFrom52wkHigh) {
      failed.push(`FALLING_KNIFE: ${(declineFromHigh * 100).toFixed(1)}% from 52wk high (< ${(this.hardFilters.maxDeclineFrom52wkHigh * 100).toFixed(0)}%)`);
    }

    // Range days check: need at least minRangeDays of sub-ADX-22 bars
    const rangeBars = bars.slice(-this.hardFilters.minRangeDays * 2);
    const adxWindow = adx(rangeBars, 14);
    if (adxWindow > 25) {
      failed.push(`MIN_RANGE_DAYS: market been trending recently (ADX ${adxWindow.toFixed(1)} > 25)`);
    }

    return { passed: failed.length === 0, failedOn: failed };
  }

  // ── Factor 1: Range Quality (25 pts) ──────────────────────────────────────

  private scoreRangeQuality(bars: OHLCV[]): FactorScore {
    const recent20   = bars.slice(-20);
    const rangeHigh  = Math.max(...recent20.map(b => b.high));
    const rangeLow   = Math.min(...recent20.map(b => b.low));
    const rangeWidth = rangeLow > 0 ? (rangeHigh - rangeLow) / rangeLow : 0.15;
    const curPrice   = bars[bars.length - 1].close;
    const pricePos   = rangeWidth > 0 ? (curPrice - rangeLow) / (rangeHigh - rangeLow) : 0.5;
    const adxVal     = adx(bars, 14);
    const touches    = countRangeTouches(bars, rangeHigh, rangeLow, 20);

    // Optimal range width: 10–25%
    const rangeWidthScore =
      rangeWidth >= 0.10 && rangeWidth <= 0.25 ? 1.0 :
      rangeWidth >= 0.08 && rangeWidth <  0.10 ? 0.7 :
      rangeWidth >  0.25 && rangeWidth <= 0.35 ? 0.6 : 0.30;

    // Position: buy in lower 30% of range
    const positionScore =
      pricePos <= 0.30 ? 1.0 :
      pricePos <= 0.40 ? 0.7 :
      pricePos <= 0.50 ? 0.4 : 0.10;

    const adxScore =
      adxVal < 15 ? 1.0 :
      adxVal < 20 ? 0.8 :
      adxVal < 25 ? 0.5 : 0.0;

    const raw = (
      rangeWidthScore               * 0.25 +
      normalizeScore(touches, 1, 5) * 0.25 +
      positionScore                 * 0.35 +
      adxScore                      * 0.15
    );

    return {
      raw,
      weighted: +(raw * 25).toFixed(2),
      components: [
        { name: 'Range Width',        value: +(rangeWidth  * 100).toFixed(1) + '%', score: rangeWidthScore,           weight: 0.25 },
        { name: 'Boundary Touches',   value: touches,                               score: normalizeScore(touches, 1, 5), weight: 0.25 },
        { name: 'Price Position',     value: +(pricePos    * 100).toFixed(1) + '%', score: positionScore,             weight: 0.35 },
        { name: 'ADX (no-trend)',     value: +adxVal.toFixed(1),                    score: adxScore,                  weight: 0.15 },
      ],
    };
  }

  // ── Factor 2: Mean-Reversion Setup (25 pts) ────────────────────────────────

  private scoreMeanReversionSetup(bars: OHLCV[]): FactorScore {
    const curPrice  = bars[bars.length - 1].close;
    const mean20    = sma(bars, 20);
    const sd20      = stdDev(bars, 20);
    const zScore    = sd20 > 0 ? (curPrice - mean20) / sd20 : 0;
    const bb        = bollinger(bars, 20, 2);
    const percentB  = (bb.upper - bb.lower) > 0
      ? (curPrice - bb.lower) / (bb.upper - bb.lower) : 0.5;
    const rsiVal    = rsi(bars, 14);
    const stoch     = stochastic(bars, 14, 3);
    const divSignal = detectRSIDivergence(bars, 14, 10);

    // BB squeeze: compare last 5-day width vs 20-day width
    const bb5  = bollinger(bars.slice(-5),  5,  2);
    const bb20 = bollinger(bars.slice(-20), 20, 2);
    const isSqueeze = bb5.width < bb20.width * 0.80;

    // Z-Score: ideal buy zone is -2 to -1 std deviations below mean
    const zScoreScore =
      zScore <= -2.0 ? 1.0 :
      zScore <= -1.5 ? 0.8 :
      zScore <= -1.0 ? 0.6 :
      zScore <= -0.5 ? 0.3 : 0.1;

    // %B: near lower band = oversold within range
    const bbScore =
      percentB <= 0.10 ? 1.0 :
      percentB <= 0.20 ? 0.8 :
      percentB <= 0.30 ? 0.5 : 0.2;

    // Stochastic: bullish cross from oversold
    const stochBullCross = stoch.k > stoch.d && stoch.kPrev <= stoch.d && stoch.k < 30;
    const stochScore     =
      stochBullCross          ? 1.0 :
      stoch.k < 20            ? 0.7 :
      stoch.k < 30            ? 0.5 : 0.2;

    // RSI not crashing (avoid freefall)
    const rsiScore =
      rsiVal >= 30 && rsiVal <= 45 ? 1.0 :
      rsiVal >= 25 && rsiVal <  30 ? 0.7 :
      rsiVal >= 45 && rsiVal <= 55 ? 0.5 : 0.2;

    const raw = (
      zScoreScore           * 0.30 +
      bbScore               * 0.25 +
      (isSqueeze ? 1 : 0.4) * 0.15 +
      (divSignal ? 1 : 0.3) * 0.15 +
      stochScore            * 0.15
    );

    return {
      raw,
      weighted: +(raw * 25).toFixed(2),
      components: [
        { name: 'Z-Score (2sd below)',    value: +zScore.toFixed(2),                          score: zScoreScore,        weight: 0.30 },
        { name: 'Bollinger %B',           value: +(percentB * 100).toFixed(1) + '%',           score: bbScore,            weight: 0.25 },
        { name: 'BB Squeeze',             value: isSqueeze ? 'YES' : 'NO',                     score: isSqueeze ? 1 : 0.4, weight: 0.15 },
        { name: 'RSI Bullish Divergence', value: divSignal  ? 'YES' : 'NO',                    score: divSignal  ? 1 : 0.3, weight: 0.15 },
        { name: 'Stochastic Bull Cross',  value: `K=${stoch.k.toFixed(1)} D=${stoch.d.toFixed(1)}`, score: stochScore,  weight: 0.15 },
        { name: 'RSI Level',              value: +rsiVal.toFixed(1),                           score: rsiScore,           weight: 0.00 },
      ],
    };
  }

  // ── Factor 3: Support Confluence (20 pts) ─────────────────────────────────

  private scoreSupportConfluence(bars: OHLCV[], stock: StockData): FactorScore {
    const curPrice = bars[bars.length - 1].close;
    const tol      = 0.020;   // 2% proximity

    const fibs     = fibonacciLevels(bars, 60);
    const nearFib  = fibs.some(f => Math.abs(curPrice - f) / curPrice < tol);

    const hvnLevels = volumeProfileNodes(bars, 60);
    const nearHVN   = hvnLevels.some(h => Math.abs(curPrice - h) / curPrice < tol);

    const swingLo       = recentSwingLow(bars, 30);
    const nearSwingLow  = Math.abs(curPrice - swingLo) / curPrice < tol;

    const nearRound     = nearRoundNumber(curPrice, 0.015);

    const ema50Val      = stock.ema50  ?? ema(bars, 50);
    const sma200Val     = stock.sma200 ?? sma(bars, 200);
    const nearEMA50     = Math.abs(curPrice - ema50Val)  / curPrice < tol;
    const nearSMA200    = Math.abs(curPrice - sma200Val) / curPrice < tol;
    const nearMA        = nearEMA50 || nearSMA200;

    const count = [nearFib, nearHVN, nearSwingLow, nearRound, nearMA].filter(Boolean).length;

    const raw = normalizeScore(count, 0, 4);

    return {
      raw,
      weighted: +(raw * 20).toFixed(2),
      components: [
        { name: 'Fibonacci Level',    value: nearFib      ? 'YES' : 'NO', score: nearFib      ? 1 : 0, weight: 0.20 },
        { name: 'Volume Profile HVN', value: nearHVN      ? 'YES' : 'NO', score: nearHVN      ? 1 : 0, weight: 0.20 },
        { name: 'Swing Low Support',  value: nearSwingLow ? 'YES' : 'NO', score: nearSwingLow ? 1 : 0, weight: 0.25 },
        { name: 'Round Number',       value: nearRound    ? 'YES' : 'NO', score: nearRound    ? 1 : 0, weight: 0.15 },
        { name: 'MA Support',         value: nearMA       ? 'YES' : 'NO', score: nearMA       ? 1 : 0, weight: 0.20 },
        { name: 'Confluence Count',   value: `${count}/5`,                score: raw,                  weight: 0.00 },
      ],
    };
  }

  // ── Factor 4: Fundamental Floor (15 pts) ──────────────────────────────────

  private scoreFundamentalFloor(stock: StockData): FactorScore {
    const pb   = stock.pb  ?? 2.0;
    const pe   = stock.pe  ?? 15;
    const rfr  = stock.market === 'US' ? 0.053 : 0.42;

    // P/B: below book value = strong floor
    const pbScore =
      pb < 1.0 ? 1.0 :
      pb < 1.5 ? 0.8 :
      pb < 2.0 ? 0.6 :
      pb < 3.0 ? 0.4 : 0.2;

    // Earnings yield vs risk-free rate
    const earningsYield  = pe > 0 ? 1 / pe : 0;
    const excessYield    = earningsYield - rfr;
    const eyScore        = normalizeScore(excessYield, -0.02, 0.10);

    // FCF as proxy for cash richness
    const fcf       = stock.freeCashFlow ?? 0;
    const cashScore = fcf > 0 ? normalizeScore(fcf / (stock.marketCap || 1), 0, 0.12) : 0;

    // Dividend yield provides income floor in sideways market
    const divY      = (stock.dividendYield ?? 0) / 100;
    const divScore  = normalizeScore(divY, 0, 0.06);

    const raw = (
      pbScore   * 0.35 +
      eyScore   * 0.30 +
      cashScore * 0.20 +
      divScore  * 0.15
    );

    return {
      raw,
      weighted: +(raw * 15).toFixed(2),
      components: [
        { name: 'P/B Ratio',          value: +pb.toFixed(2),                           score: pbScore,   weight: 0.35 },
        { name: 'Earnings Yield',     value: +(earningsYield * 100).toFixed(1) + '%',  score: eyScore,   weight: 0.30 },
        { name: 'FCF Yield',          value: fcf > 0 ? 'Positive' : 'Negative',        score: cashScore, weight: 0.20 },
        { name: 'Dividend Yield',     value: +(divY * 100).toFixed(2) + '%',           score: divScore,  weight: 0.15 },
      ],
    };
  }

  // ── Factor 5: Low Event Risk (10 pts) ─────────────────────────────────────

  private scoreLowEventRisk(stock: StockData, bars: OHLCV[]): FactorScore {
    // Historical range consistency (fraction of trading days in range-bound regime)
    const rangeConsistency = historicalRangeBehavior(bars, Math.min(bars.length, 252));

    // Volatility regime: prefer low-volatility environment
    const hvVol  = historicalVol(bars, 20);
    const volScore = normalizeScore(1 - hvVol, 0.5, 0.85); // lower vol = higher score

    // Low beta = less driven by market noise
    const betaScore = stock.beta != null
      ? normalizeScore(1 - stock.beta, 0.1, 0.8)
      : 0.5;

    // Price stability: small ATR relative to range
    const atrVal    = stock.atr14 ?? atr(bars, 14);
    const recent20  = bars.slice(-20);
    const rHigh     = Math.max(...recent20.map(b => b.high));
    const rLow      = Math.min(...recent20.map(b => b.low));
    const rangeW    = rLow > 0 ? (rHigh - rLow) / rLow : 0.15;
    const atrRangeRatio = rangeW > 0 ? (atrVal / stock.close) / rangeW : 1;
    const atrScore  = normalizeScore(1 - atrRangeRatio, 0, 0.6);

    const raw = (
      normalizeScore(rangeConsistency, 0.3, 0.8) * 0.40 +
      volScore                                    * 0.30 +
      betaScore                                   * 0.15 +
      atrScore                                    * 0.15
    );

    return {
      raw,
      weighted: +(raw * 10).toFixed(2),
      components: [
        { name: 'Range Consistency',  value: +(rangeConsistency * 100).toFixed(1) + '%', score: normalizeScore(rangeConsistency, 0.3, 0.8), weight: 0.40 },
        { name: 'Low Volatility',     value: +(hvVol * 100).toFixed(1) + '%',            score: volScore,                                   weight: 0.30 },
        { name: 'Low Beta',           value: +(stock.beta ?? 1).toFixed(2),              score: betaScore,                                  weight: 0.15 },
        { name: 'ATR/Range Ratio',    value: +atrRangeRatio.toFixed(2),                  score: atrScore,                                   weight: 0.15 },
      ],
    };
  }

  // ── Factor 6: Volatility Timing (5 pts) ───────────────────────────────────

  private scoreVolatilityTiming(bars: OHLCV[]): FactorScore {
    const hvVol       = historicalVol(bars, 20);
    const volPct      = volPercentile(bars, Math.min(bars.length, 252));

    // Implied Vol proxy: use short-term HV vs long-term HV as IV/HV surrogate
    const hvShort  = historicalVol(bars, 10);
    const hvLong   = historicalVol(bars, 30);
    const ivHvProxy = hvLong > 0 ? hvShort / hvLong : 1;

    const ivScore  = ivHvProxy < 0.8 ? 1.0 : ivHvProxy < 1.0 ? 0.7 : 0.3;

    // Low vol percentile = quiet stock = range-trading friendly
    const volPctScore = normalizeScore(1 - volPct, 0.3, 0.8);

    const raw = ivScore * 0.5 + volPctScore * 0.5;

    return {
      raw,
      weighted: +(raw * 5).toFixed(2),
      components: [
        { name: 'Short/Long HV Ratio', value: +ivHvProxy.toFixed(2),        score: ivScore,     weight: 0.50 },
        { name: 'Vol Percentile',      value: +(volPct * 100).toFixed(1)+'%', score: volPctScore, weight: 0.50 },
        { name: 'HV (20d annualised)', value: +(hvVol * 100).toFixed(1)+'%', score: 0,           weight: 0.00 },
      ],
    };
  }

  // ── Trade plan: range-based entry / take-profit / stop ────────────────────

  buildTradePlan(bars: OHLCV[], entryPrice: number): TakeProfitConfig {
    const recent20  = bars.slice(-20);
    const rangeHigh = Math.max(...recent20.map(b => b.high));
    const rangeLow  = Math.min(...recent20.map(b => b.low));
    const rangeW    = rangeHigh - rangeLow;

    return {
      target1:     +(entryPrice + rangeW * 0.50).toFixed(4),     // half-position at midpoint
      target2:     +(rangeHigh * 0.97).toFixed(4),               // rest near range top
      stopLoss:    +(rangeLow  * 0.985).toFixed(4),              // just below range low
      maxHoldDays: 15,
      rangeHigh,
      rangeLow,
      rangeWidth:  rangeLow > 0 ? rangeW / rangeLow : 0,
    };
  }

  // ── Master scoring ────────────────────────────────────────────────────────

  score(stock: StockData): DeltaV2Score {
    const bars       = this.toBars(stock);
    const hardResult = this.applyHardFilters(stock, bars);

    const f1 = this.scoreRangeQuality(bars);
    const f2 = this.scoreMeanReversionSetup(bars);
    const f3 = this.scoreSupportConfluence(bars, stock);
    const f4 = this.scoreFundamentalFloor(stock);
    const f5 = this.scoreLowEventRisk(stock, bars);
    const f6 = this.scoreVolatilityTiming(bars);

    let total = f1.weighted + f2.weighted + f3.weighted + f4.weighted + f5.weighted + f6.weighted;
    if (!hardResult.passed) total = Math.min(total, 30);
    total = Math.max(0, Math.min(100, total));

    const entryPrice = stock.close;
    const tradePlan  = this.buildTradePlan(bars, entryPrice);
    const stopLoss   = tradePlan.stopLoss;
    const stopPct    = (entryPrice - stopLoss) / entryPrice;
    const target     = tradePlan.target2;
    const rrRatio    = stopPct > 0 ? (target / entryPrice - 1) / stopPct : 0;

    // Signals
    const passed: string[]   = [];
    const failed: string[]   = [];
    const warnings: string[] = [];

    if (hardResult.passed) passed.push('Hard filters: ALL PASSED');
    else hardResult.failedOn.forEach(f => failed.push(f));

    const factorMap: [FactorScore, string][] = [
      [f1, 'Range Quality'],
      [f2, 'Mean-Reversion Setup'],
      [f3, 'Support Confluence'],
      [f4, 'Fundamental Floor'],
      [f5, 'Low Event Risk'],
      [f6, 'Volatility Timing'],
    ];
    for (const [f, label] of factorMap) {
      if (f.raw >= 0.65)     passed.push(label);
      else if (f.raw < 0.35) failed.push(label);
      else                   warnings.push(label);
    }

    const grade: DeltaV2Score['grade'] =
      total >= 85 ? 'A+'
      : total >= 75 ? 'A'
      : total >= 65 ? 'B'
      : total >= 50 ? 'C'
      : total >= 35 ? 'D'
      : 'F';

    return {
      total:            +total.toFixed(2),
      grade,
      hardFilterPassed: hardResult.passed,
      hardFilterResult: hardResult,
      factors: {
        rangeQuality:       f1,
        meanReversionSetup: f2,
        supportConfluence:  f3,
        fundamentalFloor:   f4,
        lowEventRisk:       f5,
        volatilityTiming:   f6,
      },
      tradePlan,
      stopLoss,
      stopPercent:     +stopPct.toFixed(4),
      targetPrice:     target,
      riskRewardRatio: +rrRatio.toFixed(2),
      signals:         { passed, failed, warnings },
    };
  }

  // ── Synthetic sideways bars (low ADX, mean-reverting drift) ──────────────

  private syntheticSidewaysBars(stock: StockData): OHLCV[] {
    const seed  = stock.close;
    const range = seed * 0.15;   // simulate ±7.5% channel
    const bars: OHLCV[] = [];
    let   price = seed + (Math.random() - 0.5) * range;
    const vol   = (stock.vol20Avg ?? 300_000);

    for (let i = 0; i < 252; i++) {
      // Mean-reverting force: pull toward seed
      const reversion = (seed - price) * 0.03;
      const noise     = (Math.random() - 0.5) * seed * 0.012;
      price += reversion + noise;
      const spread = price * 0.010;
      bars.push({
        date:   new Date(Date.now() - (252 - i) * 86_400_000),
        open:   +(price * (1 - 0.002)).toFixed(4),
        high:   +(price + spread).toFixed(4),
        low:    +(price - spread).toFixed(4),
        close:  +price.toFixed(4),
        volume: Math.round(vol * (0.5 + Math.random() * 0.8)),
      });
    }
    bars[bars.length - 1] = {
      ...bars[bars.length - 1],
      close: stock.close,
      open:  stock.open ?? stock.close,
      high:  stock.high ?? stock.close * 1.01,
      low:   stock.low  ?? stock.close * 0.99,
    };
    return bars;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Singleton + drop-in scorer
// ─────────────────────────────────────────────────────────────────────────────

export const deltaCriteriaV2 = new DeltaCriteriaV2();

/** Drop-in replacement for old DELTA scoring — returns 0–100 */
export function scoreDeltaV2(stock: StockData): number {
  return deltaCriteriaV2.score(stock).total;
}
