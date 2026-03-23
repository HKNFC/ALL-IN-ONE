import { Router } from 'express'
import { criteriaCalibrator } from '../services/criteriaCalibrator'
import type { CriteriaType } from '../types/market'

const router = Router()

const VALID_CRITERIA: CriteriaType[] = ['ALFA', 'BETA', 'DELTA']

function parseDateParam(val: unknown, fallback: Date): Date {
  if (typeof val === 'string') {
    const d = new Date(val)
    return isNaN(d.getTime()) ? fallback : d
  }
  return fallback
}

/** POST /api/calibrate/walk-forward */
router.post('/walk-forward', async (req, res) => {
  const { criteriaType, startDate, endDate, market = 'BIST' } = req.body

  if (!VALID_CRITERIA.includes(criteriaType)) {
    return res.status(400).json({ error: 'Invalid criteriaType — must be ALFA, BETA, or DELTA' })
  }

  const start = parseDateParam(startDate, new Date('2022-01-01'))
  const end   = parseDateParam(endDate,   new Date())

  try {
    const result = await criteriaCalibrator.walkForwardOptimization(
      criteriaType as CriteriaType,
      { start, end },
      market,
    )
    res.json(result)
  } catch (err: any) {
    res.status(500).json({ error: err.message })
  }
})

/** POST /api/calibrate/sensitivity */
router.post('/sensitivity', async (req, res) => {
  const { criteriaType, startDate, endDate, market = 'BIST' } = req.body

  if (!VALID_CRITERIA.includes(criteriaType)) {
    return res.status(400).json({ error: 'Invalid criteriaType' })
  }

  const start = parseDateParam(startDate, new Date('2023-01-01'))
  const end   = parseDateParam(endDate,   new Date())

  try {
    const report = await criteriaCalibrator.analyzeSensitivity(
      criteriaType as CriteriaType,
      { start, end },
      market,
    )
    res.json(report)
  } catch (err: any) {
    res.status(500).json({ error: err.message })
  }
})

/** POST /api/calibrate/weights */
router.post('/weights', async (req, res) => {
  const { criteriaType, startDate, endDate, market = 'BIST', method = 'GENETIC' } = req.body

  if (!VALID_CRITERIA.includes(criteriaType)) {
    return res.status(400).json({ error: 'Invalid criteriaType' })
  }
  if (!['GRID_SEARCH', 'GENETIC'].includes(method)) {
    return res.status(400).json({ error: 'method must be GRID_SEARCH or GENETIC' })
  }

  const start = parseDateParam(startDate, new Date('2023-01-01'))
  const end   = parseDateParam(endDate,   new Date())

  try {
    const result = await criteriaCalibrator.calibrateWeights(
      criteriaType as CriteriaType,
      { start, end },
      market,
      method as 'GRID_SEARCH' | 'GENETIC',
    )
    res.json(result)
  } catch (err: any) {
    res.status(500).json({ error: err.message })
  }
})

/** POST /api/calibrate/factor-importance */
router.post('/factor-importance', async (req, res) => {
  const { criteriaType, startDate, endDate, market = 'BIST' } = req.body

  if (!VALID_CRITERIA.includes(criteriaType)) {
    return res.status(400).json({ error: 'Invalid criteriaType' })
  }

  const start = parseDateParam(startDate, new Date('2023-01-01'))
  const end   = parseDateParam(endDate,   new Date())

  try {
    const importance = await criteriaCalibrator.analyzeFactorImportance(
      criteriaType as CriteriaType,
      { start, end },
      market,
    )
    res.json(importance)
  } catch (err: any) {
    res.status(500).json({ error: err.message })
  }
})

/** GET /api/calibrate/quality/:backtestId */
router.get('/quality/:backtestId', async (req, res) => {
  const { prisma } = await import('../lib/prisma')
  const { backtestId } = req.params

  try {
    const record = await prisma.backtest.findUnique({
      where: { id: backtestId },
      include: { portfolioSnapshots: true, trades: true },
    })
    if (!record) return res.status(404).json({ error: 'Backtest not found' })

    // Reconstruct a minimal BacktestResult shape for quality scoring
    const perf = {
      totalReturn:       record.totalReturn ?? 0,
      annualizedReturn:  record.annualizedReturn ?? 0,
      maxDrawdown:       record.maxDrawdown ?? 0,
      maxDrawdownPct:    record.maxDrawdown ?? 0,
      sharpeRatio:       record.sharpeRatio ?? 0,
      sortinoRatio:      0,
      calmarRatio:       0,
      recoveryFactor:    0,
      winRate:           record.winRate ?? 0,
      avgWin:            0,
      avgLoss:           0,
      profitFactor:      0,
      totalTrades:       record.totalTrades ?? 0,
      winningTrades:     0,
      losingTrades:      0,
      bestTrade:         0,
      worstTrade:        0,
      avgHoldingDays:    0,
      consecutiveWins:   0,
      consecutiveLosses: 0,
    }

    const minimal: any = {
      id:               record.id,
      config:           { market: record.market },
      performance:      perf,
      portfolioHistory: record.portfolioSnapshots.map((s) => ({
        date:            s.date,
        portfolioValue:  s.portfolioValue,
        cash:            0,
        holdings:        [],
        criteriaUsed:    s.criteriaUsed,
        marketCondition: s.marketCondition,
        dailyReturn:     0,
      })),
      trades:           record.trades,
      benchmark:        { symbol: record.market === 'BIST' ? 'XU100' : 'SPY', totalReturn: 0, annualizedReturn: 0, maxDrawdown: 0, sharpeRatio: 0 },
      consistencyCheck: false,
      completedAt:      record.createdAt,
      durationMs:       0,
    }

    const quality = criteriaCalibrator.calculateBacktestQuality(minimal)
    res.json(quality)
  } catch (err: any) {
    res.status(500).json({ error: err.message })
  }
})

/** GET /api/calibrate/params/:criteriaType */
router.get('/params/:criteriaType', (req, res) => {
  const ct = req.params.criteriaType as CriteriaType
  if (!VALID_CRITERIA.includes(ct)) {
    return res.status(400).json({ error: 'Invalid criteriaType' })
  }
  const params = criteriaCalibrator.extractCurrentParams(ct)
  res.json(params)
})

export default router
