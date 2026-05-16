/**
 * VERDENT — Diagnostic Routes
 * POST /api/diagnostic/run   — run full diagnostic on a backtest result
 * GET  /api/diagnostic/costs — return realistic cost tables for BIST / US
 */

import { Router } from 'express';
import { z }      from 'zod';
import {
  ok, fail, asyncHandler, validateBody, apiLimiter,
} from '../middleware';
import { performanceDiagnostic } from '../services/performanceDiagnostic';
import type { BacktestResult }   from '../services/backtestEngine';

const router = Router();
router.use(apiLimiter);

// ─── Schema ──────────────────────────────────────────────────────────────────
const RunDiagnosticSchema = z.object({
  backtestResult:  z.any(),            // full BacktestResult object
  market:          z.enum(['BIST', 'US']),
  transactionCost: z.number().min(0).max(0.05).default(0.001).transform(v => Number(v)),
  slippage:        z.number().min(0).max(0.05).default(0.001).transform(v => Number(v)),
});

// ─── POST /api/diagnostic/run ────────────────────────────────────────────────
router.post(
  '/run',
  validateBody(RunDiagnosticSchema),
  asyncHandler(async (req, res) => {
    const { backtestResult, market, transactionCost, slippage } =
      req.body as z.infer<typeof RunDiagnosticSchema>;

    if (!backtestResult || !backtestResult.id) {
      return fail(res, 'backtestResult with an id field is required');
    }

    const report = await performanceDiagnostic.runDiagnostic(
      backtestResult as BacktestResult,
      { market, transactionCost, slippage },
    );

    return ok(res, report);
  }),
);

// ─── GET /api/diagnostic/costs ───────────────────────────────────────────────
router.get('/costs', (_req, res) => {
  const { BIST_REALISTIC_COSTS, US_REALISTIC_COSTS } =
    require('../services/performanceDiagnostic');
  return ok(res, { BIST: BIST_REALISTIC_COSTS, US: US_REALISTIC_COSTS });
});

// ─── GET /api/diagnostic/bias-types ──────────────────────────────────────────
router.get('/bias-types', (_req, res) => {
  return ok(res, {
    biasTypes: [
      {
        id:          'LOOK_AHEAD',
        name:        'Look-Ahead Bias',
        severity:    'HIGH',
        description: 'Using future data (e.g., signal-day close as entry price) that was not available at decision time.',
        fix:         'Always enter at T+1 open after a T-day close signal.',
      },
      {
        id:          'SURVIVORSHIP',
        name:        'Survivorship Bias',
        severity:    'HIGH',
        description: "Using today's index constituents for historical scans excludes delisted/demoted stocks.",
        fix:         'Maintain historical point-in-time constituent lists.',
      },
      {
        id:          'FUNDAMENTAL_DATE',
        name:        'Fundamental Date Misalignment',
        severity:    'MEDIUM',
        description: 'Using quarterly financials before their official publication date (Q end + 45 days).',
        fix:         'Only use fundamentals published at least 45 days before the scan date.',
      },
      {
        id:          'EARNINGS',
        name:        'Earnings Announcement Bias',
        severity:    'LOW',
        description: 'Trading within ±2 days of earnings releases exposes the strategy to unpredictable gap risk.',
        fix:         'Add an earnings blackout window around announcement dates.',
      },
    ],
  });
});

export default router;
