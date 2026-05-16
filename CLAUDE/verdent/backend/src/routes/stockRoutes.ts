/**
 * GET /api/stocks/search?q=&market=&limit=    — search by symbol/name
 * GET /api/stocks/list/:market               — all stocks in market (paginated)
 * GET /api/stocks/:symbol                    — stock info
 * GET /api/stocks/:symbol/price?start=&end=&interval=
 * GET /api/stocks/:symbol/indicators         — technical indicators
 * GET /api/stocks/:symbol/fundamentals       — fundamental data
 */

import { Router } from 'express';
import { z }      from 'zod';
import { ok, fail, asyncHandler, validateQuery, apiLimiter, DateStrSchema } from '../middleware';
import { dataService } from '../services/dataService';

const router = Router();
router.use(apiLimiter);

// ── GET /search ──────────────────────────────────────────────────────────────

const SearchQuerySchema = z.object({
  q:      z.string().min(1).max(20),
  market: z.enum(['BIST','US']).optional(),
  limit:  z.coerce.number().int().min(1).max(50).default(10),
});

router.get('/search', validateQuery(SearchQuerySchema), asyncHandler(async (req, res) => {
  const q = (req as typeof req & { validQuery: z.infer<typeof SearchQuerySchema> }).validQuery;

  try {
    const { PrismaClient } = await import('@prisma/client');
    const prisma = new PrismaClient();
    const rows = await prisma.stock.findMany({
      where: {
        ...(q.market ? { market: q.market } : {}),
        OR: [
          { symbol: { contains: q.q.toUpperCase() } },
          { name:   { contains: q.q, mode: 'insensitive' } },
        ],
      },
      take: q.limit,
      orderBy: { symbol: 'asc' },
    }).finally(() => prisma.$disconnect());
    ok(res, rows);
    return;
  } catch { /* use mock */ }

  // Mock fallback
  const symbols = q.market === 'BIST'
    ? ['THYAO','EREGL','SISE','AKBNK','TUPRS','ASELS','KCHOL','BIMAS','YKBNK','FROTO']
    : ['AAPL','MSFT','GOOGL','AMZN','NVDA','META','TSLA','BRK.B','UNH','JNJ'];
  const filtered = symbols.filter(s => s.includes(q.q.toUpperCase())).slice(0, q.limit);
  ok(res, filtered.map(s => ({ symbol: s, name: s, market: q.market ?? 'BIST' })));
}));

// ── GET /list/:market ────────────────────────────────────────────────────────

const ListQuerySchema = z.object({
  limit:  z.coerce.number().int().min(1).max(500).default(50),
  offset: z.coerce.number().int().min(0).default(0),
});

router.get('/list/:market', validateQuery(ListQuerySchema), asyncHandler(async (req, res) => {
  const market = String(req.params.market).toUpperCase();
  if (market !== 'BIST' && market !== 'US') { fail(res, 'market must be BIST or US'); return; }
  const q = (req as typeof req & { validQuery: z.infer<typeof ListQuerySchema> }).validQuery;

  try {
    const { PrismaClient } = await import('@prisma/client');
    const prisma = new PrismaClient();
    const [rows, total] = await Promise.all([
      prisma.stock.findMany({ where: { market }, skip: q.offset, take: q.limit, orderBy: { symbol: 'asc' } }),
      prisma.stock.count({ where: { market } }),
    ]).finally(() => prisma.$disconnect());
    ok(res, rows, { total, limit: q.limit, offset: q.offset });
    return;
  } catch { /* mock */ }

  const all = market === 'BIST'
    ? await dataService.getBIST100Constituents().catch(() => ['THYAO','EREGL','SISE','AKBNK','TUPRS'])
    : await dataService.getSP500Constituents().catch(() => ['AAPL','MSFT','GOOGL','AMZN','NVDA']);
  const paged = all.slice(q.offset, q.offset + q.limit).map(s => ({ symbol: s, name: s, market }));
  ok(res, paged, { total: all.length, limit: q.limit, offset: q.offset });
}));

// ── GET /:symbol ─────────────────────────────────────────────────────────────

router.get('/:symbol', asyncHandler(async (req, res) => {
  const symbol = String(req.params.symbol).toUpperCase();

  try {
    const { PrismaClient } = await import('@prisma/client');
    const prisma = new PrismaClient();
    const stock = await prisma.stock.findUnique({ where: { symbol } }).finally(() => prisma.$disconnect());
    if (stock) { ok(res, stock); return; }
  } catch { /* fall through */ }

  // Mock
  ok(res, { symbol, name: symbol, market: symbol.length <= 5 && /^[A-Z]+$/.test(symbol) ? 'BIST' : 'US' });
}));

// ── GET /:symbol/price ────────────────────────────────────────────────────────

const PriceQuerySchema = z.object({
  start:    DateStrSchema.optional(),
  end:      DateStrSchema.optional(),
  interval: z.enum(['1d','1wk','1mo']).default('1d'),
});

router.get('/:symbol/price', validateQuery(PriceQuerySchema), asyncHandler(async (req, res) => {
  const symbol = String(req.params.symbol).toUpperCase();
  const q = (req as typeof req & { validQuery: z.infer<typeof PriceQuerySchema> }).validQuery;

  const startDate = q.start ? new Date(q.start) : new Date(Date.now() - 365 * 86400_000);
  const endDate   = q.end   ? new Date(q.end)   : new Date();

  try {
    const prices = await dataService.fetchStockPrice(symbol, startDate, endDate, q.interval);
    ok(res, prices);
  } catch (err) {
    fail(res, `Failed to fetch price data: ${(err as Error).message}`, 502);
  }
}));

// ── GET /:symbol/indicators ───────────────────────────────────────────────────

router.get('/:symbol/indicators', asyncHandler(async (req, res) => {
  const symbol = String(req.params.symbol).toUpperCase();

  try {
    const prices = await dataService.fetchStockPrice(symbol, new Date(Date.now() - 365 * 86400_000), new Date(), '1d');
    if (prices.length < 30) { fail(res, 'Insufficient price data to calculate indicators', 422); return; }
    const indicators = await dataService.calculateIndicators(prices);
    ok(res, { symbol, indicators, calculatedAt: new Date() });
  } catch (err) {
    fail(res, `Indicator calculation failed: ${(err as Error).message}`, 502);
  }
}));

// ── GET /:symbol/fundamentals ─────────────────────────────────────────────────

router.get('/:symbol/fundamentals', asyncHandler(async (req, res) => {
  const symbol = String(req.params.symbol).toUpperCase();

  try {
    const fundamentals = await dataService.fetchFundamentals(symbol);
    ok(res, { ...fundamentals, fetchedAt: new Date() });
  } catch (err) {
    fail(res, `Fundamentals fetch failed: ${(err as Error).message}`, 502);
  }
}));

export default router;
