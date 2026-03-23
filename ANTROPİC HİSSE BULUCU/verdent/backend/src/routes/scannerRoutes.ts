import { Router } from 'express'
import { z } from 'zod'
import { validate } from '../middleware/validate'
import { heavyLimiter, generalLimiter } from '../middleware/rateLimiter'
import { makeError } from '../middleware/errorHandler'
import { deterministicScanner } from '../services/consistencyService'
import { prisma } from '../lib/prisma'

const router = Router()

const CRITERIA = ['ALFA', 'BETA', 'DELTA'] as const
type CriteriaType = typeof CRITERIA[number]

const str = (v: string | string[]): string => (Array.isArray(v) ? v[0] : v)

const scanBody = z.object({
  criteria: z.string().transform((v) => v.toUpperCase()).refine(
    (v) => CRITERIA.includes(v as CriteriaType),
    { message: 'criteria must be ALFA, BETA, or DELTA' }
  ),
  date:   z.string().optional().transform((v) => v ? new Date(v) : new Date()),
  market: z.string().optional().default('US').transform((v) => v.toUpperCase()),
})

const idParam = z.object({
  id: z.string().min(1, 'id is required'),
})

const listQuery = z.object({
  criteria: z.string().optional(),
  market:   z.string().optional(),
  limit:    z.coerce.number().int().min(1).max(100).default(20),
  offset:   z.coerce.number().int().min(0).default(0),
})

/**
 * @openapi
 * /api/scanner/scan:
 *   post:
 *     summary: Run a stock scan with given criteria
 *     tags: [Scanner]
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required: [criteria]
 *             properties:
 *               criteria: { type: string, enum: [ALFA, BETA, DELTA] }
 *               date:     { type: string, example: '2024-06-01' }
 *               market:   { type: string, enum: [US, BIST], default: US }
 *     responses:
 *       200:
 *         description: Array of ScoredStock
 */
router.post(
  '/scan',
  heavyLimiter,
  async (req, res, next) => {
    try {
      const parsed = scanBody.parse(req.body)
      const { criteria, market } = parsed
      const date = new Date(parsed.date as unknown as string)
      const results = await deterministicScanner.scan(criteria as CriteriaType, date, market)
      res.json({
        criteria,
        market,
        date,
        count:  results.length,
        stocks: results,
      })
    } catch (err) {
      next(err)
    }
  }
)

/**
 * @openapi
 * /api/scanner/results:
 *   get:
 *     summary: Get paginated scan history from DB
 *     tags: [Scanner]
 */
router.get(
  '/results',
  generalLimiter,
  validate(listQuery, 'query'),
  async (req, res, next) => {
    try {
      const q = (req.validated?.query ?? req.query) as unknown as z.infer<typeof listQuery>
      const rows = await prisma.scanResult.findMany({
        where: {
          ...(q.criteria ? { criteria: { name: q.criteria.toUpperCase() } } : {}),
        },
        include: {
          criteria: { select: { name: true, displayName: true } },
          stock:    { select: { symbol: true, name: true, market: true } },
        },
        orderBy: { scanDate: 'desc' },
        take:    q.limit,
        skip:    q.offset,
      })

      const total = await prisma.scanResult.count({
        where: q.criteria ? { criteria: { name: q.criteria.toUpperCase() } } : {},
      })

      res.json({ total, count: rows.length, offset: q.offset, results: rows })
    } catch (err) {
      next(err)
    }
  }
)

/**
 * @openapi
 * /api/scanner/results/{id}:
 *   get:
 *     summary: Get a specific scan result
 *     tags: [Scanner]
 */
router.get(
  '/results/:id',
  generalLimiter,
  validate(idParam, 'params'),
  async (req, res, next) => {
    try {
      const id  = str(req.params.id)
      const row = await prisma.scanResult.findUnique({
        where:   { id },
        include: { criteria: true, stock: true },
      })
      if (!row) return next(makeError('Scan result not found', 404, 'NOT_FOUND'))
      res.json(row)
    } catch (err) {
      next(err)
    }
  }
)

/**
 * @openapi
 * /api/scanner/results/{id}:
 *   delete:
 *     summary: Delete a scan result
 *     tags: [Scanner]
 */
router.delete(
  '/results/:id',
  generalLimiter,
  validate(idParam, 'params'),
  async (req, res, next) => {
    try {
      const id = str(req.params.id)
      await prisma.scanResult.delete({ where: { id } })
      res.json({ message: 'Scan result deleted', id })
    } catch {
      next(makeError('Scan result not found', 404, 'NOT_FOUND'))
    }
  }
)

export default router
