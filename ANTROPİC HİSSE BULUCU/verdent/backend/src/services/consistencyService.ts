/**
 * DeterministicScanner — single source of truth for stock screening.
 *
 * BOTH the Scanner page and the BacktestEngine call `deterministicScanner.scan()`.
 * Same inputs → same hash key → same cached result → 100 % consistency.
 *
 * Cache hierarchy (fastest → slowest):
 *   1. In-process LRU Map  (TTL: 4 h, max 500 entries)
 *   2. PostgreSQL ScanResult table  (permanent, keyed by hash)
 *   3. Fresh computation
 */

import { createHash }  from 'crypto'
import { prisma } from '../lib/prisma'
import { screenStocks } from './criteriaEngine'
import type { ScoredStock, CriteriaType } from '../types/market'


// ── In-process LRU cache ─────────────────────────────────────────────────────

const TTL_MS   = 4 * 60 * 60 * 1000   // 4 hours
const MAX_SIZE = 500

interface CacheEntry {
  result:    ScoredStock[]
  expiresAt: number
}

const memCache = new Map<string, CacheEntry>()

function pruneCache(): void {
  if (memCache.size < MAX_SIZE) return
  const now   = Date.now()
  let   oldest: string | null = null
  let   oldestTs              = Infinity
  for (const [key, entry] of memCache) {
    if (entry.expiresAt < now) { memCache.delete(key); return }
    if (entry.expiresAt < oldestTs) { oldestTs = entry.expiresAt; oldest = key }
  }
  if (oldest) memCache.delete(oldest)
}

// ── Hash key ─────────────────────────────────────────────────────────────────

/**
 * Normalise date to YYYY-MM-DD so intra-day timestamps don't break caching.
 */
function cacheKey(criteria: string, date: Date, market: string): string {
  const day = date.toISOString().slice(0, 10)
  return createHash('sha256')
    .update(`${criteria.toUpperCase()}|${day}|${market.toUpperCase()}`)
    .digest('hex')
}

// ── DB cache helpers ─────────────────────────────────────────────────────────

async function lookupDbCache(
  hash: string,
): Promise<ScoredStock[] | null> {
  try {
    // We store the hash as the criteria name with a special prefix so we can
    // query without a full-text search.
    const rows = await prisma.scanResult.findMany({
      where: { criteria: { name: `__hash__${hash}` } },
      orderBy: { rank: 'asc' },
      include: { stock: { select: { symbol: true, name: true } } },
    })
    if (rows.length === 0) return null

    return rows.map((r) => ({
      symbol:            r.stock.symbol,
      name:              r.stock.name,
      score:             r.score,
      rank:              r.rank,
      entryPrice:        r.entryPrice,
      targetPrice:       r.targetPrice ?? 0,
      suggestedStopLoss: r.stopLoss    ?? 0,
      riskRewardRatio:   0,
      signals:           r.signals as unknown as ScoredStock['signals'],
    }))
  } catch {
    return null
  }
}

async function writeDbCache(
  hash:     string,
  criteria: string,
  date:     Date,
  market:   string,
  results:  ScoredStock[],
): Promise<void> {
  try {
    // Upsert a Criteria row for this hash so we can reference it
    const criteriaRow = await prisma.criteria.upsert({
      where:  { id: `__hash__${hash}` },
      update: {},
      create: {
        id:           `__hash__${hash}`,
        name:         `__hash__${hash}`,
        displayName:  `${criteria}@${date.toISOString().slice(0, 10)}/${market}`,
        market:       market.toUpperCase(),
        description:  'Auto-generated cache entry',
        rules:        {},
        scoringWeights: {},
        isActive:     false,
      },
    })

    // Upsert stock rows then ScanResult rows (best-effort)
    for (const s of results) {
      await prisma.stock.upsert({
        where:  { symbol: s.symbol },
        update: {},
        create: {
          symbol: s.symbol,
          name:   s.name,
          market: market.toUpperCase(),
        },
      }).catch(() => { /* stock might already exist with different casing */ })

      const stockRow = await prisma.stock.findUnique({ where: { symbol: s.symbol } })
      if (!stockRow) continue

      await prisma.scanResult.upsert({
        where: {
          scanDate_criteriaId_stockId: {
            scanDate:   date,
            criteriaId: criteriaRow.id,
            stockId:    stockRow.id,
          },
        },
        update: { score: s.score, rank: s.rank, signals: (s.signals ?? {}) as object },
        create: {
          scanDate:   date,
          criteriaId: criteriaRow.id,
          stockId:    stockRow.id,
          score:      s.score,
          rank:       s.rank,
          signals:    (s.signals ?? {}) as object,
          entryPrice: s.entryPrice,
          targetPrice: s.targetPrice,
          stopLoss:    s.suggestedStopLoss,
        },
      }).catch(() => { /* silently skip on conflict */ })
    }
  } catch {
    // DB cache write is non-fatal
  }
}

// ── DeterministicScanner ─────────────────────────────────────────────────────

export class DeterministicScanner {
  /**
   * The single canonical scan function used by both Scanner page and BacktestEngine.
   * Results for identical (criteria, date, market) inputs are always identical.
   */
  async scan(
    criteria: string,
    date: Date,
    market: string,
  ): Promise<ScoredStock[]> {
    const hash = cacheKey(criteria, date, market)
    const now  = Date.now()

    // ── 1. In-process cache ──
    const mem = memCache.get(hash)
    if (mem && mem.expiresAt > now && mem.result.length > 0) return mem.result

    // ── 2. Fresh computation (strict no-look-ahead) ──
    // DB cache disabled — stale results from old limited scans caused BIST-TUM miss
    const result = await screenStocks(
      criteria as CriteriaType,
      date,
      market,
    )

    // ── 3. Persist to in-process cache only ──
    pruneCache()
    memCache.set(hash, { result, expiresAt: now + TTL_MS })

    return result
  }

  /** Purge a specific entry (e.g. after new price data arrives). */
  invalidate(criteria: string, date: Date, market: string): void {
    memCache.delete(cacheKey(criteria, date, market))
  }

  /** Purge all in-process cache entries (does not touch DB). */
  invalidateAll(): void {
    memCache.clear()
  }

  /** Return cache stats for monitoring. */
  stats(): { size: number; maxSize: number; ttlMs: number } {
    return { size: memCache.size, maxSize: MAX_SIZE, ttlMs: TTL_MS }
  }
}

export const deterministicScanner = new DeterministicScanner()
