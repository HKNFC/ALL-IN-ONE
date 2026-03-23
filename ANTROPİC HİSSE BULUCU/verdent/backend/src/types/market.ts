export interface VCPResult {
  stages:        number[]
  pivot:         number
  isContracting: boolean
  score:         number
}

export interface OHLCV {
  date: Date
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface Fundamentals {
  symbol: string
  pe: number | null
  pb: number | null
  roe: number | null
  debtEquity: number | null
  revenueGrowth: number | null
  earningsGrowth: number | null
  freeCashFlow: number | null
  marketCap: number | null
  updatedAt: Date
}

export interface IndexData {
  index: string
  value: number
  change: number
  changePct: number
  date: Date
}

export interface MACDResult {
  macdLine: number[]
  signalLine: number[]
  histogram: number[]
}

export interface BollingerResult {
  upper: number[]
  middle: number[]
  lower: number[]
}

export interface ADXResult {
  adx: number[]
  plusDI: number[]
  minusDI: number[]
}

export interface StochasticResult {
  k: number[]
  d: number[]
}

export interface FibonacciLevels {
  high: number
  low: number
  level0: number
  level236: number
  level382: number
  level500: number
  level618: number
  level786: number
  level1000: number
}

export interface TechnicalIndicators {
  ema20: number[]
  ema50: number[]
  ema150: number[]
  ema200: number[]
  sma50: number[]
  sma200: number[]
  rsi14: number[]
  macd: MACDResult
  bollinger: BollingerResult
  atr14: number[]
  adx14: ADXResult
  stochastic: StochasticResult
  obv: number[]
  obvMA20: number[]
  mfi14: number[]
  vwap: number[]
  volume20avg: number[]
  fibonacci: FibonacciLevels
  vcp: VCPResult
}

export interface BreadthData {
  market: string
  advanceDeclineRatio: number
  advancingStocks: number
  decliningStocks: number
  unchangedStocks: number
  pctAbove200SMA: number
  newHighs: number
  newLows: number
  newHighLowRatio: number
  date: Date
}

export interface CacheConfig {
  dailyPriceTTL: number
  indicatorTTL: number
  fundamentalTTL: number
}

// ---------------------------------------------------------------------------
// Market Condition Analysis
// ---------------------------------------------------------------------------

export type MarketCondition = 'BULL' | 'BEAR' | 'SIDEWAYS'
export type RecommendedCriteria = 'ALFA' | 'BETA' | 'DELTA'

export interface IndicatorGroupResult {
  score: number        // contribution to total (already weighted)
  rawScore: number     // pre-weight score
  maxRaw: number       // maximum possible raw score (for confidence calc)
  details: Record<string, IndicatorDetail>
}

export interface IndicatorDetail {
  value: number | null
  signal: 'BULL' | 'BEAR' | 'NEUTRAL'
  points: number
  label: string
}

export interface MarketConditionResult {
  condition: MarketCondition
  score: number           // -10 to +10
  confidence: number      // 0-100
  indicators: {
    trend:      IndicatorGroupResult
    momentum:   IndicatorGroupResult
    volatility: IndicatorGroupResult
    breadth:    IndicatorGroupResult
  }
  recommendedCriteria: RecommendedCriteria
  date: Date
  market: string
}

// ---------------------------------------------------------------------------
// Criteria Engine
// ---------------------------------------------------------------------------

export type CriteriaType = 'ALFA' | 'BETA' | 'DELTA'

export interface SignalDetail {
  name: string
  value: number | null
  threshold: number | null
  passed: boolean
  weight: number
  contribution: number   // points actually added to score
  description: string
}

export interface ScoredStock {
  symbol: string
  name: string
  score: number          // 0-100
  rank: number
  signals: {
    technical:   SignalDetail[]
    fundamental: SignalDetail[]
    passed:      string[]
    failed:      string[]
  }
  entryPrice: number
  suggestedStopLoss: number
  targetPrice: number
  riskRewardRatio: number
}

export interface Portfolio {
  criteria:      CriteriaType
  date:          Date
  market:        string
  totalStocks:   number
  topHoldings:   ScoredStock[]
  avgScore:      number
  createdAt:     Date
}

// Full market data bundle assembled per stock before scoring
export interface StockData {
  symbol:       string
  name:         string
  market:       string
  prices:       OHLCV[]
  fundamentals: Fundamentals
  indicators:   TechnicalIndicators
  high52w:      number
  low52w:       number
  // relative-strength vs index (ratio of stock return to index return)
  relativeStrength: number | null
  // percentile rank among all scanned stocks (0-100), assigned post-assembly
  rsRank:       number
  // beta approximated from 60-day covariance
  beta:         number | null
}

export interface FilterRule {
  name:      string
  weight:    number
  check:     (stock: StockData) => { passed: boolean; value: number | null; description: string }
}

export interface CriteriaConfig {
  name?:              string
  description?:       string
  marketCondition?:   string
  type?:              CriteriaType
  label?:             string
  technicalFilters:   FilterRule[]
  fundamentalFilters: FilterRule[]
  entryRules?: {
    minScore:         number
    maxPositions:     number
    positionSize:     number
    stopLossPercent:  number
  }
  exitRules?: {
    takeProfit:       number | null
    stopLoss:         number
    rebalanceSell:    boolean
  }
}

// ---------------------------------------------------------------------------
// Backtest Engine
// ---------------------------------------------------------------------------

export type RebalancePeriod  = 'WEEKLY' | 'BIWEEKLY' | 'MONTHLY'
export type BacktestMarket   = 'BIST' | 'US' | 'BOTH'
export type BacktestCriteria = 'ALFA' | 'BETA' | 'DELTA' | 'HYBRID'

export interface BacktestConfig {
  name:             string
  criteriaType:     BacktestCriteria
  startDate:        Date
  endDate:          Date
  rebalancePeriod:  RebalancePeriod
  market:           BacktestMarket
  initialCapital:   number
  transactionCost:  number   // e.g. 0.001 = 0.1%
  slippage:         number   // e.g. 0.001 = 0.1%
}

export interface Holding {
  symbol:        string
  name:          string
  shares:        number
  entryPrice:    number
  currentPrice:  number
  value:         number
  weight:        number     // 0-1
  pnl:           number
  pnlPct:        number
}

export interface BacktestTrade {
  id:            string
  symbol:        string
  action:        'BUY' | 'SELL'
  date:          Date
  price:         number
  shares:        number
  value:         number
  cost:          number     // transaction cost paid
  reason:        string
  pnl:           number     // realised P&L (only on SELL)
  pnlPct:        number
}

export interface PortfolioSnapshot {
  date:             Date
  portfolioValue:   number
  cash:             number
  holdings:         Holding[]
  criteriaUsed:     string
  marketCondition:  string
  dailyReturn:      number
}

export interface PerformanceMetrics {
  totalReturn:       number
  annualizedReturn:  number
  maxDrawdown:       number
  maxDrawdownPct:    number
  sharpeRatio:       number
  sortinoRatio:      number
  calmarRatio:       number
  recoveryFactor:    number
  winRate:           number
  avgWin:            number
  avgLoss:           number
  profitFactor:      number
  totalTrades:       number
  winningTrades:     number
  losingTrades:      number
  bestTrade:         number
  worstTrade:        number
  avgHoldingDays:    number
  consecutiveWins:   number
  consecutiveLosses: number
}

export interface BenchmarkResult {
  symbol:           string
  totalReturn:      number
  annualizedReturn: number
  maxDrawdown:      number
  sharpeRatio:      number
}

export interface RebalanceResult {
  date:          Date
  buys:          BacktestTrade[]
  sells:         BacktestTrade[]
  holdings:      Holding[]
  cash:          number
  portfolioValue: number
  criteriaUsed:  string
}

export interface BacktestResult {
  id:               string
  config:           BacktestConfig
  performance:      PerformanceMetrics
  portfolioHistory: PortfolioSnapshot[]
  trades:           BacktestTrade[]
  benchmark:        BenchmarkResult
  consistencyCheck: boolean
  completedAt:      Date
  durationMs:       number
}
