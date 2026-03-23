import { Router } from 'express'
import { z } from 'zod'
import { randomUUID } from 'crypto'
import { validate } from '../middleware/validate'
import { heavyLimiter, generalLimiter } from '../middleware/rateLimiter'
import { makeError } from '../middleware/errorHandler'
import { backtestEngine } from '../services/backtestEngine'
import { emitWsEvent, emitBacktestProgress } from '../ws'
import { prisma } from '../lib/prisma'
import type { BacktestConfig } from '../types/market'

const router = Router()

const str = (v: string | string[]): string => (Array.isArray(v) ? v[0] : v)

const CRITERIA = ['ALFA', 'BETA', 'DELTA', 'HYBRID'] as const
const PERIODS  = ['WEEKLY', 'BIWEEKLY', 'MONTHLY'] as const
const MARKETS  = ['BIST', 'US', 'BOTH'] as const

const runBody = z.object({
  name:             z.string().min(1).max(100).default('My Backtest'),
  criteriaType:     z.string().transform((v) => v.toUpperCase()).refine(
    (v) => CRITERIA.includes(v as typeof CRITERIA[number]),
    { message: 'criteriaType must be ALFA, BETA, DELTA, or HYBRID' }
  ),
  startDate:        z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'startDate must be YYYY-MM-DD'),
  endDate:          z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'endDate must be YYYY-MM-DD'),
  rebalancePeriod:  z.string().transform((v) => v.toUpperCase()).refine(
    (v) => PERIODS.includes(v as typeof PERIODS[number]),
    { message: 'rebalancePeriod must be WEEKLY, BIWEEKLY, or MONTHLY' }
  ).default('MONTHLY'),
  market:           z.string().transform((v) => v.toUpperCase()).refine(
    (v) => MARKETS.includes(v as typeof MARKETS[number]),
    { message: 'market must be BIST, US, or BOTH' }
  ).default('US'),
  initialCapital:   z.coerce.number().positive().default(100_000),
  transactionCost:  z.coerce.number().min(0).max(0.05).default(0.001),
  slippage:         z.coerce.number().min(0).max(0.05).default(0.001),
}).refine(
  (d) => new Date(d.startDate) < new Date(d.endDate),
  { message: 'startDate must be before endDate', path: ['startDate'] }
)

const idParam   = z.object({ id: z.string().min(1) })
const listQuery = z.object({
  market: z.string().optional(),
  limit:  z.coerce.number().int().min(1).max(100).default(20),
  offset: z.coerce.number().int().min(0).default(0),
})

const runningJobs = new Map<string, { status: 'RUNNING' | 'COMPLETED' | 'FAILED'; progress: number; error?: string }>()

/**
 * @openapi
 * /api/backtest/run:
 *   post:
 *     summary: Start a new backtest asynchronously
 *     tags: [Backtest]
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             $ref: '#/components/schemas/BacktestConfig'
 *     responses:
 *       202:
 *         description: Backtest accepted, returns jobId
 */
router.post(
  '/run',
  heavyLimiter,
  async (req, res, next) => {
    try {
      const body  = runBody.parse(req.body)
      const jobId = randomUUID()

      const config: BacktestConfig = {
        name:            body.name,
        criteriaType:    body.criteriaType as BacktestConfig['criteriaType'],
        startDate:       new Date(body.startDate),
        endDate:         new Date(body.endDate),
        rebalancePeriod: body.rebalancePeriod as BacktestConfig['rebalancePeriod'],
        market:          body.market as BacktestConfig['market'],
        initialCapital:  body.initialCapital,
        transactionCost: body.transactionCost,
        slippage:        body.slippage,
      }

      runningJobs.set(jobId, { status: 'RUNNING', progress: 0 })
      res.status(202).json({ jobId, status: 'RUNNING', message: 'Backtest started' })

      backtestEngine.runBacktest(config, (event) => {
        runningJobs.set(jobId, { status: 'RUNNING', progress: event.progress })
        emitBacktestProgress(jobId, event.progress, event.message)
      })
        .then((result) => {
          runningJobs.set(jobId, { status: 'COMPLETED', progress: 100 })
          emitWsEvent('backtest:complete', { jobId, backtestId: result.id, performance: result.performance })
        })
        .catch((err: Error) => {
          runningJobs.set(jobId, { status: 'FAILED', progress: 0, error: err.message })
          emitWsEvent('backtest:complete', { jobId, error: err.message })
        })
    } catch (err) {
      next(err)
    }
  }
)

/**
 * @openapi
 * /api/backtest/status/{id}:
 *   get:
 *     summary: Check async backtest job status
 *     tags: [Backtest]
 */
router.get(
  '/status/:id',
  generalLimiter,
  validate(idParam, 'params'),
  (req, res, next) => {
    const id  = str(req.params.id)
    const job = runningJobs.get(id)
    if (!job) return next(makeError('Job not found', 404, 'NOT_FOUND'))
    res.json({ jobId: id, ...job })
  }
)

/**
 * @openapi
 * /api/backtest/results:
 *   get:
 *     summary: Get all backtests (not deleted)
 *     tags: [Backtest]
 */
router.get(
  '/results',
  generalLimiter,
  validate(listQuery, 'query'),
  async (req, res, next) => {
    try {
      const q = (req.validated?.query ?? req.query) as unknown as z.infer<typeof listQuery>
      const where = {
        isDeleted: false,
        ...(q.market ? { market: q.market.toUpperCase() } : {}),
      }

      const [rows, total] = await Promise.all([
        prisma.backtest.findMany({
          where,
          orderBy: { createdAt: 'desc' },
          take:    q.limit,
          skip:    q.offset,
          select: {
            id: true, name: true, criteriaType: true, market: true,
            startDate: true, endDate: true, rebalancePeriod: true,
            status: true, totalReturn: true, annualizedReturn: true,
            maxDrawdown: true, sharpeRatio: true, winRate: true,
            totalTrades: true, initialCapital: true, createdAt: true,
          },
        }),
        prisma.backtest.count({ where }),
      ])

      res.json({ total, count: rows.length, offset: q.offset, backtests: rows })
    } catch (err) {
      next(err)
    }
  }
)

/**
 * @openapi
 * /api/backtest/results/{id}:
 *   get:
 *     summary: Get full backtest detail including snapshots and trades
 *     tags: [Backtest]
 */
router.get(
  '/results/:id',
  generalLimiter,
  validate(idParam, 'params'),
  async (req, res, next) => {
    try {
      const id = str(req.params.id)
      const bt = await prisma.backtest.findUnique({
        where:   { id, isDeleted: false },
        include: {
          portfolioSnapshots: { orderBy: { date: 'asc' } },
          trades:             { orderBy: { date: 'asc' } },
        },
      })
      if (!bt) return next(makeError('Backtest not found', 404, 'NOT_FOUND'))
      res.json(bt)
    } catch (err) {
      next(err)
    }
  }
)

/**
 * @openapi
 * /api/backtest/{id}:
 *   delete:
 *     summary: Soft-delete a backtest
 *     tags: [Backtest]
 */
router.delete(
  '/:id',
  generalLimiter,
  validate(idParam, 'params'),
  async (req, res, next) => {
    try {
      const id = str(req.params.id)
      const bt = await prisma.backtest.findUnique({
        where:  { id },
        select: { id: true, isDeleted: true },
      })
      if (!bt) return next(makeError('Backtest not found', 404, 'NOT_FOUND'))

      await prisma.backtest.update({ where: { id }, data: { isDeleted: true } })
      res.json({ message: 'Backtest deleted', id })
    } catch (err) {
      next(err)
    }
  }
)

/**
 * @openapi
 * /api/backtest/{id}/diagnostic:
 *   get:
 *     summary: Run performance diagnostic on a backtest
 *     tags: [Backtest]
 */
router.get(
  '/:id/diagnostic',
  generalLimiter,
  validate(idParam, 'params'),
  async (req, res, next) => {
    try {
      const { runDiagnostic } = await import('../services/performanceDiagnostic')
      const report = await runDiagnostic(str(req.params.id))
      res.json(report)
    } catch (err) {
      next(err)
    }
  }
)

export default router
