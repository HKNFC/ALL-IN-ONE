import { Router } from 'express';
import { ScannerService } from '../services/scannerService';

const router = Router();
const svc    = new ScannerService();

// GET /api/scanner/scan?signal=BUY&sector=Technology&minStrength=70
router.get('/scan', async (req, res) => {
  try {
    const { signal, sector, minStrength } = req.query;
    const results = await svc.scan({
      signal: signal as 'BUY' | 'WATCH' | 'SELL' | 'ALL' | undefined,
      sector: sector as string,
      minStrength: minStrength ? Number(minStrength) : undefined,
    });
    res.json({ data: results, scannedAt: new Date().toISOString() });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// GET /api/scanner/patterns
router.get('/patterns', (_req, res) => {
  res.json({
    data: ['Bull Flag', 'Bear Flag', 'Cup & Handle', 'Head & Shoulders', 'Double Bottom', 'Double Top', 'Breakout', 'Consolidation', 'MA Crossover', 'Descending Triangle'],
  });
});

export default router;
