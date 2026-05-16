/**
 * POST   /api/backtest/run               — start new backtest (async, streams progress via WS)
 * GET    /api/backtest/status/:id        — poll run status
 * GET    /api/backtest/results           — list all (not deleted)
 * GET    /api/backtest/results/:id       — full detail
 * DELETE /api/backtest/:id               — soft-delete
 */

import { Router }       from 'express';
import { z }            from 'zod';
import { randomUUID }   from 'crypto';
import {
  ok, fail, asyncHandler, validateBody, validateQuery,
  apiLimiter, heavyLimiter, BacktestConfigSchema,
} from '../middleware';
import { BacktestEngine, type BacktestConfig, type BacktestResult } from '../services/backtestEngine';
import { wsEvents } from '../ws';

const router = Router();
router.use(apiLimiter);

// ── In-process job store ──────────────────────────────────────────────────────

type JobStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';

interface BacktestJob {
  id:        string;
  status:    JobStatus;
  progress:  number;
  config:    BacktestConfig;
  result:    BacktestResult | null;
  error:     string | null;
  startedAt: Date;
  endedAt:   Date | null;
  deleted:   boolean;
}

const jobStore = new Map<string, BacktestJob>();

// ── POST /run ─────────────────────────────────────────────────────────────────

router.post('/run', heavyLimiter, validateBody(BacktestConfigSchema), asyncHandler(async (req, res) => {
  const cfg  = req.body as z.infer<typeof BacktestConfigSchema>;
  const id   = randomUUID();

  // Coerce date strings to Date objects
  const config: BacktestConfig = {
    ...cfg,
    startDate: new Date(cfg.startDate),
    endDate:   new Date(cfg.endDate),
    criteriaType:    cfg.criteriaType,
    rebalancePeriod: cfg.rebalancePeriod,
    market:          cfg.market,
  };

  if (config.startDate >= config.endDate) {
    fail(res, 'startDate must be before endDate');
    return;
  }

  const job: BacktestJob = {
    id, status: 'PENDING', progress: 0, config,
    result: null, error: null, startedAt: new Date(), endedAt: null, deleted: false,
  };
  jobStore.set(id, job);

  // Respond immediately — processing happens in background
  ok(res, { backtestId: id, status: 'PENDING' }, undefined, 202);

  // ── Background execution ──────────────────────────────────────────────────
  (async () => {
    job.status = 'RUNNING';

    try {
      const engine = new BacktestEngine();
      const result = await engine.runBacktest(config, (p) => {
        job.progress = p.progress;
        wsEvents.emit('backtest:progress', { id, ...p });
      });

      job.result   = result;
      job.status   = 'COMPLETED';
      job.progress = 100;
      job.endedAt  = new Date();

      wsEvents.emit('backtest:progress', { id, stage: 'calculating', progress: 100, message: 'Tamamlandı' });
      wsEvents.emit('backtest:complete', { id, result });

      try {
        const { saveBacktestResult } = await import('../services/backtestEngine');
        await saveBacktestResult(result);
      } catch { /* no DB configured */ }

    } catch (err) {
      job.status  = 'FAILED';
      job.error   = (err as Error).message;
      job.endedAt = new Date();
      wsEvents.emit('backtest:failed', { id, error: job.error });
    }
  })();
}));

// ── GET /status/:id ───────────────────────────────────────────────────────────

router.get('/status/:id', asyncHandler(async (req, res) => {
  const job = jobStore.get(String(req.params.id));
  if (!job || job.deleted) { fail(res, 'Backtest not found', 404); return; }
  ok(res, {
    id:        job.id,
    status:    job.status,
    progress:  job.progress,
    error:     job.error,
    startedAt: job.startedAt,
    endedAt:   job.endedAt,
  });
}));

// ── GET /results ──────────────────────────────────────────────────────────────

const ResultsQuerySchema = z.object({
  limit:        z.coerce.number().int().min(1).max(100).default(20),
  offset:       z.coerce.number().int().min(0).default(0),
  criteriaType: z.enum(['ALFA','BETA','DELTA','HYBRID']).optional(),
  market:       z.enum(['BIST','US','BOTH']).optional(),
  status:       z.enum(['RUNNING','COMPLETED','FAILED','PENDING']).optional(),
});

router.get('/results', validateQuery(ResultsQuerySchema), asyncHandler(async (req, res) => {
  const q = (req as typeof req & { validQuery: z.infer<typeof ResultsQuerySchema> }).validQuery;

  // Try DB first
  try {
    const { PrismaClient } = await import('@prisma/client');
    const prisma = new PrismaClient();
    const [rows, total] = await Promise.all([
      prisma.backtest.findMany({
        where: {
          isDeleted:    false,
          criteriaType: q.criteriaType,
          market:       q.market,
          status:       q.status,
        },
        orderBy: { createdAt: 'desc' },
        skip: q.offset, take: q.limit,
        select: {
          id: true, name: true, criteriaType: true, market: true, status: true,
          startDate: true, endDate: true, rebalancePeriod: true, initialCapital: true,
          totalReturn: true, annualizedReturn: true, maxDrawdown: true,
          sharpeRatio: true, winRate: true, totalTrades: true, createdAt: true,
        },
      }),
      prisma.backtest.count({ where: { isDeleted: false, criteriaType: q.criteriaType, market: q.market, status: q.status } }),
    ]).finally(() => prisma.$disconnect());

    ok(res, rows, { total, limit: q.limit, offset: q.offset });
    return;
  } catch { /* use in-process store */ }

  let items = [...jobStore.values()].filter(j => !j.deleted);
  if (q.criteriaType) items = items.filter(j => j.config.criteriaType === q.criteriaType);
  if (q.market)       items = items.filter(j => j.config.market       === q.market);
  if (q.status)       items = items.filter(j => j.status              === q.status);
  items.sort((a, b) => b.startedAt.getTime() - a.startedAt.getTime());

  const total = items.length;
  const paged = items.slice(q.offset, q.offset + q.limit).map(j => ({
    id:              j.id,
    name:            j.config.name,
    criteriaType:    j.config.criteriaType,
    market:          j.config.market,
    status:          j.status,
    startDate:       j.config.startDate,
    endDate:         j.config.endDate,
    rebalancePeriod: j.config.rebalancePeriod,
    initialCapital:  j.config.initialCapital,
    totalReturn:     j.result?.performance.totalReturn     ?? null,
    annualizedReturn: j.result?.performance.annualizedReturn ?? null,
    maxDrawdown:     j.result?.performance.maxDrawdown     ?? null,
    sharpeRatio:     j.result?.performance.sharpeRatio     ?? null,
    winRate:         j.result?.performance.winRate         ?? null,
    totalTrades:     j.result?.performance.totalTrades     ?? null,
    startedAt:       j.startedAt,
  }));

  ok(res, paged, { total, limit: q.limit, offset: q.offset });
}));

// ── GET /results/:id ──────────────────────────────────────────────────────────

router.get('/results/:id', asyncHandler(async (req, res) => {
  // Try DB
  try {
    const { loadBacktestResult } = await import('../services/backtestEngine');
    const data = await loadBacktestResult(String(req.params.id));
    if (data) { ok(res, data); return; }
  } catch { /* fall through */ }

  // In-process store
  const job = jobStore.get(String(req.params.id));
  if (!job || job.deleted) { fail(res, 'Backtest not found', 404); return; }
  if (job.status !== 'COMPLETED' || !job.result) {
    ok(res, { id: job.id, status: job.status, progress: job.progress, error: job.error });
    return;
  }
  ok(res, job.result);
}));

// ── DELETE /:id ───────────────────────────────────────────────────────────────

router.delete('/:id', asyncHandler(async (req, res) => {
  // Try DB soft-delete
  try {
    const { PrismaClient } = await import('@prisma/client');
    const prisma = new PrismaClient();
    await prisma.backtest.update({ where: { id: String(req.params.id) }, data: { isDeleted: true } }).finally(() => prisma.$disconnect());
    ok(res, { deleted: String(req.params.id) });
    return;
  } catch { /* fall through */ }

  const job = jobStore.get(String(req.params.id));
  if (!job) { fail(res, 'Backtest not found', 404); return; }
  job.deleted = true;
  ok(res, { deleted: String(req.params.id) });
}));

export default router;
