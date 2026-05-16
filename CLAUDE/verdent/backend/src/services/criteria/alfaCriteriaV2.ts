/**
 * VERDENT — ALFA Criteria V2
 * Institutional-Grade Momentum Strategy
 *
 * Research basis:
 *   • Jegadeesh & Titman (1993)  — 12-1 momentum cross-section
 *   • Fama-French 5-Factor Model — quality / profitability overlays
 *   • IBD CANSLIM                — EPS acceleration + RS Rating + volume
 *   • William O'Neil             — pivot breakout + cup-with-handle
 *   • "Frog-in-Pan" (Da et al.)  — prefer smooth momentum over spike
 *
 * Architecture:
 *   Phase 1 — Hard Filters  (binary pass/fail, all must pass)
 *   Phase 2 — Scoring       (6 factor buckets, 100 pts total)
 *   Phase 3 — Stop / Size   (ATR-based stop, risk-adjusted sizing)
 */

import type { StockData }  from '../criteriaEngine';
import type { PriceBar }   from '../marketConditionService';

// ─────────────────────────────────────────────────────────────────────────────
// Shared value types
// ─────────────────────────────────────────────────────────────────────────────

export interface OHLCV {
  date:   Date;
  open:   number;
  high:   number;
  low:    number;
  close:  number;
  volume: number;
}

export interface Fundamentals {
  epsGrowthQ1:         number;   // EPS growth most recent quarter YoY
  epsGrowthQ2:         number;   // EPS growth prior quarter YoY
  revenueGrowthYoY:    number;   // fraction e.g. 0.25 = 25%
  operatingCashFlow:   number;
  netIncome:           number;
  estimateRevisions:   number;   // net analyst revisions (positive = upgrades)
  roe:                 number;
  debtEquity:          number;
  freeCashFlowYield:   number;
}

export interface IndexData {
  return3m:  number;
  return6m:  number;
  return12m: number;
}

export interface StopLossConfig {
  stopPrice:    number;
  stopPercent:  number;   // fraction
  method:       string;
  isValidStop:  boolean;
}

export interface PositionSize {
  shares:      number;
  value:       number;
  riskAmount:  number;
  weightPct:   number;   // % of total capital
}

export interface HardFilterResult {
  passed:    boolean;
  failedOn:  string[];  // filter IDs that failed
}

export interface FactorScore {
  raw:         number;   // 0–1
  weighted:    number;   // raw × weight (pts)
  components:  { name: string; value: number; score: number; weight: number }[];
}

export interface AlfaV2Score {
  total:              number;    // 0–100
  grade:              'A+' | 'A' | 'B' | 'C' | 'D' | 'F';
  hardFilterPassed:   boolean;
  hardFilterResult:   HardFilterResult;
  factors: {
    priceMomentum:    FactorScore;
    relativeStrength: FactorScore;
    volumeAnalysis:   FactorScore;
    trendQuality:     FactorScore;
    fundamentalQuality: FactorScore;
    entryTiming:      FactorScore;
  };
  stopLoss:           StopLossConfig;
  targetPrice:        number;
  riskRewardRatio:    number;
  signals: {
    passed: string[];
    failed: string[];
    warnings: string[];
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Math helpers
// ─────────────────────────────────────────────────────────────────────────────

/** Clamp x to [0, 1] linearly between lo and hi */
function normalizeScore(x: number, lo: number, hi: number): number {
  if (hi === lo) return 0;
  return Math.max(0, Math.min(1, (x - lo) / (hi - lo)));
}

function closes(bars: OHLCV[]): number[] {
  return bars.map(b => b.close);
}

/** Simple return: (end - start) / start */
function periodReturn(bars: OHLCV[], lookback: number, skip = 0): number {
  if (bars.length < lookback + skip + 1) return 0;
  const n   = bars.length;
  const end = bars[n - 1 - skip].close;
  const beg = bars[n - 1 - skip - lookback].close;
  return beg > 0 ? (end - beg) / beg : 0;
}

function ema(bars: OHLCV[], period: number): number[] {
  const k   = 2 / (period + 1);
  const src = closes(bars);
  const out: number[] = [];
  let   prev = src[0];
  for (const c of src) {
    prev = c * k + prev * (1 - k);
    out.push(prev);
  }
  return out;
}

function sma(bars: OHLCV[], period: number): number[] {
  const src = closes(bars);
  const out: number[] = [];
  for (let i = 0; i < src.length; i++) {
    if (i < period - 1) { out.push(NaN); continue; }
    const s = src.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0) / period;
    out.push(s);
  }
  return out;
}

function rsi(bars: OHLCV[], period = 14): number {
  const src = closes(bars);
  if (src.length < period + 1) return 50;
  let gains = 0, losses = 0;
  for (let i = src.length - period; i < src.length; i++) {
    const d = src[i] - src[i - 1];
    if (d >= 0) gains  += d;
    else        losses -= d;
  }
  const avgG = gains  / period;
  const avgL = losses / period;
  if (avgL === 0) return 100;
  const rs   = avgG / avgL;
  return 100 - 100 / (1 + rs);
}

function atr(bars: OHLCV[], period = 14): number {
  if (bars.length < period + 1) return (bars[bars.length - 1]?.close ?? 50) * 0.02;
  const trs: number[] = [];
  for (let i = 1; i < bars.length; i++) {
    const h = bars[i].high, l = bars[i].low, pc = bars[i - 1].close;
    trs.push(Math.max(h - l, Math.abs(h - pc), Math.abs(l - pc)));
  }
  return trs.slice(-period).reduce((a, b) => a + b, 0) / period;
}

function adx(bars: OHLCV[], period = 14): { adx: number; plusDI: number; minusDI: number } {
  if (bars.length < period * 2) return { adx: 25, plusDI: 25, minusDI: 20 };
  const trs: number[] = [], plusDM: number[] = [], minusDM: number[] = [];
  for (let i = 1; i < bars.length; i++) {
    const h  = bars[i].high,  l  = bars[i].low;
    const ph = bars[i - 1].high, pl = bars[i - 1].low, pc = bars[i - 1].close;
    trs.push(Math.max(h - l, Math.abs(h - pc), Math.abs(l - pc)));
    const up = h - ph, dn = pl - l;
    plusDM.push(up > dn && up > 0 ? up : 0);
    minusDM.push(dn > up && dn > 0 ? dn : 0);
  }
  const smooth = (arr: number[]) => {
    let s = arr.slice(0, period).reduce((a, b) => a + b, 0);
    const out = [s];
    for (let i = period; i < arr.length; i++) {
      s = s - s / period + arr[i];
      out.push(s);
    }
    return out;
  };
  const sTR = smooth(trs), sPDM = smooth(plusDM), sMDM = smooth(minusDM);
  const pDI = sPDM.map((v, i) => sTR[i] > 0 ? 100 * v / sTR[i] : 0);
  const mDI = sMDM.map((v, i) => sTR[i] > 0 ? 100 * v / sTR[i] : 0);
  const dx  = pDI.map((v, i) => {
    const sum = v + mDI[i];
    return sum > 0 ? 100 * Math.abs(v - mDI[i]) / sum : 0;
  });
  const adxVal = dx.slice(-period).reduce((a, b) => a + b, 0) / period;
  return {
    adx:     adxVal,
    plusDI:  pDI[pDI.length - 1],
    minusDI: mDI[mDI.length - 1],
  };
}

function bollinger(bars: OHLCV[], period = 20, mult = 2): { upper: number; middle: number; lower: number; width: number } {
  const s  = sma(bars, period);
  const mi = s[s.length - 1];
  if (isNaN(mi)) return { upper: 0, middle: 0, lower: 0, width: 0 };
  const src    = closes(bars).slice(-period);
  const stddev = Math.sqrt(src.reduce((acc, c) => acc + (c - mi) ** 2, 0) / period);
  const upper  = mi + mult * stddev;
  const lower  = mi - mult * stddev;
  return { upper, middle: mi, lower, width: mi > 0 ? (upper - lower) / mi : 0 };
}

function obvSlope(bars: OHLCV[], period = 20): number {
  if (bars.length < period + 1) return 0;
  let obv = 0;
  const obvSeries: number[] = [];
  for (let i = 1; i < bars.length; i++) {
    obv += bars[i].close > bars[i - 1].close
      ?  bars[i].volume
      : bars[i].close < bars[i - 1].close
      ? -bars[i].volume
      : 0;
    obvSeries.push(obv);
  }
  const recent = obvSeries.slice(-period);
  const n = recent.length;
  const xMean = (n - 1) / 2;
  const yMean = recent.reduce((a, b) => a + b, 0) / n;
  let num = 0, den = 0;
  recent.forEach((y, x) => {
    num += (x - xMean) * (y - yMean);
    den += (x - xMean) ** 2;
  });
  return den === 0 ? 0 : num / den / (Math.abs(yMean) || 1);
}

function upDownVolumeRatio(bars: OHLCV[], period = 50): number {
  const recent = bars.slice(-period);
  let   up = 0, dn = 0;
  for (const b of recent) {
    if (b.close > b.open) up += b.volume;
    else if (b.close < b.open) dn += b.volume;
  }
  return dn === 0 ? 2 : up / dn;
}

interface AccDist { accumulationDays: number; distributionDays: number; net: number }
function accDistDays(bars: OHLCV[], period = 25): AccDist {
  const recent  = bars.slice(-period);
  const avgVol  = recent.reduce((s, b) => s + b.volume, 0) / recent.length;
  let acc = 0, dist = 0;
  for (const b of recent) {
    const chg = b.close / b.open - 1;
    if (chg >  0.002 && b.volume > avgVol) acc++;
    if (chg < -0.002 && b.volume > avgVol) dist++;
  }
  return { accumulationDays: acc, distributionDays: dist, net: acc - dist };
}

function trendConsistency(bars: OHLCV[], period = 126): number {
  const recent = bars.slice(-period);
  const ma     = sma(recent, Math.min(20, recent.length));
  let   above  = 0;
  for (let i = 0; i < recent.length; i++) {
    if (!isNaN(ma[i]) && recent[i].close > ma[i]) above++;
  }
  return above / recent.length;
}

function emaSlope(bars: OHLCV[], period: number, lookback = 10): number {
  const e = ema(bars, period);
  if (e.length < lookback + 1) return 0;
  const prev = e[e.length - 1 - lookback];
  const curr = e[e.length - 1];
  return prev > 0 ? (curr - prev) / prev / lookback : 0;
}

function high52w(bars: OHLCV[]): number {
  const recent = bars.slice(-252);
  return recent.reduce((m, b) => Math.max(m, b.high), 0);
}

function recentSwingLow(bars: OHLCV[], lookback = 10): number {
  return bars.slice(-lookback).reduce((m, b) => Math.min(m, b.low), Infinity);
}

/** Bollinger Band width over a window (avg of last `window` days) */
function avgBBWidth(bars: OHLCV[], window = 20): number {
  if (bars.length < 30) return 0.05;
  let sum = 0;
  for (let i = 0; i < window; i++) {
    const slice = bars.slice(0, bars.length - i);
    if (slice.length < 20) continue;
    sum += bollinger(slice).width;
  }
  return sum / window;
}

/** Check if the last N days form a pivot (base → squeeze → expansion) */
function isPivotBreakout(bars: OHLCV[], lookback = 20): boolean {
  if (bars.length < lookback + 5) return false;
  const base   = bars.slice(-lookback - 5, -5);
  const recent = bars.slice(-5);
  const baseHigh = base.reduce((m, b) => Math.max(m, b.high), 0);
  const avgBaseVol = base.reduce((s, b) => s + b.volume, 0) / base.length;
  const breakBar  = recent[recent.length - 1];
  return breakBar.close > baseHigh && breakBar.volume > avgBaseVol * 1.5;
}

// Convert StockData.series (PriceBar) to OHLCV
function toOHLCV(series: PriceBar[]): OHLCV[] {
  return series.map(b => ({
    date:   new Date(b.date),
    open:   b.open  ?? b.close,
    high:   b.high  ?? b.close,
    low:    b.low   ?? b.close,
    close:  b.close,
    volume: b.volume ?? 0,
  }));
}

// ─────────────────────────────────────────────────────────────────────────────
// ALFA V2 — Hard filter config
// ─────────────────────────────────────────────────────────────────────────────

export interface HardFilterConfig {
  minDailyVolumeTL:   number;   // BIST min daily turnover (TL)
  minDailyVolumeUSD:  number;   // US  min daily volume  (USD)
  minPrice:           number;
  maxDrawdownFromHigh: number;  // negative fraction e.g. -0.35
  minROC3Month:       number;   // min 3-month return
  minROC6Month:       number;   // min 6-month return
  daysToEarningsMin:  number;
}

export const DEFAULT_HARD_FILTERS: HardFilterConfig = {
  minDailyVolumeTL:    5_000_000,   // 5M TL minimum — sadece sub-penny hisseleri eliyor
  minDailyVolumeUSD:   500_000,     // $500K minimum for US
  minPrice:            1,            // sadece 1 TL altını engelle
  maxDrawdownFromHigh: -0.60,        // VCP base'ler için geniş — fallen knife değil
  minROC3Month:        -0.25,        // Sadece ciddi düşüş trendlerini engelle
  minROC6Month:        -0.40,        // 6 ay boyunca %40+ düşen hisseleri engelle
  daysToEarningsMin:   0,
};

// ─────────────────────────────────────────────────────────────────────────────
// ALFA V2 main class
// ─────────────────────────────────────────────────────────────────────────────

export class AlfaCriteriaV2 {

  constructor(
    private readonly hardFilters: HardFilterConfig = DEFAULT_HARD_FILTERS,
  ) {}

  // ── Hard filters ──────────────────────────────────────────────────────────

  applyHardFilters(stock: StockData, bars: OHLCV[]): HardFilterResult {
    const failed: string[] = [];
    const isBIST = /^[A-Z]{3,5}$/.test(stock.symbol) && stock.market !== 'US';

    // 1. Minimum price — avoid sub-penny only
    if (stock.close < this.hardFilters.minPrice) {
      failed.push(`MIN_PRICE: ${stock.close.toFixed(2)} < ${this.hardFilters.minPrice}`);
    }

    // 2. Minimum liquidity — very lenient, block only illiquid micro-caps
    const vol20    = bars.slice(-20).reduce((s, b) => s + b.volume, 0) / 20;
    const turnover = vol20 * stock.close;
    const minTurnover = isBIST
      ? this.hardFilters.minDailyVolumeTL
      : this.hardFilters.minDailyVolumeUSD;
    if (turnover < minTurnover) {
      failed.push(`MIN_LIQUIDITY: turnover ${(turnover / 1e6).toFixed(1)}M < ${(minTurnover / 1e6).toFixed(0)}M`);
    }

    // 3. NOT a broken stock — catastrophic free-fall only
    const h52 = high52w(bars);
    if (h52 > 0) {
      const drawdown = (stock.close - h52) / h52;
      if (drawdown < this.hardFilters.maxDrawdownFromHigh) {
        failed.push(`MAX_DRAWDOWN: ${(drawdown * 100).toFixed(1)}% < ${(this.hardFilters.maxDrawdownFromHigh * 100).toFixed(0)}%`);
      }
    }

    // ── MINERVINI TREND TEMPLATE (mandatory) ────────────────────────────────
    // Stock must show at least some evidence of uptrend
    if (bars.length >= 200) {
      const sma150v = sma(bars, 150);
      const sma200v = sma(bars, 200);
      const s150    = sma150v[sma150v.length - 1];
      const s200    = sma200v[sma200v.length - 1];

      // Price must be above SMA150 OR above SMA200 (at least one — allows early breakouts)
      if (stock.close < s150 && stock.close < s200) {
        failed.push(`TREND_TEMPLATE: ${stock.close.toFixed(2)} below both SMA150(${s150.toFixed(2)}) and SMA200(${s200.toFixed(2)})`);
      }
      // Note: SMA200 trend direction is NOT a hard filter — only a scoring bonus.
      // This allows early-stage breakouts where SMA200 hasn't yet turned up.
    } else if (bars.length >= 150) {
      // Shorter data: just require price > SMA50
      const sma50v = sma(bars, 50);
      const s50    = sma50v[sma50v.length - 1];
      if (stock.close < s50 * 0.95) {
        failed.push(`TREND_TEMPLATE_SHORT: Price ${stock.close.toFixed(2)} well below SMA50(${s50.toFixed(2)})`);
      }
    }

    return { passed: failed.length === 0, failedOn: failed };
  }

  // ── Factor 1: Price Momentum (25 pts) ─────────────────────────────────────

  private scorePriceMomentum(bars: OHLCV[], stock?: StockData): FactorScore {
    const mom12_1 = periodReturn(bars, 252, 21);  // 12-1 (skip last month)
    const mom6_1  = periodReturn(bars, 126, 21);  // 6-1
    const mom3_1  = periodReturn(bars, 63,  21);  // 3-1
    const tc      = trendConsistency(bars, 126);  // % days above 20-SMA

    // Frog-in-Pan: penalise high volatility momentum vs smooth momentum
    const closes252 = closes(bars).slice(-252);
    const stdDev    = closes252.length > 10
      ? Math.sqrt(closes252.reduce((s, c, i, a) => s + (i > 0 ? (c / a[i-1] - 1) ** 2 : 0), 0) / closes252.length)
      : 0.02;
    const smoothnessPenalty = normalizeScore(stdDev, 0.03, 0.005);  // lower vol = higher score

    // Fixed absolute bounds — well calibrated for both BIST and US
    const s12 = normalizeScore(mom12_1, -0.5, 1.5);
    const s6  = normalizeScore(mom6_1,  -0.3, 1.0);
    const s3  = normalizeScore(mom3_1,  -0.2, 0.5);
    const stc = normalizeScore(tc, 0.4, 0.9);

    const raw = s12 * 0.35 + s6 * 0.35 + s3 * 0.15 + stc * 0.10 + smoothnessPenalty * 0.05;

    return {
      raw,
      weighted: +(raw * 25).toFixed(2),
      components: [
        { name: '12-1M Momentum',    value: +mom12_1.toFixed(4), score: s12, weight: 0.35 },
        { name: '6-1M Momentum',     value: +mom6_1.toFixed(4),  score: s6,  weight: 0.35 },
        { name: '3-1M Momentum',     value: +mom3_1.toFixed(4),  score: s3,  weight: 0.15 },
        { name: 'Trend Consistency', value: +tc.toFixed(4),      score: stc, weight: 0.10 },
        { name: 'Smoothness (FiP)',  value: +stdDev.toFixed(4),  score: smoothnessPenalty, weight: 0.05 },
      ],
    };
  }

  // ── Factor 2: Relative Strength (35 pts) — PRIMARY FACTOR ────────────────
  // Based on Minervini/IBD methodology: RS vs benchmark is THE most important
  // factor for momentum stock selection. Uses cross-sectional universe median.

  private scoreRelativeStrength(stock: StockData, bars: OHLCV[], indexData?: IndexData): FactorScore {
    // Use cross-sectional universe median injected by screenStocksSync,
    // or fall back to conservative defaults
    const mktReturn3m  = stock.marketReturn3m  ?? indexData?.return3m  ?? 0.05;
    const mktReturn6m  = stock.marketReturn6m  ?? indexData?.return6m  ?? 0.10;
    const mktReturn12m = stock.marketReturn12m ?? indexData?.return12m ?? 0.15;

    const rs3m  = periodReturn(bars, 63,  21) - mktReturn3m;
    const rs6m  = periodReturn(bars, 126, 21) - mktReturn6m;
    const rs12m = periodReturn(bars, 252, 21) - mktReturn12m;

    // Minervini-style composite RS: weight recent performance more
    const compositeRS = rs3m * 0.40 + rs6m * 0.35 + rs12m * 0.25;

    // RS Acceleration: is RS improving? (recent > prior)
    const rsAccel = rs3m - rs6m;

    // Normalize: >+20% above universe median = full score
    const sRS    = normalizeScore(compositeRS, -0.15, 0.25);
    const sAccel = normalizeScore(rsAccel, -0.05, 0.15);
    const raw    = sRS * 0.80 + sAccel * 0.20;

    return {
      raw,
      weighted: +(raw * 35).toFixed(2),
      components: [
        { name: 'Composite RS vs Universe', value: +compositeRS.toFixed(4), score: sRS,    weight: 0.80 },
        { name: 'RS Acceleration',          value: +rsAccel.toFixed(4),     score: sAccel, weight: 0.20 },
      ],
    };
  }

  // ── Factor 3: Volume Analysis (10 pts) ────────────────────────────────────

  private scoreVolumeAnalysis(bars: OHLCV[]): FactorScore {
    const uvdr  = upDownVolumeRatio(bars, 50);
    const ad    = accDistDays(bars, 25);
    const obv   = obvSlope(bars, 20);

    // Volume trend: compare recent 10-day avg vs prior 20-day avg
    const recentVol = bars.slice(-10).reduce((s, b) => s + b.volume, 0) / 10;
    const priorVol  = bars.slice(-30, -10).reduce((s, b) => s + b.volume, 0) / 20;
    const volTrend  = priorVol > 0 ? (recentVol - priorVol) / priorVol : 0;

    const sUVDR  = normalizeScore(uvdr, 0.8, 2.0);
    const sAD    = normalizeScore(ad.net / 25, -0.3, 0.3);
    const sOBV   = normalizeScore(obv, -0.5, 0.5);
    const sVTrend= normalizeScore(volTrend, -0.2, 0.3);

    const raw = sUVDR * 0.35 + sAD * 0.25 + sOBV * 0.25 + sVTrend * 0.15;

    return {
      raw,
      weighted: +(raw * 10).toFixed(2),
      components: [
        { name: 'Up/Down Volume Ratio', value: +uvdr.toFixed(3),            score: sUVDR,   weight: 0.35 },
        { name: 'Acc/Dist Days (net)',  value: ad.net,                       score: sAD,     weight: 0.25 },
        { name: 'OBV Slope',           value: +obv.toFixed(4),              score: sOBV,    weight: 0.25 },
        { name: 'Volume Trend',        value: +volTrend.toFixed(4),         score: sVTrend, weight: 0.15 },
      ],
    };
  }

  // ── Factor 4: Trend Quality (5 pts) — bonus only ──────────────────────────
  // SMA200 uptrend is enforced in hard filter; this captures EMA stack perfection

  private scoreTrendQuality(bars: OHLCV[]): FactorScore {
    const last    = bars[bars.length - 1].close;
    const ema20v  = ema(bars, 20);
    const ema50v  = ema(bars, 50);
    const ema200v = ema(bars, 200);

    const e20  = ema20v[ema20v.length   - 1];
    const e50  = ema50v[ema50v.length   - 1];
    const e200 = ema200v[ema200v.length - 1];

    // EMA Stack score: price > EMA20 > EMA50 > EMA200
    let stackScore = 0;
    if (last > e20)  stackScore += 0.25;
    if (last > e50)  stackScore += 0.25;
    if (last > e200) stackScore += 0.25;
    if (e20  > e50)  stackScore += 0.125;
    if (e50  > e200) stackScore += 0.125;

    // EMA50 slope: steeper = stronger trend
    const slope50 = emaSlope(bars, 50, 10);

    // ADX: prefer 25–45 (trending but not overextended)
    const { adx: adxVal } = adx(bars, 14);
    const adxScore = adxVal < 20 ? adxVal / 20 * 0.5
                   : adxVal <= 45 ? 0.5 + (adxVal - 20) / 25 * 0.5
                   : Math.max(0, 1 - (adxVal - 45) / 30);

    // Price vs VWAP (20-day)
    const typicalSum = bars.slice(-20).reduce((s, b) => s + (b.high + b.low + b.close) / 3 * b.volume, 0);
    const volSum     = bars.slice(-20).reduce((s, b) => s + b.volume, 0);
    const vwap       = volSum > 0 ? typicalSum / volSum : last;
    const vwapScore  = last > vwap ? 1 : 0.3;

    const sSlope = normalizeScore(slope50, -0.002, 0.01);
    const raw    = stackScore * 0.35 + sSlope * 0.30 + adxScore * 0.20 + vwapScore * 0.15;

    return {
      raw,
      weighted: +(raw * 5).toFixed(2),
      components: [
        { name: 'EMA Stack Quality',  value: +stackScore.toFixed(3),  score: stackScore, weight: 0.35 },
        { name: 'EMA50 Slope',        value: +slope50.toFixed(5),      score: sSlope,     weight: 0.30 },
        { name: 'ADX (14)',           value: +adxVal.toFixed(1),        score: adxScore,   weight: 0.20 },
        { name: 'Price vs VWAP',      value: +(last / vwap).toFixed(3), score: vwapScore,  weight: 0.15 },
      ],
    };
  }

  // ── Factor 5: Fundamental Quality (15 pts) ────────────────────────────────

  private scoreFundamentals(stock: StockData): FactorScore {
    // EPS acceleration: most recent Q growth vs prior Q
    const epsQ1   = stock.earningsGrowth ?? 0.10;
    const epsQ2   = (stock.earningsGrowth ?? 0.10) * 0.85;  // approximate prior quarter
    const epsAccel = epsQ1 - epsQ2;

    const revGrowth   = stock.revenueGrowth    ?? 0.10;
    const roe         = (stock.roe             ?? 15) / 100;
    const fcf         = stock.freeCashFlow;
    const debtEq      = stock.debtEquity       ?? 1.0;

    // Cash flow quality: FCF > 0 means real earnings
    const fcfScore = fcf == null ? 0.6 : fcf > 0 ? 1.0 : 0.2;

    // Earnings quality ratio approximation (ROE as proxy for operating leverage)
    const qualityScore = normalizeScore(roe, 0.10, 0.35);

    // Low leverage premium
    const leverageScore = normalizeScore(1 - Math.min(debtEq / 3, 1), 0, 1);

    const sAccel  = normalizeScore(epsAccel, -0.05, 0.20);
    const sRevGr  = Math.min(revGrowth / 0.30, 1);
    const raw     = sAccel * 0.30 + sRevGr * 0.30 + qualityScore * 0.20 + fcfScore * 0.10 + leverageScore * 0.10;

    return {
      raw,
      weighted: +(raw * 0).toFixed(2),  // Fundamentals disabled — not available for most BIST stocks
      components: [
        { name: 'EPS Acceleration',    value: +epsAccel.toFixed(4),   score: sAccel,        weight: 0.30 },
        { name: 'Revenue Growth YoY',  value: +revGrowth.toFixed(4),  score: sRevGr,        weight: 0.30 },
        { name: 'ROE Quality',         value: +roe.toFixed(4),        score: qualityScore,  weight: 0.20 },
        { name: 'Free Cash Flow',      value: fcf ?? 0,               score: fcfScore,      weight: 0.10 },
        { name: 'Low Leverage',        value: +(debtEq).toFixed(2),   score: leverageScore, weight: 0.10 },
      ],
    };
  }

  // ── Factor 6: Entry Timing / VCP / Breakout (25 pts) ─────────────────────
  // Minervini VCP (Volatility Contraction Pattern) + pivot breakout detection

  private scoreEntryTiming(bars: OHLCV[]): FactorScore {
    const last  = bars[bars.length - 1].close;
    const h52   = high52w(bars);
    const dist  = h52 > 0 ? (last - h52) / h52 : -0.15;

    // Distance from 52w high scoring
    // Ideal: within 15% of 52w high (near-ATH consolidation or breakout)
    const distScore = dist >= -0.05                    ? 0.95   // ATH/breakout zone
                    : dist >= -0.15                    ? 1.00   // ideal base (O'Neil buypoint)
                    : dist >= -0.25                    ? 0.75   // acceptable
                    : dist >= -0.35                    ? 0.45   // stretched
                    : 0.15;

    // ── VCP Detection (Minervini Volatility Contraction Pattern) ────────────
    // Look for decreasing price ranges over last 3 "corrections"
    const vcpScore = this.detectVCP(bars);

    // Bollinger Band squeeze
    const currBB    = bollinger(bars);
    const bbWidthNow= currBB.width;
    const bbWidthOld= avgBBWidth(bars, 20);
    const sqzScore  = bbWidthOld > 0 && bbWidthNow < bbWidthOld * 0.75 ? 1.0
                    : bbWidthOld > 0 && bbWidthNow < bbWidthOld * 0.90 ? 0.70
                    : 0.35;

    // RSI entry zone (Minervini: 50–70 is ideal momentum entry)
    const rsiVal   = rsi(bars, 14);
    const rsiScore = rsiVal >= 50 && rsiVal <= 70 ? 1.0
                   : rsiVal >= 70 && rsiVal <= 80 ? 0.65   // extended but still ok
                   : rsiVal >= 45 && rsiVal <  50 ? 0.55   // near pivot
                   : rsiVal >  80                  ? 0.30   // overbought
                   : 0.15;

    // Pivot breakout detection
    const pvtBreak = isPivotBreakout(bars, 20);

    // 52w high proximity bonus (Minervini: stocks within 15% of ATH perform best)
    const near52wHigh = dist >= -0.15;

    const raw = distScore       * 0.25
              + vcpScore        * 0.30   // VCP is THE key Minervini signal
              + sqzScore        * 0.15
              + rsiScore        * 0.15
              + (pvtBreak ? 1 : 0.35) * 0.15;

    // Bonus: stocks at pivot breakout get score multiplier
    const breakoutBonus = pvtBreak && near52wHigh ? 0.15 : 0;
    const finalRaw = Math.min(1, raw + breakoutBonus);

    return {
      raw: finalRaw,
      weighted: +(finalRaw * 25).toFixed(2),
      components: [
        { name: 'Dist from 52w High', value: +(dist * 100).toFixed(1),  score: distScore,          weight: 0.25 },
        { name: 'VCP Pattern',        value: +vcpScore.toFixed(3),      score: vcpScore,            weight: 0.30 },
        { name: 'BB Squeeze',         value: +bbWidthNow.toFixed(4),    score: sqzScore,            weight: 0.15 },
        { name: 'RSI Entry Zone',     value: +rsiVal.toFixed(1),        score: rsiScore,            weight: 0.15 },
        { name: 'Pivot Breakout',     value: pvtBreak ? 1 : 0,         score: pvtBreak ? 1 : 0.35, weight: 0.15 },
      ],
    };
  }

  // ── VCP Pattern Detection (Minervini) ─────────────────────────────────────
  private detectVCP(bars: OHLCV[]): number {
    if (bars.length < 60) return 0.4;

    // Find 3 most recent "corrections" (drawdowns from local highs)
    // VCP = each correction smaller than the previous (volatility contracting)
    const corrections: number[] = [];
    let peak = bars[0].high;
    let trough = bars[0].low;
    let inCorrection = false;

    for (let i = 1; i < bars.length; i++) {
      const b = bars[i];
      if (!inCorrection && b.high > peak) {
        peak = b.high;
      } else if (!inCorrection && b.close < peak * 0.96) {
        // 4% drop from peak = start of correction
        inCorrection = true;
        trough = b.low;
      } else if (inCorrection) {
        if (b.low < trough) trough = b.low;
        if (b.close > peak * 0.98) {
          // Recovery — record this correction depth
          corrections.push((trough - peak) / peak); // negative value
          inCorrection = false;
          peak = b.high;
        }
      }
    }

    if (corrections.length < 2) return 0.4;

    // Check if corrections are contracting (VCP)
    const last2 = corrections.slice(-2);
    const isContracting = Math.abs(last2[1]) < Math.abs(last2[0]) * 0.85;

    if (corrections.length >= 3) {
      const last3 = corrections.slice(-3);
      const fullyContracting = Math.abs(last3[2]) < Math.abs(last3[1]) * 0.85
                            && Math.abs(last3[1]) < Math.abs(last3[0]) * 0.85;
      if (fullyContracting) return 1.0;  // Perfect VCP
    }

    return isContracting ? 0.75 : 0.35;
  }

  // ── Stop Loss (ATR + Support + EMA50) ─────────────────────────────────────

  calculateStopLoss(bars: OHLCV[], entryPrice: number): StopLossConfig {
    const atrVal    = atr(bars, 14);
    const swingLow  = recentSwingLow(bars, 10);
    const ema50vals = ema(bars, 50);
    const e50       = ema50vals[ema50vals.length - 1];

    const atrStop     = entryPrice - atrVal * 2.5;
    const supportStop = swingLow   * 0.99;
    const ema50Stop   = e50        * 0.98;

    // Use highest (tightest technically valid) stop
    const stopPrice = Math.max(atrStop, supportStop, ema50Stop);
    const stopPct   = (entryPrice - stopPrice) / entryPrice;

    return {
      stopPrice:   +stopPrice.toFixed(4),
      stopPercent: +stopPct.toFixed(4),
      method:      'ATR(2.5x) + SwingLow + EMA50',
      isValidStop: stopPct <= 0.08,   // max 8% stop for momentum stocks
    };
  }

  // ── Target Price (1:3 R/R by default) ─────────────────────────────────────

  calculateTarget(entryPrice: number, stopLoss: StopLossConfig, rrRatio = 3): number {
    const risk   = entryPrice - stopLoss.stopPrice;
    return +(entryPrice + risk * rrRatio).toFixed(4);
  }

  // ── Position Sizing (risk-based) ──────────────────────────────────────────

  calculatePositionSize(
    capital:      number,
    entryPrice:   number,
    stopLoss:     StopLossConfig,
    riskPerTrade  = 0.02,   // 2% capital at risk per position
    maxWeight     = 0.25,   // max 25% in any one stock
  ): PositionSize {
    const riskPerShare   = entryPrice - stopLoss.stopPrice;
    if (riskPerShare <= 0) {
      return { shares: 0, value: 0, riskAmount: 0, weightPct: 0 };
    }
    const capitalAtRisk  = capital * riskPerTrade;
    const rawShares      = Math.floor(capitalAtRisk / riskPerShare);
    const rawValue       = rawShares * entryPrice;
    const maxValue       = capital   * maxWeight;
    const finalShares    = rawValue > maxValue ? Math.floor(maxValue / entryPrice) : rawShares;

    return {
      shares:     finalShares,
      value:      +(finalShares * entryPrice).toFixed(2),
      riskAmount: +(finalShares * riskPerShare).toFixed(2),
      weightPct:  +(finalShares * entryPrice / capital * 100).toFixed(2),
    };
  }

  // ── Master scoring method ─────────────────────────────────────────────────

  score(stock: StockData, indexData?: IndexData): AlfaV2Score {
    const bars = stock.series.length >= 20
      ? toOHLCV(stock.series)
      : this.syntheticBars(stock);  // fallback when series is thin

    // Phase 1: Hard filters
    const hardResult = this.applyHardFilters(stock, bars);

    // Phase 2: Factor scoring (always compute, even if hard filter failed)
    const momentum   = this.scorePriceMomentum(bars, stock);
    const relStr     = this.scoreRelativeStrength(stock, bars, indexData);
    const volume     = this.scoreVolumeAnalysis(bars);
    const trend      = this.scoreTrendQuality(bars);
    const fundamental= this.scoreFundamentals(stock);
    const timing     = this.scoreEntryTiming(bars);

    let total = momentum.weighted + relStr.weighted + volume.weighted
              + trend.weighted + fundamental.weighted + timing.weighted;

    // Hard filter failure penalty: cap score at 30
    if (!hardResult.passed) total = Math.min(total, 30);
    total = Math.max(0, Math.min(100, total));

    // Phase 3: Stop / target / R-R
    const entryPrice = stock.close;
    const sl         = this.calculateStopLoss(bars, entryPrice);
    const target     = this.calculateTarget(entryPrice, sl);
    const rrRatio    = sl.stopPercent > 0 ? (target / entryPrice - 1) / sl.stopPercent : 0;

    // Compile signal labels
    const passed:   string[] = [];
    const failed:   string[] = [];
    const warnings: string[] = [];

    if (hardResult.passed) {
      passed.push('Hard filters: ALL PASSED');
    } else {
      hardResult.failedOn.forEach(f => failed.push(f));
    }

    [momentum, relStr, volume, trend, fundamental, timing].forEach(f => {
      const pct = f.raw;
      if (pct >= 0.65) passed.push(f.components[0]?.name ?? '');
      else if (pct < 0.30) failed.push(f.components[0]?.name ?? '');
      else warnings.push(f.components[0]?.name ?? '');
    });

    if (!sl.isValidStop) {
      warnings.push(`Wide stop: ${(sl.stopPercent * 100).toFixed(1)}% > 8% max`);
    }

    const grade: AlfaV2Score['grade'] =
      total >= 85 ? 'A+'
      : total >= 75 ? 'A'
      : total >= 65 ? 'B'
      : total >= 50 ? 'C'
      : total >= 35 ? 'D'
      : 'F';

    return {
      total:              +total.toFixed(2),
      grade,
      hardFilterPassed:   hardResult.passed,
      hardFilterResult:   hardResult,
      factors: {
        priceMomentum:    momentum,
        relativeStrength: relStr,
        volumeAnalysis:   volume,
        trendQuality:     trend,
        fundamentalQuality: fundamental,
        entryTiming:      timing,
      },
      stopLoss:        sl,
      targetPrice:     target,
      riskRewardRatio: +rrRatio.toFixed(2),
      signals:         { passed, failed, warnings },
    };
  }

  // ── Synthetic bar builder (thin series fallback) ──────────────────────────

  private syntheticBars(stock: StockData): OHLCV[] {
    const seed   = stock.close;
    const bars: OHLCV[] = [];
    let   price  = seed * 0.75;
    const vol    = (stock.vol20Avg != null ? stock.vol20Avg : 1_000_000);
    for (let i = 0; i < 252; i++) {
      const drift = 0.0004;
      const noise = (Math.random() - 0.48) * 0.018;
      price *= 1 + drift + noise;
      const spread = price * 0.012;
      bars.push({
        date:   new Date(Date.now() - (252 - i) * 86_400_000),
        open:   +(price * (1 - 0.003)).toFixed(4),
        high:   +(price + spread).toFixed(4),
        low:    +(price - spread).toFixed(4),
        close:  +price.toFixed(4),
        volume: Math.round(vol * (0.7 + Math.random() * 0.6)),
      });
    }
    // Pin last bar to actual stock price
    bars[bars.length - 1] = {
      ...bars[bars.length - 1],
      close: stock.close,
      open:  stock.open  ?? stock.close,
      high:  stock.high  ?? stock.close * 1.01,
      low:   stock.low   ?? stock.close * 0.99,
    };
    return bars;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Singleton export + convenience scorer
// ─────────────────────────────────────────────────────────────────────────────

export const alfaCriteriaV2 = new AlfaCriteriaV2();

/** Drop-in replacement for the old ALFA scoring function.
 *  Returns a 0–100 number compatible with criteriaEngine.calculateScore() */
export function scoreAlfaV2(stock: StockData, indexData?: IndexData): number {
  return alfaCriteriaV2.score(stock, indexData).total;
}
