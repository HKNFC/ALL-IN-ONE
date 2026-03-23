import { Router } from 'express'
import { z } from 'zod'
import { validate } from '../middleware/validate'
import { generalLimiter } from '../middleware/rateLimiter'
import { deterministicScanner } from '../services/consistencyService'
import { prisma } from '../lib/prisma'

const router = Router()

const CRITERIA = ['ALFA', 'BETA', 'DELTA'] as const
type CriteriaType = typeof CRITERIA[number]

const checkQuery = z.object({
  criteria: z
    .string()
    .transform((v) => v.toUpperCase())
    .refine((v) => CRITERIA.includes(v as CriteriaType), {
      message: 'criteria must be ALFA, BETA, or DELTA',
    }),
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'date must be YYYY-MM-DD'),
  market: z
    .string()
    .optional()
    .default('US')
    .transform((v) => v.toUpperCase()),
})

/**
 * @openapi
 * /api/consistency/check:
 *   get:
 *     summary: Verify scanner and backtest produce identical results for same inputs
 *     tags: [Consistency]
 *     parameters:
 *       - in: query
 *         name: criteria
 *         required: true
 *         schema: { type: string, enum: [ALFA, BETA, DELTA] }
 *       - in: query
 *         name: date
 *         required: true
 *         schema: { type: string, example: '2024-06-03' }
 *       - in: query
 *         name: market
 *         schema: { type: string, enum: [US, BIST], default: US }
 *     responses:
 *       200:
 *         description: Consistency check result
 */
router.get(
  '/check',
  generalLimiter,
  validate(checkQuery, 'query'),
  async (req, res, next) => {
    try {
      const q          = (req.validated?.query ?? req.query) as unknown as z.infer<typeof checkQuery>
      const targetDate = new Date(q.date)

      const scanResult  = await deterministicScanner.scan(q.criteria as CriteriaType, targetDate, q.market)
      const scanSymbols = scanResult.slice(0, 5).map((s) => s.symbol).sort()

      const snapshot = await prisma.backtestSnapshot.findFirst({
        where: {
          criteriaUsed: q.criteria,
          date: {
            gte: new Date(targetDate.getTime() - 7 * 86_400_000),
            lte: new Date(targetDate.getTime() + 7 * 86_400_000),
          },
          backtest: {
            isDeleted: false,
            market:    q.market,
            status:    'COMPLETED',
          },
        },
        orderBy: { date: 'asc' },
        include: { backtest: { select: { id: true, name: true, criteriaType: true } } },
      })

      if (!snapshot) {
        return res.json({
          isConsistent:   null,
          message:        'No completed backtest snapshot found near this date. Run a backtest first.',
          scanResult:     scanResult.slice(0, 5),
          backtestResult: null,
          differences:    [],
        })
      }

      const holdings  = snapshot.holdings as Array<{ symbol: string; shares: number; price: number; value: number }>
      const btSymbols = holdings.map((h) => h.symbol).sort()

      const differences: string[] = []
      const onlyInScan = scanSymbols.filter((s) => !btSymbols.includes(s))
      const onlyInBt   = btSymbols.filter((s) => !scanSymbols.includes(s))

      if (onlyInScan.length > 0)
        differences.push(`Stocks in scanner but not in backtest snapshot: ${onlyInScan.join(', ')}`)
      if (onlyInBt.length > 0)
        differences.push(`Stocks in backtest snapshot but not in scanner: ${onlyInBt.join(', ')}`)

      return res.json({
        isConsistent: differences.length === 0,
        criteria:     q.criteria,
        date:         q.date,
        market:       q.market,
        scanResult:   scanResult.slice(0, 5),
        backtestResult: {
          backtestId:     snapshot.backtest.id,
          backtestName:   snapshot.backtest.name,
          snapshotDate:   snapshot.date,
          portfolioValue: snapshot.portfolioValue,
          holdings,
        },
        differences,
      })
    } catch (err) {
      next(err)
    }
  }
)

export default router
