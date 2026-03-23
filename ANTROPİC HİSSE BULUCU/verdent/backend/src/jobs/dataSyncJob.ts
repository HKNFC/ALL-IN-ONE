import cron from 'node-cron'
import { prisma } from '../lib/prisma'
import { dataService } from '../services/dataService'
import { analyzeMarketCondition, saveMarketCondition } from '../services/marketConditionService'
import { calculateAllIndicators } from '../utils/indicators'
import type { OHLCV } from '../types/market'


// ---------------------------------------------------------------------------
// Logger
// ---------------------------------------------------------------------------
function log(level: 'INFO' | 'WARN' | 'ERROR', msg: string, meta?: unknown): void {
  const ts = new Date().toISOString()
  const suffix = meta ? ` | ${JSON.stringify(meta)}` : ''
  console.log(`[${ts}] [DataSync] [${level}] ${msg}${suffix}`)
}

// ---------------------------------------------------------------------------
// Update a single stock: fetch prices, calc indicators, upsert to DB
// ---------------------------------------------------------------------------
async function syncStock(
  stockId: string,
  symbol: string,
  lookbackDays: number = 400
): Promise<void> {
  const endDate = new Date()
  const startDate = new Date()
  startDate.setDate(startDate.getDate() - lookbackDays)

  const prices = await dataService.fetchStockPrice(symbol, startDate, endDate, '1d')
  if (prices.length === 0) {
    log('WARN', `No price data for ${symbol}`)
    return
  }

  const indicators = calculateAllIndicators(prices)

  // Batch upsert price rows
  const upserts = prices.map((bar: OHLCV, i: number) =>
    prisma.stockPrice.upsert({
      where: { stockId_date: { stockId, date: bar.date } },
      create: {
        stockId,
        date: bar.date,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
        volume: bar.volume,
        rsi14: indicators.rsi14[i] ?? null,
        macd: indicators.macd.macdLine[i] ?? null,
        macdSignal: indicators.macd.signalLine[i] ?? null,
        ema20: indicators.ema20[i] ?? null,
        ema50: indicators.ema50[i] ?? null,
        ema200: indicators.ema200[i] ?? null,
        sma50: indicators.sma50[i] ?? null,
        sma200: indicators.sma200[i] ?? null,
        atr14: indicators.atr14[i] ?? null,
        obv: indicators.obv[i] ?? null,
        vwap: indicators.vwap[i] ?? null,
        bbUpper: indicators.bollinger.upper[i] ?? null,
        bbMiddle: indicators.bollinger.middle[i] ?? null,
        bbLower: indicators.bollinger.lower[i] ?? null,
        adx14: indicators.adx14.adx[i] ?? null,
        stochK: indicators.stochastic.k[i] ?? null,
        stochD: indicators.stochastic.d[i] ?? null,
      },
      update: {
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
        volume: bar.volume,
        rsi14: indicators.rsi14[i] ?? null,
        macd: indicators.macd.macdLine[i] ?? null,
        macdSignal: indicators.macd.signalLine[i] ?? null,
        ema20: indicators.ema20[i] ?? null,
        ema50: indicators.ema50[i] ?? null,
        ema200: indicators.ema200[i] ?? null,
        sma50: indicators.sma50[i] ?? null,
        sma200: indicators.sma200[i] ?? null,
        atr14: indicators.atr14[i] ?? null,
        obv: indicators.obv[i] ?? null,
        vwap: indicators.vwap[i] ?? null,
        bbUpper: indicators.bollinger.upper[i] ?? null,
        bbMiddle: indicators.bollinger.middle[i] ?? null,
        bbLower: indicators.bollinger.lower[i] ?? null,
        adx14: indicators.adx14.adx[i] ?? null,
        stochK: indicators.stochastic.k[i] ?? null,
        stochD: indicators.stochastic.d[i] ?? null,
      },
    })
  )

  // Execute in chunks of 50 to avoid overwhelming the DB
  const CHUNK = 50
  for (let i = 0; i < upserts.length; i += CHUNK) {
    await prisma.$transaction(upserts.slice(i, i + CHUNK))
  }

  log('INFO', `Synced ${prices.length} bars for ${symbol}`)
}

// ---------------------------------------------------------------------------
// Update market condition snapshot (uses MarketConditionService engine)
// ---------------------------------------------------------------------------
async function syncMarketConditions(): Promise<void> {
  for (const market of ['BIST', 'US']) {
    try {
      const result = await analyzeMarketCondition(market, new Date())
      await saveMarketCondition(result)
      log('INFO', `Market condition updated: ${market} → ${result.condition} score=${result.score} confidence=${result.confidence}%`)
    } catch (err) {
      log('ERROR', `Failed to sync market condition for ${market}`, err)
    }
  }
}

// ---------------------------------------------------------------------------
// Full sync job: all tracked stocks
// ---------------------------------------------------------------------------
async function runFullSync(): Promise<void> {
  log('INFO', '=== Starting full data sync ===')
  const started = Date.now()

  // Fetch all stocks tracked in DB
  const stocks = await prisma.stock.findMany({ select: { id: true, symbol: true, market: true } })

  if (stocks.length === 0) {
    log('WARN', 'No stocks in database — seeding from constituent lists')
    await seedInitialStocks()
    return
  }

  log('INFO', `Syncing ${stocks.length} stocks`)

  let success = 0
  let failed = 0

  // Process in concurrent batches, respecting API rate limits:
  // US: 5 req/min (Alpha Vantage free tier), BIST: 10 req/min
  const CONCURRENCY = 5
  for (let i = 0; i < stocks.length; i += CONCURRENCY) {
    const batch = stocks.slice(i, i + CONCURRENCY)
    const results = await Promise.allSettled(
      batch.map((s) => syncStock(s.id, s.symbol))
    )
    results.forEach((r, idx) => {
      if (r.status === 'fulfilled') {
        success++
      } else {
        failed++
        log('ERROR', `Failed to sync ${batch[idx].symbol}`, r.reason)
      }
    })

    // Rate-limit pause between batches (750ms → ~5 req/min safe margin)
    if (i + CONCURRENCY < stocks.length) {
      await sleep(750)
    }
  }

  // Update market conditions after prices are fresh
  await syncMarketConditions()

  const elapsed = ((Date.now() - started) / 1000).toFixed(1)
  log('INFO', `=== Full sync complete in ${elapsed}s — ${success} OK, ${failed} failed ===`)
}

// ---------------------------------------------------------------------------
// Seed initial stock list if database is empty
// ---------------------------------------------------------------------------
async function seedInitialStocks(): Promise<void> {
  const [bistSymbols, sp500Symbols] = await Promise.all([
    dataService.getBIST100Constituents(),
    dataService.getSP500Constituents(),
  ])

  const upserts = [
    ...bistSymbols.map((symbol) => ({
      symbol,
      name: symbol,
      market: 'BIST',
    })),
    ...sp500Symbols.map((symbol) => ({
      symbol,
      name: symbol,
      market: 'US',
    })),
  ]

  for (const stock of upserts) {
    await prisma.stock.upsert({
      where: { symbol: stock.symbol },
      create: stock,
      update: {},
    })
  }

  log('INFO', `Seeded ${upserts.length} stocks (${bistSymbols.length} BIST + ${sp500Symbols.length} US)`)
}

// ---------------------------------------------------------------------------
// Partial sync: only update today's latest bar (runs intraday)
// ---------------------------------------------------------------------------
async function runIncrementalSync(): Promise<void> {
  log('INFO', 'Starting incremental sync (last 5 days)')
  const stocks = await prisma.stock.findMany({ select: { id: true, symbol: true } })
  const CONCURRENCY = 5

  for (let i = 0; i < stocks.length; i += CONCURRENCY) {
    const batch = stocks.slice(i, i + CONCURRENCY)
    await Promise.allSettled(batch.map((s) => syncStock(s.id, s.symbol, 5)))
    if (i + CONCURRENCY < stocks.length) await sleep(750)
  }

  log('INFO', 'Incremental sync complete')
}

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

// ---------------------------------------------------------------------------
// Cron schedule registration
// ---------------------------------------------------------------------------
export function startDataSyncJob(): void {
  // Full sync: Mon–Fri at 19:00 (after US market close 18:00 UTC+1)
  cron.schedule('0 19 * * 1-5', async () => {
    try {
      await runFullSync()
    } catch (err) {
      log('ERROR', 'Full sync job threw uncaught error', err)
    }
  }, { timezone: 'Europe/Istanbul' })

  // BIST incremental sync: Mon–Fri at 18:45 (after BIST close 18:00 TR)
  cron.schedule('45 18 * * 1-5', async () => {
    try {
      await runIncrementalSync()
    } catch (err) {
      log('ERROR', 'Incremental sync job threw uncaught error', err)
    }
  }, { timezone: 'Europe/Istanbul' })

  // Market condition refresh: every weekday at 09:00 and 16:00
  cron.schedule('0 9,16 * * 1-5', async () => {
    try {
      await syncMarketConditions()
    } catch (err) {
      log('ERROR', 'Market condition sync threw uncaught error', err)
    }
  }, { timezone: 'Europe/Istanbul' })

  log('INFO', 'Data sync jobs registered (full: 19:00, incremental: 18:45, conditions: 09:00+16:00 TR time)')
}

// Allow one-off manual run via: npx ts-node src/jobs/dataSyncJob.ts
if (require.main === module) {
  runFullSync()
    .then(() => prisma.$disconnect())
    .then(() => Promise.resolve())
    .catch((err) => {
      log('ERROR', 'Manual sync failed', err)
      process.exit(1)
    })
}

export { runFullSync, runIncrementalSync, syncMarketConditions, seedInitialStocks }
