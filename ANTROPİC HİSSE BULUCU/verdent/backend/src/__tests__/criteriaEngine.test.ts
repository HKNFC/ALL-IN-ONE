jest.mock('@prisma/client', () => ({
  PrismaClient: jest.fn().mockImplementation(() => ({})),
}))

import { applyFilters, rankStocks } from '../services/criteriaEngine'
import type { ScoredStock, FilterRule, StockData } from '../types/market'

describe('CriteriaEngine – applyFilters', () => {
  it('returns empty array when no stocks passed', () => {
    const result = applyFilters([], [])
    expect(result).toEqual([])
  })

  it('returns empty array when filter array is empty (0/0 = NaN < 0.5)', () => {
    const stocks = [{ symbol: 'A' }, { symbol: 'B' }] as unknown as StockData[]
    const result = applyFilters(stocks, [])
    expect(result).toHaveLength(0)
  })

  it('filters out stocks that fail every filter', () => {
    const failingFilter: FilterRule = {
      name: 'failTest', weight: 10,
      check: () => ({ passed: false, value: 0, description: 'always fail' }),
    }
    const stocks = [{ symbol: 'A' }] as unknown as StockData[]
    const result = applyFilters(stocks, [failingFilter])
    expect(result).toHaveLength(0)
  })

  it('passes stocks that meet >= 50% of filter weight', () => {
    const passingFilter: FilterRule = {
      name: 'passTest', weight: 10,
      check: () => ({ passed: true, value: 100, description: 'always pass' }),
    }
    const stocks = [{ symbol: 'A' }] as unknown as StockData[]
    const result = applyFilters(stocks, [passingFilter])
    expect(result).toHaveLength(1)
  })

  it('passes stocks with majority weight passing (mixed filters)', () => {
    const filters: FilterRule[] = [
      { name: 'f1', weight: 60, check: () => ({ passed: true,  value: 1, description: '' }) },
      { name: 'f2', weight: 40, check: () => ({ passed: false, value: 0, description: '' }) },
    ]
    const stocks = [{ symbol: 'A' }] as unknown as StockData[]
    const result = applyFilters(stocks, filters)
    expect(result).toHaveLength(1) // 60% passes >= 50%
  })

  it('rejects stocks where majority weight fails', () => {
    const filters: FilterRule[] = [
      { name: 'f1', weight: 40, check: () => ({ passed: true,  value: 1, description: '' }) },
      { name: 'f2', weight: 60, check: () => ({ passed: false, value: 0, description: '' }) },
    ]
    const stocks = [{ symbol: 'A' }] as unknown as StockData[]
    const result = applyFilters(stocks, filters)
    expect(result).toHaveLength(0) // only 40% passes < 50%
  })
})

describe('CriteriaEngine – rankStocks', () => {
  const makeStock = (symbol: string, score: number): ScoredStock => ({
    symbol, name: symbol, score, rank: 0,
    signals: { technical: [], fundamental: [], passed: [], failed: [] },
    entryPrice: 0, suggestedStopLoss: 0, targetPrice: 0, riskRewardRatio: 0,
  })

  it('ranks stocks by score descending', () => {
    const stocks = [makeStock('A', 70), makeStock('B', 90), makeStock('C', 50)]
    const ranked = rankStocks(stocks)
    expect(ranked[0].symbol).toBe('B')
    expect(ranked[1].symbol).toBe('A')
    expect(ranked[2].symbol).toBe('C')
  })

  it('assigns rank starting at 1', () => {
    const stocks = [makeStock('A', 80), makeStock('B', 60)]
    const ranked = rankStocks(stocks)
    expect(ranked[0].rank).toBe(1)
    expect(ranked[1].rank).toBe(2)
  })

  it('handles empty array', () => {
    expect(rankStocks([])).toEqual([])
  })

  it('does not mutate the original array', () => {
    const stocks = [makeStock('A', 50), makeStock('B', 90)]
    const original = [...stocks]
    rankStocks(stocks)
    expect(stocks[0].symbol).toBe(original[0].symbol)
  })

  it('handles single stock', () => {
    const stocks = [makeStock('ONLY', 75)]
    const ranked = rankStocks(stocks)
    expect(ranked).toHaveLength(1)
    expect(ranked[0].rank).toBe(1)
  })
})
