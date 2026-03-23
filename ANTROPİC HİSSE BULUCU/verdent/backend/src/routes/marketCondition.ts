import { Router } from 'express'
import {
  getCurrentMarketCondition,
  getHistoricalMarketConditions,
  analyzeMarketCondition,
} from '../services/marketConditionService'

const router = Router()

// GET /api/market-condition/current?market=US|BIST
router.get('/current', async (req, res) => {
  const market = ((req.query.market as string) ?? 'US').toUpperCase()
  try {
    const result = await getCurrentMarketCondition(market)
    return res.json(result)
  } catch (err) {
    return res.status(500).json({ error: 'Failed to analyse market condition', detail: String(err) })
  }
})

// GET /api/market-condition/history?market=US&startDate=2024-01-01&endDate=2024-12-31
router.get('/history', async (req, res) => {
  const market    = ((req.query.market as string) ?? 'US').toUpperCase()
  const startDate = new Date((req.query.startDate as string) ?? new Date(Date.now() - 90 * 86400000))
  const endDate   = new Date((req.query.endDate   as string) ?? new Date())

  if (isNaN(startDate.getTime()) || isNaN(endDate.getTime())) {
    return res.status(400).json({ error: 'Invalid date format — use ISO 8601 (YYYY-MM-DD)' })
  }

  try {
    const results = await getHistoricalMarketConditions(market, startDate, endDate)
    return res.json({ market, count: results.length, results })
  } catch (err) {
    return res.status(500).json({ error: 'Failed to retrieve historical conditions', detail: String(err) })
  }
})

// POST /api/market-condition/analyze  { market: "US", date: "2024-06-01" }
router.post('/analyze', async (req, res) => {
  const { market = 'US', date } = req.body as { market?: string; date?: string }
  const analysisDate = date ? new Date(date) : new Date()

  if (isNaN(analysisDate.getTime())) {
    return res.status(400).json({ error: 'Invalid date' })
  }

  try {
    const result = await analyzeMarketCondition(market.toUpperCase(), analysisDate)
    return res.json(result)
  } catch (err) {
    return res.status(500).json({ error: 'Analysis failed', detail: String(err) })
  }
})

export default router
