import { Router } from 'express'
import { z } from 'zod'
import { validate } from '../middleware/validate'
import { generalLimiter, marketLimiter } from '../middleware/rateLimiter'
import { makeError } from '../middleware/errorHandler'
import { dataService } from '../services/dataService'
import { calculateAllIndicators } from '../utils/indicators'
import { prisma } from '../lib/prisma'

const router = Router()

const str = (v: string | string[]): string => (Array.isArray(v) ? v[0] : v)

const symbolParam = z.object({
  symbol: z.string().min(1).max(20).transform((v) => v.toUpperCase()),
})

const marketParam = z.object({
  market: z
    .string()
    .transform((v) => v.toUpperCase())
    .refine((v) => ['BIST', 'US'].includes(v), { message: 'market must be BIST or US' }),
})

const searchQuery = z.object({
  q:      z.string().min(1, 'Query is required').max(50),
  market: z.string().optional(),
  limit:  z.coerce.number().int().min(1).max(50).default(10),
})

const priceQuery = z.object({
  start:    z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'start must be YYYY-MM-DD').optional(),
  end:      z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'end must be YYYY-MM-DD').optional(),
  interval: z.enum(['1d', '1wk', '1mo']).default('1d'),
})

/**
 * @openapi
 * /api/stocks/search:
 *   get:
 *     summary: Search stocks by symbol or name
 *     tags: [Stocks]
 *     parameters:
 *       - in: query
 *         name: q
 *         required: true
 *         schema: { type: string, example: 'THYAO' }
 *       - in: query
 *         name: market
 *         schema: { type: string, enum: [BIST, US] }
 *       - in: query
 *         name: limit
 *         schema: { type: integer, default: 10 }
 */
router.get(
  '/search',
  generalLimiter,
  validate(searchQuery, 'query'),
  async (req, res, next) => {
    try {
      const q = (req.validated?.query ?? req.query) as unknown as z.infer<typeof searchQuery>

      const stocks = await prisma.stock.findMany({
        where: {
          OR: [
            { symbol: { contains: q.q, mode: 'insensitive' } },
            { name:   { contains: q.q, mode: 'insensitive' } },
          ],
          ...(q.market ? { market: q.market.toUpperCase() } : {}),
        },
        take: q.limit,
        select: {
          id: true, symbol: true, name: true, market: true,
          sector: true, marketCap: true,
        },
      })

      res.json({ query: q.q, count: stocks.length, stocks })
    } catch (err) {
      next(err)
    }
  }
)

/**
 * @openapi
 * /api/stocks/list/{market}:
 *   get:
 *     summary: Get all stocks in a market
 *     tags: [Stocks]
 */
router.get(
  '/list/:market',
  generalLimiter,
  validate(marketParam, 'params'),
  async (req, res, next) => {
    try {
      const market = str(req.params.market)
      const stocks = await prisma.stock.findMany({
        where:   { market },
        orderBy: { symbol: 'asc' },
        select: {
          id: true, symbol: true, name: true,
          sector: true, marketCap: true,
        },
      })
      res.json({ market, count: stocks.length, stocks })
    } catch (err) {
      next(err)
    }
  }
)

/**
 * @openapi
 * /api/stocks/{symbol}:
 *   get:
 *     summary: Get stock info by symbol
 *     tags: [Stocks]
 */
router.get(
  '/:symbol',
  generalLimiter,
  validate(symbolParam, 'params'),
  async (req, res, next) => {
    try {
      const symbol = str(req.params.symbol)
      const stock  = await prisma.stock.findUnique({
        where:  { symbol },
        select: {
          id: true, symbol: true, name: true, market: true,
          sector: true, marketCap: true, createdAt: true,
        },
      })
      if (!stock) return next(makeError('Stock not found', 404, 'NOT_FOUND'))
      res.json(stock)
    } catch (err) {
      next(err)
    }
  }
)

/**
 * @openapi
 * /api/stocks/{symbol}/price:
 *   get:
 *     summary: Get OHLCV price history for a stock
 *     tags: [Stocks]
 *     parameters:
 *       - in: path
 *         name: symbol
 *         required: true
 *         schema: { type: string }
 *       - in: query
 *         name: start
 *         schema: { type: string, example: '2024-01-01' }
 *       - in: query
 *         name: end
 *         schema: { type: string, example: '2024-12-31' }
 *       - in: query
 *         name: interval
 *         schema: { type: string, enum: [1d, 1wk, 1mo], default: '1d' }
 */
router.get(
  '/:symbol/price',
  marketLimiter,
  validate(symbolParam, 'params'),
  validate(priceQuery, 'query'),
  async (req, res, next) => {
    try {
      const symbol = str(req.params.symbol)
      const q      = (req.validated?.query ?? req.query) as unknown as z.infer<typeof priceQuery>

      const endDate   = q.end   ? new Date(q.end)   : new Date()
      const startDate = q.start ? new Date(q.start)  : (() => {
        const d = new Date(endDate)
        d.setFullYear(d.getFullYear() - 1)
        return d
      })()

      const dbPrices = await prisma.stockPrice.findMany({
        where: {
          stock:  { symbol },
          date:   { gte: startDate, lte: endDate },
        },
        orderBy: { date: 'asc' },
        select:  { date: true, open: true, high: true, low: true, close: true, volume: true },
      })

      if (dbPrices.length > 0) {
        return res.json({ symbol, interval: q.interval, count: dbPrices.length, prices: dbPrices })
      }

      const prices = await dataService.fetchStockPrice(symbol, startDate, endDate, q.interval)
      return res.json({ symbol, interval: q.interval, count: prices.length, prices })
    } catch (err) {
      next(err)
    }
  }
)

/**
 * @openapi
 * /api/stocks/{symbol}/indicators:
 *   get:
 *     summary: Get latest technical indicators for a stock
 *     tags: [Stocks]
 */
router.get(
  '/:symbol/indicators',
  marketLimiter,
  validate(symbolParam, 'params'),
  async (req, res, next) => {
    try {
      const symbol = str(req.params.symbol)

      const latest = await prisma.stockPrice.findFirst({
        where:   { stock: { symbol } },
        orderBy: { date: 'desc' },
      })

      if (latest && latest.rsi14 !== null) {
        return res.json({
          symbol,
          date:  latest.date,
          price: latest.close,
          indicators: {
            rsi14:      latest.rsi14,
            macd:       latest.macd,
            macdSignal: latest.macdSignal,
            ema20:      latest.ema20,
            ema50:      latest.ema50,
            ema200:     latest.ema200,
            sma50:      latest.sma50,
            sma200:     latest.sma200,
            atr14:      latest.atr14,
            obv:        latest.obv,
            vwap:       latest.vwap,
            bbUpper:    latest.bbUpper,
            bbMiddle:   latest.bbMiddle,
            bbLower:    latest.bbLower,
            adx14:      latest.adx14,
            stochK:     latest.stochK,
            stochD:     latest.stochD,
          },
        })
      }

      const endDate   = new Date()
      const startDate = new Date()
      startDate.setDate(startDate.getDate() - 430)

      const prices = await dataService.fetchStockPrice(symbol, startDate, endDate, '1d')
      if (prices.length < 30) throw makeError('Insufficient price data', 422, 'INSUFFICIENT_DATA')

      const indicators = calculateAllIndicators(prices)
      const lastVal    = (arr: number[]) => {
        for (let i = arr.length - 1; i >= 0; i--) {
          if (Number.isFinite(arr[i])) return arr[i]
        }
        return null
      }

      return res.json({
        symbol,
        date:  prices[prices.length - 1].date,
        price: prices[prices.length - 1].close,
        indicators: {
          rsi14:      lastVal(indicators.rsi14),
          macd:       lastVal(indicators.macd.macdLine),
          macdSignal: lastVal(indicators.macd.signalLine),
          macdHist:   lastVal(indicators.macd.histogram),
          ema20:      lastVal(indicators.ema20),
          ema50:      lastVal(indicators.ema50),
          ema200:     lastVal(indicators.ema200),
          sma50:      lastVal(indicators.sma50),
          sma200:     lastVal(indicators.sma200),
          atr14:      lastVal(indicators.atr14),
          obv:        lastVal(indicators.obv),
          vwap:       lastVal(indicators.vwap),
          bbUpper:    lastVal(indicators.bollinger.upper),
          bbMiddle:   lastVal(indicators.bollinger.middle),
          bbLower:    lastVal(indicators.bollinger.lower),
          adx14:      lastVal(indicators.adx14.adx),
          plusDI:     lastVal(indicators.adx14.plusDI),
          minusDI:    lastVal(indicators.adx14.minusDI),
          stochK:     lastVal(indicators.stochastic.k),
          stochD:     lastVal(indicators.stochastic.d),
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
 * /api/stocks/{symbol}/fundamentals:
 *   get:
 *     summary: Get fundamental data for a stock
 *     tags: [Stocks]
 */
router.get(
  '/:symbol/fundamentals',
  generalLimiter,
  validate(symbolParam, 'params'),
  async (req, res, next) => {
    try {
      const symbol = str(req.params.symbol)

      const latest = await prisma.stockPrice.findFirst({
        where:   { stock: { symbol }, pe: { not: null } },
        orderBy: { date: 'desc' },
        select: {
          date: true, close: true,
          pe: true, pb: true, roe: true,
          debtEquity: true, revenueGrowth: true,
          earningsGrowth: true, freeCashFlow: true,
        },
      })

      if (latest) return res.json({ symbol, fundamentals: latest })

      const fundamentals = await dataService.fetchFundamentals(symbol)
      return res.json({ symbol, fundamentals })
    } catch (err) {
      next(err)
    }
  }
)

export default router
