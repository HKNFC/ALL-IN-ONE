/**
 * VERDENT — Shared middleware, helpers, and Zod validation schemas.
 * Imported by all route files.
 */

import { Request, Response, NextFunction, RequestHandler } from 'express';
import rateLimit from 'express-rate-limit';
import { z, ZodError, ZodSchema } from 'zod';

// ─── Standard API response envelope ──────────────────────────────────────────

export interface ApiSuccess<T> {
  ok:   true;
  data: T;
  meta?: Record<string, unknown>;
}

export interface ApiError {
  ok:      false;
  error:   string;
  details?: unknown;
}

export function ok<T>(res: Response, data: T, meta?: Record<string, unknown>, status = 200): void {
  const body: ApiSuccess<T> = { ok: true, data };
  if (meta) body.meta = meta;
  res.status(status).json(body);
}

export function fail(res: Response, message: string, status = 400, details?: unknown): void {
  const body: ApiError = { ok: false, error: message };
  if (details !== undefined) body.details = details;
  res.status(status).json(body);
}

// ─── Async wrapper — catches thrown errors and forwards to Express error handler

export function asyncHandler(
  fn: (req: Request, res: Response, next: NextFunction) => Promise<void>,
): RequestHandler {
  return (req, res, next) => fn(req, res, next).catch(next);
}

// ─── Zod request validation middleware ───────────────────────────────────────

export function validateBody<T>(schema: ZodSchema<T>): RequestHandler {
  return (req, res, next) => {
    const result = schema.safeParse(req.body);
    if (!result.success) {
      fail(res, 'Validation error', 422, formatZodError(result.error));
      return;
    }
    req.body = result.data;
    next();
  };
}

export function validateQuery<T>(schema: ZodSchema<T>): RequestHandler {
  return (req, res, next) => {
    const result = schema.safeParse(req.query);
    if (!result.success) {
      fail(res, 'Invalid query parameters', 422, formatZodError(result.error));
      return;
    }
    (req as Request & { validQuery: T }).validQuery = result.data;
    next();
  };
}

function formatZodError(err: ZodError) {
  return err.issues.map(i => ({ field: i.path.join('.'), message: i.message }));
}

// ─── Rate limiters ────────────────────────────────────────────────────────────

/** General API limiter — 120 req / min per IP */
export const apiLimiter = rateLimit({
  windowMs: 60_000,
  max:      120,
  standardHeaders: true,
  legacyHeaders:   false,
  message: { ok: false, error: 'Too many requests — slow down' },
});

/** Heavy compute limiter (scan/backtest) — 10 req / min per IP */
export const heavyLimiter = rateLimit({
  windowMs: 60_000,
  max:      10,
  standardHeaders: true,
  legacyHeaders:   false,
  message: { ok: false, error: 'Too many compute requests — max 10/min' },
});

// ─── Shared Zod schemas ───────────────────────────────────────────────────────

export const MarketSchema  = z.enum(['BIST', 'BISTTUM', 'BIST100', 'BIST100DISI', 'US', 'BOTH']);
export const CriteriaSchema = z.enum(['ALFA', 'BETA', 'DELTA', 'HYBRID']);
export const PeriodSchema  = z.enum(['WEEKLY', 'MONTHLY']);
export const DateStrSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'Expected YYYY-MM-DD');

export const BacktestConfigSchema = z.object({
  name:            z.string().min(1).max(100),
  criteriaType:    CriteriaSchema,
  startDate:       DateStrSchema,
  endDate:         DateStrSchema,
  rebalancePeriod: PeriodSchema,
  market:          MarketSchema,
  initialCapital:  z.number().min(1_000).max(1_000_000_000).default(100_000),
  transactionCost: z.number().min(0).max(0.05).default(0.001),
  slippage:        z.number().min(0).max(0.05).default(0.001),
  portfolioSize:   z.union([z.literal(1), z.literal(3), z.literal(5), z.literal(7)]).default(5),
});

export const ScanBodySchema = z.object({
  criteria: z.enum(['ALFA', 'BETA', 'DELTA']),
  date:     DateStrSchema,
  market:   z.enum(['BIST', 'BISTTUM', 'BIST100', 'BIST100DISI', 'US']),
});

// ─── Global Express error handler ────────────────────────────────────────────
// Mount this LAST in index.ts: app.use(globalErrorHandler)

export function globalErrorHandler(
  err:  Error,
  _req: Request,
  res:  Response,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  _next: NextFunction,
): void {
  console.error('[API Error]', err.message, err.stack);

  if (err instanceof ZodError) {
    fail(res, 'Validation error', 422, formatZodError(err));
    return;
  }

  const status = (err as Error & { status?: number }).status ?? 500;
  fail(res, err.message || 'Internal server error', status);
}
