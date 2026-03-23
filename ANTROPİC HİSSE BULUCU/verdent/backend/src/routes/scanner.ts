import { Router } from 'express'

const router = Router()

const stockUniverse = [
  { symbol: 'NVDA', name: 'NVIDIA Corp.', sector: 'Technology', price: 875.32, changePct: 2.15, volume: 42.3, mktCap: '2.16T', pe: 68.4, rsi: 72.1, signal: 'BUY' },
  { symbol: 'META', name: 'Meta Platforms', sector: 'Technology', price: 518.47, changePct: 2.43, volume: 18.7, mktCap: '1.32T', pe: 24.8, rsi: 65.3, signal: 'BUY' },
  { symbol: 'AAPL', name: 'Apple Inc.', sector: 'Technology', price: 189.45, changePct: 0.65, volume: 56.2, mktCap: '2.93T', pe: 31.2, rsi: 54.7, signal: 'HOLD' },
  { symbol: 'MSFT', name: 'Microsoft', sector: 'Technology', price: 412.88, changePct: -0.56, volume: 22.1, mktCap: '3.07T', pe: 37.5, rsi: 48.2, signal: 'HOLD' },
  { symbol: 'GOOGL', name: 'Alphabet', sector: 'Technology', price: 168.42, changePct: 0.52, volume: 25.4, mktCap: '2.07T', pe: 26.1, rsi: 51.8, signal: 'HOLD' },
  { symbol: 'AMZN', name: 'Amazon', sector: 'Consumer', price: 187.63, changePct: 1.74, volume: 35.8, mktCap: '1.96T', pe: 64.2, rsi: 61.4, signal: 'BUY' },
  { symbol: 'TSLA', name: 'Tesla Inc.', sector: 'Auto', price: 245.12, changePct: -3.51, volume: 89.4, mktCap: '780B', pe: 75.3, rsi: 38.2, signal: 'SELL' },
  { symbol: 'JPM', name: 'JPMorgan Chase', sector: 'Finance', price: 196.45, changePct: 0.96, volume: 12.3, mktCap: '567B', pe: 11.8, rsi: 56.9, signal: 'BUY' },
  { symbol: 'XOM', name: 'Exxon Mobil', sector: 'Energy', price: 105.67, changePct: -1.15, volume: 19.7, mktCap: '425B', pe: 13.4, rsi: 42.3, signal: 'SELL' },
  { symbol: 'JNJ', name: 'Johnson & Johnson', sector: 'Healthcare', price: 148.92, changePct: 0.30, volume: 8.9, mktCap: '357B', pe: 15.6, rsi: 49.1, signal: 'HOLD' },
  { symbol: 'V', name: 'Visa Inc.', sector: 'Finance', price: 274.58, changePct: 1.15, volume: 7.2, mktCap: '556B', pe: 30.2, rsi: 58.7, signal: 'BUY' },
  { symbol: 'WMT', name: 'Walmart', sector: 'Consumer', price: 67.42, changePct: 1.34, volume: 14.5, mktCap: '543B', pe: 28.9, rsi: 62.4, signal: 'BUY' },
]

router.post('/scan', (req, res) => {
  const { sector, minRsi, maxRsi, minChangePct, signal } = req.body

  let results = [...stockUniverse]

  if (sector && sector !== 'All') results = results.filter((s) => s.sector === sector)
  if (minRsi !== undefined) results = results.filter((s) => s.rsi >= minRsi)
  if (maxRsi !== undefined) results = results.filter((s) => s.rsi <= maxRsi)
  if (minChangePct !== undefined) results = results.filter((s) => s.changePct >= minChangePct)
  if (signal) results = results.filter((s) => s.signal === signal)

  res.json({ count: results.length, results, scannedAt: new Date().toISOString() })
})

router.get('/presets', (_req, res) => {
  res.json([
    { id: 'momentum', name: 'Momentum Stocks', filters: { minRsi: 60 } },
    { id: 'oversold', name: 'Oversold RSI', filters: { maxRsi: 30 } },
    { id: 'positive_day', name: 'Positive Day', filters: { minChangePct: 1.0 } },
    { id: 'buy_signal', name: 'Buy Signal', filters: { signal: 'BUY' } },
  ])
})

export default router
