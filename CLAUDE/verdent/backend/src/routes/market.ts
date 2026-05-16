import { Router } from 'express';
import { MarketService } from '../services/marketService';

const router = Router();
const svc    = new MarketService();

// GET /api/market/quotes?symbols=AAPL,MSFT,NVDA
router.get('/quotes', async (req, res) => {
  try {
    const symbols = (req.query.symbols as string)?.split(',') ?? [];
    const quotes  = await svc.getQuotes(symbols);
    res.json({ data: quotes, timestamp: new Date().toISOString() });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// GET /api/market/ohlcv/:symbol?period=1Y
router.get('/ohlcv/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const period = (req.query.period as string) || '1Y';
    const data   = await svc.getOHLCV(symbol, period);
    res.json({ symbol, period, data });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// GET /api/market/indices
router.get('/indices', async (_req, res) => {
  try {
    const indices = await svc.getIndices();
    res.json({ data: indices });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// GET /api/market/search?q=apple
router.get('/search', async (req, res) => {
  try {
    const q       = (req.query.q as string) || '';
    const results = await svc.search(q);
    res.json({ results });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

export default router;
