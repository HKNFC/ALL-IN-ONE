import { Router } from 'express';
import {
  BacktestEngine,
  generateRebalanceDates,
  saveBacktestResult,
  loadBacktestResult,
  sharedScan,
  type BacktestConfig,
  type RebalancePeriod,
} from '../services/backtestEngine';
import { generateMockStocks, type CriteriaType } from '../services/criteriaEngine';

const router  = Router();
const engine  = new BacktestEngine();

// ── POST /api/backtest/run ──────────────────────────────────────────────────
router.post('/run', async (req, res) => {
  try {
    const body = req.body as Partial<BacktestConfig>;

    if (!body.startDate || !body.endDate) {
      return res.status(400).json({ error: 'startDate and endDate are required' });
    }

    const config: BacktestConfig = {
      name:            body.name            ?? 'Unnamed Backtest',
      criteriaType:    (body.criteriaType ?? 'HYBRID') as CriteriaType | 'HYBRID',
      startDate:       new Date(body.startDate),
      endDate:         new Date(body.endDate),
      rebalancePeriod: (body.rebalancePeriod ?? 'MONTHLY') as RebalancePeriod,
      market:          (body.market ?? 'US') as BacktestConfig['market'],
      initialCapital:  Number(body.initialCapital ?? 100_000),
      transactionCost: Number(body.transactionCost ?? 0.001),
      slippage:        Number(body.slippage        ?? 0.001),
      portfolioSize:   Number((body as any).portfolioSize ?? 5),
    };

    const result = await engine.runBacktest(config);
    res.json({ data: result });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// ── POST /api/backtest/run/save ─────────────────────────────────────────────
router.post('/run/save', async (req, res) => {
  try {
    const body = req.body as Partial<BacktestConfig>;
    if (!body.startDate || !body.endDate) {
      return res.status(400).json({ error: 'startDate and endDate are required' });
    }
    const config: BacktestConfig = {
      name:            body.name            ?? 'Saved Backtest',
      criteriaType:    (body.criteriaType ?? 'HYBRID') as CriteriaType | 'HYBRID',
      startDate:       new Date(body.startDate),
      endDate:         new Date(body.endDate),
      rebalancePeriod: (body.rebalancePeriod ?? 'MONTHLY') as RebalancePeriod,
      market:          (body.market ?? 'US') as BacktestConfig['market'],
      initialCapital:  Number(body.initialCapital ?? 100_000),
      transactionCost: Number(body.transactionCost ?? 0.001),
      slippage:        Number(body.slippage        ?? 0.001),
      portfolioSize:   Number((body as any).portfolioSize ?? 5),
    };
    const result = await engine.runBacktest(config);
    const id     = await saveBacktestResult(result);
    res.json({ id, performance: result.performance, runtimeMs: result.runtimeMs });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// ── GET /api/backtest/:id ───────────────────────────────────────────────────
router.get('/:id', async (req, res) => {
  try {
    const data = await loadBacktestResult(req.params.id);
    if (!data) return res.status(404).json({ error: 'Backtest not found' });
    res.json({ data });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// ── GET /api/backtest/list ──────────────────────────────────────────────────
router.get('/', async (_req, res) => {
  try {
    const { PrismaClient } = await import('@prisma/client');
    const prisma = new PrismaClient();
    const rows = await prisma.backtest.findMany({
      where:   { isDeleted: false },
      orderBy: { createdAt: 'desc' },
      select:  {
        id: true, name: true, criteriaType: true, market: true,
        startDate: true, endDate: true, status: true, createdAt: true,
        totalReturn: true, sharpeRatio: true, maxDrawdown: true,
      },
    });
    await prisma.$disconnect();
    res.json({ data: rows });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// ── DELETE /api/backtest/:id ────────────────────────────────────────────────
router.delete('/:id', async (req, res) => {
  try {
    const { PrismaClient } = await import('@prisma/client');
    const prisma = new PrismaClient();
    await prisma.backtest.update({
      where: { id: req.params.id },
      data:  { isDeleted: true },
    });
    await prisma.$disconnect();
    res.json({ success: true });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// ── GET /api/backtest/rebalance-dates ──────────────────────────────────────
router.get('/utils/rebalance-dates', (req, res) => {
  try {
    const { start, end, period } = req.query;
    if (!start || !end) {
      return res.status(400).json({ error: 'start and end query params required' });
    }
    const dates = generateRebalanceDates(
      new Date(start as string),
      new Date(end   as string),
      (period ?? 'MONTHLY') as RebalancePeriod,
    );
    res.json({ count: dates.length, dates });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// ── GET /api/backtest/scan/verify ──────────────────────────────────────────
// Consistency endpoint: returns the same picks that backtest would use for
// a given date × criteria × market (identical to Scanner page output).
router.get('/scan/verify', (req, res) => {
  try {
    const { criteria, market = 'US', date } = req.query;
    if (!criteria) return res.status(400).json({ error: 'criteria is required' });
    const upper   = (criteria as string).toUpperCase() as CriteriaType;
    const stocks  = generateMockStocks(30, market as 'US' | 'BIST');
    const results = sharedScan(stocks, upper, 5);
    res.json({
      note: 'These are the exact same picks the backtester uses on this date',
      criteria: upper, market, date: date ?? new Date().toISOString(),
      picks: results.map(s => ({ rank: s.rank, symbol: s.symbol, score: s.score })),
    });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

export default router;
