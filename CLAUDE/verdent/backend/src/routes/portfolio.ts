import { Router } from 'express';
import { PortfolioService } from '../services/portfolioService';

const router = Router();
const svc    = new PortfolioService();

// GET /api/portfolio
router.get('/', async (_req, res) => {
  try {
    const portfolio = await svc.getAll();
    res.json({ data: portfolio });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// POST /api/portfolio
router.post('/', async (req, res) => {
  try {
    const { symbol, shares, avgCost } = req.body;
    if (!symbol || !shares || !avgCost) {
      return res.status(400).json({ error: 'symbol, shares, avgCost required' });
    }
    const position = await svc.addPosition({ symbol, shares: Number(shares), avgCost: Number(avgCost) });
    res.status(201).json({ data: position });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// PUT /api/portfolio/:id
router.put('/:id', async (req, res) => {
  try {
    const updated = await svc.updatePosition(req.params.id, req.body);
    res.json({ data: updated });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// DELETE /api/portfolio/:id
router.delete('/:id', async (req, res) => {
  try {
    await svc.deletePosition(req.params.id);
    res.json({ success: true });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// GET /api/portfolio/summary
router.get('/summary', async (_req, res) => {
  try {
    const summary = await svc.getSummary();
    res.json({ data: summary });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

export default router;
