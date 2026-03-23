import type { Request, Response, NextFunction } from 'express'
import { ZodError } from 'zod'

export interface ApiError extends Error {
  statusCode?: number
  code?:       string
}

export function errorHandler(
  err: ApiError,
  _req: Request,
  res: Response,
  _next: NextFunction
): void {
  if (err instanceof ZodError) {
    res.status(400).json({
      error: 'Validation error',
      code:  'VALIDATION_ERROR',
      issues: err.issues.map((e) => ({
        field:   e.path.join('.'),
        message: e.message,
      })),
    })
    return
  }

  const status  = err.statusCode ?? 500
  const message = err.message    ?? 'Internal server error'
  const code    = err.code       ?? (status === 404 ? 'NOT_FOUND' : 'INTERNAL_ERROR')

  if (status >= 500) console.error(`[${new Date().toISOString()}] ERROR:`, err)

  res.status(status).json({ error: message, code })
}

export function notFoundHandler(_req: Request, res: Response): void {
  res.status(404).json({ error: 'Route not found', code: 'NOT_FOUND' })
}

export function makeError(message: string, statusCode: number, code?: string): ApiError {
  const err: ApiError = new Error(message)
  err.statusCode = statusCode
  err.code       = code
  return err
}
