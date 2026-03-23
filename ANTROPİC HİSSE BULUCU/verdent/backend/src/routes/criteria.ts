import { Router } from 'express'
import { screenStocks, getTop5Portfolio, CRITERIA_CONFIGS } from '../services/criteriaEngine'
import type { CriteriaType } from '../types/market'

const router = Router()

const VALID_CRITERIA = new Set<CriteriaType>(['ALFA', 'BETA', 'DELTA'])

function parseCriteria(raw: unknown): CriteriaType | null {
  const val = String(raw ?? '').toUpperCase()
  return VALID_CRITERIA.has(val as CriteriaType) ? (val as CriteriaType) : null
}

// GET /api/criteria
// Returns all available criteria configs (without the check functions)
router.get('/', (_req, res) => {
  const configs = Object.values(CRITERIA_CONFIGS).map((c) => ({
    type:        c.type,
    label:       c.label,
    technicalFilters:   c.technicalFilters.map((f) => ({ name: f.name, weight: f.weight })),
    fundamentalFilters: c.fundamentalFilters.map((f) => ({ name: f.name, weight: f.weight })),
  }))
  return res.json(configs)
})

// GET /api/criteria/screen?criteria=ALFA&market=US&date=2024-06-01
router.get('/screen', async (req, res) => {
  const criteria = parseCriteria(req.query.criteria)
  if (!criteria) return res.status(400).json({ error: 'criteria must be ALFA, BETA, or DELTA' })

  const market = ((req.query.market as string) ?? 'US').toUpperCase()
  const date   = req.query.date ? new Date(req.query.date as string) : new Date()
  if (isNaN(date.getTime())) return res.status(400).json({ error: 'Invalid date format' })

  try {
    const results = await screenStocks(criteria, date, market)
    return res.json({ criteria, market, date, count: results.length, stocks: results })
  } catch (err) {
    return res.status(500).json({ error: 'Screening failed', detail: String(err) })
  }
})

// GET /api/criteria/portfolio?criteria=ALFA&market=US&date=2024-06-01
router.get('/portfolio', async (req, res) => {
  const criteria = parseCriteria(req.query.criteria)
  if (!criteria) return res.status(400).json({ error: 'criteria must be ALFA, BETA, or DELTA' })

  const market = ((req.query.market as string) ?? 'US').toUpperCase()
  const date   = req.query.date ? new Date(req.query.date as string) : new Date()
  if (isNaN(date.getTime())) return res.status(400).json({ error: 'Invalid date format' })

  try {
    const portfolio = await getTop5Portfolio(criteria, date, market)
    return res.json(portfolio)
  } catch (err) {
    return res.status(500).json({ error: 'Portfolio generation failed', detail: String(err) })
  }
})

// POST /api/criteria/screen  { criteria, market, date }
router.post('/screen', async (req, res) => {
  const { market = 'US', date } = req.body as { market?: string; date?: string }
  const criteria = parseCriteria(req.body.criteria)
  if (!criteria) return res.status(400).json({ error: 'criteria must be ALFA, BETA, or DELTA' })

  const analysisDate = date ? new Date(date) : new Date()
  if (isNaN(analysisDate.getTime())) return res.status(400).json({ error: 'Invalid date' })

  try {
    const results = await screenStocks(criteria, analysisDate, market.toUpperCase())
    return res.json({ criteria, market: market.toUpperCase(), date: analysisDate, count: results.length, stocks: results })
  } catch (err) {
    return res.status(500).json({ error: 'Screening failed', detail: String(err) })
  }
})

export default router
