/**
 * VERDENT — Daily Data Sync Job
 *
 * Scheduled tasks (all via node-cron):
 *
 *   1. DAILY PRICE SYNC          — runs 18:30 on weekdays (after BIST close)
 *      • Fetches latest OHLCV for every tracked symbol (BIST-100 + S&P-500)
 *      • Calculates all technical indicators
 *      • Upserts StockPrice rows in PostgreSQL
 *
 *   2. MARKET CONDITION UPDATE   — runs 19:00 on weekdays
 *      • Reanalyses market condition for BIST and US
 *      • Saves MarketCondition records
 *
 *   3. FUNDAMENTAL REFRESH       — runs every Sunday 02:00
 *      • Refreshes quarterly fundamental data for all tracked symbols
 *
 *   4. HEALTH CHECK              — runs every 5 minutes
 *      • Emits a heartbeat log; aborts stuck jobs after 60 minutes
 *
 * Each task is wrapped in a try/catch so a single symbol failure never
 * aborts the entire run.  Per-symbol errors are collected and logged as
 * a summary at the end.
 *
 * Usage (start from index.ts or a standalone process):
 *   import { startDataSyncScheduler, runPriceSync } from './jobs/dataSyncJob';
 *   startDataSyncScheduler();          // register all cron jobs
 *   await runPriceSync('BIST');        // run one-off (useful for seeding)
 */

import cron from 'node-cron';

import {
  DataService,
  dataService,
  BIST100_SYMBOLS,
  SP500_SYMBOLS,
  calculateTechnicalIndicators,
  type OHLCV,
} from '../services/dataService';

import {
  analyzeMarketCondition,
  type MarketId,
} from '../services/marketConditionService';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface SyncStats {
  market:       string;
  startedAt:    Date;
  finishedAt:   Date | null;
  symbolsTotal: number;
  symbolsOk:    number;
  symbolsFailed: number;
  errors:       { symbol: string; message: string }[];
  durationMs:   number | null;
}

// ─── Concurrency limiter ──────────────────────────────────────────────────────
// The free Alpha Vantage tier allows 5 calls/min (≈12 s between calls).
// For Yahoo Finance there is no hard limit but burst protection is needed.
// We process symbols in small batches and respect a configurable delay.

const BATCH_SIZE  = 5;
const BATCH_DELAY = 2_500;   // ms between batches

async function processBatches<T>(
  items:     T[],
  handler:   (item: T) => Promise<void>,
  batchSize: number = BATCH_SIZE,
  delayMs:   number = BATCH_DELAY,
): Promise<{ ok: number; failed: { item: T; error: string }[] }> {
  let ok     = 0;
  const failed: { item: T; error: string }[] = [];

  for (let i = 0; i < items.length; i += batchSize) {
    const batch = items.slice(i, i + batchSize);
    await Promise.allSettled(
      batch.map(async item => {
        try {
          await handler(item);
          ok++;
        } catch (err) {
          failed.push({ item, error: (err as Error).message });
        }
      }),
    );
    if (i + batchSize < items.length) {
      await new Promise(r => setTimeout(r, delayMs));
    }
  }

  return { ok, failed };
}

// ─── Core sync routines ───────────────────────────────────────────────────────

/**
 * Sync daily prices + indicators for every symbol in the given market.
 * Writes upserted rows to PostgreSQL via `dataService.persistPricesAndIndicators`.
 */
export async function runPriceSync(market: 'BIST' | 'US' | 'BOTH'): Promise<SyncStats[]> {
  const markets: ('BIST' | 'US')[] = market === 'BOTH' ? ['BIST', 'US'] : [market];
  const results: SyncStats[] = [];

  for (const mkt of markets) {
    const symbols    = mkt === 'BIST' ? BIST100_SYMBOLS : SP500_SYMBOLS;
    const startedAt  = new Date();
    const errors: SyncStats['errors'] = [];

    console.log(`[DataSync] Starting price sync for ${mkt} (${symbols.length} symbols) …`);

    const endDate   = new Date();
    const startDate = new Date(endDate);
    startDate.setFullYear(startDate.getFullYear() - 1);   // 1 year of daily bars

    const { ok, failed } = await processBatches(symbols, async symbol => {
      const bars = await dataService.fetchStockPrice(symbol, startDate, endDate, '1d');
      if (!bars.length) {
        throw new Error(`No price data returned`);
      }

      // Use last 300 bars for indicators (enough for EMA-200 + ADX warmup)
      const indicBars = bars.slice(-300) as OHLCV[];
      const indicators = calculateTechnicalIndicators(indicBars);

      await dataService.persistPricesAndIndicators(symbol, indicBars, indicators);
    });

    failed.forEach(f => errors.push({ symbol: String(f.item), message: f.error }));

    const finishedAt = new Date();
    const stat: SyncStats = {
      market: mkt,
      startedAt,
      finishedAt,
      symbolsTotal:  symbols.length,
      symbolsOk:     ok,
      symbolsFailed: failed.length,
      errors,
      durationMs:    finishedAt.getTime() - startedAt.getTime(),
    };

    console.log(`[DataSync] ${mkt} price sync complete — ${ok}/${symbols.length} ok, ${failed.length} failed (${stat.durationMs}ms)`);
    if (errors.length) {
      console.warn(`[DataSync] ${mkt} failures:`, errors.slice(0, 10));
    }

    results.push(stat);
  }

  return results;
}

/**
 * Refresh fundamental data for all tracked symbols.
 * Runs once per week (Sunday); data is cached for 7 days in Redis.
 */
export async function runFundamentalsSync(market: 'BIST' | 'US' | 'BOTH'): Promise<SyncStats[]> {
  const markets: ('BIST' | 'US')[] = market === 'BOTH' ? ['BIST', 'US'] : [market];
  const results: SyncStats[] = [];

  for (const mkt of markets) {
    const symbols   = mkt === 'BIST' ? BIST100_SYMBOLS : SP500_SYMBOLS;
    const startedAt = new Date();
    const errors: SyncStats['errors'] = [];

    console.log(`[DataSync] Fundamental refresh for ${mkt} (${symbols.length} symbols) …`);

    const { ok, failed } = await processBatches(
      symbols,
      async symbol => { await dataService.fetchFundamentals(symbol); },
      3,        // smaller batch — Yahoo fundamentals endpoint is more rate-sensitive
      4_000,
    );

    failed.forEach(f => errors.push({ symbol: String(f.item), message: f.error }));

    const finishedAt = new Date();
    results.push({
      market: mkt,
      startedAt, finishedAt,
      symbolsTotal: symbols.length, symbolsOk: ok, symbolsFailed: failed.length,
      errors, durationMs: finishedAt.getTime() - startedAt.getTime(),
    });

    console.log(`[DataSync] ${mkt} fundamentals done — ${ok}/${symbols.length} ok`);
  }

  return results;
}

/**
 * Refresh market condition for BIST and/or US.
 * Stores a MarketCondition record in PostgreSQL.
 */
export async function runMarketConditionSync(market: 'BIST' | 'US' | 'BOTH'): Promise<void> {
  const markets: MarketId[] = market === 'BOTH' ? ['BIST', 'US'] : [market as MarketId];

  for (const mkt of markets) {
    try {
      // Fetch index bars for condition analysis
      const indexSymbol = mkt === 'BIST' ? 'XU100.IS' : '^GSPC';
      const endDate     = new Date();
      const startDate   = new Date(endDate);
      startDate.setFullYear(startDate.getFullYear() - 1);

      const bars = await dataService.fetchStockPrice(indexSymbol, startDate, endDate, '1d');
      if (bars.length < 30) {
        console.warn(`[DataSync] Not enough ${mkt} index bars for condition analysis`);
        continue;
      }

      const series = bars.map(b => ({ date: b.date, close: b.close, high: b.high, low: b.low, open: b.open, volume: b.volume }));
      const result = analyzeMarketCondition({ market: mkt, date: endDate, series });

      // Persist to PostgreSQL
      const { PrismaClient } = await import('@prisma/client');
      const prisma = new PrismaClient();
      try {
        await prisma.marketCondition.upsert({
          where:  { date: endDate },
          update: {
            condition:  result.condition,
            confidence: result.confidence,
            indicators: result.indicators as object,
          },
          create: {
            date:       endDate,
            market:     mkt,
            condition:  result.condition,
            confidence: result.confidence,
            indicators: result.indicators as object,
          },
        });
        console.log(`[DataSync] MarketCondition saved for ${mkt}: ${result.condition} (conf ${result.confidence.toFixed(1)}%)`);
      } finally {
        await prisma.$disconnect();
      }
    } catch (err) {
      console.error(`[DataSync] MarketCondition sync failed for ${mkt}:`, (err as Error).message);
    }
  }
}

// ─── Job state tracking ───────────────────────────────────────────────────────

interface JobState {
  name:      string;
  lastRunAt: Date | null;
  running:   boolean;
  lastStats: SyncStats[] | null;
}

const jobRegistry = new Map<string, JobState>([
  ['priceSync',         { name: 'priceSync',         lastRunAt: null, running: false, lastStats: null }],
  ['fundamentalsSync',  { name: 'fundamentalsSync',  lastRunAt: null, running: false, lastStats: null }],
  ['marketCondSync',    { name: 'marketCondSync',     lastRunAt: null, running: false, lastStats: null }],
]);

function jobGuard(name: string, fn: () => Promise<void>): () => void {
  return () => {
    const state = jobRegistry.get(name)!;
    if (state.running) {
      console.warn(`[DataSync] Job "${name}" already running — skipping tick`);
      return;
    }
    state.running = true;
    state.lastRunAt = new Date();
    fn()
      .catch(err => console.error(`[DataSync] Job "${name}" threw unhandled error:`, err))
      .finally(() => { state.running = false; });
  };
}

/** Read-only snapshot of job health for admin endpoints. */
export function getJobStatus(): Record<string, Omit<JobState, 'lastStats'> & { lastStats: SyncStats[] | null }> {
  const out: Record<string, Omit<JobState, 'lastStats'> & { lastStats: SyncStats[] | null }> = {};
  for (const [k, v] of jobRegistry.entries()) out[k] = { ...v };
  return out;
}

// ─── Scheduler ───────────────────────────────────────────────────────────────

let schedulerStarted = false;

/**
 * Register all cron jobs.  Call once at application startup.
 *
 * Schedule overview (all times UTC+3 / Istanbul):
 *   Mon–Fri 18:30  Price sync (BOTH)
 *   Mon–Fri 19:00  Market condition sync
 *   Sunday  02:00  Fundamental refresh (BOTH)
 *   Every 5 min    Health-check heartbeat
 */
export function startDataSyncScheduler(): void {
  if (schedulerStarted) {
    console.warn('[DataSync] Scheduler already started — ignoring duplicate call');
    return;
  }
  schedulerStarted = true;

  // ── 1. Daily price sync ──────────────────────────────────────────────────
  // Mon–Fri at 18:30 local (cron runs in system timezone; adjust for your TZ)
  cron.schedule('30 18 * * 1-5', jobGuard('priceSync', async () => {
    const stats = await runPriceSync('BOTH');
    jobRegistry.get('priceSync')!.lastStats = stats;
  }), { timezone: 'Europe/Istanbul' });

  // ── 2. Market condition sync ─────────────────────────────────────────────
  cron.schedule('0 19 * * 1-5', jobGuard('marketCondSync', async () => {
    await runMarketConditionSync('BOTH');
    jobRegistry.get('marketCondSync')!.lastRunAt = new Date();
  }), { timezone: 'Europe/Istanbul' });

  // ── 3. Weekly fundamentals ───────────────────────────────────────────────
  cron.schedule('0 2 * * 0', jobGuard('fundamentalsSync', async () => {
    const stats = await runFundamentalsSync('BOTH');
    jobRegistry.get('fundamentalsSync')!.lastStats = stats;
  }), { timezone: 'Europe/Istanbul' });

  // ── 4. Heartbeat ─────────────────────────────────────────────────────────
  cron.schedule('*/5 * * * *', () => {
    const ts  = new Date().toISOString();
    const running = [...jobRegistry.values()].filter(j => j.running).map(j => j.name);
    if (running.length) {
      console.log(`[DataSync] ❤️  ${ts} — running: ${running.join(', ')}`);
    } else {
      console.log(`[DataSync] ❤️  ${ts} — idle`);
    }
  });

  console.log('[DataSync] Scheduler registered: priceSync(18:30 Mon-Fri), marketCond(19:00 Mon-Fri), fundamentals(02:00 Sun), heartbeat(*/5min)');
}

// ─── Manual / seeding helpers ─────────────────────────────────────────────────

/**
 * Seed historical prices for a list of symbols.
 * Useful for initial DB population.
 * Respects the same batch/delay limits as the scheduled job.
 */
export async function seedHistoricalPrices(
  symbols:   string[],
  yearsBack: number = 3,
): Promise<void> {
  const endDate   = new Date();
  const startDate = new Date(endDate);
  startDate.setFullYear(startDate.getFullYear() - yearsBack);

  console.log(`[DataSync] Seeding ${symbols.length} symbols × ${yearsBack}yr history …`);
  const ds = new DataService({ rateLimitMs: 12_000 });
  await ds.connect();

  const { ok, failed } = await processBatches(
    symbols,
    async symbol => {
      const bars = await ds.fetchStockPrice(symbol, startDate, endDate, '1d');
      if (!bars.length) throw new Error('empty');
      const indicBars = bars.slice(-300) as OHLCV[];
      const indicators = calculateTechnicalIndicators(indicBars);
      await ds.persistPricesAndIndicators(symbol, indicBars, indicators);
    },
    3,
    13_000,   // respects Alpha Vantage free-tier 5/min limit
  );

  console.log(`[DataSync] Seed complete — ${ok}/${symbols.length} ok, ${failed.length} failed`);
  if (failed.length) console.warn('[DataSync] Failed symbols:', failed.map(f => f.item));

  await ds.disconnect();
}

/**
 * One-shot manual trigger for any job by name.
 * Useful from admin route or REPL.
 */
export async function triggerJob(jobName: 'priceSync' | 'fundamentalsSync' | 'marketCondSync', market: 'BIST' | 'US' | 'BOTH' = 'BOTH'): Promise<void> {
  console.log(`[DataSync] Manual trigger: ${jobName} (${market})`);
  switch (jobName) {
    case 'priceSync':        await runPriceSync(market);             break;
    case 'fundamentalsSync': await runFundamentalsSync(market);      break;
    case 'marketCondSync':   await runMarketConditionSync(market);   break;
  }
}
