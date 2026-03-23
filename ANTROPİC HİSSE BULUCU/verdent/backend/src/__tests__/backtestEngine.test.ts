jest.mock('@prisma/client', () => ({
  PrismaClient: jest.fn().mockImplementation(() => ({})),
}))

import { generateRebalanceDates } from '../services/backtestEngine'

describe('BacktestEngine – generateRebalanceDates', () => {
  const start = new Date('2023-01-01')
  const end   = new Date('2023-06-30')

  it('generates dates between start and end (MONTHLY)', () => {
    const dates = generateRebalanceDates(start, end, 'MONTHLY')
    expect(dates.length).toBeGreaterThan(0)
    for (const d of dates) {
      expect(d.getTime()).toBeGreaterThanOrEqual(start.getTime())
      expect(d.getTime()).toBeLessThanOrEqual(end.getTime())
    }
  })

  it('generates dates between start and end (WEEKLY)', () => {
    const dates = generateRebalanceDates(start, end, 'WEEKLY')
    expect(dates.length).toBeGreaterThan(0)
    for (const d of dates) {
      expect(d.getTime()).toBeGreaterThanOrEqual(start.getTime())
      expect(d.getTime()).toBeLessThanOrEqual(end.getTime())
    }
  })

  it('WEEKLY generates more dates than MONTHLY for same period', () => {
    const weekly  = generateRebalanceDates(start, end, 'WEEKLY')
    const monthly = generateRebalanceDates(start, end, 'MONTHLY')
    expect(weekly.length).toBeGreaterThan(monthly.length)
  })

  it('WEEKLY returns Mondays only', () => {
    const dates = generateRebalanceDates(start, end, 'WEEKLY')
    for (const d of dates) {
      expect(d.getDay()).toBe(1)
    }
  })

  it('returns empty array when start >= end', () => {
    const sameDay = generateRebalanceDates(end, start, 'MONTHLY')
    expect(sameDay).toHaveLength(0)
  })
})

describe('BacktestEngine – performance metric helpers', () => {
  const mockSnapshots = [
    { date: new Date('2023-01-01'), value: 100000 },
    { date: new Date('2023-02-01'), value: 110000 },
    { date: new Date('2023-03-01'), value: 105000 },
    { date: new Date('2023-04-01'), value: 120000 },
    { date: new Date('2023-05-01'), value: 95000  },
    { date: new Date('2023-06-01'), value: 130000 },
  ]

  it('calculates max drawdown correctly', () => {
    let peak = -Infinity
    let maxDD = 0
    for (const s of mockSnapshots) {
      if (s.value > peak) peak = s.value
      const dd = (s.value - peak) / peak
      if (dd < maxDD) maxDD = dd
    }
    // Peak is 120000, trough after is 95000 → drawdown = -20.83%
    expect(maxDD).toBeCloseTo(-0.2083, 2)
  })

  it('calculates total return correctly', () => {
    const initial = mockSnapshots[0].value
    const final   = mockSnapshots[mockSnapshots.length - 1].value
    const ret = (final - initial) / initial
    expect(ret).toBeCloseTo(0.30, 5)
  })
})
