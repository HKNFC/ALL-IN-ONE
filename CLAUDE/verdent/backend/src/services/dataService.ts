/**
 * VERDENT — Data Service
 *
 * Responsibilities:
 *  • Fetch OHLCV price data for US (Alpha Vantage / Yahoo Finance) and
 *    BIST (IsYatirim / Bigpara scraper) markets
 *  • Calculate every technical indicator needed by the criteria engine
 *  • Persist prices + indicators to PostgreSQL via Prisma
 *  • Two-level cache: in-process Map (hot) + Redis (warm)
 *    - Daily prices     : 30-day Redis TTL
 *    - Technical indic. : 24-hour Redis TTL
 *    - Fundamental data : 7-day Redis TTL
 *  • Static constituent lists for BIST-100 and S&P-500
 *
 * All indicator maths are self-contained — no external TA library
 * dependencies so the module remains lightweight and auditable.
 */

import axios, { AxiosInstance } from 'axios';
import { createClient, RedisClientType } from 'redis';

// ─── Type definitions ─────────────────────────────────────────────────────────

export interface OHLCV {
  date:   Date;
  open:   number;
  high:   number;
  low:    number;
  close:  number;
  volume: number;
}

export interface Fundamentals {
  symbol:          string;
  pe:              number | null;
  pb:              number | null;
  roe:             number | null;
  debtEquity:      number | null;
  revenueGrowth:   number | null;   // YoY %
  earningsGrowth:  number | null;   // YoY %
  freeCashFlow:    number | null;
  dividendYield:   number | null;
  currentRatio:    number | null;
  operatingMargin: number | null;
  marketCap:       number | null;
  sector:          string | null;
  fetchedAt:       Date;
}

export interface IndexData {
  index:    string;
  date:     Date;
  value:    number;
  change:   number;
  changePct: number;
}

export interface MACDResult {
  macd:        number;
  signal:      number;
  histogram:   number;
}

export interface BollingerResult {
  upper:  number;
  middle: number;
  lower:  number;
}

export interface ADXResult {
  adx:  number;
  plusDI:  number;
  minusDI: number;
}

export interface StochasticResult {
  k: number;
  d: number;
}

export interface FibonacciLevels {
  high:    number;
  low:     number;
  r236:    number;
  r382:    number;
  r500:    number;
  r618:    number;
  r786:    number;
  r1000:   number;
}

export interface TechnicalIndicators {
  ema20:          number | null;
  ema50:          number | null;
  ema200:         number | null;
  sma50:          number | null;
  sma200:         number | null;
  rsi14:          number | null;
  macd:           MACDResult | null;
  bollinger:      BollingerResult | null;
  atr14:          number | null;
  adx14:          ADXResult | null;
  stochastic:     StochasticResult | null;
  obv:            number | null;
  vwap:           number | null;
  volume20avg:    number | null;
  high52w:        number | null;
  low52w:         number | null;
  fibonacci:      FibonacciLevels | null;
}

export interface BreadthData {
  market:              string;
  date:                Date;
  advanceDeclineRatio: number;
  pctAbove200SMA:      number;
  new52wHighs:         number;
  new52wLows:          number;
  totalStocks:         number;
}

export interface SplitEvent {
  date:       string;   // "YYYY-MM-DD"
  fromFactor: number;
  toFactor:   number;
  ratio:      number;   // toFactor / fromFactor
}

interface TwelveDataSplitsResponse {
  splits?: Array<{ date: string; from_factor: string; to_factor: string; ratio: string; description: string }>;
}

// ─── Pure indicator functions ─────────────────────────────────────────────────
// All functions accept a plain number[] or OHLCV[].
// Nothing stateful — safe to call from any thread / worker.

/** Simple Moving Average */
export function calculateSMA(closes: number[], period: number): number | null {
  if (closes.length < period) return null;
  const slice = closes.slice(-period);
  return slice.reduce((s, v) => s + v, 0) / period;
}

/**
 * Exponential Moving Average — seeded from the first SMA.
 * Returns the final EMA value after processing all `closes`.
 */
export function calculateEMA(closes: number[], period: number): number | null {
  if (closes.length < period) return null;
  const k = 2 / (period + 1);
  let ema = closes.slice(0, period).reduce((s, v) => s + v, 0) / period;
  for (let i = period; i < closes.length; i++) {
    ema = closes[i] * k + ema * (1 - k);
  }
  return ema;
}

/** Full EMA series (same length as input, first `period-1` entries are null) */
export function emaSeriesFull(closes: number[], period: number): (number | null)[] {
  if (closes.length < period) return closes.map(() => null);
  const k   = 2 / (period + 1);
  const out: (number | null)[] = Array(period - 1).fill(null);
  let   ema = closes.slice(0, period).reduce((s, v) => s + v, 0) / period;
  out.push(ema);
  for (let i = period; i < closes.length; i++) {
    ema = closes[i] * k + ema * (1 - k);
    out.push(ema);
  }
  return out;
}

/**
 * RSI — Wilder's smoothed method (industry standard).
 * Period is typically 14.
 */
export function calculateRSI(closes: number[], period: number = 14): number | null {
  if (closes.length < period + 1) return null;

  // Initial average gain/loss from first `period` changes
  let avgGain = 0;
  let avgLoss = 0;
  for (let i = 1; i <= period; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff >= 0) avgGain += diff;
    else           avgLoss += Math.abs(diff);
  }
  avgGain /= period;
  avgLoss /= period;

  // Wilder smoothing for remaining bars
  for (let i = period + 1; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1];
    const gain = diff >= 0 ? diff : 0;
    const loss = diff <  0 ? Math.abs(diff) : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
  }

  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}

/**
 * MACD — (fastEMA − slowEMA), signal EMA of MACD, histogram.
 * Standard: fast=12, slow=26, signal=9.
 */
export function calculateMACD(
  closes: number[],
  fast:   number = 12,
  slow:   number = 26,
  signal: number = 9,
): MACDResult | null {
  if (closes.length < slow + signal) return null;

  const fastSeries = emaSeriesFull(closes, fast);
  const slowSeries = emaSeriesFull(closes, slow);

  // MACD line — defined only where both EMAs exist
  const macdLine: number[] = [];
  for (let i = 0; i < closes.length; i++) {
    const f = fastSeries[i];
    const s = slowSeries[i];
    if (f !== null && s !== null) macdLine.push(f - s);
  }

  if (macdLine.length < signal) return null;

  // Signal line = EMA(macdLine, signal)
  const signalVal = calculateEMA(macdLine, signal);
  if (signalVal === null) return null;

  const macdVal = macdLine[macdLine.length - 1];
  return {
    macd:      macdVal,
    signal:    signalVal,
    histogram: macdVal - signalVal,
  };
}

/**
 * Bollinger Bands — SMA ± stdDev * multiplier.
 * Standard: period=20, multiplier=2.
 */
export function calculateBollinger(
  closes:     number[],
  period:     number = 20,
  multiplier: number = 2,
): BollingerResult | null {
  if (closes.length < period) return null;
  const slice  = closes.slice(-period);
  const middle = slice.reduce((s, v) => s + v, 0) / period;
  const variance = slice.reduce((s, v) => s + (v - middle) ** 2, 0) / period;
  const stdDev = Math.sqrt(variance);
  return {
    upper:  middle + multiplier * stdDev,
    middle,
    lower:  middle - multiplier * stdDev,
  };
}

/**
 * ATR — Average True Range using Wilder's smoothing.
 * True Range = max(H-L, |H-prevC|, |L-prevC|)
 */
export function calculateATR(bars: OHLCV[], period: number = 14): number | null {
  if (bars.length < period + 1) return null;

  const trs: number[] = [];
  for (let i = 1; i < bars.length; i++) {
    const { high, low } = bars[i];
    const prevClose    = bars[i - 1].close;
    trs.push(Math.max(high - low, Math.abs(high - prevClose), Math.abs(low - prevClose)));
  }

  // Seed with simple average of first `period` TRs
  let atr = trs.slice(0, period).reduce((s, v) => s + v, 0) / period;
  for (let i = period; i < trs.length; i++) {
    atr = (atr * (period - 1) + trs[i]) / period;
  }
  return atr;
}

/**
 * ADX — Wilder's Average Directional Index with +DI / −DI.
 * Requires at least 2*period bars for a stable reading.
 */
export function calculateADX(bars: OHLCV[], period: number = 14): ADXResult | null {
  if (bars.length < 2 * period + 1) return null;

  // Directional movement
  const plusDMs:  number[] = [];
  const minusDMs: number[] = [];
  const trs:      number[] = [];

  for (let i = 1; i < bars.length; i++) {
    const curr = bars[i];
    const prev = bars[i - 1];
    const upMove   = curr.high  - prev.high;
    const downMove = prev.low   - curr.low;
    plusDMs .push(upMove   > downMove && upMove   > 0 ? upMove   : 0);
    minusDMs.push(downMove > upMove   && downMove > 0 ? downMove : 0);
    const tr = Math.max(curr.high - curr.low, Math.abs(curr.high - prev.close), Math.abs(curr.low - prev.close));
    trs.push(tr);
  }

  // Wilder smooth
  function wilderSmooth(arr: number[], p: number): number[] {
    let smoothed = arr.slice(0, p).reduce((s, v) => s + v, 0);
    const out = [smoothed];
    for (let i = p; i < arr.length; i++) {
      smoothed = smoothed - smoothed / p + arr[i];
      out.push(smoothed);
    }
    return out;
  }

  const smoothTR    = wilderSmooth(trs,      period);
  const smoothPlus  = wilderSmooth(plusDMs,  period);
  const smoothMinus = wilderSmooth(minusDMs, period);

  const dxArr: number[] = [];
  for (let i = 0; i < smoothTR.length; i++) {
    const tr = smoothTR[i];
    if (tr === 0) { dxArr.push(0); continue; }
    const plusDI  = (smoothPlus[i]  / tr) * 100;
    const minusDI = (smoothMinus[i] / tr) * 100;
    const dx = (Math.abs(plusDI - minusDI) / (plusDI + minusDI)) * 100;
    dxArr.push(dx);
  }

  if (dxArr.length < period) return null;
  const adx = dxArr.slice(-period).reduce((s, v) => s + v, 0) / period;

  const last  = smoothTR.length - 1;
  const tr    = smoothTR[last];
  const plus  = tr > 0 ? (smoothPlus[last]  / tr) * 100 : 0;
  const minus = tr > 0 ? (smoothMinus[last] / tr) * 100 : 0;

  return { adx, plusDI: plus, minusDI: minus };
}

/**
 * Full Stochastic Oscillator — %K and %D.
 * kPeriod=14, dPeriod=3 (signal line SMA of %K), slowing=3 (raw %K → smooth %K).
 */
export function calculateStochastic(
  bars:     OHLCV[],
  kPeriod:  number = 14,
  slowing:  number = 3,
  dPeriod:  number = 3,
): StochasticResult | null {
  if (bars.length < kPeriod + slowing + dPeriod - 2) return null;

  // Raw %K for each bar
  const rawK: number[] = [];
  for (let i = kPeriod - 1; i < bars.length; i++) {
    const slice = bars.slice(i - kPeriod + 1, i + 1);
    const hh = Math.max(...slice.map(b => b.high));
    const ll = Math.min(...slice.map(b => b.low));
    rawK.push(hh === ll ? 50 : ((bars[i].close - ll) / (hh - ll)) * 100);
  }

  // Slow %K = SMA(rawK, slowing)
  const slowK: number[] = [];
  for (let i = slowing - 1; i < rawK.length; i++) {
    slowK.push(rawK.slice(i - slowing + 1, i + 1).reduce((s, v) => s + v, 0) / slowing);
  }

  if (slowK.length < dPeriod) return null;

  // %D = SMA(slowK, dPeriod)
  const d = slowK.slice(-dPeriod).reduce((s, v) => s + v, 0) / dPeriod;
  return { k: slowK[slowK.length - 1], d };
}

/**
 * OBV — On Balance Volume.
 * Returns cumulative OBV value at the last bar.
 */
export function calculateOBV(bars: OHLCV[]): number | null {
  if (bars.length < 2) return null;
  let obv = 0;
  for (let i = 1; i < bars.length; i++) {
    const diff = bars[i].close - bars[i - 1].close;
    if      (diff > 0) obv += bars[i].volume;
    else if (diff < 0) obv -= bars[i].volume;
    // diff === 0 → no change
  }
  return obv;
}

/**
 * VWAP — Volume Weighted Average Price.
 * Uses the classic intra-period cumulative formula:
 *   VWAP = Σ(typical_price * volume) / Σ(volume)
 * Typically reset daily; here we compute over the entire series passed.
 */
export function calculateVWAP(bars: OHLCV[]): number | null {
  if (bars.length === 0) return null;
  let cumPV = 0;
  let cumV  = 0;
  for (const b of bars) {
    const tp = (b.high + b.low + b.close) / 3;
    cumPV += tp * b.volume;
    cumV  += b.volume;
  }
  return cumV === 0 ? null : cumPV / cumV;
}

/** Simple N-period volume average */
export function calculateVolumeAverage(bars: OHLCV[], period: number = 20): number | null {
  if (bars.length < period) return null;
  return bars.slice(-period).reduce((s, b) => s + b.volume, 0) / period;
}

/** 52-week high / low */
export function calculate52WeekRange(bars: OHLCV[]): { high: number; low: number } {
  const trailing = bars.slice(-252);   // ~252 trading days per year
  return {
    high: Math.max(...trailing.map(b => b.high)),
    low:  Math.min(...trailing.map(b => b.low)),
  };
}

/**
 * Fibonacci Retracement levels from swing high to swing low.
 * Standard levels: 0%, 23.6%, 38.2%, 50%, 61.8%, 78.6%, 100%.
 */
export function calculateFibonacci(high: number, low: number): FibonacciLevels {
  const diff = high - low;
  return {
    high,
    low,
    r236: high - diff * 0.236,
    r382: high - diff * 0.382,
    r500: high - diff * 0.500,
    r618: high - diff * 0.618,
    r786: high - diff * 0.786,
    r1000: low,
  };
}

/** Convenience: compute every indicator from a single OHLCV[] array. */
export function calculateTechnicalIndicators(bars: OHLCV[]): TechnicalIndicators {
  const closes  = bars.map(b => b.close);
  const range52 = bars.length >= 2 ? calculate52WeekRange(bars) : null;

  return {
    ema20:       calculateEMA(closes, 20),
    ema50:       calculateEMA(closes, 50),
    ema200:      calculateEMA(closes, 200),
    sma50:       calculateSMA(closes, 50),
    sma200:      calculateSMA(closes, 200),
    rsi14:       calculateRSI(closes, 14),
    macd:        calculateMACD(closes),
    bollinger:   calculateBollinger(closes),
    atr14:       calculateATR(bars, 14),
    adx14:       calculateADX(bars, 14),
    stochastic:  calculateStochastic(bars),
    obv:         calculateOBV(bars),
    vwap:        calculateVWAP(bars),
    volume20avg: calculateVolumeAverage(bars, 20),
    high52w:     range52?.high ?? null,
    low52w:      range52?.low  ?? null,
    fibonacci:   range52 ? calculateFibonacci(range52.high, range52.low) : null,
  };
}

// ─── Static constituents ──────────────────────────────────────────────────────

// ── Stock universe — single source of truth ───────────────────────────────────
import {
  BIST100_SYMBOLS,
  BIST100DISI_SYMBOLS,
  BISTTUM_SYMBOLS,
  US_MARKET_SYMBOLS,
} from './stockUniverse';

export {
  BIST100_SYMBOLS,
  BIST100DISI_SYMBOLS,
  BISTTUM_SYMBOLS,
  US_MARKET_SYMBOLS,
};

// Backward-compat alias
export { US_MARKET_SYMBOLS as SP500_SYMBOLS } from './stockUniverse';

// ─── Data adapters ────────────────────────────────────────────────────────────

interface AlphaVantageBar {
  '1. open': string; '2. high': string; '3. low': string;
  '4. close': string; '5. volume': string;
}

interface YahooBar {
  date: string; open: number; high: number; low: number; close: number; volume: number;
}

// ─── Twelve Data ──────────────────────────────────────────────────────────────
async function fetchTwelveData(
  http:      AxiosInstance,
  apiKey:    string,
  symbol:    string,
  interval:  '1d' | '1wk' | '1mo',
  startDate: Date,
  endDate:   Date,
): Promise<OHLCV[]> {
  const ivMap: Record<string, string> = { '1d': '1day', '1wk': '1week', '1mo': '1month' };
  const isBIST   = /^[A-Z]{4,5}$/.test(symbol) && !symbol.includes('.');
  const tdSymbol = isBIST ? `${symbol}:BIST` : symbol;
  const fmt      = (d: Date) => d.toISOString().slice(0, 10);

  const { data } = await http.get('https://api.twelvedata.com/time_series', {
    params: {
      symbol:     tdSymbol,
      interval:   ivMap[interval],
      start_date: fmt(startDate),
      end_date:   fmt(endDate),
      outputsize: 5000,
      order:      'ASC',
      apikey:     apiKey,
      dp:         5,
    },
    timeout: 20_000,
  });

  if (data?.status === 'error') throw new Error(`Twelve Data error (${tdSymbol}): ${data.message}`);
  if (data?.code === 429)       throw new Error(`Twelve Data rate limit (${tdSymbol})`);

  const values: Array<{ datetime: string; open: string; high: string; low: string; close: string; volume: string }> =
    data?.values ?? [];

  return values
    .map(v => ({
      date:   new Date(v.datetime),
      open:   parseFloat(v.open),
      high:   parseFloat(v.high),
      low:    parseFloat(v.low),
      close:  parseFloat(v.close),
      volume: parseFloat(v.volume) || 0,
    }))
    .filter(b => !isNaN(b.close) && b.close > 0);
}

// ── Twelve Data Batch: birden fazla sembol tek seferinde çek (Grown plan) ────
export async function fetchTwelveDataBatch(
  http:    AxiosInstance,
  apiKey:  string,
  symbols: string[],
  market:  'BIST' | 'US' = 'BIST',
): Promise<Record<string, { price: number; change: number; changePct: number; volume: number }>> {
  const tdSymbols = symbols.map(s =>
    market === 'BIST' ? `${s}:BIST` : s
  ).join(',');

  const { data } = await http.get('https://api.twelvedata.com/price', {
    params: { symbol: tdSymbols, apikey: apiKey, dp: 4 },
    timeout: 15_000,
  });

  const result: Record<string, { price: number; change: number; changePct: number; volume: number }> = {};

  // Batch response: { THYAO:BIST: { price: "45.32" }, ... }
  for (const sym of symbols) {
    const key = market === 'BIST' ? `${sym}:BIST` : sym;
    const entry = data?.[key] ?? data?.[sym];
    if (entry?.price) {
      result[sym] = {
        price:     parseFloat(entry.price)             || 0,
        change:    parseFloat(entry.change ?? '0')     || 0,
        changePct: parseFloat(entry.percent_change ?? '0') || 0,
        volume:    parseFloat(entry.volume ?? '0')     || 0,
      };
    }
  }
  return result;
}

// ── Twelve Data Technical Indicators: API-side hesaplama (Grown plan) ────────
export async function fetchTwelveIndicator(
  http:      AxiosInstance,
  apiKey:    string,
  symbol:    string,
  indicator: string,           // 'rsi' | 'macd' | 'ema' | 'adx' | 'bbands' | 'atr' | 'stoch'
  params:    Record<string, string | number>,
  market:    'BIST' | 'US' = 'BIST',
): Promise<Record<string, number | string>[]> {
  const tdSymbol = market === 'BIST' ? `${symbol}:BIST` : symbol;
  const { data } = await http.get(`https://api.twelvedata.com/${indicator}`, {
    params: {
      symbol:   tdSymbol,
      interval: '1day',
      outputsize: 100,
      order:    'ASC',
      apikey:   apiKey,
      dp:       4,
      ...params,
    },
    timeout: 15_000,
  });

  if (data?.status === 'error') throw new Error(`TD indicator error: ${data.message}`);
  return data?.values ?? [];
}

// ── Twelve Data Fundamentals (Grown plan) ─────────────────────────────────────
export async function fetchTwelveDataFundamentals(
  http:   AxiosInstance,
  apiKey: string,
  symbol: string,
  market: 'BIST' | 'US' = 'BIST',
): Promise<Record<string, unknown>> {
  const tdSymbol = market === 'BIST' ? `${symbol}:BIST` : symbol;
  const results: Record<string, unknown> = {};

  // statistics endpoint (P/E, P/B, EPS, revenue growth vb.)
  try {
    const { data: stats } = await http.get('https://api.twelvedata.com/statistics', {
      params: { symbol: tdSymbol, apikey: apiKey },
      timeout: 15_000,
    });
    if (stats?.valuations_metrics) Object.assign(results, stats.valuations_metrics);
    if (stats?.financials)         Object.assign(results, stats.financials);
    if (stats?.stock_statistics)   Object.assign(results, stats.stock_statistics);
  } catch (e) {
    console.warn(`[TD Fundamentals] statistics failed for ${symbol}:`, (e as Error).message);
  }

  // profile endpoint (sector, industry, description)
  try {
    const { data: profile } = await http.get('https://api.twelvedata.com/profile', {
      params: { symbol: tdSymbol, apikey: apiKey },
      timeout: 10_000,
    });
    if (profile) Object.assign(results, { profile });
  } catch { /* optional */ }

  return results;
}

// ── Twelve Data Quote (anlık fiyat + temel metrikler tek çağrıda) ─────────────
export async function fetchTwelveDataQuote(
  http:   AxiosInstance,
  apiKey: string,
  symbol: string,
  market: 'BIST' | 'US' = 'BIST',
) {
  const tdSymbol = market === 'BIST' ? `${symbol}:BIST` : symbol;
  const { data } = await http.get('https://api.twelvedata.com/quote', {
    params: { symbol: tdSymbol, apikey: apiKey, dp: 4 },
    timeout: 10_000,
  });
  if (data?.status === 'error') throw new Error(`TD quote error: ${data.message}`);
  return data as {
    symbol: string; name: string; currency: string; exchange: string;
    open: string; high: string; low: string; close: string;
    previous_close: string; change: string; percent_change: string;
    volume: string; fifty_two_week?: { low: string; high: string };
  };
}

async function fetchAlphaVantage(
  http:     AxiosInstance,
  apiKey:   string,
  symbol:   string,
  interval: '1d' | '1wk' | '1mo',
  startDate: Date,
  endDate:   Date,
): Promise<OHLCV[]> {
  const fnMap: Record<string, string> = { '1d': 'TIME_SERIES_DAILY_ADJUSTED', '1wk': 'TIME_SERIES_WEEKLY_ADJUSTED', '1mo': 'TIME_SERIES_MONTHLY_ADJUSTED' };
  const tsKey: Record<string, string> = { '1d': 'Time Series (Daily)', '1wk': 'Weekly Adjusted Time Series', '1mo': 'Monthly Adjusted Time Series' };

  const { data } = await http.get('https://www.alphavantage.co/query', {
    params: { function: fnMap[interval], symbol, outputsize: 'full', apikey: apiKey },
    timeout: 15_000,
  });

  const series: Record<string, AlphaVantageBar> = data[tsKey[interval]] ?? {};
  return Object.entries(series)
    .map(([dateStr, bar]) => ({
      date:   new Date(dateStr),
      open:   parseFloat(bar['1. open']),
      high:   parseFloat(bar['2. high']),
      low:    parseFloat(bar['3. low']),
      close:  parseFloat(bar['4. close']),
      volume: parseFloat(bar['5. volume']),
    }))
    .filter(b => b.date >= startDate && b.date <= endDate)
    .sort((a, b) => a.date.getTime() - b.date.getTime());
}

async function fetchYahooFinance(
  http:      AxiosInstance,
  symbol:    string,
  interval:  '1d' | '1wk' | '1mo',
  startDate: Date,
  endDate:   Date,
): Promise<OHLCV[]> {
  const ivMap: Record<string, string> = { '1d': '1d', '1wk': '1wk', '1mo': '1mo' };
  const period1 = Math.floor(startDate.getTime() / 1000);
  const period2 = Math.floor(endDate.getTime()   / 1000);

  const { data } = await http.get(
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}`,
    { params: { interval: ivMap[interval], period1, period2 }, timeout: 15_000 },
  );

  const result    = data?.chart?.result?.[0];
  const timestamps: number[] = result?.timestamp ?? [];
  const q         = result?.indicators?.quote?.[0] ?? {};

  return timestamps.map((ts: number, i: number) => ({
    date:   new Date(ts * 1000),
    open:   q.open?.[i]   ?? 0,
    high:   q.high?.[i]   ?? 0,
    low:    q.low?.[i]    ?? 0,
    close:  q.close?.[i]  ?? 0,
    volume: q.volume?.[i] ?? 0,
  })).filter(b => b.close > 0);
}

/** Bigpara scraper for BIST symbols */
async function fetchBigpara(
  http:      AxiosInstance,
  symbol:    string,
  startDate: Date,
  endDate:   Date,
): Promise<OHLCV[]> {
  const fmt = (d: Date) => d.toISOString().split('T')[0].replace(/-/g, '.');
  const url  = `https://bigpara.hurriyet.com.tr/api/v1/borsa/hisse/${symbol}/fiyatlar/`;
  const { data } = await http.get(url, {
    params: { baslangic: fmt(startDate), bitis: fmt(endDate) },
    timeout: 12_000,
    headers: { 'User-Agent': 'Mozilla/5.0', Referer: 'https://bigpara.hurriyet.com.tr/' },
  });

  const rows: YahooBar[] = data?.data ?? [];
  return rows.map(r => ({
    date:   new Date(r.date),
    open:   r.open, high: r.high, low: r.low, close: r.close, volume: r.volume,
  })).filter(b => b.date >= startDate && b.date <= endDate)
    .sort((a, b) => a.date.getTime() - b.date.getTime());
}

// ─── Redis cache helper ───────────────────────────────────────────────────────

type RedisClient = ReturnType<typeof createClient>;

async function cacheGet<T>(redis: RedisClient | null, key: string): Promise<T | null> {
  if (!redis) return null;
  try {
    const v = await (redis as RedisClientType).get(key);
    return v ? (JSON.parse(v) as T) : null;
  } catch {
    return null;
  }
}

async function cacheSet(redis: RedisClient | null, key: string, value: unknown, ttlSeconds: number): Promise<void> {
  if (!redis) return;
  try {
    await (redis as RedisClientType).set(key, JSON.stringify(value), { EX: ttlSeconds });
  } catch { /* non-fatal */ }
}

// ─── DataService ─────────────────────────────────────────────────────────────

export interface DataServiceConfig {
  alphaVantageKey?: string;
  twelveDataKey?:   string;
  redisUrl?:        string;
  rateLimitMs?:     number;   // minimum ms between Alpha Vantage calls (free: 12_000)
}

export class DataService {
  private http:     AxiosInstance;
  private redis:    RedisClient | null = null;
  private lastCallAt = 0;
  private readonly rateLimitMs: number;
  private readonly avKey: string;
  private _tdKey: string | null = null;

  // In-process hot cache (avoids Redis round-trips for repeated lookups)
  private hotCache = new Map<string, { value: unknown; expiresAt: number }>();

  private get tdKey(): string {
    if (this._tdKey === null) {
      this._tdKey = this.config.twelveDataKey ?? process.env['TWELVE_DATA_API_KEY'] ?? '';
    }
    return this._tdKey;
  }

  constructor(private config: DataServiceConfig = {}) {
    this.avKey       = config.alphaVantageKey ?? process.env['ALPHA_VANTAGE_KEY'] ?? '';
    this.rateLimitMs = config.rateLimitMs     ?? 12_000;
    this.http        = axios.create({
      headers: {
        'Accept-Encoding': 'gzip',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      },
    });
  }

  async connect(): Promise<void> {
    const url = this.config.redisUrl ?? process.env['REDIS_URL'];
    if (!url) return;
    try {
      this.redis = createClient({ url });
      await (this.redis as RedisClientType).connect();
      console.log('[DataService] Redis connected');
    } catch (err) {
      console.warn('[DataService] Redis unavailable — falling back to in-process cache only:', (err as Error).message);
      this.redis = null;
    }
  }

  async disconnect(): Promise<void> {
    if (this.redis) await (this.redis as RedisClientType).quit();
  }

  // ── Cache utilities ─────────────────────────────────────────────────────────

  private hotGet<T>(key: string): T | null {
    const entry = this.hotCache.get(key);
    if (!entry) return null;
    if (Date.now() > entry.expiresAt) { this.hotCache.delete(key); return null; }
    return entry.value as T;
  }

  private hotSet(key: string, value: unknown, ttlMs: number): void {
    this.hotCache.set(key, { value, expiresAt: Date.now() + ttlMs });
  }

  private async get<T>(key: string): Promise<T | null> {
    return this.hotGet<T>(key) ?? cacheGet<T>(this.redis, key);
  }

  private async set(key: string, value: unknown, ttlSeconds: number): Promise<void> {
    this.hotSet(key, value, ttlSeconds * 1_000);
    await cacheSet(this.redis, key, value, ttlSeconds);
  }

  // ── Rate-limit guard (Alpha Vantage free tier) ──────────────────────────────

  private async rateLimit(): Promise<void> {
    const wait = this.rateLimitMs - (Date.now() - this.lastCallAt);
    if (wait > 0) await new Promise(r => setTimeout(r, wait));
    this.lastCallAt = Date.now();
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /** Fetch OHLCV for a symbol, with Redis/hot-cache and automatic source fallback. */
  async fetchStockPrice(
    symbol:    string,
    startDate: Date,
    endDate:   Date,
    interval:  '1d' | '1wk' | '1mo' = '1d',
  ): Promise<OHLCV[]> {
    const key   = `price:${symbol}:${interval}:${startDate.toISOString().slice(0,10)}:${endDate.toISOString().slice(0,10)}`;
    const TTL   = 30 * 86_400;   // 30 days
    const cached = await this.get<OHLCV[]>(key);
    if (cached) return cached.map(b => ({ ...b, date: new Date(b.date) }));

    const isBIST = /^[A-Z]{4,5}$/.test(symbol) && !symbol.includes('.');
    let bars: OHLCV[] = [];

    // ── Twelve Data (birincil kaynak — BIST + US) ───────────────────────────
    if (this.tdKey) {
      try {
        bars = await fetchTwelveData(this.http, this.tdKey, symbol, interval, startDate, endDate);
        if (bars.length > 0) {
          await this.set(key, bars, TTL);
          return bars;
        }
      } catch (e) {
        console.warn(`[DataService] Twelve Data failed for ${symbol}:`, (e as Error).message);
      }
    }

    // ── Fallback zinciri ────────────────────────────────────────────────────
    // BIST: BigPara → Alpha Vantage
    // US:   Yahoo Finance → Alpha Vantage
    try {
      if (isBIST) {
        bars = await fetchBigpara(this.http, symbol, startDate, endDate);
      } else {
        bars = await fetchYahooFinance(this.http, symbol, interval, startDate, endDate);
      }
    } catch { /* try alpha vantage */ }

    if (bars.length === 0 && this.avKey) {
      try {
        await this.rateLimit();
        bars = await fetchAlphaVantage(this.http, this.avKey, symbol, interval, startDate, endDate);
      } catch { /* give up */ }
    }

    if (bars.length > 0) await this.set(key, bars, TTL);
    return bars;
  }

  /** Fetch stock split events for a BIST symbol from Twelve Data. */
  async fetchSplits(symbol: string, market: string): Promise<SplitEvent[]> {
    const isBIST = market !== 'US' && market !== 'BOTH';
    if (!isBIST) return [];  // splits rarely matter for US in this context

    const tdSym = `${symbol}:BIST`;
    const cacheKey = `splits:${tdSym}`;

    const cached = await this.get<SplitEvent[]>(cacheKey);
    if (cached) return cached;

    try {
      const resp = await this.http.get<TwelveDataSplitsResponse>(
        'https://api.twelvedata.com/splits',
        { params: { symbol: tdSym, apikey: this.tdKey } }
      );
      const splits: SplitEvent[] = (resp.data?.splits ?? []).map((s: any) => ({
        date:        s.date,                      // "2023-02-17"
        fromFactor:  Number(s.from_factor),       // 2100
        toFactor:    Number(s.to_factor),         // 100
        ratio:       Number(s.ratio),             // 0.04762 = to/from
      }));
      await this.set(cacheKey, splits, 86_400 * 7); // cache 7 days
      return splits;
    } catch {
      return [];
    }
  }

  /** Calculate all technical indicators for the given price history. */
  async calculateIndicators(bars: OHLCV[]): Promise<TechnicalIndicators> {
    return calculateTechnicalIndicators(bars);
  }

  /** Fetch fundamental data — currently sourced from Yahoo Finance's summary endpoint. */
  async fetchFundamentals(symbol: string): Promise<Fundamentals> {
    const key = `fundamentals:${symbol}`;
    const TTL = 7 * 86_400;   // 7 days
    const cached = await this.get<Fundamentals>(key);
    if (cached) return { ...cached, fetchedAt: new Date(cached.fetchedAt) };

    let fund: Fundamentals = {
      symbol, pe: null, pb: null, roe: null, debtEquity: null,
      revenueGrowth: null, earningsGrowth: null, freeCashFlow: null,
      dividendYield: null, currentRatio: null, operatingMargin: null,
      marketCap: null, sector: null, fetchedAt: new Date(),
    };

    try {
      const { data } = await this.http.get(
        `https://query1.finance.yahoo.com/v10/finance/quoteSummary/${encodeURIComponent(symbol)}`,
        { params: { modules: 'financialData,defaultKeyStatistics,summaryProfile' }, timeout: 12_000 },
      );
      const fd = data?.quoteSummary?.result?.[0];
      if (fd) {
        const fin  = fd.financialData          ?? {};
        const stat = fd.defaultKeyStatistics   ?? {};
        const prof = fd.summaryProfile         ?? {};
        fund = {
          symbol,
          pe:              stat.trailingPE?.raw                 ?? null,
          pb:              stat.priceToBook?.raw                ?? null,
          roe:             fin.returnOnEquity?.raw != null      ? fin.returnOnEquity.raw * 100 : null,
          debtEquity:      stat.debtToEquity?.raw               ?? null,
          revenueGrowth:   fin.revenueGrowth?.raw != null       ? fin.revenueGrowth.raw * 100  : null,
          earningsGrowth:  fin.earningsGrowth?.raw != null      ? fin.earningsGrowth.raw * 100 : null,
          freeCashFlow:    fin.freeCashflow?.raw                ?? null,
          dividendYield:   stat.dividendYield?.raw != null      ? stat.dividendYield.raw * 100 : null,
          currentRatio:    fin.currentRatio?.raw                ?? null,
          operatingMargin: fin.operatingMargins?.raw != null    ? fin.operatingMargins.raw * 100 : null,
          marketCap:       stat.marketCap?.raw                  ?? null,
          sector:          prof.sector                          ?? null,
          fetchedAt:       new Date(),
        };
      }
    } catch (err) {
      console.warn(`[DataService] Fundamentals fetch failed for ${symbol}:`, (err as Error).message);
    }

    await this.set(key, fund, TTL);
    return fund;
  }

  /** Fetch a market index value. */
  async fetchMarketIndex(
    index: 'BIST100' | 'SP500' | 'VIX',
    date?: Date,
  ): Promise<IndexData | null> {
    const symbolMap: Record<string, string> = { BIST100: 'XU100.IS', SP500: '^GSPC', VIX: '^VIX' };
    const symbol = symbolMap[index];
    const endDate  = date ?? new Date();
    const startDate = new Date(endDate);
    startDate.setDate(startDate.getDate() - 7);

    const bars = await this.fetchStockPrice(symbol, startDate, endDate, '1d');
    if (bars.length < 2) return null;

    const last = bars[bars.length - 1];
    const prev = bars[bars.length - 2];
    const change    = last.close - prev.close;
    const changePct = (change / prev.close) * 100;

    return { index, date: last.date, value: last.close, change, changePct };
  }

  /** BIST100 constituent list (static; refreshed on each release). */
  async getBIST100Constituents(): Promise<string[]> {
    return BIST100_SYMBOLS;
  }

  /** S&P 500 constituent list (static; refreshed on each release). */
  async getSP500Constituents(): Promise<string[]> {
    return US_MARKET_SYMBOLS;
  }

  /** 52-week high/low for a single symbol. */
  async calculate52WeekHighLow(symbol: string): Promise<{ high: number; low: number } | null> {
    const end   = new Date();
    const start = new Date(end);
    start.setFullYear(start.getFullYear() - 1);
    const bars = await this.fetchStockPrice(symbol, start, end, '1d');
    if (!bars.length) return null;
    return calculate52WeekRange(bars);
  }

  /**
   * Market breadth for BIST or US.
   * Scans a representative sample (up to 50 symbols) to keep API usage reasonable.
   */
  async getMarketBreadth(market: 'BIST' | 'US'): Promise<BreadthData> {
    const symbols = market === 'BIST' ? BISTTUM_SYMBOLS.slice(0, 50) : US_MARKET_SYMBOLS.slice(0, 50);
    const end     = new Date();
    const start   = new Date(end);
    start.setFullYear(start.getFullYear() - 1);

    let advances = 0; let declines = 0; let aboveSMA200 = 0;
    let new52hHigh = 0; let new52wLow = 0;

    await Promise.allSettled(symbols.map(async sym => {
      try {
        const bars = await this.fetchStockPrice(sym, start, end, '1d');
        if (bars.length < 5) return;
        const last   = bars[bars.length - 1];
        const prev   = bars[bars.length - 2];
        const closes = bars.map(b => b.close);
        const sma200 = calculateSMA(closes, 200);
        const range  = calculate52WeekRange(bars);

        if (last.close > prev.close) advances++; else declines++;
        if (sma200 !== null && last.close > sma200) aboveSMA200++;
        if (last.close >= range.high * 0.98) new52hHigh++;
        if (last.close <= range.low  * 1.02) new52wLow++;
      } catch { /* skip */ }
    }));

    const total = advances + declines || 1;
    return {
      market, date: end,
      advanceDeclineRatio: advances / (declines || 1),
      pctAbove200SMA:      (aboveSMA200 / total) * 100,
      new52wHighs:         new52hHigh,
      new52wLows:          new52wLow,
      totalStocks:         total,
    };
  }

  // ── Grown Plan: anlık fiyat + değişim (birden fazla sembol) ──────────────────
  /**
   * Batch quote: 120 sembol kadar tek API çağrısında çeker.
   * Twelve Data /price?symbol=A,B,C syntax — Grown plan destekli.
   */
  async fetchBatchQuotes(
    symbols: string[],
    market:  'BIST' | 'US' = 'BIST',
  ): Promise<Record<string, { price: number; change: number; changePct: number; volume: number }>> {
    if (!this.tdKey) throw new Error('TWELVE_DATA_API_KEY missing');
    const CHUNK = 120;
    const result: Record<string, { price: number; change: number; changePct: number; volume: number }> = {};

    // API 120 sembole kadar destekliyor — büyük listeleri böl
    for (let i = 0; i < symbols.length; i += CHUNK) {
      const chunk = symbols.slice(i, i + CHUNK);
      try {
        const batch = await fetchTwelveDataBatch(this.http, this.tdKey, chunk, market);
        Object.assign(result, batch);
      } catch (err) {
        console.warn(`[DataService.fetchBatchQuotes] chunk ${i}-${i+CHUNK} failed:`, (err as Error).message);
      }
    }
    return result;
  }

  // ── Grown Plan: Twelve Data API-side teknik indikatörler ─────────────────────
  /**
   * Tek sembol için RSI, MACD, EMA, ADX, Bollinger, ATR, Stochastic değerlerini
   * Twelve Data'nın kendi hesaplama motorundan çeker. Paralel 7 istek gönderir.
   */
  async fetchRealIndicators(
    symbol: string,
    market: 'BIST' | 'US' = 'BIST',
  ): Promise<Partial<TechnicalIndicators>> {
    if (!this.tdKey) throw new Error('TWELVE_DATA_API_KEY missing');

    const get = (ind: string, p: Record<string, string | number>) =>
      fetchTwelveIndicator(this.http, this.tdKey, symbol, ind, p, market)
        .catch(() => [] as Record<string, number | string>[]);

    const [rsiVals, macdVals, ema20Vals, ema50Vals, ema200Vals, adxVals, bbandsVals, atrVals, stochVals] =
      await Promise.all([
        get('rsi',    { time_period: 14 }),
        get('macd',   { fast_period: 12, slow_period: 26, signal_period: 9 }),
        get('ema',    { time_period: 20, series_type: 'close' }),
        get('ema',    { time_period: 50, series_type: 'close' }),
        get('ema',    { time_period: 200, series_type: 'close' }),
        get('adx',    { time_period: 14 }),
        get('bbands', { time_period: 20, sd: 2, series_type: 'close' }),
        get('atr',    { time_period: 14 }),
        get('stoch',  { fast_k_period: 14, slow_d_period: 3, slow_k_period: 3 }),
      ]);

    const last = <T extends Record<string, number | string>>(arr: T[]): T | undefined => arr[arr.length - 1];

    const rsi    = last(rsiVals);
    const macd   = last(macdVals);
    const ema20  = last(ema20Vals);
    const ema50  = last(ema50Vals);
    const ema200 = last(ema200Vals);
    const adx    = last(adxVals);
    const bb     = last(bbandsVals);
    const atr    = last(atrVals);
    const stoch  = last(stochVals);

    return {
      rsi14:    rsi    ? +rsi['rsi']            : undefined,
      ema20:    ema20  ? +ema20['ema']           : undefined,
      ema50:    ema50  ? +ema50['ema']           : undefined,
      ema200:   ema200 ? +ema200['ema']          : undefined,
      adx14:    adx    ? +adx['adx']             : undefined,
      atr14:    atr    ? +atr['atr']             : undefined,
      macd: macd ? {
        macd:      +macd['macd']     || 0,
        signal:    +macd['macd_signal'] || 0,
        histogram: +macd['macd_hist']   || 0,
      } : undefined,
      bollinger: bb ? {
        upper:  +bb['upper_band'] || 0,
        middle: +bb['middle_band'] || 0,
        lower:  +bb['lower_band'] || 0,
      } : undefined,
      stochastic: stoch ? {
        k: +stoch['slow_k'] || 0,
        d: +stoch['slow_d'] || 0,
      } : undefined,
    } as Partial<TechnicalIndicators>;
  }

  // ── Grown Plan: Fundamentals ─────────────────────────────────────────────────
  /**
   * Twelve Data /statistics + /profile — P/E, P/B, EPS, büyüme vb.
   */
  async fetchFundamentalsFromTD(
    symbol: string,
    market: 'BIST' | 'US' = 'BIST',
  ): Promise<Fundamentals | null> {
    if (!this.tdKey) return null;
    try {
      const raw = await fetchTwelveDataFundamentals(this.http, this.tdKey, symbol, market);
      const stats  = raw as Record<string, unknown>;
      const n = (k: string): number => parseFloat(String(stats[k] ?? '0')) || 0;

      return {
        symbol,
        pe:              n('pe_ratio') || null,
        pb:              n('price_to_book') || null,
        roe:             n('return_on_equity_ttm') / 100 || null,
        debtEquity:      n('total_debt_to_equity') || null,
        revenueGrowth:   n('quarterly_revenue_growth_yoy') / 100 || null,
        earningsGrowth:  n('quarterly_earnings_growth_yoy') / 100 || null,
        freeCashFlow:    null,
        dividendYield:   n('dividend_yield') / 100 || null,
        currentRatio:    n('current_ratio') || null,
        operatingMargin: n('operating_profit_margin') / 100 || null,
        marketCap:       n('market_cap') || null,
        sector:          null,
        fetchedAt:       new Date(),
      } satisfies Fundamentals;
    } catch {
      return null;
    }
  }

  // ── Grown Plan: Hisse analiz özeti (tek çağrıda fiyat + indikatör) ─────────
  /**
   * Tarama için ihtiyaç duyulan tüm veriyi paralel olarak çeker:
   * - 1 yıllık günlük OHLCV
   * - Teknik indikatörler (TD API)
   * - Anlık quote (52H high/low dahil)
   */
  async fetchFullStockSnapshot(
    symbol: string,
    market: 'BIST' | 'US' = 'BIST',
  ): Promise<{
    bars:       OHLCV[];
    indicators: Partial<TechnicalIndicators>;
    quote:      Awaited<ReturnType<typeof fetchTwelveDataQuote>> | null;
    fundamentals: Fundamentals | null;
  }> {
    const end   = new Date();
    const start = new Date(end);
    start.setFullYear(start.getFullYear() - 1);

    const [bars, indicators, quote, fundamentals] = await Promise.allSettled([
      this.fetchStockPrice(symbol, start, end, '1d'),
      this.fetchRealIndicators(symbol, market),
      fetchTwelveDataQuote(this.http, this.tdKey, symbol, market).catch(() => null),
      this.fetchFundamentalsFromTD(symbol, market),
    ]);

    return {
      bars:         bars.status         === 'fulfilled' ? bars.value         : [],
      indicators:   indicators.status   === 'fulfilled' ? indicators.value   : {},
      quote:        quote.status        === 'fulfilled' ? quote.value        : null,
      fundamentals: fundamentals.status === 'fulfilled' ? fundamentals.value : null,
    };
  }

  /**
   * Persist an OHLCV + indicator batch for a single symbol to PostgreSQL.
   * Uses Prisma's upsert so it's safe to call repeatedly.
   */
  async persistPricesAndIndicators(
    symbol:  string,
    bars:    OHLCV[],
    indics:  TechnicalIndicators,
  ): Promise<void> {
    const { PrismaClient } = await import('@prisma/client');
    const prisma = new PrismaClient();
    try {
      const stock = await prisma.stock.upsert({
        where:  { symbol },
        update: {},
        create: { symbol, name: symbol, market: /^[A-Z]{4,5}$/.test(symbol) ? 'BIST' : 'NYSE/NASDAQ' },
      });

      // Write only the last bar to keep writes fast; bulk-seed separately if needed
      const last = bars[bars.length - 1];
      if (!last) return;

      await prisma.stockPrice.upsert({
        where:  { stockId_date: { stockId: stock.id, date: last.date } },
        update: {
          open: last.open, high: last.high, low: last.low, close: last.close, volume: last.volume,
          ema20:      indics.ema20,       ema50:      indics.ema50,
          ema200:     indics.ema200,      sma50:      indics.sma50,
          sma200:     indics.sma200,      rsi14:      indics.rsi14,
          macd:       indics.macd?.macd,  macdSignal: indics.macd?.signal,
          atr14:      indics.atr14,       obv:        indics.obv,
          vwap:       indics.vwap,        adx14:      indics.adx14?.adx,
          bbUpper:    indics.bollinger?.upper, bbMiddle: indics.bollinger?.middle,
          bbLower:    indics.bollinger?.lower, stochK:   indics.stochastic?.k,
          stochD:     indics.stochastic?.d,
        },
        create: {
          stockId: stock.id, date: last.date,
          open: last.open, high: last.high, low: last.low, close: last.close, volume: last.volume,
          ema20:      indics.ema20,       ema50:      indics.ema50,
          ema200:     indics.ema200,      sma50:      indics.sma50,
          sma200:     indics.sma200,      rsi14:      indics.rsi14,
          macd:       indics.macd?.macd,  macdSignal: indics.macd?.signal,
          atr14:      indics.atr14,       obv:        indics.obv,
          vwap:       indics.vwap,        adx14:      indics.adx14?.adx,
          bbUpper:    indics.bollinger?.upper, bbMiddle: indics.bollinger?.middle,
          bbLower:    indics.bollinger?.lower, stochK:   indics.stochastic?.k,
          stochD:     indics.stochastic?.d,
        },
      });
    } finally {
      await prisma.$disconnect();
    }
  }
}

// Singleton export so routes share one connection pool
export const dataService = new DataService();
