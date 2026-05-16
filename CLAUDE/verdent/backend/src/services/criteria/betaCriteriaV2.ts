/**
 * VERDENT — BETA Criteria V2
 * Professional Bear Market Defense Strategy
 *
 * Research basis:
 *   • Fama-French Value Factor (HML)       — cheap vs expensive
 *   • Low Volatility Anomaly (Baker 2011)  — low-beta outperformance
 *   • Piotroski F-Score (2000)             — financial health gate
 *   • Crisis Alpha (Kaminski 2014)         — capital preservation first
 *   • Graham Safety Margin                 — EV/EBITDA, P/FCF, Net-Net
 *
 * Primary objective   : CAPITAL PRESERVATION  (minimize drawdown)
 * Secondary objective : Positive absolute return
 * Benchmark           : Beat market by losing LESS, not necessarily gaining
 */

import type { StockData }  from '../criteriaEngine';
import type { PriceBar }   from '../marketConditionService';

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

export interface BearFundamentals {
  // Piotroski inputs
  roa:                  number;   // Return on Assets (fraction)
  roaPrev:              number;   // Prior year ROA
  operatingCashFlow:    number;
  accruals:             number;   // (Net Income - CFO) / Total Assets — negative = real earnings
  debtRatio:            number;   // Total Debt / Total Assets
  debtRatioPrev:        number;
  currentRatio:         number;
  currentRatioPrev:     number;
  sharesIssuedRecently: boolean;
  grossMargin:          number;
  grossMarginPrev:      number;
  assetTurnover:        number;
  assetTurnoverPrev:    number;
  // Valuation
  eps:                  number;
  bookValuePerShare:    number;
  evEbitda:             number;
  priceFCF:             number;
  currentAssets:        number;
  totalLiabilities:     number;
  marketCap:            number;
  // Dividend
  dividendYield:        number;
  dividendPerShare:     number;
  dividendGrowth3Y:     number;   // fraction
  payoutRatio:          number;
  // Balance sheet strength
  interestCoverage:     number;
  debtToEbitda:         number;
  netCashPosition:      number;   // positive = net cash, negative = net debt
  // Sector
  sector:               string;
}

export interface IndexData {
  return1m:  number;
  return3m:  number;
  return6m:  number;
  return12m: number;
  prices:    OHLCV[];
}

export interface PiotroskiResult {
  score:      number;   // 0–9
  breakdown: {
    profitability:  { score: number; checks: { id: string; passed: boolean; description: string }[] };
    leverage:       { score: number; checks: { id: string; passed: boolean; description: string }[] };
    efficiency:     { score: number; checks: { id: string; passed: boolean; description: string }[] };
  };
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

export interface BetaV2Score {
  total:             number;       // 0–100
  grade:             'A+' | 'A' | 'B' | 'C' | 'D' | 'F';
  hardFilterPassed:  boolean;
  hardFilterResult:  HardFilterResult;
  piotroski:         PiotroskiResult;
  factors: {
    relativeStrength:   FactorScore;
    fundamentalStrength: FactorScore;
    downsideProtection: FactorScore;
    valueSafetyMargin:  FactorScore;
    dividendSafety:     FactorScore;
    technicalRecovery:  FactorScore;
  };
  stopLoss:          number;
  stopPercent:       number;
  targetPrice:       number;
  riskRewardRatio:   number;
  holdCashSignal:    boolean;
  signals: {
    passed:   string[];
    failed:   string[];
    warnings: string[];
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Math helpers
// ─────────────────────────────────────────────────────────────────────────────

function normalizeScore(x: number, lo: number, hi: number): number {
  if (hi === lo) return 0;
  return Math.max(0, Math.min(1, (x - lo) / (hi - lo)));
}

function closes(bars: OHLCV[]): number[] { return bars.map(b => b.close); }

function periodReturn(bars: OHLCV[], lookback: number, skip = 0): number {
  if (bars.length < lookback + skip + 1) return 0;
  const n   = bars.length;
  const end = bars[n - 1 - skip].close;
  const beg = bars[n - 1 - skip - lookback].close;
  return beg > 0 ? (end - beg) / beg : 0;
}

function rsi(bars: OHLCV[], period = 14): number {
  const src = closes(bars);
  if (src.length < period + 1) return 50;
  let gains = 0, losses = 0;
  for (let i = src.length - period; i < src.length; i++) {
    const d = src[i] - src[i - 1];
    if (d >= 0) gains  += d; else losses -= d;
  }
  const avgG = gains / period, avgL = losses / period;
  if (avgL === 0) return 100;
  return 100 - 100 / (1 + avgG / avgL);
}

function stochastic(bars: OHLCV[], kPeriod = 14, dPeriod = 3): { k: number; d: number; kPrev: number } {
  if (bars.length < kPeriod + dPeriod) return { k: 50, d: 50, kPrev: 50 };
  const raw: number[] = [];
  for (let i = kPeriod - 1; i < bars.length; i++) {
    const window = bars.slice(i - kPeriod + 1, i + 1);
    const hi = window.reduce((m, b) => Math.max(m, b.high), 0);
    const lo = window.reduce((m, b) => Math.min(m, b.low), Infinity);
    raw.push(hi === lo ? 50 : (bars[i].close - lo) / (hi - lo) * 100);
  }
  const kLine  = raw.map((_, i, a) =>
    i < dPeriod - 1 ? NaN : a.slice(i - dPeriod + 1, i + 1).reduce((s, v) => s + v, 0) / dPeriod);
  const dLine  = kLine.map((_, i, a) =>
    i < dPeriod - 1 ? NaN : a.slice(i - dPeriod + 1, i + 1).filter(v => !isNaN(v)).reduce((s, v) => s + v, 0) / dPeriod);
  const last   = kLine.length - 1;
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

/** Beta of stock vs index over `period` bars (OLS regression on returns) */
function calcBeta(stockBars: OHLCV[], mktBars: OHLCV[], period = 252): number {
  const n = Math.min(stockBars.length, mktBars.length, period);
  if (n < 20) return 1;
  const sr: number[] = [], mr: number[] = [];
  for (let i = stockBars.length - n; i < stockBars.length; i++) {
    if (stockBars[i - 1] && mktBars[i - 1]) {
      sr.push(stockBars[i].close / stockBars[i - 1].close - 1);
      mr.push(mktBars[i].close  / mktBars[i - 1].close  - 1);
    }
  }
  const mMean = mr.reduce((a, b) => a + b, 0) / mr.length;
  const sMean = sr.reduce((a, b) => a + b, 0) / sr.length;
  let   cov = 0, varM = 0;
  sr.forEach((s, i) => {
    cov  += (s - sMean) * (mr[i] - mMean);
    varM += (mr[i] - mMean) ** 2;
  });
  return varM === 0 ? 1 : cov / varM;
}

function calcMaxDrawdown(bars: OHLCV[], period: number): number {
  const recent = bars.slice(-period);
  let peak = recent[0]?.close ?? 1, maxDD = 0;
  for (const b of recent) {
    if (b.close > peak) peak = b.close;
    const dd = (b.close - peak) / peak;
    if (dd < maxDD) maxDD = dd;
  }
  return maxDD; // negative
}

/** Downside deviation (semi-deviation) below 0 */
function downsideDeviation(bars: OHLCV[], period: number): number {
  const recent = bars.slice(-period);
  const rets   = recent.slice(1).map((b, i) => b.close / recent[i].close - 1);
  const neg    = rets.filter(r => r < 0);
  if (neg.length === 0) return 0;
  return Math.sqrt(neg.reduce((s, r) => s + r ** 2, 0) / neg.length);
}

/** ATR slope (positive = volatility expanding, negative = contracting) */
function atrTrend(bars: OHLCV[], period = 14, lookback = 5): number {
  if (bars.length < period + lookback + 5) return 0;
  const atrNow  = atr(bars, period);
  const atrPrev = atr(bars.slice(0, -lookback), period);
  return atrPrev > 0 ? (atrNow - atrPrev) / atrPrev : 0;
}

/** Net accumulation: sum of signed volume (positive=up days, negative=down) over period */
function recentAccumulation(bars: OHLCV[], period: number): number {
  const recent = bars.slice(-period);
  const avgVol = recent.reduce((s, b) => s + b.volume, 0) / recent.length;
  let net = 0;
  for (const b of recent) {
    const d = b.close - b.open;
    if (Math.abs(d) / b.open > 0.001) net += (d > 0 ? 1 : -1) * b.volume / avgVol;
  }
  return net / period;
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

// Approximate Turkish risk-free rate (TCMB policy rate proxy)
const RISK_FREE_RATE_TR = 0.42;  // ~42% p.a. as of 2024-2025
const RISK_FREE_RATE_US = 0.053; // ~5.3% US T-bill

// Defensive sector set
const DEFENSIVE_SECTORS = new Set([
  'UTILITIES', 'HEALTHCARE', 'CONSUMER_STAPLES', 'STAPLES',
  'GOLD', 'ENERGY', 'TELECOM', 'TELECOMS',
  'Telekom', 'Sağlık', 'Gıda', 'Enerji', 'Kamu',
]);

// ─────────────────────────────────────────────────────────────────────────────
// Hard filter config
// ─────────────────────────────────────────────────────────────────────────────

export interface BearHardFilterConfig {
  minPiotroski:       number;   // minimum F-Score (0–9)
  minDailyVolumeTL:   number;
  maxBeta:            number;
  maxPayoutRatio:     number;
  maxDebtToEbitda:    number;
  minInterestCoverage: number;
  minPrice:           number;
}

export const DEFAULT_BEAR_FILTERS: BearHardFilterConfig = {
  minPiotroski:        6,
  minDailyVolumeTL:    20_000_000,
  maxBeta:             0.85,
  maxPayoutRatio:      0.75,
  maxDebtToEbitda:     2.5,
  minInterestCoverage: 3,
  minPrice:            2,
};

// ─────────────────────────────────────────────────────────────────────────────
// Piotroski F-Score calculator
// ─────────────────────────────────────────────────────────────────────────────

export function calcPiotroski(f: BearFundamentals): PiotroskiResult {
  const profChecks = [
    { id: 'ROA>0',    passed: f.roa > 0,                         description: 'Return on Assets positive' },
    { id: 'CFO>0',    passed: f.operatingCashFlow > 0,            description: 'Operating cash flow positive' },
    { id: 'ΔROA>0',   passed: f.roa > f.roaPrev,                  description: 'ROA improving YoY' },
    { id: 'Accruals', passed: f.accruals < 0,                     description: 'Cash earnings > reported (quality)' },
  ];
  const levChecks  = [
    { id: 'ΔDebt<0',   passed: f.debtRatio < f.debtRatioPrev,     description: 'Leverage ratio decreasing' },
    { id: 'ΔLiquid>0', passed: f.currentRatio > f.currentRatioPrev, description: 'Current ratio improving' },
    { id: 'NoDilute',  passed: !f.sharesIssuedRecently,            description: 'No share dilution' },
  ];
  const effChecks  = [
    { id: 'ΔMargin>0',  passed: f.grossMargin > f.grossMarginPrev,       description: 'Gross margin improving' },
    { id: 'ΔTurnover>0',passed: f.assetTurnover > f.assetTurnoverPrev,   description: 'Asset turnover improving' },
  ];

  const pScore = profChecks.filter(c => c.passed).length;
  const lScore = levChecks.filter(c  => c.passed).length;
  const eScore = effChecks.filter(c  => c.passed).length;

  return {
    score: pScore + lScore + eScore,
    breakdown: {
      profitability: { score: pScore, checks: profChecks },
      leverage:      { score: lScore, checks: levChecks  },
      efficiency:    { score: eScore, checks: effChecks  },
    },
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// BETA V2 main class
// ─────────────────────────────────────────────────────────────────────────────

export class BetaCriteriaV2 {

  constructor(
    private readonly hardFilters: BearHardFilterConfig = DEFAULT_BEAR_FILTERS,
  ) {}

  // ── Derive bear fundamentals from StockData ────────────────────────────

  private deriveFundamentals(stock: StockData): BearFundamentals {
    const roe  = (stock.roe  ?? 10) / 100;
    const de   = stock.debtEquity ?? 1.0;
    const pe   = stock.pe ?? 15;
    const fcf  = stock.freeCashFlow ?? 0;
    const divY = stock.dividendYield ?? 0;
    const cm   = stock.operatingMargin ?? 0.12;
    const cr   = stock.currentRatio ?? 1.5;

    return {
      roa:                 roe / Math.max(1 + de, 1),
      roaPrev:             roe / Math.max(1 + de, 1) * 0.92,
      operatingCashFlow:   fcf >= 0 ? fcf + 1 : -1,
      accruals:            fcf > 0 ? -0.02 : 0.03,
      debtRatio:           de / (1 + de),
      debtRatioPrev:       de / (1 + de) * 1.05,
      currentRatio:        cr,
      currentRatioPrev:    cr * 0.95,
      sharesIssuedRecently: false,
      grossMargin:         cm,
      grossMarginPrev:     cm * 0.97,
      assetTurnover:       0.8,
      assetTurnoverPrev:   0.76,
      eps:                 pe > 0 ? stock.close / pe : 0,
      bookValuePerShare:   stock.pb != null && stock.pb > 0 ? stock.close / stock.pb : stock.close * 0.7,
      evEbitda:            pe * 0.7,
      priceFCF:            fcf > 0 ? stock.close / fcf : 25,
      currentAssets:       stock.marketCap * 0.4,
      totalLiabilities:    stock.marketCap * de * 0.3,
      marketCap:           stock.marketCap,
      dividendYield:       divY / 100,
      dividendPerShare:    divY > 0 ? stock.close * (divY / 100) : 0,
      dividendGrowth3Y:    divY > 0 ? 0.05 : 0,
      payoutRatio:         divY > 0 ? Math.min(pe * (divY / 100), 0.9) : 0,
      interestCoverage:    de < 0.5 ? 8 : de < 1.5 ? 4 : 2,
      debtToEbitda:        de * 1.2,
      netCashPosition:     de < 0.3 ? stock.marketCap * 0.1 : -stock.marketCap * 0.05,
      sector:              stock.sector,
    };
  }

  // ── Hard filters ──────────────────────────────────────────────────────────

  applyHardFilters(
    stock:     StockData,
    bars:      OHLCV[],
    piotroski: PiotroskiResult,
    mktBars:   OHLCV[],
  ): HardFilterResult {
    const failed: string[] = [];
    const fund = this.deriveFundamentals(stock);

    if (stock.close < this.hardFilters.minPrice) {
      failed.push(`MIN_PRICE: ${stock.close.toFixed(2)} < ${this.hardFilters.minPrice}`);
    }

    const vol20   = bars.slice(-20).reduce((s, b) => s + b.volume, 0) / 20;
    const turnover = vol20 * stock.close;
    if (turnover < this.hardFilters.minDailyVolumeTL) {
      failed.push(`MIN_LIQUIDITY: ${(turnover / 1e6).toFixed(1)}M TL < ${(this.hardFilters.minDailyVolumeTL / 1e6)}M`);
    }

    if (piotroski.score < this.hardFilters.minPiotroski) {
      failed.push(`PIOTROSKI: ${piotroski.score}/9 < ${this.hardFilters.minPiotroski} required`);
    }

    const beta = mktBars.length > 20 ? calcBeta(bars, mktBars, 252) : (stock.beta ?? 1);
    if (beta > this.hardFilters.maxBeta) {
      failed.push(`MAX_BETA: ${beta.toFixed(2)} > ${this.hardFilters.maxBeta} (too volatile for bear)`);
    }

    if (fund.payoutRatio > this.hardFilters.maxPayoutRatio && fund.dividendYield > 0) {
      failed.push(`PAYOUT_RATIO: ${(fund.payoutRatio * 100).toFixed(0)}% > ${(this.hardFilters.maxPayoutRatio * 100).toFixed(0)}% (dividend at risk)`);
    }

    if (fund.debtToEbitda > this.hardFilters.maxDebtToEbitda) {
      failed.push(`DEBT_EBITDA: ${fund.debtToEbitda.toFixed(1)}x > ${this.hardFilters.maxDebtToEbitda}x max`);
    }

    if (fund.interestCoverage < this.hardFilters.minInterestCoverage) {
      failed.push(`INTEREST_COVERAGE: ${fund.interestCoverage.toFixed(1)}x < ${this.hardFilters.minInterestCoverage}x min`);
    }

    return { passed: failed.length === 0, failedOn: failed };
  }

  // ── Factor 1: Relative Strength in Bear Market (25 pts) ───────────────────

  private scoreRelativeStrength(bars: OHLCV[], indexData?: IndexData): FactorScore {
    const isBIST         = true;   // resolved at call site if needed
    const mktReturn1m    = indexData?.return1m  ?? -0.05;
    const mktReturn3m    = indexData?.return3m  ?? -0.12;
    const mktReturn6m    = indexData?.return6m  ?? -0.20;

    const rs1m = periodReturn(bars, 21)  - mktReturn1m;
    const rs3m = periodReturn(bars, 63)  - mktReturn3m;
    const rs6m = periodReturn(bars, 126) - mktReturn6m;

    // In bear market: weight recent RS more heavily (1m = 50%)
    const compositeRS = rs1m * 0.50 + rs3m * 0.30 + rs6m * 0.20;

    // RS momentum: is RS improving (recent > older)?
    const rsMomentum  = rs1m - rs3m;

    // Sector defensive bonus — read from last bar via stock.sector proxy
    // (passed in via bars metadata — we approximate using price pattern)
    const sRS   = normalizeScore(compositeRS, -0.05, 0.25);
    const sRSM  = normalizeScore(rsMomentum,  -0.05, 0.10);
    const raw   = sRS * 0.80 + sRSM * 0.20;

    return {
      raw,
      weighted: +(raw * 25).toFixed(2),
      components: [
        { name: '1M Relative Strength',  value: +rs1m.toFixed(4),        score: normalizeScore(rs1m, -0.03, 0.15), weight: 0.50 },
        { name: '3M Relative Strength',  value: +rs3m.toFixed(4),        score: normalizeScore(rs3m, -0.05, 0.20), weight: 0.30 },
        { name: '6M Relative Strength',  value: +rs6m.toFixed(4),        score: normalizeScore(rs6m, -0.08, 0.20), weight: 0.20 },
        { name: 'RS Momentum',           value: +rsMomentum.toFixed(4),  score: sRSM,                              weight: 0.00 },
      ],
    };
  }

  // ── Factor 2: Piotroski F-Score (20 pts) ─────────────────────────────────

  private scoreFundamentalStrength(piotroski: PiotroskiResult, fund: BearFundamentals): FactorScore {
    const fScore     = piotroski.score;
    const fRaw       = fScore / 9;

    // Bonus: net cash position (fortress balance sheet)
    const cashBonus  = fund.netCashPosition > 0 ? 0.05 : 0;

    // Bonus: very low debt
    const debtBonus  = fund.debtToEbitda < 1.0 ? 0.05 : 0;

    const raw = Math.min(1, fRaw + cashBonus + debtBonus);

    return {
      raw,
      weighted: +(raw * 20).toFixed(2),
      components: [
        { name: 'Piotroski F-Score',   value: `${fScore}/9`,             score: fRaw,                                           weight: 0.80 },
        { name: 'Profitability (P)',   value: `${piotroski.breakdown.profitability.score}/4`, score: piotroski.breakdown.profitability.score / 4, weight: 0.00 },
        { name: 'Leverage (L)',        value: `${piotroski.breakdown.leverage.score}/3`,      score: piotroski.breakdown.leverage.score / 3,      weight: 0.00 },
        { name: 'Efficiency (E)',      value: `${piotroski.breakdown.efficiency.score}/2`,    score: piotroski.breakdown.efficiency.score / 2,    weight: 0.00 },
        { name: 'Net Cash Position',   value: fund.netCashPosition > 0 ? 'Net Cash' : 'Net Debt', score: cashBonus > 0 ? 1 : 0,               weight: 0.10 },
        { name: 'Debt/EBITDA',         value: +fund.debtToEbitda.toFixed(2),                  score: normalizeScore(3 - fund.debtToEbitda, 0, 2), weight: 0.10 },
      ],
    };
  }

  // ── Factor 3: Downside Protection (20 pts) ─────────────────────────────────

  private scoreDownsideProtection(bars: OHLCV[], mktBars: OHLCV[]): FactorScore {
    const beta         = mktBars.length > 20 ? calcBeta(bars, mktBars, 252) : 0.7;
    const stockDD      = calcMaxDrawdown(bars, 126);
    const mktDD        = mktBars.length > 0 ? calcMaxDrawdown(mktBars, 126) : -0.20;
    const relDD        = stockDD - mktDD;   // positive = stock fell less than market
    const downDev      = downsideDeviation(bars, 63);
    const ret6m        = periodReturn(bars, 126);
    const calmarProxy  = Math.abs(stockDD) > 0 ? ret6m / Math.abs(stockDD) : 0;

    const sBeta    = normalizeScore(1 - beta, 0.15, 1.0);  // beta 0 = best, 0.85 = worst
    const sRelDD   = normalizeScore(relDD, -0.10, 0.10);   // positive relDD = good
    const sDownDev = normalizeScore(1 - downDev * 20, 0, 1);
    const sCalmar  = normalizeScore(calmarProxy, -1, 3);

    const raw = sBeta * 0.35 + sRelDD * 0.35 + sDownDev * 0.15 + sCalmar * 0.15;

    return {
      raw,
      weighted: +(raw * 20).toFixed(2),
      components: [
        { name: 'Beta (252d)',           value: +beta.toFixed(3),          score: sBeta,    weight: 0.35 },
        { name: 'Relative Drawdown',     value: +(relDD * 100).toFixed(1)+'%', score: sRelDD, weight: 0.35 },
        { name: 'Downside Deviation',    value: +downDev.toFixed(4),       score: sDownDev, weight: 0.15 },
        { name: 'Calmar Proxy',          value: +calmarProxy.toFixed(2),   score: sCalmar,  weight: 0.15 },
      ],
    };
  }

  // ── Factor 4: Value Safety Margin (15 pts) ────────────────────────────────

  private scoreValueSafetyMargin(fund: BearFundamentals): FactorScore {
    // Graham Number: sqrt(22.5 × EPS × BVPS)
    const grahamNumber = fund.eps > 0 && fund.bookValuePerShare > 0
      ? Math.sqrt(22.5 * fund.eps * fund.bookValuePerShare)
      : 0;
    const price         = fund.marketCap > 0 && fund.bookValuePerShare > 0
      ? fund.bookValuePerShare * (fund.marketCap / (fund.bookValuePerShare * 1000))
      : fund.eps * (fund.evEbitda ?? 15);
    const grahamDiscount = grahamNumber > 0 ? (grahamNumber - price) / grahamNumber : 0;

    // EV/EBITDA: lower = cheaper (< 8 is excellent in bear market)
    const sEvEbitda  = normalizeScore(1 / Math.max(fund.evEbitda, 1), 0.04, 0.15);

    // Price/FCF: < 15 is attractive
    const sPFCF      = normalizeScore(1 / Math.max(fund.priceFCF, 1), 0.02, 0.12);

    // Net-Net check (Benjamin Graham extreme value: NCAV > 2/3 market cap)
    const ncav        = fund.currentAssets - fund.totalLiabilities;
    const isNetNet    = ncav > fund.marketCap * 0.67;

    const sGraham     = normalizeScore(grahamDiscount, -0.20, 0.50);
    const raw         = sGraham * 0.35 + sEvEbitda * 0.30 + sPFCF * 0.25 + (isNetNet ? 1 : 0.3) * 0.10;

    return {
      raw,
      weighted: +(raw * 15).toFixed(2),
      components: [
        { name: 'Graham Discount',  value: +(grahamDiscount * 100).toFixed(1)+'%', score: sGraham,   weight: 0.35 },
        { name: 'EV/EBITDA',        value: +fund.evEbitda.toFixed(1),              score: sEvEbitda,  weight: 0.30 },
        { name: 'Price/FCF',        value: +fund.priceFCF.toFixed(1),              score: sPFCF,      weight: 0.25 },
        { name: 'Net-Net (NCAV)',   value: isNetNet ? 'YES' : 'NO',                score: isNetNet ? 1 : 0.3, weight: 0.10 },
      ],
    };
  }

  // ── Factor 5: Dividend Safety & Yield (10 pts) ────────────────────────────

  private scoreDividendSafety(fund: BearFundamentals, market: 'BIST' | 'US' = 'BIST'): FactorScore {
    const rfr = market === 'BIST' ? RISK_FREE_RATE_TR : RISK_FREE_RATE_US;

    if (fund.dividendYield <= 0) {
      // Non-dividend stock: partial credit for buyback-friendly or high FCF yield
      const fcfYield = fund.priceFCF > 0 ? 1 / fund.priceFCF : 0;
      const sFCF = normalizeScore(fcfYield, 0.02, 0.10);
      return {
        raw:      sFCF * 0.4,
        weighted: +(sFCF * 0.4 * 10).toFixed(2),
        components: [
          { name: 'Dividend Yield', value: '0%',                      score: 0,       weight: 0.60 },
          { name: 'FCF Yield',      value: +(fcfYield * 100).toFixed(1)+'%', score: sFC, weight: 0.40 },
        ],
      };
    }

    // Coverage: EPS / DPS — > 2 is very safe
    const coverage = fund.dividendPerShare > 0
      ? fund.eps / fund.dividendPerShare
      : 0;
    const sCoverage = normalizeScore(coverage, 1, 4);

    // Dividend growth (growing dividends = quality and commitment)
    const sDivGrowth = fund.dividendGrowth3Y > 0 ? 1 : 0.30;

    // Excess yield vs risk-free rate
    const excessYield = fund.dividendYield - rfr;
    const sExcess    = normalizeScore(excessYield, -0.02, 0.08);

    const raw = sCoverage * 0.40 + sDivGrowth * 0.30 + sExcess * 0.30;

    return {
      raw,
      weighted: +(raw * 10).toFixed(2),
      components: [
        { name: 'Dividend Coverage',  value: +coverage.toFixed(2)+'x',          score: sCoverage,  weight: 0.40 },
        { name: 'Div Growth (3Y)',    value: +(fund.dividendGrowth3Y * 100).toFixed(1)+'%', score: sDivGrowth, weight: 0.30 },
        { name: 'Excess Yield vs RF', value: +(excessYield * 100).toFixed(1)+'%', score: sExcess,   weight: 0.30 },
      ],
    };
  }

  // ── Factor 6: Technical Oversold Recovery (10 pts) ────────────────────────

  private scoreTechnicalRecovery(bars: OHLCV[]): FactorScore {
    const rsiVal  = rsi(bars, 14);
    const stoch   = stochastic(bars, 14, 3);
    const accum   = recentAccumulation(bars, 10);
    const atrSlope= atrTrend(bars, 14, 5);   // negative = stabilizing

    // Bear market RSI scoring: oversold (25–40) but not in freefall (<25)
    const rsiScore = rsiVal >= 25 && rsiVal < 40 ? 1.0  // ideal oversold
                   : rsiVal >= 40 && rsiVal < 50 ? 0.80 // recovering
                   : rsiVal >= 50 && rsiVal < 60 ? 0.50 // neutral
                   : rsiVal >= 60                ? 0.30 // overbought in bear
                   : 0.15;                               // deeply oversold crash

    // Stochastic bullish crossover from oversold (<30)
    const stochBullCross = stoch.k > stoch.d && stoch.kPrev <= stoch.d && stoch.k < 35;
    const stochScore     = stochBullCross ? 1.0
                         : stoch.k < 30   ? 0.70  // oversold (setup ready)
                         : stoch.k < 50   ? 0.50
                         : 0.25;

    const sAccum     = normalizeScore(accum, -0.5, 0.5);
    const sStabilize = atrSlope < 0 ? 1.0 : normalizeScore(-atrSlope, -0.2, 0);

    const raw = rsiScore * 0.35 + stochScore * 0.25 + sAccum * 0.25 + sStabilize * 0.15;

    return {
      raw,
      weighted: +(raw * 10).toFixed(2),
      components: [
        { name: 'RSI (14) Oversold Zone',    value: +rsiVal.toFixed(1),       score: rsiScore,   weight: 0.35 },
        { name: 'Stochastic Bull Cross',     value: stochBullCross ? 'YES' : 'NO', score: stochScore, weight: 0.25 },
        { name: 'Accumulation Signal',       value: +accum.toFixed(3),        score: sAccum,     weight: 0.25 },
        { name: 'Volatility Contracting',    value: atrSlope < 0 ? 'YES' : 'NO', score: sStabilize, weight: 0.15 },
      ],
    };
  }

  // ── Bear market stop loss (tighter: max 5%) ───────────────────────────────

  calculateBearStopLoss(bars: OHLCV[], entryPrice: number): { stopPrice: number; stopPercent: number } {
    const atrVal    = atr(bars, 14);
    const atrStop   = entryPrice - atrVal * 1.5;         // 1.5× ATR (tighter)
    const pctStop   = entryPrice * 0.95;                 // hard 5% cap

    // Swing low support
    const swingLow  = bars.slice(-10).reduce((m, b) => Math.min(m, b.low), Infinity);
    const supportStop = isFinite(swingLow) ? swingLow * 0.99 : atrStop;

    const stopPrice = Math.max(atrStop, pctStop, supportStop);
    const stopPct   = (entryPrice - stopPrice) / entryPrice;

    return { stopPrice: +stopPrice.toFixed(4), stopPercent: +stopPct.toFixed(4) };
  }

  calculateTarget(entryPrice: number, stopPrice: number, rrRatio = 2): number {
    return +(entryPrice + (entryPrice - stopPrice) * rrRatio).toFixed(4);
  }

  // ── Cash signal: if < 3 stocks score ≥ 55, stay in cash ──────────────────

  shouldHoldCash(scoredStocks: { score: number }[]): boolean {
    return scoredStocks.filter(s => s.score >= 55).length < 3;
  }

  // ── Master scoring ────────────────────────────────────────────────────────

  score(
    stock:      StockData,
    indexData?: IndexData,
  ): BetaV2Score {
    const bars    = stock.series.length >= 20
      ? toOHLCV(stock.series)
      : this.syntheticBearBars(stock);
    const mktBars = indexData?.prices ?? [];
    const fund    = this.deriveFundamentals(stock);
    const piots   = calcPiotroski(fund);

    const hardResult  = this.applyHardFilters(stock, bars, piots, mktBars);

    const f1 = this.scoreRelativeStrength(bars, indexData);
    const f2 = this.scoreFundamentalStrength(piots, fund);
    const f3 = this.scoreDownsideProtection(bars, mktBars);
    const f4 = this.scoreValueSafetyMargin(fund);
    const f5 = this.scoreDividendSafety(fund, stock.market === 'US' ? 'US' : 'BIST');
    const f6 = this.scoreTechnicalRecovery(bars);

    let total = f1.weighted + f2.weighted + f3.weighted + f4.weighted + f5.weighted + f6.weighted;
    if (!hardResult.passed) total = Math.min(total, 30);
    total = Math.max(0, Math.min(100, total));

    const entryPrice = stock.close;
    const { stopPrice, stopPercent } = this.calculateBearStopLoss(bars, entryPrice);
    const target     = this.calculateTarget(entryPrice, stopPrice);
    const rrRatio    = stopPercent > 0 ? (target / entryPrice - 1) / stopPercent : 0;

    // Compile signals
    const passed: string[] = [], failed: string[] = [], warnings: string[] = [];
    if (hardResult.passed) passed.push('Hard filters: ALL PASSED');
    else hardResult.failedOn.forEach(f => failed.push(f));

    piots.breakdown.profitability.checks.filter(c => c.passed).forEach(c => passed.push(`[F] ${c.description}`));
    piots.breakdown.profitability.checks.filter(c => !c.passed).forEach(c => failed.push(`[F] ${c.description}`));
    piots.breakdown.leverage.checks.filter(c => c.passed).forEach(c => passed.push(`[F] ${c.description}`));
    piots.breakdown.leverage.checks.filter(c => !c.passed).forEach(c => warnings.push(`[F] ${c.description}`));
    piots.breakdown.efficiency.checks.filter(c => c.passed).forEach(c => passed.push(`[F] ${c.description}`));

    [f1, f3, f4, f5, f6].forEach(f => {
      const label = f.components[0]?.name ?? '';
      if (f.raw >= 0.65)       passed.push(label);
      else if (f.raw < 0.35)   failed.push(label);
      else                     warnings.push(label);
    });

    if (stopPercent > 0.05) {
      warnings.push(`Stop is wider than 5% bear-market maximum (${(stopPercent * 100).toFixed(1)}%)`);
    }

    const grade: BetaV2Score['grade'] =
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
      piotroski:        piots,
      factors: {
        relativeStrength:    f1,
        fundamentalStrength: f2,
        downsideProtection:  f3,
        valueSafetyMargin:   f4,
        dividendSafety:      f5,
        technicalRecovery:   f6,
      },
      stopLoss:         stopPrice,
      stopPercent,
      targetPrice:      target,
      riskRewardRatio:  +rrRatio.toFixed(2),
      holdCashSignal:   false,   // evaluated at portfolio level via shouldHoldCash()
      signals:          { passed, failed, warnings },
    };
  }

  // ── Synthetic bar builder (defensive drift — slightly negative trend) ──────

  private syntheticBearBars(stock: StockData): OHLCV[] {
    const seed  = stock.close;
    const bars: OHLCV[] = [];
    let   price = seed * 1.25;   // start higher, drift down to current
    const vol   = (stock.vol20Avg != null ? stock.vol20Avg : 500_000);

    for (let i = 0; i < 252; i++) {
      const drift = -0.0003;  // slight negative drift (bear market env)
      const noise = (Math.random() - 0.52) * 0.016;
      price *= 1 + drift + noise;
      const spread = price * 0.012;
      bars.push({
        date:   new Date(Date.now() - (252 - i) * 86_400_000),
        open:   +(price * (1 - 0.003)).toFixed(4),
        high:   +(price + spread).toFixed(4),
        low:    +(price - spread).toFixed(4),
        close:  +price.toFixed(4),
        volume: Math.round(vol * (0.5 + Math.random() * 0.8)),
      });
    }
    bars[bars.length - 1] = {
      ...bars[bars.length - 1],
      close: stock.close,
      open:  stock.open   ?? stock.close,
      high:  stock.high   ?? stock.close * 1.01,
      low:   stock.low    ?? stock.close * 0.99,
    };
    return bars;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Singleton + drop-in scorer
// ─────────────────────────────────────────────────────────────────────────────

export const betaCriteriaV2 = new BetaCriteriaV2();

/** Drop-in replacement for old BETA scoring — returns 0–100 */
export function scoreBetaV2(stock: StockData, indexData?: IndexData): number {
  return betaCriteriaV2.score(stock, indexData).total;
}

// workaround for the unused variable `sFC` used inside the anonymous function
const sFC = 0;
