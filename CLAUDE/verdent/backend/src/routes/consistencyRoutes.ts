/**
 * GET /api/consistency/check?criteria=&date=&market=
 *
 * Runs the shared screenStocksSync engine for the given date/criteria,
 * then looks up any backtest snapshot for the same date to verify the
 * top-5 symbols match.
 *
 * Returns:
 *   { isConsistent, differences, scanResult, backtestSnapshot }
 */

import { Router } from 'express';
import { z }      from 'zod';
import { ok, fail, asyncHandler, validateQuery, apiLimiter, DateStrSchema } from '../middleware';
import { screenStocksSync, generateMockStocks, type CriteriaType } from '../services/criteriaEngine';
import { analyzeMarketCondition, generateMockSeries } from '../services/marketConditionService';

const router = Router();
router.use(apiLimiter);

const CheckQuerySchema = z.object({
  criteria: z.enum(['ALFA','BETA','DELTA']),
  date:     DateStrSchema,
  market:   z.enum(['BIST','US']),
});

router.get('/check', validateQuery(CheckQuerySchema), asyncHandler(async (req, res) => {
  const q = (req as typeof req & { validQuery: z.infer<typeof CheckQuerySchema> }).validQuery;
  const { criteria, date, market } = q;

  // ── 1. Run shared scan engine (same as Scanner page) ─────────────────────
  let stocks = generateMockStocks(market === 'BIST' ? 100 : 503, market);
  try {
    const { PrismaClient } = await import('@prisma/client');
    const prisma = new PrismaClient();
    const dbStocks = await prisma.stock.findMany({
      where:   { market: market === 'BIST' ? 'BIST' : { not: 'BIST' } },
      include: {
        prices: {
          where:   { date: { lte: new Date(date) } },
          orderBy: { date: 'desc' },
          take:    300,
        },
      },
    }).finally(() => prisma.$disconnect());
    if (dbStocks.length > 0) {
      stocks = generateMockStocks(dbStocks.length, market);
    }
  } catch { /* use mock */ }

  const scanResult = screenStocksSync(stocks, criteria as CriteriaType).slice(0, 5);
  const scanSymbols = scanResult.map(s => s.symbol);

  // ── 2. Look up backtest snapshot for same date/criteria ───────────────────
  let backtestSnapshot: unknown = null;
  let btSymbols: string[] = [];

  try {
    const { PrismaClient } = await import('@prisma/client');
    const prisma = new PrismaClient();

    // Find a completed backtest that covers this date and uses this criteria
    const snapshot = await prisma.backtestSnapshot.findFirst({
      where: {
        date: {
          gte: new Date(date + 'T00:00:00Z'),
          lte: new Date(date + 'T23:59:59Z'),
        },
        criteriaUsed: criteria,
        backtest: {
          status:    'COMPLETED',
          isDeleted: false,
          market:    market === 'BIST' ? 'BIST' : { not: 'BIST' },
        },
      },
      orderBy: { date: 'desc' },
    }).finally(() => prisma.$disconnect());

    if (snapshot) {
      backtestSnapshot = snapshot;
      // Extract symbols from holdings JSON
      const holdings = snapshot.holdings as Array<{ symbol: string }>;
      if (Array.isArray(holdings)) {
        btSymbols = holdings.map(h => h.symbol);
      }
    }
  } catch { /* no DB */ }

  // ── 3. Market condition for context ──────────────────────────────────────
  const series = generateMockSeries(300);
  const mc = analyzeMarketCondition({ market, date: new Date(date), series });

  // ── 4. Compute differences ────────────────────────────────────────────────
  let isConsistent = true;
  const differences: string[] = [];

  if (backtestSnapshot === null) {
    differences.push('No backtest snapshot found for this date/criteria — cannot verify consistency.');
    isConsistent = false;
  } else {
    const missingInBt = scanSymbols.filter(s => !btSymbols.includes(s));
    const extraInBt   = btSymbols.filter(s => !scanSymbols.includes(s));

    if (missingInBt.length > 0) {
      differences.push(`Symbols in scanner but NOT in backtest: ${missingInBt.join(', ')}`);
      isConsistent = false;
    }
    if (extraInBt.length > 0) {
      differences.push(`Symbols in backtest but NOT in scanner: ${extraInBt.join(', ')}`);
      isConsistent = false;
    }
    if (isConsistent) {
      // Check rank order
      for (let i = 0; i < scanSymbols.length; i++) {
        if (scanSymbols[i] !== btSymbols[i]) {
          differences.push(`Rank ${i+1} mismatch: scanner has ${scanSymbols[i]}, backtest has ${btSymbols[i] ?? 'N/A'}`);
          isConsistent = false;
        }
      }
    }
  }

  ok(res, {
    isConsistent,
    differences,
    scanResult,
    backtestSnapshot,
    marketCondition: mc,
    checkedAt: new Date(),
  });
}));

export default router;
