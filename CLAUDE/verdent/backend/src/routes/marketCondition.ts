import { Router } from 'express';
import {
  analyzeMarketCondition,
  getCurrentMarketCondition,
  getHistoricalMarketConditions,
  saveMarketCondition,
  loadMarketConditions,
  generateMockSeries,
  type MarketId,
} from '../services/marketConditionService';

const router = Router();

// ── GET /api/market-condition/current/:market ────────────────────────────────
// Returns the current condition for US or BIST using a mock/live series.
router.get('/current/:market', (req, res) => {
  try {
    const market = (req.params.market.toUpperCase() === 'BIST' ? 'BIST' : 'US') as MarketId;
    const vix    = req.query.vix ? parseFloat(req.query.vix as string) : null;

    // In production, replace generateMockSeries() with a real DB/API lookup.
    const series = generateMockSeries(300, 'BULL');
    const result = getCurrentMarketCondition(market, series, vix);

    res.json({ data: result });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// ── POST /api/market-condition/analyze ───────────────────────────────────────
// Full analysis with caller-supplied series + optional breadth/VIX.
router.post('/analyze', (req, res) => {
  try {
    const { market, date, series, vix, breadth } = req.body;
    if (!market || !series?.length) {
      return res.status(400).json({ error: '`market` and `series` are required' });
    }
    const result = analyzeMarketCondition({
      market: (market as string).toUpperCase() as MarketId,
      date:   date ? new Date(date) : new Date(),
      series: series.map((b: any) => ({ ...b, date: new Date(b.date) })),
      vix:    vix ?? null,
      breadth: breadth ?? null,
    });
    res.json({ data: result });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// ── POST /api/market-condition/save ─────────────────────────────────────────
router.post('/save', async (req, res) => {
  try {
    const { market, date, series, vix, breadth } = req.body;
    if (!market || !series?.length) {
      return res.status(400).json({ error: '`market` and `series` are required' });
    }
    const result = analyzeMarketCondition({
      market: (market as string).toUpperCase() as MarketId,
      date:   date ? new Date(date) : new Date(),
      series: series.map((b: any) => ({ ...b, date: new Date(b.date) })),
      vix:    vix ?? null,
      breadth: breadth ?? null,
    });
    await saveMarketCondition(result);
    res.json({ data: result, saved: true });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// ── GET /api/market-condition/history/:market ────────────────────────────────
router.get('/history/:market', async (req, res) => {
  try {
    const market    = (req.params.market.toUpperCase() === 'BIST' ? 'BIST' : 'US') as MarketId;
    const startDate = req.query.start ? new Date(req.query.start as string) : new Date(Date.now() - 90 * 86400000);
    const endDate   = req.query.end   ? new Date(req.query.end   as string) : new Date();

    const rows = await loadMarketConditions(market, startDate, endDate);
    res.json({ data: rows, count: rows.length });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// ── GET /api/market-condition/backfill/:market ───────────────────────────────
// Compute + save historical conditions from a mock series (dev/demo only).
router.get('/backfill/:market', async (req, res) => {
  try {
    const market    = (req.params.market.toUpperCase() === 'BIST' ? 'BIST' : 'US') as MarketId;
    const days      = req.query.days ? parseInt(req.query.days as string) : 90;
    const series    = generateMockSeries(days + 200, 'BULL'); // extra bars for indicator warmup

    const startDate = new Date(Date.now() - days * 86400000);
    const endDate   = new Date();
    const results   = getHistoricalMarketConditions(market, series, startDate, endDate);

    // Persist all in parallel (fire-and-forget errors)
    await Promise.allSettled(results.map(r => saveMarketCondition(r)));

    res.json({ saved: results.length, from: startDate, to: endDate });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

export default router;
