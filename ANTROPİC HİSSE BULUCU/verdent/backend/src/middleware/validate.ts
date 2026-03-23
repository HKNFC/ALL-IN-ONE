import type { Request, Response, NextFunction } from 'express'
import { ZodSchema, ZodError } from 'zod'

type Target = 'body' | 'query' | 'params'

declare module 'express-serve-static-core' {
  interface Request {
    validated?: Record<string, unknown>
  }
}

export function validate<T>(schema: ZodSchema<T>, target: Target = 'body') {
  return (req: Request, res: Response, next: NextFunction): void => {
    const result = schema.safeParse(req[target])
    if (!result.success) {
      const err = result.error as ZodError
      res.status(400).json({
        error:  'Validation error',
        code:   'VALIDATION_ERROR',
        issues: err.issues.map((e) => ({
          field:   e.path.join('.'),
          message: e.message,
        })),
      })
      return
    }
    // Store parsed data on req.validated to avoid Express 5 read-only props
    if (!req.validated) req.validated = {}
    req.validated[target] = result.data as Record<string, unknown>
    next()
  }
}
