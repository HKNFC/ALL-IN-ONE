import { Router } from 'express'

const router = Router()

interface BacktestParams {
  strategy: string
  symbol: string
  startDate: string
  endDate: string
  capital: number
}

const runBacktestLogic = (params: BacktestParams) => {
  const { capital } = params
  const totalReturnPct = 8 + Math.random() * 25
  const finalValue = capital * (1 + totalReturnPct / 100)
  const trades = Math.floor(20 + Math.random() * 40)
  const winRate = 55 + Math.random() * 20

  return {
    id: Date.now().toString(),
    params,
    metrics: {
      totalReturn: parseFloat(totalReturnPct.toFixed(2)),
      finalValue: parseFloat(finalValue.toFixed(2)),
      sharpeRatio: parseFloat((1.2 + Math.random() * 1.2).toFixed(2)),
      maxDrawdown: parseFloat((-(5 + Math.random() * 10)).toFixed(2)),
      winRate: parseFloat(winRate.toFixed(1)),
      totalTrades: trades,
      profitFactor: parseFloat((1.5 + Math.random() * 1.5).toFixed(2)),
      avgWinAmount: parseFloat((200 + Math.random() * 400).toFixed(2)),
      avgLossAmount: parseFloat((-(100 + Math.random() * 200)).toFixed(2)),
    },
    completedAt: new Date().toISOString(),
  }
}

const backtestHistory: ReturnType<typeof runBacktestLogic>[] = []

router.post('/run', (req, res) => {
  const params: BacktestParams = req.body
  if (!params.strategy || !params.symbol || !params.startDate || !params.endDate) {
    return res.status(400).json({ error: 'Missing required parameters: strategy, symbol, startDate, endDate' })
  }
  const result = runBacktestLogic({ ...params, capital: params.capital || 100000 })
  backtestHistory.unshift(result)
  return res.json(result)
})

router.get('/list', (_req, res) => {
  res.json(backtestHistory)
})

router.get('/:id', (req, res) => {
  const bt = backtestHistory.find((b) => b.id === req.params.id)
  if (!bt) return res.status(404).json({ error: 'Backtest not found' })
  return res.json(bt)
})

export default router
