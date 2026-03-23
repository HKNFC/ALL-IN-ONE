import { Router } from 'express'
import { backtestEngine, generateRebalanceDates } from '../services/backtestEngine'
import { prisma } from '../lib/prisma'
import type { BacktestConfig, BacktestCriteria, RebalancePeriod, BacktestMarket } from '../types/market'

const router = Router()

const VALID_CRITERIA  = new Set<BacktestCriteria>(['ALFA', 'BETA', 'DELTA', 'HYBRID'])
const VALID_PERIOD    = new Set<RebalancePeriod>(['WEEKLY', 'MONTHLY'])
const VALID_MARKET    = new Set<BacktestMarket>(['BIST', 'US', 'BOTH'])

// POST /api/backtest/run
router.post('/run', async (req, res) => {
  const body = req.body as Partial<BacktestConfig>

  const criteriaType = String(body.criteriaType ?? '').toUpperCase() as BacktestCriteria
  const market       = String(body.market ?? 'US').toUpperCase()     as BacktestMarket
  const period       = String(body.rebalancePeriod ?? 'MONTHLY').toUpperCase() as RebalancePeriod

  if (!VALID_CRITERIA.has(criteriaType))
    return res.status(400).json({ error: 'criteriaType must be ALFA, BETA, DELTA, or HYBRID' })
  if (!VALID_PERIOD.has(period))
    return res.status(400).json({ error: 'rebalancePeriod must be WEEKLY or MONTHLY' })
  if (!VALID_MARKET.has(market))
    return res.status(400).json({ error: 'market must be BIST, US, or BOTH' })

  const startDate = new Date(body.startDate ?? new Date(Date.now() - 365 * 86_400_000))
  const endDate   = new Date(body.endDate   ?? new Date())
  if (isNaN(startDate.getTime()) || isNaN(endDate.getTime()))
    return res.status(400).json({ error: 'Invalid date format — use ISO 8601' })
  if (startDate >= endDate)
    return res.status(400).json({ error: 'startDate must be before endDate' })

  const config: BacktestConfig = {
    name:            String(body.name ?? `${criteriaType} Backtest`),
    criteriaType,
    startDate,
    endDate,
    rebalancePeriod: period,
    market,
    initialCapital:  Number(body.initialCapital  ?? 100_000),
    transactionCost: Number(body.transactionCost ?? 0.001),
    slippage:        Number(body.slippage        ?? 0.001),
  }

  try {
    const result = await backtestEngine.runBacktest(config)
    return res.json(result)
  } catch (err) {
    return res.status(500).json({ error: 'Backtest failed', detail: String(err) })
  }
})

// GET /api/backtest/list?market=US&limit=20
router.get('/list', async (req, res) => {
  const market = req.query.market as string | undefined
  const limit  = Math.min(Number(req.query.limit ?? 20), 100)

  try {
    const rows = await prisma.backtest.findMany({
      where:   { isDeleted: false, ...(market ? { market: market.toUpperCase() } : {}) },
      orderBy: { createdAt: 'desc' },
      take:    limit,
      select: {
        id: true, name: true, criteriaType: true, market: true,
        startDate: true, endDate: true, status: true,
        totalReturn: true, annualizedReturn: true, maxDrawdown: true,
        sharpeRatio: true, winRate: true, totalTrades: true, createdAt: true,
      },
    })
    return res.json({ count: rows.length, backtests: rows })
  } catch (err) {
    return res.status(500).json({ error: 'Failed to fetch backtest list', detail: String(err) })
  }
})

// GET /api/backtest/:id
router.get('/:id', async (req, res) => {
  try {
    const bt = await prisma.backtest.findUnique({
      where: { id: req.params.id },
      include: {
        portfolioSnapshots: { orderBy: { date: 'asc' } },
        trades:             { orderBy: { date: 'asc' } },
      },
    })
    if (!bt) return res.status(404).json({ error: 'Backtest not found' })
    return res.json(bt)
  } catch (err) {
    return res.status(500).json({ error: 'Failed to fetch backtest', detail: String(err) })
  }
})

// DELETE /api/backtest/:id  (soft-delete)
router.delete('/:id', async (req, res) => {
  try {
    await prisma.backtest.update({ where: { id: req.params.id }, data: { isDeleted: true } })
    return res.json({ message: 'Backtest deleted' })
  } catch {
    return res.status(404).json({ error: 'Backtest not found' })
  }
})

// GET /api/backtest/rebalance-dates?startDate=2024-01-01&endDate=2024-12-31&period=MONTHLY
router.get('/rebalance-dates', (req, res) => {
  const startDate = new Date(req.query.startDate as string ?? '')
  const endDate   = new Date(req.query.endDate   as string ?? '')
  const period    = String(req.query.period ?? 'MONTHLY').toUpperCase() as RebalancePeriod

  if (isNaN(startDate.getTime()) || isNaN(endDate.getTime()))
    return res.status(400).json({ error: 'Invalid date format' })
  if (!VALID_PERIOD.has(period))
    return res.status(400).json({ error: 'period must be WEEKLY or MONTHLY' })

  const dates = generateRebalanceDates(startDate, endDate, period)
  return res.json({ count: dates.length, dates })
})

export default router
