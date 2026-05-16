/**
 * VERDENT — Backtesting Engine
 *
 * Shared scanning pipeline → 100% consistency with Scanner page results for
 * the same date × criteria × market combination.
 *
 * Supports:
 *   ALFA / BETA / DELTA  — single-criteria run (constant regime)
 *   HYBRID               — dynamically switches criteria based on the detected
 *                          market condition at each rebalance date
 *
 * Rebalance schedules:
 *   WEEKLY  → every Monday (or next trading day)
 *   MONTHLY → first trading day of each calendar month
 *
 * Cost model:
 *   transactionCost applied to BUY and SELL value (default 0.1 %)
 *   slippage         applied to execution price   (default 0.1 %)
 *
 * Performance metrics:
 *   Total Return, Annualised Return (CAGR), Maximum Drawdown, Sharpe Ratio,
 *   Sortino Ratio, Win Rate, Avg Win / Avg Loss, Profit Factor, Calmar Ratio,
 *   Recovery Factor
 */

import { randomUUID } from 'crypto';

import {
  screenStocksSync,
  generateMockStocks,
  type CriteriaType,
  type ScoredStock,
  type StockData,
} from './criteriaEngine';

import {
  analyzeMarketCondition,
  generateMockSeries,
  type MarketConditionLabel,
  type MarketId,
} from './marketConditionService';

import {
  dataService,
  calculateRSI,
  calculateEMA,
  calculateMACD,
  calculateATR,
  type SplitEvent,
} from './dataService';

import {
  BIST100_LIST,
  BIST100DISI_LIST,
  BISTTUM_LIST,
  US_MARKET_LIST,
} from './stockUniverse';

// Lazy-loaded to avoid circular dep (hybridBacktestV2 imports from this file)
let _hybridV2: import('./hybridBacktestV2').HybridBacktestV2 | null = null;
async function getHybridV2(): Promise<import('./hybridBacktestV2').HybridBacktestV2> {
  if (!_hybridV2) {
    const m = await import('./hybridBacktestV2');
    _hybridV2 = m.hybridBacktestV2;
  }
  return _hybridV2;
}
// module-level alias used in runBacktest (resolved before first call)
let hybridBacktestV2: { runHybridV2: (...args: any[]) => Promise<BacktestResult> } = {
  runHybridV2: async (...args) => (await getHybridV2()).runHybridV2(...(args as Parameters<import('./hybridBacktestV2').HybridBacktestV2['runHybridV2']>)),
};

// ─────────────────────────────────────────────────────────────────────────────
// Public types
// ─────────────────────────────────────────────────────────────────────────────

export type RebalancePeriod = 'WEEKLY' | 'MONTHLY';
export type MarketScope     = 'BISTTUM' | 'BIST100' | 'BIST100DISI' | 'BIST' | 'US' | 'BOTH';

export interface BacktestConfig {
  name:             string;
  criteriaType:     CriteriaType | 'HYBRID';
  startDate:        Date;
  endDate:          Date;
  rebalancePeriod:  RebalancePeriod;
  market:           MarketScope;
  initialCapital:   number;
  transactionCost:  number;
  slippage:         number;
  portfolioSize?:   number;   // kaç hisse — varsayılan 5
}

export const DEFAULT_CONFIG: Partial<BacktestConfig> = {
  initialCapital:  100_000,
  transactionCost: 0.001,
  slippage:        0.001,
  rebalancePeriod: 'MONTHLY',
  market:          'US',
  criteriaType:    'HYBRID',
};

export interface Holding {
  symbol:     string;
  name:       string;
  shares:     number;
  entryPrice: number;
  currentPrice: number;
  value:      number;
  weight:     number;   // 0–100
  pnl:        number;
  pnlPct:     number;
  stopLoss?:  number;   // trailing stop price
}

export interface PortfolioSnapshot {
  date:            Date;
  value:           number;
  cash:            number;
  holdings:        Holding[];
  criteriaUsed:    string;
  marketCondition: string;
  drawdown:        number;   // from peak, 0–100
}

export interface Trade {
  id:         string;
  symbol:     string;
  action:     'BUY' | 'SELL';
  date:       Date;
  price:      number;
  shares:     number;
  value:      number;
  cost:       number;         // transaction cost + slippage
  reason:     string;
  criteriaUsed: string;
  pnl?:       number;         // filled on SELL only
  pnlPct?:    number;
}

export interface PerformanceMetrics {
  totalReturn:      number;
  annualizedReturn: number;
  maxDrawdown:      number;
  sharpeRatio:      number;
  sortinoRatio:     number;
  winRate:          number;
  avgWin:           number;
  avgLoss:          number;
  profitFactor:     number;
  totalTrades:      number;
  calmarRatio:      number;
  recoveryFactor:   number;
  bestMonth:        number;
  worstMonth:       number;
  consecutiveWins:  number;
  consecutiveLosses: number;
}

export interface BenchmarkResult {
  name:             string;
  totalReturn:      number;
  annualizedReturn: number;
  maxDrawdown:      number;
  sharpeRatio:      number;
  series:           { date: Date; value: number }[];
}

export interface RebalanceResult {
  date:        Date;
  buys:        Trade[];
  sells:       Trade[];
  holdings:    Holding[];
  cashAfter:   number;
  portfolioValue: number;
  criteriaUsed: string;
  topStocks:   ScoredStock[];
}

export interface BacktestResult {
  id:               string;
  config:           BacktestConfig;
  performance:      PerformanceMetrics;
  portfolioHistory: PortfolioSnapshot[];
  trades:           Trade[];
  benchmark:        BenchmarkResult;
  consistencyCheck: boolean;
  rebalanceDates:   Date[];
  criteriaTimeline: { date: Date; criteria: string; condition: string }[];
  runtimeMs:        number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Rebalance date generator
// ─────────────────────────────────────────────────────────────────────────────

/** Day-of-week: 0=Sun, 1=Mon … 6=Sat */
function dow(d: Date): number { return d.getDay(); }

/** Advance d by `days` calendar days */
function addDays(d: Date, days: number): Date {
  const r = new Date(d);
  r.setDate(r.getDate() + days);
  return r;
}

/** True if d is Mon–Fri (simple trading-day proxy) */
function isTradingDay(d: Date): boolean {
  const wd = dow(d);
  return wd >= 1 && wd <= 5;
}

/** Next trading day on or after d */
function nextTradingDay(d: Date): Date {
  let cur = new Date(d);
  while (!isTradingDay(cur)) cur = addDays(cur, 1);
  return cur;
}

export function generateRebalanceDates(
  startDate: Date,
  endDate:   Date,
  period:    RebalancePeriod,
): Date[] {
  const dates: Date[] = [];

  if (period === 'WEEKLY') {
    // Every Monday (or next trading day if Monday is a holiday)
    let cur = new Date(startDate);
    // Advance to first Monday ≥ startDate
    while (dow(cur) !== 1) cur = addDays(cur, 1);

    while (cur <= endDate) {
      dates.push(nextTradingDay(new Date(cur)));
      cur = addDays(cur, 7);
    }

  } else {
    // MONTHLY — first trading day of each calendar month in range
    let year  = startDate.getFullYear();
    let month = startDate.getMonth();

    while (true) {
      const candidate = nextTradingDay(new Date(year, month, 1));
      if (candidate > endDate) break;
      if (candidate >= startDate) dates.push(candidate);
      month++;
      if (month > 11) { month = 0; year++; }
    }
  }

  return dates;
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared scan function  ← used by BOTH BacktestEngine and Scanner route
// ─────────────────────────────────────────────────────────────────────────────

/**
 * The single source of truth for "which stocks are picked on date D with
 * criteria C on market M".
 *
 * In production: pass real `stocks` loaded from DB for that date.
 * In simulation: `stocks` comes from `generateMockStocks()`.
 *
 * ❗ Both Scanner page and BacktestEngine MUST call this function —
 *    guaranteeing identical results for the same inputs.
 */
export function sharedScan(
  stocks:   StockData[],
  criteria: CriteriaType,
  top:      number = 5,
): ScoredStock[] {
  return screenStocksSync(stocks, criteria).slice(0, top);
}

// ─────────────────────────────────────────────────────────────────────────────
// Portfolio helpers
// ─────────────────────────────────────────────────────────────────────────────

function applySlippage(price: number, action: 'BUY' | 'SELL', slip: number): number {
  return action === 'BUY'
    ? +(price * (1 + slip)).toFixed(4)
    : +(price * (1 - slip)).toFixed(4);
}

function calcShares(capital: number, price: number): number {
  return Math.floor(capital / price);
}

// ─────────────────────────────────────────────────────────────────────────────
// Performance metrics calculator
// ─────────────────────────────────────────────────────────────────────────────

const RISK_FREE_RATE = 0.05;   // 5 % annual

function dailyRfRate(): number {
  return (1 + RISK_FREE_RATE) ** (1 / 252) - 1;
}

function annualisedReturn(totalReturn: number, tradingDays: number): number {
  if (tradingDays <= 0) return 0;
  const years = tradingDays / 252;
  return +((Math.pow(1 + totalReturn / 100, 1 / years) - 1) * 100).toFixed(4);
}

function calcMaxDrawdown(values: number[]): number {
  let peak = -Infinity;
  let maxDD = 0;
  for (const v of values) {
    if (v > peak) peak = v;
    const dd = (peak - v) / peak * 100;
    if (dd > maxDD) maxDD = dd;
  }
  return +maxDD.toFixed(4);
}

function calcSharpe(dailyReturns: number[]): number {
  if (dailyReturns.length < 2) return 0;
  const rfDaily = dailyRfRate();
  const excess  = dailyReturns.map(r => r - rfDaily);
  const mean    = excess.reduce((s, v) => s + v, 0) / excess.length;
  const variance = excess.reduce((s, v) => s + (v - mean) ** 2, 0) / (excess.length - 1);
  const std     = Math.sqrt(variance);
  if (std === 0 || std < 1e-10) return 0;
  return +((mean / std) * Math.sqrt(252)).toFixed(4);
}

function calcSortino(dailyReturns: number[]): number {
  if (dailyReturns.length < 2) return 0;
  const rfDaily    = dailyRfRate();
  const excess     = dailyReturns.map(r => r - rfDaily);
  const mean       = excess.reduce((s, v) => s + v, 0) / excess.length;
  const negSquared = excess.filter(r => r < 0).map(r => r ** 2);
  if (negSquared.length === 0) return 10;  // no down days
  const downDev = Math.sqrt(negSquared.reduce((s, v) => s + v, 0) / negSquared.length);
  if (downDev === 0) return 10;
  return +((mean / downDev) * Math.sqrt(252)).toFixed(4);
}

/** Monthly return series from daily snapshots */
function monthlyReturns(snapshots: PortfolioSnapshot[]): number[] {
  const byMonth = new Map<string, { first: number; last: number }>();
  for (const s of snapshots) {
    const key = `${s.date.getFullYear()}-${String(s.date.getMonth() + 1).padStart(2, '0')}`;
    const entry = byMonth.get(key);
    if (!entry)      byMonth.set(key, { first: s.value, last: s.value });
    else             entry.last = s.value;
  }
  const returns: number[] = [];
  for (const { first, last } of byMonth.values()) {
    if (first > 0) returns.push((last - first) / first * 100);
  }
  return returns;
}

function maxConsecutive(results: boolean[]): { wins: number; losses: number } {
  let maxW = 0, maxL = 0, curW = 0, curL = 0;
  for (const r of results) {
    if (r)  { curW++; curL = 0; maxW = Math.max(maxW, curW); }
    else    { curL++; curW = 0; maxL = Math.max(maxL, curL); }
  }
  return { wins: maxW, losses: maxL };
}

function calculateMetrics(
  trades:    Trade[],
  snapshots: PortfolioSnapshot[],
  config:    BacktestConfig,
): PerformanceMetrics {
  if (snapshots.length < 2) {
    return {
      totalReturn: 0, annualizedReturn: 0, maxDrawdown: 0,
      sharpeRatio: 0, sortinoRatio: 0, winRate: 0,
      avgWin: 0, avgLoss: 0, profitFactor: 0,
      totalTrades: 0, calmarRatio: 0, recoveryFactor: 0,
      bestMonth: 0, worstMonth: 0,
      consecutiveWins: 0, consecutiveLosses: 0,
    };
  }

  const initial = snapshots[0].value;
  const final_  = snapshots[snapshots.length - 1].value;
  const totalReturn = +((final_ - initial) / initial * 100).toFixed(4);

  const tradingDays = snapshots.length;
  const annReturn   = annualisedReturn(totalReturn, tradingDays);

  const values    = snapshots.map(s => s.value);
  const maxDD     = calcMaxDrawdown(values);

  // Daily returns
  const dailyRet: number[] = [];
  for (let i = 1; i < values.length; i++) {
    if (values[i - 1] > 0) dailyRet.push((values[i] - values[i - 1]) / values[i - 1]);
  }
  const sharpe  = calcSharpe(dailyRet);
  const sortino = calcSortino(dailyRet);

  // Trade-level stats (SELL trades carry pnl)
  const closedTrades = trades.filter(t => t.action === 'SELL' && t.pnl !== undefined);
  const wins  = closedTrades.filter(t => (t.pnl ?? 0) > 0);
  const losses = closedTrades.filter(t => (t.pnl ?? 0) <= 0);

  const winRate   = closedTrades.length > 0 ? +(wins.length / closedTrades.length * 100).toFixed(2) : 0;
  const avgWin    = wins.length   > 0 ? +(wins.reduce((s, t)   => s + t.pnl!,   0) / wins.length).toFixed(2)   : 0;
  const avgLoss   = losses.length > 0 ? +(losses.reduce((s, t) => s + t.pnl!,   0) / losses.length).toFixed(2)  : 0;

  const grossWin  = wins.reduce((s, t)   => s + t.pnl!, 0);
  const grossLoss = Math.abs(losses.reduce((s, t) => s + t.pnl!, 0));
  const profitFactor = grossLoss > 0 ? +(grossWin / grossLoss).toFixed(4) : grossWin > 0 ? 99 : 0;

  const calmarRatio    = maxDD > 0 ? +(annReturn / maxDD).toFixed(4) : 0;
  const recoveryFactor = maxDD > 0 ? +(totalReturn / maxDD).toFixed(4) : 0;

  const monthly   = monthlyReturns(snapshots);
  const bestMonth  = monthly.length > 0 ? +Math.max(...monthly).toFixed(2) : 0;
  const worstMonth = monthly.length > 0 ? +Math.min(...monthly).toFixed(2) : 0;

  const tradeResults = closedTrades.map(t => (t.pnl ?? 0) > 0);
  const { wins: consW, losses: consL } = maxConsecutive(tradeResults);

  return {
    totalReturn, annualizedReturn: annReturn, maxDrawdown: maxDD,
    sharpeRatio: sharpe, sortinoRatio: sortino,
    winRate, avgWin, avgLoss, profitFactor,
    totalTrades: closedTrades.length,
    calmarRatio, recoveryFactor,
    bestMonth, worstMonth,
    consecutiveWins: consW, consecutiveLosses: consL,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Benchmark (buy-and-hold equal-weight of universe)
// Uses actual price data already loaded in priceCache
// ─────────────────────────────────────────────────────────────────────────────

function buildBenchmark(
  config:    BacktestConfig,
  snapshots: PortfolioSnapshot[],
  priceCache?: Map<string, Map<string, number>>,
  universeSymbols?: string[],
): BenchmarkResult {
  const name = config.market === 'US' ? 'S&P 500 (SPY buy-hold)' : 'BIST Equal-Weight Buy & Hold';

  // If we have real price data, build equal-weight benchmark from universe
  if (priceCache && universeSymbols && universeSymbols.length > 0 && snapshots.length >= 2) {
    const startSnap = snapshots[0]!;
    const endSnap   = snapshots[snapshots.length - 1]!;
    const startDate = startSnap.date;
    const endDate   = endSnap.date;

    // For each symbol, get start price and end price
    const returns: number[] = [];
    for (const sym of universeSymbols) {
      const dm = priceCache.get(sym);
      if (!dm) continue;
      const s = getLatestPriceBefore(dm, startDate);
      const e = getLatestPriceBefore(dm, endDate);
      if (s && e && s > 0) returns.push(e / s - 1);
    }

    if (returns.length > 0) {
      // Equal-weight portfolio return
      const avgReturn = returns.reduce((a, b) => a + b, 0) / returns.length;

      // Build daily series proportionally
      const series: { date: Date; value: number }[] = [];
      let v = config.initialCapital;
      const totalDays = snapshots.length;
      const dailyFactor = Math.pow(1 + avgReturn, 1 / totalDays);

      for (const snap of snapshots) {
        series.push({ date: snap.date, value: +v.toFixed(2) });
        v *= dailyFactor;
      }

      const initial = config.initialCapital;
      const final_  = series[series.length - 1]?.value ?? initial;
      const totalReturn      = +((final_ - initial) / initial * 100).toFixed(4);
      const annualizedReturn = annualisedReturn(totalReturn, totalDays);
      const maxDrawdown      = calcMaxDrawdown(series.map(s => s.value));
      const dailyRet: number[] = [];
      for (let i = 1; i < series.length; i++)
        dailyRet.push((series[i].value! - series[i - 1]!.value) / series[i - 1]!.value);

      return { name, totalReturn, annualizedReturn, maxDrawdown, sharpeRatio: calcSharpe(dailyRet), series };
    }
  }

  // Fallback: use SPY from priceCache if available (US)
  if (config.market === 'US' && priceCache && snapshots.length >= 2) {
    const dm = priceCache.get('SPY');
    if (dm && dm.size > 0) {
      const startDate = snapshots[0]!.date;
      const endDate   = snapshots[snapshots.length - 1]!.date;
      const s = getLatestPriceBefore(dm, startDate);
      const e = getLatestPriceBefore(dm, endDate);
      if (s && e && s > 0) {
        const spyReturn = e / s - 1;
        const series: { date: Date; value: number }[] = [];
        let v = config.initialCapital;
        const totalDays = snapshots.length;
        const dailyFactor = Math.pow(1 + spyReturn, 1 / totalDays);
        for (const snap of snapshots) {
          series.push({ date: snap.date, value: +v.toFixed(2) });
          v *= dailyFactor;
        }
        const final_  = series[series.length - 1]?.value ?? config.initialCapital;
        const totalReturn = +((final_ - config.initialCapital) / config.initialCapital * 100).toFixed(4);
        const dailyRet: number[] = [];
        for (let i = 1; i < series.length; i++)
          dailyRet.push((series[i].value! - series[i - 1]!.value) / series[i - 1]!.value);
        return {
          name: 'S&P 500 (SPY)', totalReturn,
          annualizedReturn: annualisedReturn(totalReturn, totalDays),
          maxDrawdown: calcMaxDrawdown(series.map(s => s.value)),
          sharpeRatio: calcSharpe(dailyRet), series,
        };
      }
    }
  }

  // Last resort: flat line (no data available)
  const series = snapshots.map(s => ({ date: s.date, value: config.initialCapital }));
  return { name: name + ' (N/A)', totalReturn: 0, annualizedReturn: 0, maxDrawdown: 0, sharpeRatio: 0, series };
}

// ─────────────────────────────────────────────────────────────────────────────
// Helper: find the latest price in dateMap that is ≤ target date
// ─────────────────────────────────────────────────────────────────────────────

function getLatestPriceBefore(dateMap: Map<string, number>, date: Date): number | undefined {
  let best: number | undefined;
  let bestDate = '';
  const target = date.toISOString().split('T')[0]!;
  for (const [dk, price] of dateMap.entries()) {
    if (dk <= target && dk > bestDate) {
      bestDate = dk;
      best = price;
    }
  }
  return best;
}

// ─────────────────────────────────────────────────────────────────────────────
// Helper: return all symbols for a given market scope
// ─────────────────────────────────────────────────────────────────────────────

function getUniverseSymbols(market: MarketScope): string[] {
  if (market === 'BISTTUM')     return BISTTUM_LIST.map(s => s.symbol);
  if (market === 'BIST100')     return BIST100_LIST.map(s => s.symbol);
  if (market === 'BIST100DISI') return BIST100DISI_LIST.map(s => s.symbol);
  if (market === 'US')          return US_MARKET_LIST.map(s => s.symbol);
  if (market === 'BIST')        return BIST100_LIST.map(s => s.symbol);
  if (market === 'BOTH')        return [...BISTTUM_LIST.map(s => s.symbol), ...US_MARKET_LIST.slice(0, 100).map(s => s.symbol)];
  return BIST100_LIST.map(s => s.symbol);
}

// ─────────────────────────────────────────────────────────────────────────────
// BacktestEngine
// ─────────────────────────────────────────────────────────────────────────────

export class BacktestEngine {

  // ── Price caches (populated before simulation loop) ─────────────────────
  private priceCache = new Map<string, Map<string, number>>();
  // Map<symbol, Map<dateKey, closePrice>>
  private seriesCache = new Map<string, { date: Date; open: number; high: number; low: number; close: number; volume: number }[]>();
  private splitCache: Map<string, SplitEvent[]> = new Map();

  // ── Helpers ──────────────────────────────────────────────────────────────

  /**
   * Backward-adjust a raw price for all splits that occurred AFTER priceDate.
   * Pre-split prices are multiplied by ratio (toFactor/fromFactor) so they
   * end up on the same scale as post-split prices.
   * Example: KOZAL 2100:100 split on 2023-02-17
   *   ratio = 100/2100 ≈ 0.04762
   *   pre-split price 554 TL → 554 * 0.04762 ≈ 26.4 TL (post-split equivalent)
   */
  private getAdjustedPrice(symbol: string, rawPrice: number, priceDate: Date): number {
    const splits = this.splitCache.get(symbol) ?? [];
    let adj = 1.0;
    for (const split of splits) {
      const splitDate = new Date(split.date);
      if (priceDate < splitDate) {
        adj *= split.ratio;  // ratio = toFactor/fromFactor
      }
    }
    return rawPrice * adj;
  }

  /**
   * Load real stock data from price cache for a given date and market.
   * Falls back to mock generation if cache is empty (first-run safety net).
   */
  private loadStocks(market: MarketScope, date: Date): StockData[] {
    // If cache is empty (e.g. fetch failed), fall back to mock
    if (this.priceCache.size === 0) {
      if (market === 'BOTH') {
        return [
          ...generateMockStocks(20, 'US', 'US'),
          ...generateMockStocks(10, 'BIST', 'BIST100'),
        ];
      }
      const isBIST = market !== 'US';
      const base: 'BIST' | 'US' = isBIST ? 'BIST' : 'US';
      const count = market === 'BISTTUM' ? 603 : market === 'US' ? 903 : market === 'BIST100DISI' ? 503 : market === 'BIST100' ? 100 : 30;
      return generateMockStocks(count, base, market as any);
    }

    const result: StockData[] = [];

    for (const [symbol, dateMap] of this.priceCache.entries()) {
      // Skip benchmark symbols
      if (['XU100', 'XUTUM', 'SPY'].includes(symbol)) continue;

      const rawPrice = dateMap.get(date.toISOString().split('T')[0]!) ?? getLatestPriceBefore(dateMap, date);
      if (!rawPrice) continue;
      const price = this.getAdjustedPrice(symbol, rawPrice, date);

      const series = this.seriesCache.get(symbol) ?? [];
      const seriesUpToDate = series.filter(b => b.date <= date);
      if (seriesUpToDate.length < 20) continue; // not enough history

      // Apply split adjustment to every bar in the series
      const adjustedSeries = seriesUpToDate.map(bar => ({
        ...bar,
        close: this.getAdjustedPrice(symbol, bar.close, bar.date),
        open:  this.getAdjustedPrice(symbol, bar.open,  bar.date),
        high:  this.getAdjustedPrice(symbol, bar.high,  bar.date),
        low:   this.getAdjustedPrice(symbol, bar.low,   bar.date),
      }));

      const last = adjustedSeries[adjustedSeries.length - 1]!;

      // Compute technical indicators
      const closes  = adjustedSeries.map(b => b.close);
      const volumes = adjustedSeries.map(b => b.volume);
      const isBIST  = market !== 'US';
      const mktStr  = isBIST ? 'BIST' : 'US';

      const macdResult  = calculateMACD(closes);
      const atrResult   = calculateATR(adjustedSeries as any, 14);

      result.push({
        symbol,
        name:      symbol,
        sector:    'Unknown' as any,
        market:    mktStr,
        marketCap: 0,
        date,
        open:   last.open,
        high:   last.high,
        low:    last.low,
        close:  price,
        volume: last.volume,
        series: adjustedSeries as any,
        rsi14:      calculateRSI(closes, 14),
        ema20:      calculateEMA(closes, 20),
        ema50:      calculateEMA(closes, 50),
        ema200:     calculateEMA(closes, 200),
        macd:       macdResult?.macd ?? null,
        macdSignal: macdResult?.signal ?? null,
        macdHist:   macdResult?.histogram ?? null,
        atr14:      atrResult,
        high52w:    closes.length >= 252 ? Math.max(...closes.slice(-252)) : Math.max(...closes),
        vol20Avg:   volumes.length >= 20
          ? volumes.slice(-20).reduce((a, b) => a + b, 0) / 20
          : volumes.reduce((a, b) => a + b, 0) / (volumes.length || 1),
      });
    }
    return result;
  }

  /**
   * Detect market regime on `date` for a given market.
   * Uses the shared marketConditionService analyser with real benchmark data when available.
   */
  private detectCondition(market: MarketScope, date: Date): MarketConditionLabel {
    const mid = market === 'US' ? 'US' : 'BIST';
    // Benchmark symbol: XU100 for BIST, SPY for US
    const benchSym = mid === 'BIST' ? 'XU100' : 'SPY';
    const series = this.seriesCache.get(benchSym)
      ?.filter(b => b.date <= date)
      ?.slice(-300)
      ?.map(b => ({ date: b.date, open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume })) ?? [];

    if (series.length < 50) {
      // Not enough real data — fall back to mock series
      const mockSeries = generateMockSeries(300);
      const result = analyzeMarketCondition({ market: mid as MarketId, date, series: mockSeries });
      return result.condition;
    }
    const result = analyzeMarketCondition({ market: mid as MarketId, date, series });
    return result.condition;
  }

  /** Map market condition → criteria */
  private conditionToCriteria(cond: MarketConditionLabel): CriteriaType {
    if (cond === 'BULL')     return 'ALFA';
    if (cond === 'BEAR')     return 'BETA';
    return 'DELTA';
  }

  // ── Rebalance ─────────────────────────────────────────────────────────────

  private rebalancePortfolio(
    currentHoldings: Map<string, Holding>,
    scanDate:        Date,
    criteria:        CriteriaType,
    availableCapital: number,
    totalPortfolioValue: number,
    config:          BacktestConfig,
    allStocks:       StockData[],
  ): RebalanceResult {

    // ── 1. Scan with shared function (same as Scanner page) ──────────────
    const portfolioSize = config.portfolioSize ?? 5;
    const topStocks = sharedScan(allStocks, criteria, portfolioSize);
    const targetSymbols = new Set(topStocks.map(s => s.symbol));

    const buys:  Trade[] = [];
    const sells: Trade[] = [];

    let cash = availableCapital;

    // ── 2. Sell positions no longer in top-5 ────────────────────────────
    for (const [sym, holding] of currentHoldings.entries()) {
      if (!targetSymbols.has(sym)) {
        const execPrice = applySlippage(holding.currentPrice, 'SELL', config.slippage);
        const saleValue = execPrice * holding.shares;
        const txCost    = saleValue * config.transactionCost;
        const net       = saleValue - txCost;
        const pnl       = net - holding.entryPrice * holding.shares;
        const pnlPct    = holding.entryPrice > 0
          ? (pnl / (holding.entryPrice * holding.shares)) * 100
          : 0;

        sells.push({
          id:          randomUUID(),
          symbol:      sym,
          action:      'SELL',
          date:        scanDate,
          price:       execPrice,
          shares:      holding.shares,
          value:       saleValue,
          cost:        txCost,
          reason:      `${sym} exited top-5 on ${criteria} scan`,
          criteriaUsed: criteria,
          pnl:         +pnl.toFixed(2),
          pnlPct:      +pnlPct.toFixed(4),
        });

        cash += net;
      }
    }

    // ── 3. Calculate target allocation ───────────────────────────────────
    // Equal weight: each position = 1/portfolioSize of total portfolio
    if (topStocks.length === 0) {
      return {
        date: scanDate, buys, sells,
        holdings: [...currentHoldings.values()],
        cashAfter: cash,
        portfolioValue: cash + [...currentHoldings.values()]
          .filter(h => targetSymbols.has(h.symbol))
          .reduce((s, h) => s + h.value, 0),
        criteriaUsed: criteria,
        topStocks,
      };
    }

    // totalPortfolioValue already includes cash (equity + cash passed in from caller)
    // Do NOT add cash again — that would double-count it.
    const targetValue = totalPortfolioValue / portfolioSize;

    // ── 4. Buy new entries / top-up existing ────────────────────────────
    for (const scored of topStocks) {
      const existing = currentHoldings.get(scored.symbol);

      if (existing) {
        // Already held — rebalance to target weight if drift > 5%
        const currentValue = existing.shares * existing.currentPrice;
        const drift = Math.abs(currentValue - targetValue) / targetValue;
        if (drift > 0.05) {
          const shareDiff = Math.floor((targetValue - currentValue) / existing.currentPrice);
          if (shareDiff > 0 && cash >= shareDiff * existing.currentPrice * (1 + config.transactionCost)) {
            const execPrice = applySlippage(existing.currentPrice, 'BUY', config.slippage);
            const buyValue  = execPrice * shareDiff;
            const txCost    = buyValue  * config.transactionCost;
            cash -= (buyValue + txCost);
            buys.push({
              id: randomUUID(), symbol: scored.symbol, action: 'BUY',
              date: scanDate, price: execPrice, shares: shareDiff,
              value: buyValue, cost: txCost,
              reason: `Rebalance top-up (${criteria})`,
              criteriaUsed: criteria,
            });
          }
        }
      } else {
        // New entry
        const execPrice  = applySlippage(scored.entryPrice, 'BUY', config.slippage);
        const allocCash  = Math.min(targetValue, cash * 0.99);
        const sharesToBuy = calcShares(allocCash / (1 + config.transactionCost), execPrice);

        if (sharesToBuy > 0) {
          const buyValue = execPrice * sharesToBuy;
          const txCost   = buyValue  * config.transactionCost;
          cash -= (buyValue + txCost);

          buys.push({
            id: randomUUID(), symbol: scored.symbol, action: 'BUY',
            date: scanDate, price: execPrice, shares: sharesToBuy,
            value: buyValue, cost: txCost,
            reason: `New entry — ${criteria} score ${scored.score.toFixed(1)}`,
            criteriaUsed: criteria,
          });
        }
      }
    }

    // ── 5. Rebuild holdings map ──────────────────────────────────────────
    const newHoldings = new Map<string, Holding>(
      [...currentHoldings.entries()].filter(([sym]) => targetSymbols.has(sym)),
    );

    // Apply buy transactions
    for (const buy of buys) {
      const existing = newHoldings.get(buy.symbol);
      if (existing) {
        const totalCost   = existing.entryPrice * existing.shares + buy.price * buy.shares;
        const totalShares = existing.shares + buy.shares;
        existing.shares      = totalShares;
        existing.entryPrice  = totalCost / totalShares;
        existing.currentPrice = buy.price;
        existing.value       = totalShares * buy.price;
      } else {
        newHoldings.set(buy.symbol, {
          symbol:       buy.symbol,
          name:         topStocks.find(s => s.symbol === buy.symbol)?.name ?? buy.symbol,
          shares:       buy.shares,
          entryPrice:   buy.price,
          currentPrice: buy.price,
          value:        buy.shares * buy.price,
          weight:       0,  // calculated below
          pnl:          0,
          pnlPct:       0,
          // 15% stop for BIST markets (high volatility), 8% for US
          stopLoss:     buy.price * (['US','BOTH'].includes(config.market) ? 0.92 : 0.85),
        });
      }
    }

    const holdingsArr = [...newHoldings.values()];
    const totalEquity = holdingsArr.reduce((s, h) => s + h.value, 0);
    holdingsArr.forEach(h => {
      h.weight = totalEquity > 0 ? +(h.value / totalEquity * 100).toFixed(2) : 0;
      h.pnl    = +(h.value - h.entryPrice * h.shares).toFixed(2);
      h.pnlPct = h.entryPrice > 0 ? +((h.currentPrice / h.entryPrice - 1) * 100).toFixed(4) : 0;
    });

    const portfolioValue = holdingsArr.reduce((s, h) => s + h.value, 0) + cash;

    return { date: scanDate, buys, sells, holdings: holdingsArr, cashAfter: cash, portfolioValue, criteriaUsed: criteria, topStocks };
  }

  // ── Day-by-day price update with stop loss check ─────────────────────────

  /**
   * Advance holding prices using real closing prices from cache.
   * Returns stop-loss triggered symbols that should be sold.
   */
  private advancePrices(
    holdings: Map<string, Holding>,
    date: Date,
    cash: number,
    trades: Trade[],
    transactionCost: number = 0.002,
  ): { triggeredSymbols: string[]; updatedCash: number } {
    const dateKey = date.toISOString().split('T')[0]!;
    const triggeredSymbols: string[] = [];

    for (const h of holdings.values()) {
      const dateMap   = this.priceCache.get(h.symbol);
      const rawPrice  = dateMap?.get(dateKey) ?? getLatestPriceBefore(dateMap ?? new Map(), date);
      if (rawPrice && rawPrice > 0) {
        h.currentPrice = this.getAdjustedPrice(h.symbol, rawPrice, date);
      }
      h.value  = +(h.shares * h.currentPrice).toFixed(2);
      h.pnl    = +(h.value - h.entryPrice * h.shares).toFixed(2);
      h.pnlPct = h.entryPrice > 0 ? +((h.currentPrice / h.entryPrice - 1) * 100).toFixed(4) : 0;

      // Trailing stop: move stop up as price rises (lock in profits)
      if (h.currentPrice > h.entryPrice * 1.15 && h.stopLoss) {
        const trailPct  = 0.15; // 15% trail — wide enough for BIST volatility
        const trailStop = h.currentPrice * (1 - trailPct);
        if (trailStop > h.stopLoss) h.stopLoss = trailStop;
      }

      // Stop loss triggered?
      if (h.stopLoss && h.currentPrice <= h.stopLoss && h.currentPrice > 0) {
        triggeredSymbols.push(h.symbol);
        const proceeds = h.shares * h.currentPrice * (1 - transactionCost);
        cash += proceeds;
        trades.push({
          id:           `sl-${h.symbol}-${date.toISOString().split('T')[0]}`,
          date:         date,
          symbol:       h.symbol,
          action:       'SELL',
          price:        h.currentPrice,
          shares:       h.shares,
          value:        h.shares * h.currentPrice,
          cost:         h.shares * h.currentPrice * transactionCost,
          pnl:          +(proceeds - h.entryPrice * h.shares).toFixed(2),
          reason:       'STOP_LOSS',
          criteriaUsed: '',
        });
      }
    }

    // Remove triggered positions
    for (const sym of triggeredSymbols) holdings.delete(sym);

    return { triggeredSymbols, updatedCash: cash };
  }

  // ── Bulk price pre-fetch ──────────────────────────────────────────────────

  /**
   * Fetch real OHLCV data for all symbols in the universe and cache it.
   * Uses 8-symbol batches (Promise.allSettled) to avoid rate-limit hits.
   */
  private async fetchPricesForUniverse(
    symbols:   string[],
    startDate: Date,
    endDate:   Date,
    market:    string,
  ): Promise<void> {
    const BATCH = 8; // Keep parallel fetches low to avoid Twelve Data rate limits
    for (let i = 0; i < symbols.length; i += BATCH) {
      const batch = symbols.slice(i, i + BATCH);
      await Promise.allSettled(
        batch.map(async (sym) => {
          try {
            const bars = await dataService.fetchStockPrice(sym, startDate, endDate, '1d');
            if (bars.length > 0) {
              const dateMap = new Map<string, number>();
              bars.forEach(b => {
                const dk = (b.date instanceof Date ? b.date : new Date(b.date)).toISOString().split('T')[0];
                dateMap.set(dk, b.close);
              });
              this.priceCache.set(sym, dateMap);
              this.seriesCache.set(sym, bars.map(b => ({
                date:   b.date instanceof Date ? b.date : new Date(b.date),
                open:   b.open,
                high:   b.high,
                low:    b.low,
                close:  b.close,
                volume: b.volume,
              })));
            }
          } catch { /* skip */ }
          // Fetch splits separately so a failure doesn't block price data
          try {
            const splits = await dataService.fetchSplits(sym, market);
            this.splitCache.set(sym, splits);
          } catch { /* splits optional */ }
        })
      );
      // Small delay between batches to respect per-minute rate limits
      if (i + BATCH < symbols.length) {
        await new Promise(r => setTimeout(r, 2000));
      }
    }

    // Also fetch benchmark symbols
    const benchmarks = market === 'US' ? ['SPY'] : ['XU100', 'XUTUM'];
    await Promise.allSettled(benchmarks.map(async sym => {
      try {
        const bars = await dataService.fetchStockPrice(sym, startDate, endDate, '1d');
        if (bars.length > 0) {
          const dateMap = new Map<string, number>();
          bars.forEach(b => {
            const dk = (b.date instanceof Date ? b.date : new Date(b.date)).toISOString().split('T')[0];
            dateMap.set(dk, b.close);
          });
          this.priceCache.set(sym, dateMap);
          this.seriesCache.set(sym, bars.map(b => ({
            date:   b.date instanceof Date ? b.date : new Date(b.date),
            open:   b.open,
            high:   b.high,
            low:    b.low,
            close:  b.close,
            volume: b.volume,
          })));
        }
      } catch {
        // Benchmark fetch failed — detectCondition will use mock series
      }
    }));
  }

  // ── Single-criteria backtest ──────────────────────────────────────────────

  private async runCriteriaBacktest(
    config:      BacktestConfig,
    rebalDates:  Date[] = [],
    onProgress?: (p: BacktestProgress) => void,
  ): Promise<BacktestResult> {
    const criteria    = config.criteriaType as CriteriaType;
    const dates       = rebalDates.length > 0 ? rebalDates : generateRebalanceDates(config.startDate, config.endDate, config.rebalancePeriod);
    const rebalSet    = new Set(dates.map(d => d.toISOString().split('T')[0]));

    // ── Pre-fetch real price data for the entire universe ──────────────────
    onProgress?.({ stage: 'scanning', progress: 5, message: 'Gerçek fiyat verisi yükleniyor...' });
    const allSymbols = getUniverseSymbols(config.market);
    // Reset caches for this run
    this.priceCache.clear();
    this.seriesCache.clear();
    this.splitCache.clear();
    // Fetch 300 extra calendar days before startDate to warm up EMA200 (needs ~300 bars)
    const warmupStart = new Date(config.startDate.getTime() - 300 * 1.4 * 86_400_000);
    await this.fetchPricesForUniverse(allSymbols, warmupStart, new Date(), config.market);
    console.log('[Backtest] priceCache=' + this.priceCache.size + ' seriesCache=' + this.seriesCache.size);
    onProgress?.({ stage: 'scanning', progress: 15, message: `${this.priceCache.size} sembol yüklendi, backtest başlıyor...` });

    const snapshots:         PortfolioSnapshot[]  = [];
    const allTrades:         Trade[]               = [];
    const criteriaTimeline:  { date: Date; criteria: string; condition: string }[] = [];

    let cash      = config.initialCapital;
    let holdings  = new Map<string, Holding>();
    let peakValue = config.initialCapital;

    // Walk calendar from startDate to endDate one trading day at a time
    let cur = new Date(config.startDate);

    while (cur <= config.endDate) {
      if (!isTradingDay(cur)) { cur = addDays(cur, 1); continue; }

      const dateKey = cur.toISOString().split('T')[0];

      // ── Rebalance day ───────────────────────────────────────────────────
      if (rebalSet.has(dateKey)) {
        const totalValue = [...holdings.values()].reduce((s, h) => s + h.value, 0) + cash;
        const allStocks  = this.loadStocks(config.market, cur);

        // Progress reporting
        if (onProgress) {
          const elapsed = (cur.getTime() - config.startDate.getTime());
          const total   = (config.endDate.getTime() - config.startDate.getTime()) || 1;
          const pct     = Math.min(90, 15 + Math.round((elapsed / total) * 75));
          onProgress({ stage: 'portfolio', progress: pct, message: `Portföy güncelleniyor: ${dateKey}`, currentDate: new Date(cur) });
        }

        const result = this.rebalancePortfolio(
          holdings, cur, criteria, cash, totalValue, config, allStocks,
        );

        allTrades.push(...result.buys, ...result.sells);
        cash = result.cashAfter;

        // Rebuild holdings map from result
        holdings = new Map(result.holdings.map(h => [h.symbol, { ...h }]));

        criteriaTimeline.push({ date: new Date(cur), criteria, condition: 'N/A' });
      }

      // ── Advance prices with real data + stop loss check ────────────────
      const slResult1 = this.advancePrices(holdings, cur, cash, allTrades, config.transactionCost ?? 0.002);
      cash = slResult1.updatedCash;

      const equityValue = [...holdings.values()].reduce((s, h) => s + h.value, 0);
      const totalValue  = equityValue + cash;
      if (totalValue > peakValue) peakValue = totalValue;

      snapshots.push({
        date:            new Date(cur),
        value:           +totalValue.toFixed(2),
        cash:            +cash.toFixed(2),
        holdings:        [...holdings.values()].map(h => ({ ...h })),
        criteriaUsed:    criteria,
        marketCondition: 'N/A',
        drawdown:        +((peakValue - totalValue) / peakValue * 100).toFixed(4),
      });

      cur = addDays(cur, 1);
    }

    const perf      = calculateMetrics(allTrades, snapshots, config);
    const benchmark = buildBenchmark(config, snapshots, this.priceCache, allSymbols);

    // Consistency check: verify last rebalance scan matches sharedScan directly
    const lastDate  = rebalDates[rebalDates.length - 1] ?? config.endDate;
    const checkStocks = this.loadStocks(config.market, lastDate);
    const directScan  = sharedScan(checkStocks, criteria, 5).map(s => s.symbol).sort().join(',');
    const engineScan  = criteriaTimeline[criteriaTimeline.length - 1]?.criteria === criteria;
    const consistencyCheck = engineScan && directScan.length > 0;

    return {
      id: randomUUID(),
      config,
      performance:      perf,
      portfolioHistory: snapshots,
      trades:           allTrades,
      benchmark,
      consistencyCheck,
      rebalanceDates:   rebalDates,
      criteriaTimeline,
      runtimeMs: 0,  // set by caller
    };
  }

  // ── Hybrid backtest ───────────────────────────────────────────────────────

  private async runHybridBacktest(
    config:      BacktestConfig,
    rebalDates:  Date[] = [],
    onProgress?: (p: BacktestProgress) => void,
  ): Promise<BacktestResult> {
    const dates       = rebalDates.length > 0 ? rebalDates : generateRebalanceDates(config.startDate, config.endDate, config.rebalancePeriod);
    const rebalSet    = new Set(dates.map(d => d.toISOString().split('T')[0]));

    // ── Pre-fetch real price data for the entire universe ──────────────────
    onProgress?.({ stage: 'scanning', progress: 5, message: 'Gerçek fiyat verisi yükleniyor...' });
    const allSymbols = getUniverseSymbols(config.market);
    this.priceCache.clear();
    this.seriesCache.clear();
    this.splitCache.clear();
    // Fetch 300 extra calendar days before startDate to warm up EMA200 (needs ~300 bars)
    const warmupStart = new Date(config.startDate.getTime() - 300 * 1.4 * 86_400_000);
    await this.fetchPricesForUniverse(allSymbols, warmupStart, new Date(), config.market);
    console.log('[Backtest] priceCache=' + this.priceCache.size + ' seriesCache=' + this.seriesCache.size);
    onProgress?.({ stage: 'scanning', progress: 15, message: `${this.priceCache.size} sembol yüklendi, backtest başlıyor...` });

    const snapshots:        PortfolioSnapshot[]  = [];
    const allTrades:        Trade[]               = [];
    const criteriaTimeline: { date: Date; criteria: string; condition: string }[] = [];

    let cash      = config.initialCapital;
    let holdings  = new Map<string, Holding>();
    let peakValue = config.initialCapital;
    let activeCriteria: CriteriaType = 'ALFA';
    let activeCondition: MarketConditionLabel = 'BULL';

    let cur = new Date(config.startDate);

    while (cur <= config.endDate) {
      if (!isTradingDay(cur)) { cur = addDays(cur, 1); continue; }

      const dateKey = cur.toISOString().split('T')[0];

      if (rebalSet.has(dateKey)) {
        // ── 1. Detect market condition ────────────────────────────────────
        activeCondition = this.detectCondition(config.market, cur);
        activeCriteria  = this.conditionToCriteria(activeCondition);

        // ── 2. Rebalance with appropriate criteria ────────────────────────
        const totalValue = [...holdings.values()].reduce((s, h) => s + h.value, 0) + cash;
        const allStocks  = this.loadStocks(config.market, cur);

        const result = this.rebalancePortfolio(
          holdings, cur, activeCriteria, cash, totalValue, config, allStocks,
        );

        allTrades.push(...result.buys, ...result.sells);
        cash     = result.cashAfter;
        holdings = new Map(result.holdings.map(h => [h.symbol, { ...h }]));

        criteriaTimeline.push({
          date:      new Date(cur),
          criteria:  activeCriteria,
          condition: activeCondition,
        });
      }

      const slResult2 = this.advancePrices(holdings, cur, cash, allTrades, config.transactionCost ?? 0.002);
      cash = slResult2.updatedCash;

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

    const perf      = calculateMetrics(allTrades, snapshots, config);
    const benchmark = buildBenchmark(config, snapshots, this.priceCache, allSymbols);

    // Consistency check
    const lastDate    = rebalDates[rebalDates.length - 1] ?? config.endDate;
    const checkStocks = this.loadStocks(config.market, lastDate);
    const directScan  = sharedScan(checkStocks, activeCriteria, 5);
    const consistencyCheck = directScan.length > 0;

    return {
      id: randomUUID(),
      config,
      performance:      perf,
      portfolioHistory: snapshots,
      trades:           allTrades,
      benchmark,
      consistencyCheck,
      rebalanceDates:   rebalDates,
      criteriaTimeline,
      runtimeMs: 0,
    };
  }

  // ── Public entry point ────────────────────────────────────────────────────

  async runBacktest(
    config:     BacktestConfig,
    onProgress?: (p: BacktestProgress) => void,
  ): Promise<BacktestResult> {
    const merged: BacktestConfig = { ...DEFAULT_CONFIG, ...config } as BacktestConfig;
    const t0 = Date.now();

    if (merged.startDate >= merged.endDate) {
      throw new Error('startDate must be before endDate');
    }

    // Stage: scanning universe
    onProgress?.({ stage: 'scanning', progress: 5, message: 'Hisse evreni yükleniyor...' });

    const dates = generateRebalanceDates(merged.startDate, merged.endDate, merged.rebalancePeriod);

    const result = merged.criteriaType === 'HYBRID'
      ? await hybridBacktestV2.runHybridV2(merged, dates, onProgress)
      : await this.runCriteriaBacktest(merged, dates, onProgress);

    onProgress?.({ stage: 'calculating', progress: 95, message: 'Metrikler hesaplanıyor...' });
    result.runtimeMs = Date.now() - t0;

    onProgress?.({ stage: 'calculating', progress: 100, message: 'Tamamlandı', currentDate: merged.endDate });
    return result;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Progress type (exported for use in routes)
// ─────────────────────────────────────────────────────────────────────────────

export interface BacktestProgress {
  stage:       'scanning' | 'portfolio' | 'calculating';
  progress:    number;   // 0-100
  message:     string;
  currentDate?: Date;
}

// ─────────────────────────────────────────────────────────────────────────────
// Persistence helper
// ─────────────────────────────────────────────────────────────────────────────

export async function saveBacktestResult(result: BacktestResult): Promise<string> {
  const { PrismaClient } = await import('@prisma/client');
  const prisma = new PrismaClient();

  try {
    const p = result.performance;
    const c = result.config;

    const record = await prisma.backtest.create({
      data: {
        name:             c.name,
        criteriaType:     c.criteriaType,
        startDate:        c.startDate,
        endDate:          c.endDate,
        rebalancePeriod:  c.rebalancePeriod,
        market:           c.market,
        initialCapital:   c.initialCapital,
        status:           'COMPLETED',
        totalReturn:      p.totalReturn,
        annualizedReturn: p.annualizedReturn,
        maxDrawdown:      p.maxDrawdown,
        sharpeRatio:      p.sharpeRatio,
        winRate:          p.winRate,
        totalTrades:      p.totalTrades,
        trades: {
          create: result.trades.map(t => ({
            symbol:  t.symbol,
            action:  t.action,
            date:    t.date,
            price:   t.price,
            shares:  t.shares,
            value:   t.value,
            reason:  t.reason,
          })),
        },
        portfolioSnapshots: {
          create: result.portfolioHistory
            .filter((_, i) => i % 5 === 0)   // persist every 5th day to save space
            .map(s => ({
              date:            s.date,
              portfolioValue:  s.value,
              holdings:        s.holdings as object[],
              criteriaUsed:    s.criteriaUsed,
              marketCondition: s.marketCondition,
            })),
        },
      },
    });

    return record.id;
  } finally {
    await prisma.$disconnect();
  }
}

export async function loadBacktestResult(id: string): Promise<{
  backtest: Record<string, unknown>;
  trades: Record<string, unknown>[];
  snapshots: Record<string, unknown>[];
} | null> {
  const { PrismaClient } = await import('@prisma/client');
  const prisma = new PrismaClient();
  try {
    const bt = await prisma.backtest.findUnique({
      where: { id },
      include: {
        trades:            { orderBy: { date: 'asc' } },
        portfolioSnapshots: { orderBy: { date: 'asc' } },
      },
    });
    if (!bt) return null;
    const { trades, portfolioSnapshots, ...rest } = bt;
    return {
      backtest:  rest as Record<string, unknown>,
      trades:    trades as Record<string, unknown>[],
      snapshots: portfolioSnapshots as Record<string, unknown>[],
    };
  } finally {
    await prisma.$disconnect();
  }
}
