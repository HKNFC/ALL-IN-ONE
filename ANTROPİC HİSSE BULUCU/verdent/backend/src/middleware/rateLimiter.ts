import rateLimit from 'express-rate-limit'

const json429 = (_req: unknown, res: { status: (n: number) => { json: (b: unknown) => void } }): void => {
  res.status(429).json({ error: 'Too many requests, please slow down.', code: 'RATE_LIMITED' })
}

// General API — 120 req / min
export const generalLimiter = rateLimit({
  windowMs:         60 * 1000,
  max:              120,
  standardHeaders:  true,
  legacyHeaders:    false,
  handler:          json429,
})

// Heavy compute (backtest / full scan) — 10 req / min
export const heavyLimiter = rateLimit({
  windowMs:         60 * 1000,
  max:              10,
  standardHeaders:  true,
  legacyHeaders:    false,
  handler:          json429,
})

// Market data — 60 req / min
export const marketLimiter = rateLimit({
  windowMs:         60 * 1000,
  max:              60,
  standardHeaders:  true,
  legacyHeaders:    false,
  handler:          json429,
})
