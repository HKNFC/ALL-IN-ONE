/**
 * POST /api/scanner/scan                — run a scan (shared engine, backtest-consistent)
 * GET  /api/scanner/results             — list saved scan results
 * GET  /api/scanner/results/:id         — get a specific result
 * DELETE /api/scanner/results/:id       — delete a result
 */

import { Router }   from 'express';
import { z }        from 'zod';
import { randomUUID } from 'crypto';
import {
  ok, fail, asyncHandler, validateBody, validateQuery,
  apiLimiter, heavyLimiter, ScanBodySchema,
} from '../middleware';
import { screenStocksSync, generateMockStocks, type CriteriaType, type UniverseType } from '../services/criteriaEngine';
import { analyzeMarketCondition, generateMockSeries } from '../services/marketConditionService';
import { wsEvents } from '../ws';

const router = Router();
router.use(apiLimiter);

// ── In-memory result store (replace with DB queries in production) ────────────

interface StoredScan {
  id:              string;
  criteria:        string;
  date:            string;
  market:          string;
  scannedTotal:    number;
  passedFilters:   number;
  stocks:          unknown[];
  marketCondition: unknown;
  runtimeMs:       number;
  savedAt:         Date;
}
const scanStore = new Map<string, StoredScan>();

// ── POST /scan ────────────────────────────────────────────────────────────────

router.post('/scan', heavyLimiter, validateBody(ScanBodySchema), asyncHandler(async (req, res) => {
  const { criteria, date, market } = req.body as z.infer<typeof ScanBodySchema>;
  const t0 = Date.now();

  // Resolve stock universe based on market/universe type
  const isBIST = market !== 'US';
  const baseMarket: 'BIST' | 'US' = isBIST ? 'BIST' : 'US';
  const mockCount = market === 'US' ? 903 : market === 'BISTTUM' ? 603 : market === 'BIST100' ? 100 : market === 'BIST100DISI' ? 503 : 100;
  let stocks = generateMockStocks(mockCount, baseMarket, market as UniverseType);
  try {
    const { PrismaClient } = await import('@prisma/client');
    const { BIST100_SYMBOLS } = await import('../services/dataService');
    const prisma = new PrismaClient();

    // Build DB filter based on universe
    const marketFilter = isBIST
      ? { market: 'BIST' as const }
      : { market: { not: 'BIST' as const } };

    const dbStocks = await prisma.stock.findMany({
      where: marketFilter,
      include: {
        prices: {
          where:   { date: { lte: new Date(date) } },
          orderBy: { date: 'desc' },
          take:    300,
        },
      },
    }).finally(() => prisma.$disconnect());

    if (dbStocks.length > 0) {
      // Filter by universe if BIST100 or BIST100DISI
      let filtered = dbStocks;
      if (market === 'BIST100')     filtered = dbStocks.filter(s => BIST100_SYMBOLS.includes(s.symbol));
      if (market === 'BIST100DISI') filtered = dbStocks.filter(s => !BIST100_SYMBOLS.includes(s.symbol));
      stocks = generateMockStocks(filtered.length, baseMarket, market as UniverseType);
    }
  } catch { /* use mock */ }

  const topStocks = screenStocksSync(stocks, criteria as CriteriaType).slice(0, 5);

  // Market condition on that date
  const series = generateMockSeries(300);
  const mc = analyzeMarketCondition({ market: baseMarket, date: new Date(date), series });

  const result: StoredScan = {
    id:              randomUUID(),
    criteria,
    date,
    market,
    scannedTotal:    stocks.length,
    passedFilters:   topStocks.length,
    stocks:          topStocks,
    marketCondition: mc,
    runtimeMs:       Date.now() - t0,
    savedAt:         new Date(),
  };

  scanStore.set(result.id, result);
  wsEvents.emit('scan:complete', { id: result.id, result });

  ok(res, result, undefined, 201);
}));

// ── GET /results ──────────────────────────────────────────────────────────────

const ListQuerySchema = z.object({
  limit:    z.coerce.number().int().min(1).max(100).default(20),
  offset:   z.coerce.number().int().min(0).default(0),
  criteria: z.enum(['ALFA','BETA','DELTA']).optional(),
  market:   z.enum(['BIST','US']).optional(),
});

router.get('/results', validateQuery(ListQuerySchema), asyncHandler(async (req, res) => {
  const q = (req as typeof req & { validQuery: z.infer<typeof ListQuerySchema> }).validQuery;

  let items = [...scanStore.values()].sort((a, b) => b.savedAt.getTime() - a.savedAt.getTime());
  if (q.criteria) items = items.filter(i => i.criteria === q.criteria);
  if (q.market)   items = items.filter(i => i.market   === q.market);

  const total  = items.length;
  const paged  = items.slice(q.offset, q.offset + q.limit);
  ok(res, paged, { total, limit: q.limit, offset: q.offset });
}));

// ── GET /results/:id ──────────────────────────────────────────────────────────

router.get('/results/:id', asyncHandler(async (req, res) => {
  const item = scanStore.get(String(req.params.id));
  if (!item) { fail(res, 'Scan result not found', 404); return; }
  ok(res, item);
}));

// ── DELETE /results/:id ───────────────────────────────────────────────────────

router.delete('/results/:id', asyncHandler(async (req, res) => {
  if (!scanStore.has(String(req.params.id))) { fail(res, 'Scan result not found', 404); return; }
  scanStore.delete(String(req.params.id));
  ok(res, { deleted: String(req.params.id) });
}));

export default router;
