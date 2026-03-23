import { Router } from 'express'
import { z } from 'zod'
import { validate } from '../middleware/validate'
import { marketLimiter } from '../middleware/rateLimiter'
import { makeError } from '../middleware/errorHandler'
import {
  getCurrentMarketCondition,
  getHistoricalMarketConditions,
  analyzeMarketCondition,
} from '../services/marketConditionService'
import { dataService } from '../services/dataService'
import { calculateAllIndicators } from '../utils/indicators'
import { prisma } from '../lib/prisma'

const router = Router()

const MARKETS = ['BIST', 'US'] as const
type Market = typeof MARKETS[number]

const marketParam = z.object({
  market: z.string().transform((v) => v.toUpperCase()).refine(
    (v) => MARKETS.includes(v as Market),
    { message: 'market must be BIST or US' }
  ),
})

const dateParam = z.object({
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'date must be YYYY-MM-DD'),
})

const historyQuery = z.object({
  startDate: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  endDate:   z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
})

// Helper: safely read a string param after validate() middleware has coerced it
const str = (v: string | string[]): string => (Array.isArray(v) ? v[0] : v)

/**
 * @openapi
 * /api/market/condition/{market}:
 *   get:
 *     summary: Get current market condition
 *     tags: [Market]
 *     parameters:
 *       - in: path
 *         name: market
 *         required: true
 *         schema: { type: string, enum: [BIST, US] }
 *     responses:
 *       200:
 *         description: MarketConditionResult
 *       400:
 *         description: Validation error
 */
router.get(
  '/condition/:market',
  marketLimiter,
  validate(marketParam, 'params'),
  async (req, res, next) => {
    try {
      const market = str(req.params.market)
      const result = await getCurrentMarketCondition(market)
      res.json(result)
    } catch (err) {
      next(err)
    }
  }
)

/**
 * @openapi
 * /api/market/condition/{market}/{date}:
 *   get:
 *     summary: Get market condition for a specific date
 *     tags: [Market]
 *     parameters:
 *       - in: path
 *         name: market
 *         required: true
 *         schema: { type: string, enum: [BIST, US] }
 *       - in: path
 *         name: date
 *         required: true
 *         schema: { type: string, example: '2024-06-01' }
 *     responses:
 *       200:
 *         description: MarketConditionResult
 */
router.get(
  '/condition/:market/:date',
  marketLimiter,
  validate(marketParam, 'params'),
  async (req, res, next) => {
    try {
      const market = str(req.params.market)
      const date   = str(req.params.date)
      const parsed = dateParam.safeParse({ date })
      if (!parsed.success) return next(makeError('date must be YYYY-MM-DD', 400, 'VALIDATION_ERROR'))
      const result = await analyzeMarketCondition(market, new Date(date))
      res.json(result)
    } catch (err) {
      next(err)
    }
  }
)

/**
 * @openapi
 * /api/market/indicators/{market}:
 *   get:
 *     summary: Get detailed technical indicators for the market index
 *     tags: [Market]
 */
router.get(
  '/indicators/:market',
  marketLimiter,
  validate(marketParam, 'params'),
  async (req, res, next) => {
    try {
      const market      = str(req.params.market)
      const indexSymbol = market === 'BIST' ? 'XU100.IS' : 'SPY'

      const endDate   = new Date()
      const startDate = new Date()
      startDate.setDate(startDate.getDate() - 430)

      const prices = await dataService.fetchStockPrice(indexSymbol, startDate, endDate, '1d')
      if (prices.length < 30) throw makeError('Insufficient price data for indicators', 422, 'INSUFFICIENT_DATA')

      const indicators = calculateAllIndicators(prices)
      const latest     = prices[prices.length - 1]

      const lastVal = (arr: number[]) => {
        for (let i = arr.length - 1; i >= 0; i--) {
          if (Number.isFinite(arr[i])) return arr[i]
        }
        return null
      }

      res.json({
        symbol:  indexSymbol,
        market,
        date:    latest.date,
        price:   latest.close,
        indicators: {
          ema20:      lastVal(indicators.ema20),
          ema50:      lastVal(indicators.ema50),
          ema200:     lastVal(indicators.ema200),
          sma50:      lastVal(indicators.sma50),
          sma200:     lastVal(indicators.sma200),
          rsi14:      lastVal(indicators.rsi14),
          macd:       lastVal(indicators.macd.macdLine),
          macdSignal: lastVal(indicators.macd.signalLine),
          macdHist:   lastVal(indicators.macd.histogram),
          bbUpper:    lastVal(indicators.bollinger.upper),
          bbMiddle:   lastVal(indicators.bollinger.middle),
          bbLower:    lastVal(indicators.bollinger.lower),
          atr14:      lastVal(indicators.atr14),
          adx14:      lastVal(indicators.adx14.adx),
          plusDI:     lastVal(indicators.adx14.plusDI),
          minusDI:    lastVal(indicators.adx14.minusDI),
          stochK:     lastVal(indicators.stochastic.k),
          stochD:     lastVal(indicators.stochastic.d),
          obv:        lastVal(indicators.obv),
          vwap:       lastVal(indicators.vwap),
          fibonacci:  indicators.fibonacci,
        },
      })
    } catch (err) {
      next(err)
    }
  }
)

/**
 * @openapi
 * /api/market/history/{market}:
 *   get:
 *     summary: Get market condition history
 *     tags: [Market]
 *     parameters:
 *       - in: query
 *         name: startDate
 *         schema: { type: string, example: '2024-01-01' }
 *       - in: query
 *         name: endDate
 *         schema: { type: string, example: '2024-12-31' }
 */
router.get(
  '/history/:market',
  marketLimiter,
  validate(marketParam, 'params'),
  validate(historyQuery, 'query'),
  async (req, res, next) => {
    try {
      const market    = str(req.params.market)
      const startDate = req.query.startDate ? str(req.query.startDate as string | string[]) : undefined
      const endDate   = req.query.endDate   ? str(req.query.endDate   as string | string[]) : undefined

      const where = {
        market,
        ...(startDate || endDate ? {
          date: {
            ...(startDate ? { gte: new Date(startDate) } : {}),
            ...(endDate   ? { lte: new Date(endDate)   } : {}),
          },
        } : {}),
      }

      const rows = await prisma.marketCondition.findMany({
        where,
        orderBy: { date: 'asc' },
        take:    365,
      })

      if (rows.length > 0) {
        return res.json({ market, count: rows.length, history: rows })
      }

      const end   = endDate   ? new Date(endDate)   : new Date()
      const start = startDate ? new Date(startDate) : new Date(end.getTime() - 90 * 86_400_000)
      const results = await getHistoricalMarketConditions(market, start, end)
      return res.json({ market, count: results.length, history: results })
    } catch (err) {
      return next(err)
    }
  }
)

export default router
