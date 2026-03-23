import { Router } from 'express'

const router = Router()

const generateOHLC = (basePrice: number, count: number) => {
  const data = []
  let price = basePrice
  const now = Date.now()
  for (let i = count; i >= 0; i--) {
    const open = price + (Math.random() - 0.5) * 3
    const close = open + (Math.random() - 0.48) * 4
    const high = Math.max(open, close) + Math.random() * 2
    const low = Math.min(open, close) - Math.random() * 2
    data.push({ time: Math.floor((now - i * 86400000) / 1000), open, high, low, close, volume: Math.floor(Math.random() * 50000000) + 10000000 })
    price = close
  }
  return data
}

const mockQuotes: Record<string, { price: number; change: number; changePct: number; volume: number; mktCap: string }> = {
  AAPL: { price: 189.45, change: 1.23, changePct: 0.65, volume: 56200000, mktCap: '2.93T' },
  NVDA: { price: 875.32, change: 18.45, changePct: 2.15, volume: 42300000, mktCap: '2.16T' },
  MSFT: { price: 412.88, change: -2.34, changePct: -0.56, volume: 22100000, mktCap: '3.07T' },
  TSLA: { price: 245.12, change: -8.92, changePct: -3.51, volume: 89400000, mktCap: '780B' },
  AMZN: { price: 187.63, change: 3.21, changePct: 1.74, volume: 35800000, mktCap: '1.96T' },
  GOOGL: { price: 168.42, change: 0.88, changePct: 0.52, volume: 25400000, mktCap: '2.07T' },
}

router.get('/quote/:symbol', (req, res) => {
  const symbol = req.params.symbol.toUpperCase()
  const quote = mockQuotes[symbol]
  if (!quote) {
    return res.status(404).json({ error: `Symbol ${symbol} not found` })
  }
  return res.json({ symbol, ...quote, timestamp: new Date().toISOString() })
})

router.get('/history/:symbol', (req, res) => {
  const symbol = req.params.symbol.toUpperCase()
  const period = (req.query.period as string) || '3M'
  const periodMap: Record<string, number> = { '1D': 1, '1W': 7, '1M': 30, '3M': 90, '1Y': 365 }
  const days = periodMap[period] || 90
  const basePrice = mockQuotes[symbol]?.price || 150
  const data = generateOHLC(basePrice, days)
  return res.json({ symbol, period, data })
})

router.get('/overview', (_req, res) => {
  res.json({
    indices: [
      { name: 'S&P 500', value: 5234.18, change: 0.82 },
      { name: 'NASDAQ', value: 16421.45, change: 1.24 },
      { name: 'DOW', value: 39123.78, change: 0.41 },
      { name: 'VIX', value: 13.42, change: -2.15 },
    ],
    timestamp: new Date().toISOString(),
  })
})

router.get('/movers', (_req, res) => {
  res.json({
    gainers: [
      { symbol: 'NVDA', changePct: 2.15 },
      { symbol: 'META', changePct: 2.43 },
      { symbol: 'AMZN', changePct: 1.74 },
    ],
    losers: [
      { symbol: 'TSLA', changePct: -3.51 },
      { symbol: 'XOM', changePct: -1.15 },
      { symbol: 'MSFT', changePct: -0.56 },
    ],
  })
})

export default router
