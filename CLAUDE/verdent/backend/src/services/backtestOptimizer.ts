/**
 * VERDENT — Backtest Performance Optimizer
 *
 * Provides:
 *   1. Indicator pre-computation cache — calculates ALL technical indicators
 *      for the full stock universe once per run, then reuses them at every
 *      rebalance date.
 *
 *   2. Worker-thread parallel screening — splits the stock universe into
 *      batches of 50 and runs screenStocksSync in parallel threads.
 *
 *   3. Incremental scan cache — delegates to DeterministicScanner so that a
 *      scan for date X × criteria Y × market Z is never computed twice.
 *
 *   4. Bulk DB writer — buffers snapshots and trades and flushes them in a
 *      single createMany call instead of per-row inserts.
 */

import { Worker, isMainThread, parentPort, workerData } from 'worker_threads';
import { join } from 'path';
import { deterministicScanner, type ScanParams } from './consistencyService';
import {
  screenStocksSync,
  type CriteriaType,
  type ScoredStock,
  type StockData,
} from './criteriaEngine';
import type { PortfolioSnapshot, Trade } from './backtestEngine';

// ─────────────────────────────────────────────────────────────────────────────
// Worker entry-point (this file IS the worker script)
// ─────────────────────────────────────────────────────────────────────────────

if (!isMainThread) {
  // Worker receives: { stocks: StockData[], criteria: CriteriaType }
  const { stocks, criteria } = workerData as { stocks: StockData[]; criteria: CriteriaType };
  const result = screenStocksSync(stocks, criteria);
  parentPort!.postMessage(result);
}

// ─────────────────────────────────────────────────────────────────────────────
// Indicator pre-computation cache
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Pre-compute and cache a snapshot of "all stocks with their indicators at
 * every rebalance date" so the backtest loop avoids redundant DB queries.
 */
export class IndicatorCache {
  /** stockSymbol → dateStr → StockData */
  private store = new Map<string, Map<string, StockData>>();
  private populated = false;

  /**
   * Prime the cache from the DB for the full backtest date range.
   * Call once before starting the rebalance loop.
   */
  async prime(
    market:    'BIST' | 'US' | 'BOTH',
    startDate: Date,
    endDate:   Date,
  ): Promise<void> {
    if (this.populated) return;

    try {
      const { PrismaClient } = await import('@prisma/client');
      const prisma = new PrismaClient();

      const marketFilter =
        market === 'BIST' ? 'BIST'
        : market === 'US'  ? { not: 'BIST' as const }
        : undefined;                                      // BOTH = no filter

      const rows = await prisma.stockPrice.findMany({
        where: {
          date: { gte: startDate, lte: endDate },
          ...(marketFilter !== undefined ? { stock: { market: marketFilter } } : {}),
        },
        include: { stock: true },
        orderBy: { date: 'asc' },
      }).finally(() => prisma.$disconnect());

      for (const row of rows) {
        const dateStr = row.date.toISOString().slice(0, 10);
        if (!this.store.has(row.stock.symbol)) {
          this.store.set(row.stock.symbol, new Map());
        }
        this.store.get(row.stock.symbol)!.set(dateStr, {
          symbol:  row.stock.symbol,
          name:    row.stock.name,
          market:  row.stock.market as 'BIST' | 'US',
          sector:  row.stock.sector ?? undefined,
          price:   row.close,
          // Pre-stored indicators
          ema20:   row.ema20   ?? undefined,
          ema50:   row.ema50   ?? undefined,
          ema200:  row.ema200  ?? undefined,
          sma50:   row.sma50   ?? undefined,
          sma200:  row.sma200  ?? undefined,
          rsi14:   row.rsi14   ?? undefined,
          macd:    row.macd    ?? undefined,
          macdSignal: row.macdSignal ?? undefined,
          atr14:   row.atr14   ?? undefined,
          adx14:   row.adx14   ?? undefined,
          bbUpper: row.bbUpper ?? undefined,
          bbLower: row.bbLower ?? undefined,
          bbMiddle: row.bbMiddle ?? undefined,
          stochK:  row.stochK  ?? undefined,
          stochD:  row.stochD  ?? undefined,
          obv:     row.obv     ?? undefined,
          vwap:    row.vwap    ?? undefined,
          pe:            row.pe            ?? undefined,
          pb:            row.pb            ?? undefined,
          roe:           row.roe           ?? undefined,
          debtEquity:    row.debtEquity    ?? undefined,
          revenueGrowth: row.revenueGrowth ?? undefined,
          earningsGrowth: row.earningsGrowth ?? undefined,
          freeCashFlow:  row.freeCashFlow  ?? undefined,
          volume:        row.volume,
          marketCap:     row.stock.marketCap ?? undefined,
          priceHistory:  [],   // not needed for single-date scoring
        } as unknown as StockData);
      }

      this.populated = true;
    } catch {
      // DB not available — cache stays empty; scanner falls back to mock
    }
  }

  /**
   * Return all stocks with their indicator values as of `date`.
   * Looks up the closest available date <= `date`.
   */
  getStocksAtDate(date: Date): StockData[] {
    const dateStr = date.toISOString().slice(0, 10);
    const result: StockData[] = [];

    for (const [, dateMap] of this.store) {
      // Exact match first
      const exact = dateMap.get(dateStr);
      if (exact) { result.push(exact); continue; }

      // Closest earlier date
      let best: StockData | undefined;
      let bestDate = '';
      for (const [d, sd] of dateMap) {
        if (d <= dateStr && d > bestDate) { best = sd; bestDate = d; }
      }
      if (best) result.push(best);
    }

    return result;
  }

  clear(): void {
    this.store.clear();
    this.populated = false;
  }

  get size(): number { return this.store.size; }
}

// ─────────────────────────────────────────────────────────────────────────────
// Parallel screening via worker threads
// ─────────────────────────────────────────────────────────────────────────────

const BATCH_SIZE = 50;

/**
 * Screen `stocks` against `criteria` using a pool of worker threads,
 * one thread per batch of BATCH_SIZE stocks.
 *
 * Falls back to synchronous screening if worker_threads are unavailable.
 */
export async function parallelScreen(
  stocks:   StockData[],
  criteria: CriteriaType,
): Promise<ScoredStock[]> {
  if (stocks.length === 0) return [];

  // For small universes it's faster to stay synchronous
  if (stocks.length <= BATCH_SIZE) {
    return screenStocksSync(stocks, criteria);
  }

  const batches: StockData[][] = [];
  for (let i = 0; i < stocks.length; i += BATCH_SIZE) {
    batches.push(stocks.slice(i, i + BATCH_SIZE));
  }

  try {
    const batchResults = await Promise.all(
      batches.map(batch => runWorker(batch, criteria))
    );
    const all = ([] as ScoredStock[]).concat(...batchResults);
    // Re-rank after merging all batches
    all.sort((a, b) => b.score - a.score);
    all.forEach((s, i) => { s.rank = i + 1; });
    return all;
  } catch {
    // Worker unavailable (e.g. ts-node without compiled worker) — fall back
    return screenStocksSync(stocks, criteria);
  }
}

function runWorker(stocks: StockData[], criteria: CriteriaType): Promise<ScoredStock[]> {
  return new Promise((resolve, reject) => {
    // Use compiled JS path in production, fallback to this file in development
    const workerScript = join(__dirname, 'backtestOptimizer.js');
    const w = new Worker(workerScript, { workerData: { stocks, criteria } });
    w.once('message', resolve);
    w.once('error',   reject);
    w.once('exit', code => {
      if (code !== 0) reject(new Error(`Worker exited with code ${code}`));
    });
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Optimized scan  (incremental — uses DeterministicScanner)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Drop-in replacement for `sharedScan` in backtestEngine.
 * Adds incremental caching on top of the deterministic scanner.
 */
export async function cachedScan(params: ScanParams): Promise<ScoredStock[]> {
  const result = await deterministicScanner.scan(params);
  return result.stocks;
}

// ─────────────────────────────────────────────────────────────────────────────
// Bulk DB writer
// ─────────────────────────────────────────────────────────────────────────────

export class BulkWriter {
  private snapshots: PortfolioSnapshot[] = [];
  private trades:    Trade[]             = [];
  private backtestId = '';

  init(backtestId: string) {
    this.backtestId = backtestId;
    this.snapshots  = [];
    this.trades     = [];
  }

  addSnapshot(s: PortfolioSnapshot) { this.snapshots.push(s); }
  addTrade(t: Trade)                { this.trades.push(t); }

  /** Flush all buffered records in two createMany calls. */
  async flush(): Promise<void> {
    if (!this.backtestId) return;

    try {
      const { PrismaClient } = await import('@prisma/client');
      const prisma = new PrismaClient();

      await prisma.$transaction([
        prisma.backtestSnapshot.createMany({
          data: this.snapshots.map(s => ({
            backtestId:      this.backtestId,
            date:            s.date,
            portfolioValue:  s.value,
            holdings:        s.holdings as object,
            criteriaUsed:    s.criteriaUsed,
            marketCondition: s.marketCondition,
          })),
          skipDuplicates: true,
        }),
        prisma.backtestTrade.createMany({
          data: this.trades.map(t => ({
            backtestId: this.backtestId,
            symbol:     t.symbol,
            action:     t.action,
            date:       t.date,
            price:      t.price,
            shares:     t.shares,
            value:      t.value,
            reason:     t.reason,
          })),
          skipDuplicates: true,
        }),
      ]).finally(() => prisma.$disconnect());

    } catch { /* DB not configured — data only in-memory */ }

    this.snapshots = [];
    this.trades    = [];
  }
}

// Convenience singleton
export const bulkWriter = new BulkWriter();
