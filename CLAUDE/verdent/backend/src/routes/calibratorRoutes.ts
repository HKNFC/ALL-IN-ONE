/**
 * VERDENT — Calibration Routes
 *
 * POST /api/calibrate/walk-forward   — Run walk-forward optimisation
 * POST /api/calibrate/sensitivity    — Parameter sensitivity analysis
 * POST /api/calibrate/weights        — Optimise scoring weights
 * POST /api/calibrate/factors        — Factor importance (drop-one)
 * POST /api/calibrate/quality        — Score an existing backtest result
 * POST /api/calibrate/full           — Run the full calibration pipeline
 */

import { Router, Request, Response } from 'express';
import { criteriaCalibrator }        from '../services/criteriaCalibrator';
import type { CriteriaType }         from '../services/criteriaEngine';
import type { MarketScope }          from '../services/backtestEngine';

const router = Router();

// ─── helpers ────────────────────────────────────────────────────────────────

function ok(res: Response, data: unknown) {
  res.json({ success: true, data });
}

function fail(res: Response, message: string, status = 400) {
  res.status(status).json({ success: false, error: message });
}

function parseDates(body: Record<string, unknown>): { start: Date; end: Date } | null {
  try {
    const start = new Date(body.startDate as string);
    const end   = new Date(body.endDate   as string);
    if (isNaN(start.getTime()) || isNaN(end.getTime())) return null;
    return { start, end };
  } catch {
    return null;
  }
}

const VALID_CRITERIA: CriteriaType[] = ['ALFA', 'BETA', 'DELTA'];

// ─── POST /api/calibrate/walk-forward ───────────────────────────────────────

router.post('/walk-forward', async (req: Request, res: Response) => {
  const { criteriaType, market } = req.body as Record<string, unknown>;

  if (!VALID_CRITERIA.includes(criteriaType as CriteriaType)) {
    return fail(res, 'criteriaType must be ALFA | BETA | DELTA');
  }

  const dates = parseDates(req.body as Record<string, unknown>);
  if (!dates) return fail(res, 'Invalid startDate or endDate');

  const daySpan = (dates.end.getTime() - dates.start.getTime()) / 86_400_000;
  if (daySpan < 180) return fail(res, 'Date range must be at least 180 days for walk-forward');

  try {
    const result = await criteriaCalibrator.walkForwardOptimization(
      criteriaType as CriteriaType,
      dates,
      (market as MarketScope) ?? 'BIST100',
    );
    ok(res, result);
  } catch (err: unknown) {
    fail(res, String(err), 500);
  }
});

// ─── POST /api/calibrate/sensitivity ────────────────────────────────────────

router.post('/sensitivity', async (req: Request, res: Response) => {
  const { criteriaType, market } = req.body as Record<string, unknown>;

  if (!VALID_CRITERIA.includes(criteriaType as CriteriaType)) {
    return fail(res, 'criteriaType must be ALFA | BETA | DELTA');
  }
  const dates = parseDates(req.body as Record<string, unknown>);
  if (!dates) return fail(res, 'Invalid startDate or endDate');

  const daySpan = (dates.end.getTime() - dates.start.getTime()) / 86_400_000;
  if (daySpan < 90) return fail(res, 'Date range must be at least 90 days');

  // Use default params if not supplied
  const { baseParams } = req.body as { baseParams?: Record<string, unknown> };

  try {
    // If caller does not provide baseParams, criteriaCalibrator will use defaults internally
    const result = await criteriaCalibrator.analyzeSensitivity(
      criteriaType as CriteriaType,
      (baseParams as any) ?? undefined,
      dates,
      (market as MarketScope) ?? 'BIST100',
    );
    ok(res, result);
  } catch (err: unknown) {
    fail(res, String(err), 500);
  }
});

// ─── POST /api/calibrate/weights ────────────────────────────────────────────

router.post('/weights', async (req: Request, res: Response) => {
  const { criteriaType, method, market } = req.body as Record<string, unknown>;

  if (!VALID_CRITERIA.includes(criteriaType as CriteriaType)) {
    return fail(res, 'criteriaType must be ALFA | BETA | DELTA');
  }
  const dates = parseDates(req.body as Record<string, unknown>);
  if (!dates) return fail(res, 'Invalid startDate or endDate');

  const validMethods = ['GRID_SEARCH', 'GENETIC'];
  const resolvedMethod = validMethods.includes(method as string)
    ? (method as 'GRID_SEARCH' | 'GENETIC')
    : 'GENETIC';

  try {
    const result = await criteriaCalibrator.calibrateWeights(
      criteriaType as CriteriaType,
      dates,
      resolvedMethod,
      (market as MarketScope) ?? 'BIST100',
    );
    ok(res, result);
  } catch (err: unknown) {
    fail(res, String(err), 500);
  }
});

// ─── POST /api/calibrate/factors ────────────────────────────────────────────

router.post('/factors', async (req: Request, res: Response) => {
  const { criteriaType, market } = req.body as Record<string, unknown>;

  if (!VALID_CRITERIA.includes(criteriaType as CriteriaType)) {
    return fail(res, 'criteriaType must be ALFA | BETA | DELTA');
  }
  const dates = parseDates(req.body as Record<string, unknown>);
  if (!dates) return fail(res, 'Invalid startDate or endDate');

  try {
    const result = await criteriaCalibrator.analyzeFactorImportance(
      criteriaType as CriteriaType,
      dates,
      (market as MarketScope) ?? 'BIST100',
    );
    ok(res, result);
  } catch (err: unknown) {
    fail(res, String(err), 500);
  }
});

// ─── POST /api/calibrate/quality ────────────────────────────────────────────

router.post('/quality', (req: Request, res: Response) => {
  const { backtestResult, benchmarkReturn } = req.body as Record<string, unknown>;

  if (!backtestResult || typeof backtestResult !== 'object') {
    return fail(res, 'backtestResult is required');
  }

  try {
    const report = criteriaCalibrator.calculateBacktestQuality(
      backtestResult as any,
      typeof benchmarkReturn === 'number' ? benchmarkReturn : 15,
    );
    ok(res, report);
  } catch (err: unknown) {
    fail(res, String(err), 500);
  }
});

// ─── POST /api/calibrate/full ────────────────────────────────────────────────

router.post('/full', async (req: Request, res: Response) => {
  const { criteriaType, market } = req.body as Record<string, unknown>;

  if (!VALID_CRITERIA.includes(criteriaType as CriteriaType)) {
    return fail(res, 'criteriaType must be ALFA | BETA | DELTA');
  }
  const dates = parseDates(req.body as Record<string, unknown>);
  if (!dates) return fail(res, 'Invalid startDate or endDate');

  const daySpan = (dates.end.getTime() - dates.start.getTime()) / 86_400_000;
  if (daySpan < 180) return fail(res, 'Date range must be at least 180 days');

  try {
    const result = await criteriaCalibrator.runFullCalibration(
      criteriaType as CriteriaType,
      dates,
      (market as MarketScope) ?? 'BIST100',
    );
    ok(res, result);
  } catch (err: unknown) {
    fail(res, String(err), 500);
  }
});

export default router;
