import { prisma } from '../lib/prisma'
import { dataService } from './dataService'
import {
  calculateEMA,
  calculateSMA,
  calculateRSI,
  calculateMACD,
  calculateATR,
  calculateADX,
} from '../utils/indicators'
import type {
  OHLCV,
  BreadthData,
  MarketConditionResult,
  MarketCondition,
  RecommendedCriteria,
  IndicatorGroupResult,
  IndicatorDetail,
} from '../types/market'


// ---------------------------------------------------------------------------
// Weight config (must sum to 1.0)
// ---------------------------------------------------------------------------
const WEIGHTS = {
  trend:      0.40,
  momentum:   0.30,
  volatility: 0.20,
  breadth:    0.10,
}

// Max raw scores per group (used for normalisation to ±10 total)
const MAX_RAW = {
  trend:      6,   // 3 indicators × ±2
  momentum:   3,   // 3 indicators × ±1
  volatility: 2,   // 2 indicators × ±1
  breadth:    3,   // 3 indicators × ±1
}

// Index symbol map
const INDEX_SYMBOL: Record<string, string> = {
  BIST: 'XU100.IS',
  US:   'SPY',
}

// ---------------------------------------------------------------------------
// Helper: last valid value in array
// ---------------------------------------------------------------------------
function lastValid(arr: number[]): number | null {
  for (let i = arr.length - 1; i >= 0; i--) {
    if (!isNaN(arr[i]) && arr[i] !== null) return arr[i]
  }
  return null
}

// ---------------------------------------------------------------------------
// Helper: detect HH/HL or LH/LL over the last N swings
// ---------------------------------------------------------------------------
function detectSwingStructure(
  prices: OHLCV[],
  lookback: number = 20
): 'HIGHER_HIGHS' | 'LOWER_LOWS' | 'MIXED' {
  if (prices.length < lookback + 1) return 'MIXED'
  const recent = prices.slice(-lookback)

  // Find local highs and lows (simple pivot: bar is higher/lower than both neighbours)
  const highs: number[] = []
  const lows: number[] = []
  for (let i = 1; i < recent.length - 1; i++) {
    if (recent[i].high > recent[i - 1].high && recent[i].high > recent[i + 1].high) {
      highs.push(recent[i].high)
    }
    if (recent[i].low < recent[i - 1].low && recent[i].low < recent[i + 1].low) {
      lows.push(recent[i].low)
    }
  }

  const isHH = highs.length >= 2 && highs[highs.length - 1] > highs[highs.length - 2]
  const isHL = lows.length >= 2 && lows[lows.length - 1] > lows[lows.length - 2]
  const isLH = highs.length >= 2 && highs[highs.length - 1] < highs[highs.length - 2]
  const isLL = lows.length >= 2 && lows[lows.length - 1] < lows[lows.length - 2]

  if (isHH && isHL) return 'HIGHER_HIGHS'
  if (isLH && isLL) return 'LOWER_LOWS'
  return 'MIXED'
}

// ---------------------------------------------------------------------------
// TREND group  (max raw ±6)
// ---------------------------------------------------------------------------
function scoreTrend(prices: OHLCV[]): IndicatorGroupResult {
  const details: Record<string, IndicatorDetail> = {}
  let rawScore = 0

  const sma50arr  = calculateSMA(prices, 50)
  const sma200arr = calculateSMA(prices, 200)
  const latestClose = prices[prices.length - 1]?.close ?? 0
  const sma50  = lastValid(sma50arr)
  const sma200 = lastValid(sma200arr)

  // 1. Price vs 200 SMA
  if (sma200 !== null) {
    const pts = latestClose > sma200 ? 2 : -2
    rawScore += pts
    details.priceVs200SMA = {
      value: sma200,
      signal: pts > 0 ? 'BULL' : 'BEAR',
      points: pts,
      label: pts > 0
        ? `Price ${((latestClose / sma200 - 1) * 100).toFixed(1)}% above 200 SMA`
        : `Price ${((1 - latestClose / sma200) * 100).toFixed(1)}% below 200 SMA`,
    }
  } else {
    details.priceVs200SMA = { value: null, signal: 'NEUTRAL', points: 0, label: 'Insufficient data for 200 SMA' }
  }

  // 2. 50 SMA vs 200 SMA (Golden / Death Cross)
  if (sma50 !== null && sma200 !== null) {
    const pts = sma50 > sma200 ? 2 : -2
    rawScore += pts
    details.smaCross = {
      value: sma50 - sma200,
      signal: pts > 0 ? 'BULL' : 'BEAR',
      points: pts,
      label: pts > 0 ? 'Golden Cross (50 SMA > 200 SMA)' : 'Death Cross (50 SMA < 200 SMA)',
    }
  } else {
    details.smaCross = { value: null, signal: 'NEUTRAL', points: 0, label: 'Insufficient data for SMA cross' }
  }

  // 3. Higher Highs / Lower Lows
  const swing = detectSwingStructure(prices, 40)
  const swingPts = swing === 'HIGHER_HIGHS' ? 2 : swing === 'LOWER_LOWS' ? -2 : 0
  rawScore += swingPts
  details.swingStructure = {
    value: null,
    signal: swingPts > 0 ? 'BULL' : swingPts < 0 ? 'BEAR' : 'NEUTRAL',
    points: swingPts,
    label: swing === 'HIGHER_HIGHS'
      ? 'Higher Highs & Higher Lows (uptrend structure)'
      : swing === 'LOWER_LOWS'
      ? 'Lower Highs & Lower Lows (downtrend structure)'
      : 'No clear swing structure (mixed)',
  }

  const score = rawScore * WEIGHTS.trend * (10 / MAX_RAW.trend)
  return { score: parseFloat(score.toFixed(3)), rawScore, maxRaw: MAX_RAW.trend, details }
}

// ---------------------------------------------------------------------------
// MOMENTUM group  (max raw ±3)
// ---------------------------------------------------------------------------
function scoreMomentum(prices: OHLCV[]): IndicatorGroupResult {
  const details: Record<string, IndicatorDetail> = {}
  let rawScore = 0

  const rsiArr  = calculateRSI(prices, 14)
  const macd    = calculateMACD(prices, 12, 26, 9)
  const adxData = calculateADX(prices, 14)

  // 1. RSI(14)
  const rsi = lastValid(rsiArr)
  if (rsi !== null) {
    const pts = rsi > 50 ? 1 : rsi < 40 ? -1 : 0
    rawScore += pts
    details.rsi14 = {
      value: rsi,
      signal: pts > 0 ? 'BULL' : pts < 0 ? 'BEAR' : 'NEUTRAL',
      points: pts,
      label: `RSI(14) = ${rsi.toFixed(1)} — ${rsi > 50 ? 'above' : rsi < 40 ? 'below' : 'in'} key 50/40 zone`,
    }
  } else {
    details.rsi14 = { value: null, signal: 'NEUTRAL', points: 0, label: 'Insufficient data for RSI' }
  }

  // 2. MACD vs Signal
  const macdVal   = lastValid(macd.macdLine)
  const signalVal = lastValid(macd.signalLine)
  if (macdVal !== null && signalVal !== null) {
    const pts = macdVal > signalVal ? 1 : -1
    rawScore += pts
    details.macd = {
      value: parseFloat((macdVal - signalVal).toFixed(4)),
      signal: pts > 0 ? 'BULL' : 'BEAR',
      points: pts,
      label: pts > 0
        ? `MACD (${macdVal.toFixed(3)}) above signal (${signalVal.toFixed(3)})`
        : `MACD (${macdVal.toFixed(3)}) below signal (${signalVal.toFixed(3)})`,
    }
  } else {
    details.macd = { value: null, signal: 'NEUTRAL', points: 0, label: 'Insufficient data for MACD' }
  }

  // 3. ADX — confirms or weakens existing trend direction
  const adxVal   = lastValid(adxData.adx)
  const plusDI   = lastValid(adxData.plusDI)
  const minusDI  = lastValid(adxData.minusDI)
  if (adxVal !== null && plusDI !== null && minusDI !== null) {
    // Strong trend: follow DI direction; weak: neutral
    const trending = adxVal > 25
    const pts = !trending ? 0 : plusDI > minusDI ? 1 : -1
    rawScore += pts
    details.adx14 = {
      value: adxVal,
      signal: pts > 0 ? 'BULL' : pts < 0 ? 'BEAR' : 'NEUTRAL',
      points: pts,
      label: adxVal > 25
        ? `ADX = ${adxVal.toFixed(1)} (strong trend) — ${plusDI > minusDI ? '+DI dominant (bullish)' : '-DI dominant (bearish)'}`
        : `ADX = ${adxVal.toFixed(1)} (weak trend / sideways)`,
    }
  } else {
    details.adx14 = { value: null, signal: 'NEUTRAL', points: 0, label: 'Insufficient data for ADX' }
  }

  const score = rawScore * WEIGHTS.momentum * (10 / MAX_RAW.momentum)
  return { score: parseFloat(score.toFixed(3)), rawScore, maxRaw: MAX_RAW.momentum, details }
}

// ---------------------------------------------------------------------------
// VOLATILITY group  (max raw ±2)
// ---------------------------------------------------------------------------
async function scoreVolatility(
  prices: OHLCV[],
  market: string
): Promise<IndicatorGroupResult> {
  const details: Record<string, IndicatorDetail> = {}
  let rawScore = 0

  // 1. VIX (US only; for BIST we use ATR% as substitute)
  if (market === 'US') {
    try {
      const endDate = new Date()
      const startDate = new Date()
      startDate.setDate(startDate.getDate() - 10)
      const vixPrices = await dataService.fetchStockPrice('^VIX', startDate, endDate, '1d')
      const vix = vixPrices[vixPrices.length - 1]?.close ?? null

      if (vix !== null) {
        const pts = vix < 15 ? 1 : vix > 25 ? -1 : 0
        rawScore += pts
        details.vix = {
          value: vix,
          signal: pts > 0 ? 'BULL' : pts < 0 ? 'BEAR' : 'NEUTRAL',
          points: pts,
          label: `VIX = ${vix.toFixed(2)} — ${vix < 15 ? 'low fear (bullish)' : vix > 25 ? 'high fear (bearish)' : 'neutral range 15-25'}`,
        }
      }
    } catch {
      details.vix = { value: null, signal: 'NEUTRAL', points: 0, label: 'VIX data unavailable' }
    }
  } else {
    details.vix = { value: null, signal: 'NEUTRAL', points: 0, label: 'VIX not applicable for BIST' }
  }

  // 2. ATR% (ATR as % of price — low = sideways, high = trending)
  const atrArr = calculateATR(prices, 14)
  const atr    = lastValid(atrArr)
  const close  = prices[prices.length - 1]?.close ?? 0
  if (atr !== null && close > 0) {
    const atrPct = (atr / close) * 100
    // ATR% < 1.5% → sideways (negative for trending signal); ATR% > 3% → strong move
    const pts = atrPct < 1.5 ? -1 : atrPct > 3.0 ? 1 : 0
    rawScore += pts
    details.atrPct = {
      value: parseFloat(atrPct.toFixed(2)),
      signal: pts > 0 ? 'BULL' : pts < 0 ? 'BEAR' : 'NEUTRAL',
      points: pts,
      label: `ATR(14) = ${atrPct.toFixed(2)}% of price — ${atrPct < 1.5 ? 'low volatility / sideways' : atrPct > 3.0 ? 'high volatility / trending' : 'moderate volatility'}`,
    }
  } else {
    details.atrPct = { value: null, signal: 'NEUTRAL', points: 0, label: 'Insufficient data for ATR' }
  }

  const score = rawScore * WEIGHTS.volatility * (10 / MAX_RAW.volatility)
  return { score: parseFloat(score.toFixed(3)), rawScore, maxRaw: MAX_RAW.volatility, details }
}

// ---------------------------------------------------------------------------
// BREADTH group  (max raw ±3)
// ---------------------------------------------------------------------------
async function scoreBreadth(
  breadth: BreadthData | null
): Promise<IndicatorGroupResult> {
  const details: Record<string, IndicatorDetail> = {}
  let rawScore = 0

  if (!breadth) {
    return {
      score: 0,
      rawScore: 0,
      maxRaw: MAX_RAW.breadth,
      details: { breadth: { value: null, signal: 'NEUTRAL', points: 0, label: 'Breadth data unavailable' } },
    }
  }

  // 1. Advance / Decline ratio
  const adRatio = breadth.advanceDeclineRatio
  const adPts = adRatio >= 1.5 ? 1 : adRatio <= 0.67 ? -1 : 0
  rawScore += adPts
  details.advanceDecline = {
    value: parseFloat(adRatio.toFixed(2)),
    signal: adPts > 0 ? 'BULL' : adPts < 0 ? 'BEAR' : 'NEUTRAL',
    points: adPts,
    label: `A/D ratio = ${adRatio.toFixed(2)} (${breadth.advancingStocks} up / ${breadth.decliningStocks} down)`,
  }

  // 2. % of stocks above 200 SMA
  const pct = breadth.pctAbove200SMA
  const pctPts = pct >= 60 ? 1 : pct <= 35 ? -1 : 0
  rawScore += pctPts
  details.pctAbove200SMA = {
    value: parseFloat(pct.toFixed(1)),
    signal: pctPts > 0 ? 'BULL' : pctPts < 0 ? 'BEAR' : 'NEUTRAL',
    points: pctPts,
    label: `${pct.toFixed(1)}% of stocks above 200 SMA`,
  }

  // 3. New Highs vs New Lows
  const hlRatio = breadth.newHighLowRatio
  const hlPts = hlRatio >= 2 ? 1 : hlRatio <= 0.5 ? -1 : 0
  rawScore += hlPts
  details.newHighLow = {
    value: parseFloat(hlRatio.toFixed(2)),
    signal: hlPts > 0 ? 'BULL' : hlPts < 0 ? 'BEAR' : 'NEUTRAL',
    points: hlPts,
    label: `${breadth.newHighs} new highs vs ${breadth.newLows} new lows (ratio ${hlRatio.toFixed(2)})`,
  }

  const score = rawScore * WEIGHTS.breadth * (10 / MAX_RAW.breadth)
  return { score: parseFloat(score.toFixed(3)), rawScore, maxRaw: MAX_RAW.breadth, details }
}

// ---------------------------------------------------------------------------
// Confidence: % of indicators that agree with the final condition
// ---------------------------------------------------------------------------
function calculateConfidence(
  groups: MarketConditionResult['indicators'],
  condition: MarketCondition
): number {
  const allDetails: IndicatorDetail[] = [
    ...Object.values(groups.trend.details),
    ...Object.values(groups.momentum.details),
    ...Object.values(groups.volatility.details),
    ...Object.values(groups.breadth.details),
  ].filter((d) => d.value !== null || d.points !== 0)

  if (allDetails.length === 0) return 50

  const agreeing = allDetails.filter((d) => {
    if (condition === 'BULL') return d.signal === 'BULL'
    if (condition === 'BEAR') return d.signal === 'BEAR'
    return d.signal === 'NEUTRAL'
  }).length

  // Base confidence + bonus for agreement strength
  const basePct = (agreeing / allDetails.length) * 100

  // Boost/dampen by score magnitude
  return Math.min(100, Math.max(0, Math.round(basePct)))
}

// ---------------------------------------------------------------------------
// Criteria recommendation based on condition
// ---------------------------------------------------------------------------
function recommendCriteria(condition: MarketCondition): RecommendedCriteria {
  switch (condition) {
    case 'BULL':     return 'ALFA'   // Momentum / breakout strategy
    case 'SIDEWAYS': return 'BETA'   // Mean-reversion / range strategy
    case 'BEAR':     return 'DELTA'  // Defensive / short strategy
  }
}

// ---------------------------------------------------------------------------
// Core analysis function
// ---------------------------------------------------------------------------
async function analyzeMarketCondition(
  market: string,
  date: Date
): Promise<MarketConditionResult> {
  const indexSymbol = INDEX_SYMBOL[market] ?? INDEX_SYMBOL['US']

  // Fetch ~14 months of data so all indicators (SMA200, ADX, etc.) have enough history
  const endDate = new Date(date)
  const startDate = new Date(date)
  startDate.setDate(startDate.getDate() - 430)

  const [prices, breadthData] = await Promise.all([
    dataService.fetchStockPrice(indexSymbol, startDate, endDate, '1d').catch(() => [] as OHLCV[]),
    dataService.getMarketBreadth(market as 'BIST' | 'US').catch(() => null),
  ])

  if (prices.length < 30) {
    // Not enough data — return neutral
    const neutral: IndicatorGroupResult = {
      score: 0, rawScore: 0, maxRaw: 0,
      details: { error: { value: null, signal: 'NEUTRAL', points: 0, label: 'Insufficient price data' } },
    }
    return {
      condition: 'SIDEWAYS',
      score: 0,
      confidence: 0,
      indicators: { trend: neutral, momentum: neutral, volatility: neutral, breadth: neutral },
      recommendedCriteria: 'BETA',
      date,
      market,
    }
  }

  // Score all four groups in parallel
  const [trendGroup, momentumGroup, volatilityGroup, breadthGroup] = await Promise.all([
    Promise.resolve(scoreTrend(prices)),
    Promise.resolve(scoreMomentum(prices)),
    scoreVolatility(prices, market),
    scoreBreadth(breadthData),
  ])

  const totalScore = parseFloat(
    (trendGroup.score + momentumGroup.score + volatilityGroup.score + breadthGroup.score).toFixed(2)
  )

  const condition: MarketCondition =
    totalScore > 3 ? 'BULL' : totalScore < -3 ? 'BEAR' : 'SIDEWAYS'

  const indicators = {
    trend:      trendGroup,
    momentum:   momentumGroup,
    volatility: volatilityGroup,
    breadth:    breadthGroup,
  }

  const confidence = calculateConfidence(indicators, condition)

  return {
    condition,
    score: totalScore,
    confidence,
    indicators,
    recommendedCriteria: recommendCriteria(condition),
    date,
    market,
  }
}

// ---------------------------------------------------------------------------
// Public API functions
// ---------------------------------------------------------------------------

export async function getCurrentMarketCondition(
  market: string
): Promise<MarketConditionResult> {
  return analyzeMarketCondition(market, new Date())
}

export async function getHistoricalMarketConditions(
  market: string,
  startDate: Date,
  endDate: Date
): Promise<MarketConditionResult[]> {
  const results: MarketConditionResult[] = []
  const cursor = new Date(startDate)
  const end    = new Date(endDate)

  // Step weekly (daily would be too many API calls)
  while (cursor <= end) {
    // Skip weekends
    const dow = cursor.getDay()
    if (dow !== 0 && dow !== 6) {
      try {
        const result = await analyzeMarketCondition(market, new Date(cursor))
        results.push(result)
      } catch {
        // skip failed dates
      }
    }
    cursor.setDate(cursor.getDate() + 7)
  }

  return results
}

export async function saveMarketCondition(
  result: MarketConditionResult
): Promise<void> {
  const dayStart = new Date(result.date)
  dayStart.setHours(0, 0, 0, 0)

  await prisma.marketCondition.upsert({
    where: { date: dayStart },
    create: {
      date:        dayStart,
      market:      result.market,
      condition:   result.condition,
      confidence:  result.confidence,
      indicators:  result.indicators as object,
      sp500Trend:  result.market === 'US'   ? result.condition : undefined,
      bistTrend:   result.market === 'BIST' ? result.condition : undefined,
    },
    update: {
      condition:  result.condition,
      confidence: result.confidence,
      indicators: result.indicators as object,
      sp500Trend: result.market === 'US'   ? result.condition : undefined,
      bistTrend:  result.market === 'BIST' ? result.condition : undefined,
    },
  })
}

export { analyzeMarketCondition }
