import { Router } from 'express'

const router = Router()

interface Position {
  id: string
  symbol: string
  name: string
  shares: number
  avgPrice: number
  currentPrice: number
  sector: string
}

let positions: Position[] = [
  { id: '1', symbol: 'AAPL', name: 'Apple Inc.', shares: 50, avgPrice: 165.20, currentPrice: 189.45, sector: 'Technology' },
  { id: '2', symbol: 'NVDA', name: 'NVIDIA', shares: 15, avgPrice: 480.00, currentPrice: 875.32, sector: 'Technology' },
  { id: '3', symbol: 'MSFT', name: 'Microsoft', shares: 30, avgPrice: 380.00, currentPrice: 412.88, sector: 'Technology' },
  { id: '4', symbol: 'JPM', name: 'JPMorgan', shares: 40, avgPrice: 175.00, currentPrice: 196.45, sector: 'Finance' },
  { id: '5', symbol: 'AMZN', name: 'Amazon', shares: 25, avgPrice: 175.00, currentPrice: 187.63, sector: 'Consumer' },
]

const enrich = (p: Position) => ({
  ...p,
  value: p.shares * p.currentPrice,
  pnl: p.shares * (p.currentPrice - p.avgPrice),
  pnlPct: ((p.currentPrice - p.avgPrice) / p.avgPrice) * 100,
})

router.get('/positions', (_req, res) => {
  const enriched = positions.map(enrich)
  const totalValue = enriched.reduce((s, p) => s + p.value, 0)
  const totalPnl = enriched.reduce((s, p) => s + p.pnl, 0)
  res.json({ positions: enriched, totalValue, totalPnl })
})

router.post('/positions', (req, res) => {
  const { symbol, name, shares, avgPrice, currentPrice, sector } = req.body
  if (!symbol || !shares || !avgPrice || !currentPrice) {
    return res.status(400).json({ error: 'Missing required fields' })
  }
  const newPosition: Position = {
    id: Date.now().toString(),
    symbol: symbol.toUpperCase(),
    name: name || symbol.toUpperCase(),
    shares: parseFloat(shares),
    avgPrice: parseFloat(avgPrice),
    currentPrice: parseFloat(currentPrice),
    sector: sector || 'Other',
  }
  positions.push(newPosition)
  return res.status(201).json(enrich(newPosition))
})

router.delete('/positions/:id', (req, res) => {
  const before = positions.length
  positions = positions.filter((p) => p.id !== req.params.id)
  if (positions.length === before) {
    return res.status(404).json({ error: 'Position not found' })
  }
  return res.json({ message: 'Position removed' })
})

router.get('/performance', (_req, res) => {
  const monthlyData = [
    { month: 'Jul', value: 108000 }, { month: 'Aug', value: 104000 },
    { month: 'Sep', value: 115000 }, { month: 'Oct', value: 122000 },
    { month: 'Nov', value: 118000 }, { month: 'Dec', value: 131450 },
  ]
  res.json({ monthlyData })
})

export default router
