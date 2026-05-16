/**
 * GET /api/market/condition/:market          — current condition
 * GET /api/market/condition/:market/:date    — historical condition
 * GET /api/market/indicators/:market         — detailed indicators breakdown
 * GET /api/market/history/:market            — paginated condition history
 * GET /api/market/breadth/:market            — advance/decline, % above 200SMA, new-highs/lows
 * GET /api/market/index/:index               — latest index value (BIST100 | SP500 | VIX)
 */

import { Router } from 'express';
import { z }       from 'zod';
import { ok, fail, asyncHandler, validateQuery, apiLimiter, DateStrSchema } from '../middleware';
import { analyzeMarketCondition, generateMockSeries } from '../services/marketConditionService';
import { dataService } from '../services/dataService';
import { MarketService } from '../services/marketService';

const marketSvc = new MarketService();

const router = Router();
router.use(apiLimiter);

// ── Param validation ─────────────────────────────────────────────────────────

function resolveMarket(raw: string): 'BIST' | 'US' | null {
  const m = raw.toUpperCase();
  if (m === 'BIST' || m === 'US') return m;
  return null;
}

// ── GET /indices — ticker band için S&P, NASDAQ, DOW, VIX, BTC, GOLD, USD/TRY ──

router.get('/indices', asyncHandler(async (_req, res) => {
  const data = await marketSvc.getIndices();
  ok(res, data);
}));

// ── GET /condition/:market ────────────────────────────────────────────────────

router.get('/condition/:market', asyncHandler(async (req, res) => {
  const market = resolveMarket(String(req.params.market));
  if (!market) { fail(res, 'market must be BIST or US'); return; }

  try {
    // Attempt real data fetch; fall back to mock on error
    const bars = await dataService.fetchStockPrice(
      market === 'BIST' ? 'XU100.IS' : '^GSPC',
      new Date(Date.now() - 365 * 86400_000),
      new Date(),
      '1d',
    );
    const series = bars.length >= 30
      ? bars.map(b => ({ date: b.date, open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume }))
      : generateMockSeries(300);
    const result = analyzeMarketCondition({ market, date: new Date(), series });
    ok(res, result);
  } catch {
    const series = generateMockSeries(300);
    ok(res, analyzeMarketCondition({ market, date: new Date(), series }));
  }
}));

// ── GET /condition/:market/:date ──────────────────────────────────────────────

router.get('/condition/:market/:date', asyncHandler(async (req, res) => {
  const market = resolveMarket(String(req.params.market));
  if (!market) { fail(res, 'market must be BIST or US'); return; }

  const parsed = DateStrSchema.safeParse(String(req.params.date));
  if (!parsed.success) { fail(res, 'date must be YYYY-MM-DD'); return; }

  const targetDate = new Date(parsed.data);
  if (isNaN(targetDate.getTime())) { fail(res, 'Invalid date'); return; }

  try {
    const { PrismaClient } = await import('@prisma/client');
    const prisma = new PrismaClient();
    const record = await prisma.marketCondition.findFirst({
      where: {
        market,
        date: { gte: new Date(parsed.data + 'T00:00:00Z'), lte: new Date(parsed.data + 'T23:59:59Z') },
      },
    }).finally(() => prisma.$disconnect());

    if (record) { ok(res, record); return; }
  } catch { /* fall through to mock */ }

  // Deterministic mock for historical dates
  const series = generateMockSeries(300);
  ok(res, analyzeMarketCondition({ market, date: targetDate, series }));
}));

// ── GET /indicators/:market ───────────────────────────────────────────────────

router.get('/indicators/:market', asyncHandler(async (req, res) => {
  const market = resolveMarket(String(req.params.market));
  if (!market) { fail(res, 'market must be BIST or US'); return; }

  const series = generateMockSeries(300);
  const result = analyzeMarketCondition({ market, date: new Date(), series });
  ok(res, {
    market,
    condition: result.condition,
    score:     result.score,
    confidence: result.confidence,
    indicators: result.indicators,
    updatedAt:  new Date(),
  });
}));

// ── GET /history/:market ──────────────────────────────────────────────────────

const HistoryQuerySchema = z.object({
  limit:  z.coerce.number().int().min(1).max(365).default(30),
  offset: z.coerce.number().int().min(0).default(0),
});

router.get('/history/:market', validateQuery(HistoryQuerySchema), asyncHandler(async (req, res) => {
  const market = resolveMarket(String(req.params.market));
  if (!market) { fail(res, 'market must be BIST or US'); return; }

  const { limit, offset } = (req as typeof req & { validQuery: z.infer<typeof HistoryQuerySchema> }).validQuery;

  try {
    const { PrismaClient } = await import('@prisma/client');
    const prisma = new PrismaClient();
    const [records, total] = await Promise.all([
      prisma.marketCondition.findMany({
        where:   { market },
        orderBy: { date: 'desc' },
        skip:    offset,
        take:    limit,
      }),
      prisma.marketCondition.count({ where: { market } }),
    ]).finally(() => prisma.$disconnect());
    ok(res, records, { total, limit, offset });
    return;
  } catch { /* fall through */ }

  // Mock history
  const mock = Array.from({ length: limit }, (_, i) => {
    const d = new Date(Date.now() - (offset + i) * 86400_000);
    const s = generateMockSeries(300);
    return analyzeMarketCondition({ market, date: d, series: s });
  });
  ok(res, mock, { total: 365, limit, offset });
}));

// ── GET /breadth/:market ──────────────────────────────────────────────────────

router.get('/breadth/:market', asyncHandler(async (req, res) => {
  const market = resolveMarket(String(req.params.market));
  if (!market) { fail(res, 'market must be BIST or US'); return; }

  try {
    const breadth = await dataService.getMarketBreadth(market);
    ok(res, breadth);
  } catch (err) {
    // Fallback mock
    ok(res, {
      market, date: new Date(),
      advanceDeclineRatio: market === 'BIST' ? 1.42 : 0.78,
      pctAbove200SMA:      market === 'BIST' ? 68.2 : 41.3,
      new52wHighs:         market === 'BIST' ? 12 : 7,
      new52wLows:          market === 'BIST' ? 3 : 18,
      totalStocks:         market === 'BIST' ? 100 : 503,
    });
  }
}));

// ── GET /index/:index ─────────────────────────────────────────────────────────

router.get('/index/:index', asyncHandler(async (req, res) => {
  const valid = ['BIST100', 'SP500', 'VIX'] as const;
  type Idx = typeof valid[number];
  const index = String(req.params.index).toUpperCase() as Idx;
  if (!valid.includes(index)) { fail(res, `index must be one of ${valid.join(', ')}`); return; }

  try {
    const data = await dataService.fetchMarketIndex(index);
    if (!data) { fail(res, 'No data available', 404); return; }
    ok(res, data);
  } catch {
    fail(res, 'Failed to fetch index data', 502);
  }
}));

export default router;
