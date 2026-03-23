import { randomUUID } from 'crypto'
import { prisma } from '../lib/prisma'
import { dataService } from './dataService'
import { analyzeMarketCondition } from './marketConditionService'
import { deterministicScanner } from './consistencyService'
import { BulkWriter, indicatorCache } from './backtestOptimizer'
import type { ProgressCallback } from './backtestOptimizer'
import { hybridBacktestV2 } from './hybridBacktestV2'
import {
  orchestrateRebalance,
  updateTrailingStops,
  shouldSellStock,
  type ManagedHolding,
} from './portfolioManager'
import type {
  BacktestConfig,
  BacktestResult,
  BacktestTrade,
  BacktestCriteria,
  CriteriaType,
  Holding,
  PortfolioSnapshot,
  PerformanceMetrics,
  BenchmarkResult,
  RebalanceResult,
  ScoredStock,
  OHLCV,
} from '../types/market'


// Risk-free rate assumption (annualised)
const RISK_FREE_RATE = 0.04

// ---------------------------------------------------------------------------
// Rebalance date generators
// ---------------------------------------------------------------------------

export function generateRebalanceDates(
  startDate: Date,
  endDate: Date,
  period: 'WEEKLY' | 'BIWEEKLY' | 'MONTHLY'
): Date[] {
  const dates: Date[] = []
  const cursor = new Date(startDate)

  if (period === 'BIWEEKLY') {
    // Every 15 calendar days from startDate
    while (cursor <= endDate) {
      // Skip weekends
      const d = new Date(cursor)
      while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() + 1)
      if (d <= endDate) dates.push(new Date(d))
      cursor.setDate(cursor.getDate() + 15)
    }
    return dates
  }

  if (period === 'WEEKLY') {
    // Advance to first Monday on or after startDate
    const dow = cursor.getDay()                  // 0=Sun … 6=Sat
    const daysToMonday = dow === 0 ? 1 : dow === 1 ? 0 : 8 - dow
    cursor.setDate(cursor.getDate() + daysToMonday)

    while (cursor <= endDate) {
      dates.push(new Date(cursor))
      cursor.setDate(cursor.getDate() + 7)
    }
  } else {
    // MONTHLY: first business day of each calendar month
    cursor.setDate(1)
    if (cursor < startDate) cursor.setMonth(cursor.getMonth() + 1)

    while (cursor <= endDate) {
      const first = new Date(cursor)
      first.setDate(1)
      // Advance past weekend
      while (first.getDay() === 0 || first.getDay() === 6) {
        first.setDate(first.getDate() + 1)
      }
      if (first <= endDate) dates.push(new Date(first))
      cursor.setMonth(cursor.getMonth() + 1)
    }
  }

  return dates
}

// ---------------------------------------------------------------------------
// Price lookup helper — find closing price for a symbol on/near a date
// ---------------------------------------------------------------------------
async function getPriceOnDate(symbol: string, date: Date): Promise<number | null> {
  const start = new Date(date)
  start.setDate(start.getDate() - 5)
  try {
    const bars = await dataService.fetchStockPrice(symbol, start, date, '1d')
    if (bars.length === 0) return null
    return bars[bars.length - 1].close
  } catch {
    return null
  }
}

// ---------------------------------------------------------------------------
// Transaction cost helper
// ---------------------------------------------------------------------------
function applyTxCost(value: number, txCost: number, slippage: number): number {
  return value * (txCost + slippage)
}

// ---------------------------------------------------------------------------
// Performance Metrics Calculator
// ---------------------------------------------------------------------------
function calculateMetrics(
  trades: BacktestTrade[],
  snapshots: PortfolioSnapshot[],
  initialCapital: number,
  years: number
): PerformanceMetrics {
  const finalValue   = snapshots[snapshots.length - 1]?.portfolioValue ?? initialCapital
  const totalReturn  = (finalValue - initialCapital) / initialCapital

  // CAGR
  const annualizedReturn = years > 0
    ? Math.pow(1 + totalReturn, 1 / years) - 1
    : 0

  // Max Drawdown
  let peak     = initialCapital
  let maxDD    = 0
  let maxDDPct = 0
  for (const s of snapshots) {
    if (s.portfolioValue > peak) peak = s.portfolioValue
    const dd    = peak - s.portfolioValue
    const ddPct = peak > 0 ? dd / peak : 0
    if (dd > maxDD)       maxDD    = dd
    if (ddPct > maxDDPct) maxDDPct = ddPct
  }

  // Daily returns for Sharpe / Sortino
  const dailyReturns = snapshots
    .map((s) => s.dailyReturn)
    .filter((r) => Number.isFinite(r))

  const dailyRF = RISK_FREE_RATE / 252
  const excessReturns = dailyReturns.map((r) => r - dailyRF)

  const meanExcess = excessReturns.length > 0
    ? excessReturns.reduce((a, b) => a + b, 0) / excessReturns.length
    : 0

  const variance = excessReturns.length > 1
    ? excessReturns.reduce((a, b) => a + (b - meanExcess) ** 2, 0) / (excessReturns.length - 1)
    : 0
  const stdDev = Math.sqrt(Math.max(0, variance))

  const sharpeRatio = stdDev > 1e-10 ? (meanExcess / stdDev) * Math.sqrt(252) : 0

  // Sortino (downside deviation only)
  const negativeReturns = excessReturns.filter((r) => r < 0)
  const downsideDevSq   = negativeReturns.length > 0
    ? negativeReturns.reduce((a, b) => a + (b - meanExcess) ** 2, 0) / negativeReturns.length
    : 0
  const downsideDev     = Math.sqrt(Math.max(0, downsideDevSq))
  const sortinoRatio    = downsideDev > 1e-10 ? (meanExcess / downsideDev) * Math.sqrt(252) : 0

  // Calmar & Recovery
  const calmarRatio     = maxDDPct > 0 ? annualizedReturn / maxDDPct : 0
  const recoveryFactor  = maxDD > 0 ? (finalValue - initialCapital) / maxDD : 0

  // Trade statistics (SELL trades with realised P&L)
  const closedTrades = trades.filter((t) => t.action === 'SELL')
  const winners      = closedTrades.filter((t) => t.pnl > 0)
  const losers       = closedTrades.filter((t) => t.pnl <= 0)

  const winRate      = closedTrades.length > 0 ? winners.length / closedTrades.length : 0
  const avgWin       = winners.length > 0 ? winners.reduce((s, t) => s + t.pnl, 0) / winners.length : 0
  const avgLoss      = losers.length  > 0 ? losers.reduce((s, t)  => s + t.pnl, 0) / losers.length  : 0
  const grossWin     = winners.reduce((s, t) => s + t.pnl, 0)
  const grossLoss    = Math.abs(losers.reduce((s, t) => s + t.pnl, 0))
  const profitFactor = grossLoss > 0 ? grossWin / grossLoss : grossWin > 0 ? Infinity : 0

  const pnls         = closedTrades.map((t) => t.pnl)
  const bestTrade    = pnls.length > 0 ? Math.max(...pnls) : 0
  const worstTrade   = pnls.length > 0 ? Math.min(...pnls) : 0

  // Average holding days: pair each SELL with the nearest prior BUY of same symbol
  let totalHoldingDays = 0
  let holdingCount     = 0
  for (const sell of closedTrades) {
    const matchBuy = trades
      .filter((t) => t.action === 'BUY' && t.symbol === sell.symbol && t.date <= sell.date)
      .sort((a, b) => b.date.getTime() - a.date.getTime())[0]
    if (matchBuy) {
      totalHoldingDays += (sell.date.getTime() - matchBuy.date.getTime()) / 86_400_000
      holdingCount++
    }
  }
  const avgHoldingDays = holdingCount > 0 ? totalHoldingDays / holdingCount : 0

  // Consecutive wins / losses
  let consWins = 0, consLosses = 0, curWins = 0, curLosses = 0
  for (const t of closedTrades) {
    if (t.pnl > 0) { curWins++; curLosses = 0;  consWins   = Math.max(consWins,   curWins)   }
    else            { curLosses++; curWins = 0;   consLosses = Math.max(consLosses, curLosses) }
  }

  return {
    totalReturn:       round4(totalReturn),
    annualizedReturn:  round4(annualizedReturn),
    maxDrawdown:       round2(maxDD),
    maxDrawdownPct:    round4(maxDDPct),
    sharpeRatio:       round4(sharpeRatio),
    sortinoRatio:      round4(sortinoRatio),
    calmarRatio:       round4(calmarRatio),
    recoveryFactor:    round4(recoveryFactor),
    winRate:           round4(winRate),
    avgWin:            round2(avgWin),
    avgLoss:           round2(avgLoss),
    profitFactor:      round4(profitFactor),
    totalTrades:       trades.length,
    winningTrades:     winners.length,
    losingTrades:      losers.length,
    bestTrade:         round2(bestTrade),
    worstTrade:        round2(worstTrade),
    avgHoldingDays:    round2(avgHoldingDays),
    consecutiveWins:   consWins,
    consecutiveLosses: consLosses,
  }
}

// ---------------------------------------------------------------------------
// Benchmark metrics calculator
// ---------------------------------------------------------------------------
async function calculateBenchmark(
  market: string,
  startDate: Date,
  endDate: Date,
  years: number
): Promise<BenchmarkResult> {
  const symbol = market === 'BIST' ? 'XU100.IS' : 'SPY'
  try {
    const prices = await dataService.fetchStockPrice(symbol, startDate, endDate, '1d')
    if (prices.length < 2) throw new Error('Insufficient benchmark data')

    const start = prices[0].close
    const end   = prices[prices.length - 1].close
    const ret   = (end - start) / start
    const annRet = years > 0 ? Math.pow(1 + ret, 1 / years) - 1 : 0

    // Max drawdown
    let peak = start, maxDD = 0
    for (const p of prices) {
      if (p.close > peak) peak = p.close
      const dd = peak > 0 ? (peak - p.close) / peak : 0
      if (dd > maxDD) maxDD = dd
    }

    // Daily returns for Sharpe
    const dailyRets = prices.slice(1).map((p, i) => (p.close - prices[i].close) / prices[i].close)
    const mean      = dailyRets.reduce((a, b) => a + b, 0) / dailyRets.length
    const variance  = dailyRets.reduce((a, b) => a + (b - mean) ** 2, 0) / dailyRets.length
    const sharpe    = variance > 0 ? ((mean - RISK_FREE_RATE / 252) / Math.sqrt(variance)) * Math.sqrt(252) : 0

    return { symbol, totalReturn: round4(ret), annualizedReturn: round4(annRet), maxDrawdown: round4(maxDD), sharpeRatio: round4(sharpe) }
  } catch {
    return { symbol, totalReturn: 0, annualizedReturn: 0, maxDrawdown: 0, sharpeRatio: 0 }
  }
}

// ---------------------------------------------------------------------------
// Portfolio rebalancer — powered by AdvancedPortfolioManager
// ---------------------------------------------------------------------------
async function rebalancePortfolio(
  currentHoldings: Holding[],
  cash:            number,
  totalValue:      number,
  scanDate:        Date,
  criteriaType:    CriteriaType,
  market:          string,
  config:          BacktestConfig,
  snapshots:       PortfolioSnapshot[],
): Promise<RebalanceResult> {
  const trades: BacktestTrade[] = []

  // ── Shared scan (identical to Scanner page) ───────────────────────────────
  let allScanResults: ScoredStock[] = await deterministicScanner.scan(criteriaType, scanDate, market)
    .catch(() => [])
  const activeCriteriaType = criteriaType

  // ── Fetch recent close prices for volatility-adjusted sizing ─────────────
  const closePrices = new Map<string, number[]>()
  await Promise.allSettled(
    allScanResults.slice(0, 20).map(async (s) => {
      try {
        const prices = await dataService.fetchStockPrice(
          s.symbol,
          new Date(scanDate.getTime() - 60 * 86_400_000),
          scanDate, '1d'
        )
        if (prices.length > 0) closePrices.set(s.symbol, prices.map((p) => p.close))
      } catch { /* non-fatal */ }
    })
  )

  // ── Update trailing stops on existing holdings ───────────────────────────
  const priceMap = new Map<string, number>()
  await Promise.allSettled(
    currentHoldings.map(async (h) => {
      const p = await getPriceOnDate(h.symbol, scanDate)
      if (p) priceMap.set(h.symbol, p)
    })
  )
  const managedHoldings: ManagedHolding[] = currentHoldings.map((h) => ({
    ...h,
    stopLoss:       (h as ManagedHolding).stopLoss       ?? h.entryPrice * 0.85,
    trailingActive: (h as ManagedHolding).trailingActive ?? false,
    entryDate:      (h as ManagedHolding).entryDate      ?? scanDate,
    currentATR:     (h as ManagedHolding).currentATR     ?? h.entryPrice * 0.02,
  }))
  const trailedHoldings = updateTrailingStops(managedHoldings, priceMap)

  // ── Orchestrate: sizing / circuit-breaker / gating / diversification ────
  const plan = orchestrateRebalance({
    scanResults:     allScanResults,
    currentHoldings: trailedHoldings,
    snapshots,
    condition:       'BULL' as const,
    criteriaType:    activeCriteriaType,
    config,
    closePrices,
  })

  // ── Circuit breaker: sell everything, hold cash ──────────────────────────
  if (plan.circuitBreaker.triggered) {
    let availCash = cash
    for (const h of trailedHoldings) {
      const price     = priceMap.get(h.symbol) ?? h.currentPrice
      const execPrice = price * (1 - config.slippage)
      const value     = h.shares * execPrice
      const cost      = applyTxCost(value, config.transactionCost, 0)
      availCash += value - cost
      trades.push({
        id: randomUUID(), symbol: h.symbol, action: 'SELL', date: scanDate,
        price: round4(execPrice), shares: h.shares, value: round2(value),
        cost: round2(cost), reason: `Circuit breaker triggered (drawdown ${(plan.circuitBreaker.drawdown * 100).toFixed(1)}%)`,
        pnl: round2((value - cost) - h.shares * h.entryPrice), pnlPct: 0,
      })
    }
    return {
      date: scanDate, buys: [], sells: trades,
      holdings: [], cash: round2(availCash),
      portfolioValue: round2(availCash), criteriaUsed: activeCriteriaType,
    }
  }

  // ── Smart rebalance gate: skip if cost > expected alpha ─────────────────
  if (plan.skip) {
    // Keep existing positions — just update current prices
    const updatedHoldings: Holding[] = trailedHoldings.map((h) => {
      const cp = priceMap.get(h.symbol) ?? h.currentPrice
      return { ...h, currentPrice: round4(cp), value: round2(h.shares * cp) }
    })
    const portfolioValue = cash + updatedHoldings.reduce((s, h) => s + h.value, 0)
    return { date: scanDate, buys: [], sells: [], holdings: updatedHoldings, cash: round2(cash), portfolioValue: round2(portfolioValue), criteriaUsed: criteriaType }
  }

  // ── Sell using momentum-based exit logic ─────────────────────────────────
  let availableCash = cash
  const holdToKeep  = new Set<string>()

  for (const holding of trailedHoldings) {
    const cp  = priceMap.get(holding.symbol) ?? holding.currentPrice
    const dec = shouldSellStock(holding, cp, allScanResults)

    if (dec.sell || !plan.stocks.some((s) => s.symbol === holding.symbol)) {
      const execPrice = cp * (1 - config.slippage)
      const value     = holding.shares * execPrice
      const cost      = applyTxCost(value, config.transactionCost, 0)
      const pnl       = (value - cost) - holding.shares * holding.entryPrice
      availableCash  += value - cost
      trades.push({
        id: randomUUID(), symbol: holding.symbol, action: 'SELL', date: scanDate,
        price: round4(execPrice), shares: holding.shares, value: round2(value),
        cost: round2(cost), reason: dec.reason,
        pnl: round2(pnl), pnlPct: round4(pnl / (holding.shares * holding.entryPrice || 1)),
      })
    } else {
      holdToKeep.add(holding.symbol)
    }
  }

  // ── Buy new positions using dynamic weights & exposure ───────────────────
  const investable       = availableCash * plan.exposure.maxExposure
  const updatedHoldings: Holding[] = []

  // Keep surviving positions (momentum / score still good)
  for (const h of trailedHoldings) {
    if (holdToKeep.has(h.symbol)) {
      const cp = priceMap.get(h.symbol) ?? h.currentPrice
      updatedHoldings.push({ ...h, currentPrice: round4(cp), value: round2(h.shares * cp) })
    }
  }

  // Buy new entries
  for (const stock of plan.stocks) {
    if (holdToKeep.has(stock.symbol)) continue   // already kept above

    const weightEntry = plan.weights.find((w) => w.symbol === stock.symbol)
    const weight      = weightEntry?.weight ?? 1 / plan.stocks.length
    const targetAlloc = investable * weight

    const price     = await getPriceOnDate(stock.symbol, scanDate) ?? stock.entryPrice
    const execPrice = price * (1 + config.slippage)
    if (execPrice <= 0) continue

    const cost     = applyTxCost(targetAlloc, config.transactionCost, 0)
    const netAlloc = targetAlloc - cost
    const shares   = round4(netAlloc / execPrice)

    availableCash -= targetAlloc

    // Stop loss: BIST 15%, US 10% — BIST has much higher daily volatility
    const stopPct     = config.market === 'BIST' ? 0.85 : 0.90
    const initialStop = execPrice * stopPct

    trades.push({
      id: randomUUID(), symbol: stock.symbol, action: 'BUY', date: scanDate,
      price: round4(execPrice), shares, value: round2(netAlloc), cost: round2(cost),
      reason: `${activeCriteriaType} entry | score ${stock.score.toFixed(1)} | wt ${(weight * 100).toFixed(1)}%`,
      pnl: 0, pnlPct: 0,
    })

    updatedHoldings.push({
      symbol: stock.symbol, name: stock.name, shares,
      entryPrice: round4(execPrice), currentPrice: round4(execPrice),
      value: round2(netAlloc), weight, pnl: 0, pnlPct: 0,
      // Extended fields for trailing stop
      stopLoss:       round4(initialStop),
      trailingActive: false,
      entryDate:      scanDate,
      currentATR:     round4(execPrice * 0.02),
    } as ManagedHolding)
  }

  const portfolioValue = Math.max(0, availableCash) +
    updatedHoldings.reduce((s, h) => s + h.value, 0)

  return {
    date:           scanDate,
    buys:           trades.filter((t) => t.action === 'BUY'),
    sells:          trades.filter((t) => t.action === 'SELL'),
    holdings:       updatedHoldings,
    cash:           round2(Math.max(0, availableCash)),
    portfolioValue: round2(portfolioValue),
    criteriaUsed:   activeCriteriaType,
  }
}

// ---------------------------------------------------------------------------
// Single-criteria backtest
// ---------------------------------------------------------------------------
async function runCriteriaBacktest(
  config:       BacktestConfig,
  market:       string,
  criteriaType: CriteriaType,
  _onProgress?: ProgressCallback,
): Promise<{ snapshots: PortfolioSnapshot[]; trades: BacktestTrade[] }> {
  const rebalanceDates = generateRebalanceDates(config.startDate, config.endDate, config.rebalancePeriod)

  let cash     = config.initialCapital
  let holdings: Holding[] = []
  const allTrades: BacktestTrade[]      = []
  const snapshots: PortfolioSnapshot[]  = []
  let prevValue = config.initialCapital

  for (const date of rebalanceDates) {
    let marketConditionLabel = 'UNKNOWN'
    try {
      const mc = await analyzeMarketCondition(market, date)
      marketConditionLabel = mc.condition
    } catch { /* non-fatal */ }

    const result = await rebalancePortfolio(
      holdings, cash,
      cash + holdings.reduce((s, h) => s + h.value, 0),
      date, criteriaType, market, config, snapshots
    )

    holdings = result.holdings
    cash     = result.cash
    allTrades.push(...result.buys, ...result.sells)

    const dailyReturn = prevValue > 0 ? (result.portfolioValue - prevValue) / prevValue : 0
    prevValue = result.portfolioValue

    snapshots.push({
      date,
      portfolioValue:  result.portfolioValue,
      cash,
      holdings,
      criteriaUsed:    criteriaType,
      marketCondition: marketConditionLabel,
      dailyReturn,
    })
  }

  return { snapshots, trades: allTrades }
}

// ---------------------------------------------------------------------------
// Hybrid backtest V2 — delegated to HybridBacktestV2 with confirmation gate,
// multi-timeframe regime detection, and smooth transition logic
// ---------------------------------------------------------------------------
async function runHybridBacktest(
  config:      BacktestConfig,
  market:      string,
  onProgress?: ProgressCallback,
): Promise<{ snapshots: PortfolioSnapshot[]; trades: BacktestTrade[] }> {
  const rebalanceDates = generateRebalanceDates(config.startDate, config.endDate, config.rebalancePeriod)

  hybridBacktestV2.reset()

  return hybridBacktestV2.run(
    config,
    market,
    rebalanceDates,
    // Adapter: RebalanceFn signature → local rebalancePortfolio
    (holdings, cash, totalValue, date, criteria, mkt, cfg, snaps) =>
      rebalancePortfolio(holdings, cash, totalValue, date, criteria, mkt, cfg, snaps),
    (pct, date, msg) => onProgress?.({ stage: 'scanning', progress: pct, currentDate: date, message: msg }),
  )
}

// ---------------------------------------------------------------------------
// Consistency check: re-run scan for the first rebalance date and verify
// that the symbols returned match what the live scanner would return
// ---------------------------------------------------------------------------
async function runConsistencyCheck(
  config: BacktestConfig,
  firstRebalanceDate: Date,
  firstSnapshotHoldings: Holding[],
  market: string,
  criteriaType: CriteriaType
): Promise<boolean> {
  try {
    const liveResults = await deterministicScanner.scan(criteriaType, firstRebalanceDate, market)
    const liveTop5 = liveResults.slice(0, 5).map((s) => s.symbol).sort()
    const btTop5   = firstSnapshotHoldings.map((h) => h.symbol).sort()
    return JSON.stringify(liveTop5) === JSON.stringify(btTop5)
  } catch {
    return false
  }
}

// ---------------------------------------------------------------------------
// Main orchestrator
// ---------------------------------------------------------------------------
export class BacktestEngine {

  async runBacktest(
    config: BacktestConfig,
    onProgress?: ProgressCallback,
  ): Promise<BacktestResult> {
    const startedAt = Date.now()
    const id        = randomUUID()

    const years = (config.endDate.getTime() - config.startDate.getTime()) / (365.25 * 86_400_000)

    const markets = config.market === 'BOTH' ? ['BIST', 'US'] : [config.market]

    onProgress?.({
      stage: 'initialising', progress: 0, currentDate: null,
      message: 'Göstergeler önbelleğe alınıyor…',
    })

    // Pre-warm indicator cache so rebalance loops are fast
    try {
      // Use DB stocks first (full universe); fall back to index constituents
      const dbSymbols = await dataService.getBIST100Constituents()
        .then(list => list.length >= 50 ? list : [])
        .catch(() => [])
      const symbols = dbSymbols.length >= 50
        ? dbSymbols
        : await (config.market === 'BIST'
            ? dataService.getBIST100Constituents()
            : dataService.getSP500Constituents())

      // --- Prefetch ALL price data for the backtest period (avoids per-call rate limits) ---
      onProgress?.({
        stage: 'initialising', progress: 2, currentDate: null,
        message: 'Fiyat verileri önceden yükleniyor…',
      })
      const prefetchSymbols = symbols
        .map((s: any) => ({ symbol: typeof s === 'string' ? s : s.symbol, market: config.market }))
      // Always include the benchmark index in the prefetch (needed for relative strength in criteriaEngine)
      const benchmarkSymbol = config.market === 'BIST' ? 'XU100.IS' : 'SPY'
      if (!prefetchSymbols.some((s: any) => s.symbol === benchmarkSymbol)) {
        prefetchSymbols.push({ symbol: benchmarkSymbol, market: config.market })
      }
      await dataService.prefetchPrices(
        prefetchSymbols,
        new Date(config.startDate.getTime() - 430 * 86_400_000), // extra history for indicators
        config.endDate,
        (done, total) => onProgress?.({
          stage: 'initialising',
          progress: Math.round(2 + (done / total) * 20),
          currentDate: null,
          message: `Fiyat verisi yükleniyor: ${done}/${total}`,
        })
      )

      await indicatorCache.prewarm(symbols.map((s: any) => typeof s === 'string' ? s : s.symbol), config.startDate, config.endDate, 20,
        (done, total) => onProgress?.({
          stage: 'initialising',
          progress: Math.round(22 + (done / total) * 10),
          currentDate: null,
          message: `${done}/${total} sembol önbelleğe alındı`,
        }))
    } catch { /* non-fatal */ }

    // Collect snapshots & trades across markets (merged for BOTH)
    const allSnapshots: PortfolioSnapshot[] = []
    const allTrades:    BacktestTrade[]     = []

    for (const market of markets) {
      let result: { snapshots: PortfolioSnapshot[]; trades: BacktestTrade[] }

      if (config.criteriaType === 'HYBRID') {
        result = await runHybridBacktest(config, market, onProgress)
      } else {
        result = await runCriteriaBacktest(config, market, config.criteriaType as CriteriaType, onProgress)
      }

      allSnapshots.push(...result.snapshots)
      allTrades.push(...result.trades)
    }

    // Sort snapshots chronologically and rebuild dailyReturn vs previous snapshot
    allSnapshots.sort((a, b) => a.date.getTime() - b.date.getTime())
    for (let i = 1; i < allSnapshots.length; i++) {
      const prev = allSnapshots[i - 1].portfolioValue
      allSnapshots[i].dailyReturn = prev > 0
        ? (allSnapshots[i].portfolioValue - prev) / prev
        : 0
    }

    const performance = calculateMetrics(allTrades, allSnapshots, config.initialCapital, years)

    const primaryMarket = config.market === 'BOTH' ? 'US' : config.market
    const benchmark     = await calculateBenchmark(primaryMarket, config.startDate, config.endDate, years)

    // Consistency check using first rebalance date
    const firstSnapshot = allSnapshots[0]
    const criteriaForCheck: CriteriaType =
      config.criteriaType === 'HYBRID'
        ? (firstSnapshot?.criteriaUsed as CriteriaType ?? 'DELTA')
        : (config.criteriaType as CriteriaType)

    const consistencyCheck = firstSnapshot
      ? await runConsistencyCheck(
          config,
          firstSnapshot.date,
          firstSnapshot.holdings,
          primaryMarket,
          criteriaForCheck
        )
      : false

    const btResult: BacktestResult = {
      id,
      config,
      performance,
      portfolioHistory: allSnapshots,
      trades: allTrades,
      benchmark,
      consistencyCheck,
      completedAt: new Date(),
      durationMs:  Date.now() - startedAt,
    }

    await persistBacktest(btResult, onProgress).catch(() => {/* non-fatal */})

    // Clear prefetch store to free memory
    dataService.clearPrefetch()

    return btResult
  }
}

// ---------------------------------------------------------------------------
// Persist to DB
// ---------------------------------------------------------------------------
async function persistBacktest(
  result:     BacktestResult,
  onProgress?: ProgressCallback,
): Promise<void> {
  onProgress?.({
    stage: 'saving', progress: 90, currentDate: null,
    message: 'Sonuçlar veritabanına kaydediliyor…',
  })

  const bt = await prisma.backtest.create({
    data: {
      name:             result.config.name,
      criteriaType:     result.config.criteriaType,
      criteriaId:       null,
      startDate:        result.config.startDate,
      endDate:          result.config.endDate,
      rebalancePeriod:  result.config.rebalancePeriod,
      market:           result.config.market,
      initialCapital:   result.config.initialCapital,
      status:           'COMPLETED',
      totalReturn:      result.performance.totalReturn      * 100,
      annualizedReturn: result.performance.annualizedReturn * 100,
      maxDrawdown:      result.performance.maxDrawdownPct   * 100,
      sharpeRatio:      result.performance.sharpeRatio,
      winRate:          result.performance.winRate          * 100,
      totalTrades:      result.performance.totalTrades,
    },
  })

  // Use BulkWriter for O(1) DB round-trips instead of N inserts
  const writer = new BulkWriter()

  result.portfolioHistory.forEach((s) =>
    writer.addSnapshot({
      backtestId:      bt.id,
      date:            s.date,
      portfolioValue:  s.portfolioValue,
      holdings:        s.holdings as object,
      criteriaUsed:    s.criteriaUsed,
      marketCondition: s.marketCondition,
    }),
  )

  result.trades.forEach((t) =>
    writer.addTrade({
      backtestId: bt.id,
      symbol:     t.symbol,
      action:     t.action,
      date:       t.date,
      price:      t.price,
      shares:     t.shares,
      value:      t.value,
      reason:     t.reason,
    }),
  )

  const { snapshots, trades } = await writer.flush()

  onProgress?.({
    stage: 'saving', progress: 100, currentDate: null,
    message: `Kaydedildi: ${snapshots} anlık görüntü, ${trades} işlem`,
  })
}

// ---------------------------------------------------------------------------
// Rounding utilities
// ---------------------------------------------------------------------------
function round2(n: number): number  { return Math.round(n * 100) / 100 }
function round4(n: number): number  { return Math.round(n * 10000) / 10000 }

// Singleton export
export const backtestEngine = new BacktestEngine()
