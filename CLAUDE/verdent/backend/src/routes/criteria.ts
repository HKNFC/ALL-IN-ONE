import { Router } from 'express';
import {
  screenStocks,
  getTop5Portfolio,
  saveScanResults,
  generateMockStocks,
  screenStocksSync,
  CRITERIA_CONFIGS,
  type CriteriaType,
} from '../services/criteriaEngine';

const router = Router();

// ── GET /api/criteria/configs ─────────────────────────────────────────────────
// Return metadata for all three criteria sets
router.get('/configs', (_req, res) => {
  const out = Object.entries(CRITERIA_CONFIGS).map(([type, cfg]) => ({
    type,
    filterCount: cfg.filters.length,
    mandatoryFilters: cfg.filters.filter(f => f.mandatory).map(f => f.id),
    weights: cfg.weights,
    filters: cfg.filters.map(f => ({
      id: f.id, label: f.label, category: f.category, mandatory: f.mandatory,
    })),
  }));
  res.json({ data: out });
});

// ── POST /api/criteria/screen ──────────────────────────────────────────────────
// Run a full screen. Body: { criteria, market, date? }
router.post('/screen', async (req, res) => {
  try {
    const { criteria, market, date } = req.body;
    if (!criteria || !market) {
      return res.status(400).json({ error: '`criteria` and `market` are required' });
    }
    const upper = (criteria as string).toUpperCase() as CriteriaType;
    if (!['ALFA', 'BETA', 'DELTA'].includes(upper)) {
      return res.status(400).json({ error: 'criteria must be ALFA, BETA, or DELTA' });
    }
    const d       = date ? new Date(date) : new Date();
    const results = await screenStocks(upper, d, market);
    res.json({ criteria: upper, market, date: d, count: results.length, data: results });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// ── POST /api/criteria/screen/mock ────────────────────────────────────────────
// Sync screen against mock data (no DB needed) — useful for demos
router.post('/screen/mock', (req, res) => {
  try {
    const { criteria, market = 'US', count = 30 } = req.body;
    const upper = (criteria as string).toUpperCase() as CriteriaType;
    if (!['ALFA', 'BETA', 'DELTA'].includes(upper)) {
      return res.status(400).json({ error: 'criteria must be ALFA, BETA, or DELTA' });
    }
    const stocks  = generateMockStocks(Number(count), market as 'US' | 'BIST');
    const results = screenStocksSync(stocks, upper);
    res.json({ criteria: upper, market, count: results.length, data: results });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// ── GET /api/criteria/top5/:criteria ─────────────────────────────────────────
// Build a top-5 portfolio for the given criteria and market
router.get('/top5/:criteria', async (req, res) => {
  try {
    const upper   = req.params.criteria.toUpperCase() as CriteriaType;
    const market  = (req.query.market as string) || 'US';
    const date    = req.query.date ? new Date(req.query.date as string) : new Date();
    const portfolio = await getTop5Portfolio(upper, date, market);
    res.json({ data: portfolio });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// ── POST /api/criteria/save ───────────────────────────────────────────────────
// Run screen and persist results to DB
router.post('/save', async (req, res) => {
  try {
    const { criteria, market, date } = req.body;
    const upper = (criteria as string).toUpperCase() as CriteriaType;
    const d     = date ? new Date(date) : new Date();
    const results = await screenStocks(upper, d, market || 'US');
    await saveScanResults(results, upper, d, market || 'US');
    res.json({ saved: results.filter(r => r.score > 0).length, criteria: upper });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

export default router;
