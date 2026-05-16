/**
 * Unit tests — backtestEngine
 * Tests metrics calculations, rebalance date generation, and result shape.
 */
import {
  BacktestEngine,
  generateRebalanceDates,
  type BacktestConfig,
} from '../services/backtestEngine';

// ── generateRebalanceDates ────────────────────────────────────────────────────

describe('generateRebalanceDates', () => {
  const start = new Date('2023-01-01');
  const end   = new Date('2023-12-31');

  it('MONTHLY: first date is on or after startDate', () => {
    const dates = generateRebalanceDates(start, end, 'MONTHLY');
    expect(dates.length).toBeGreaterThan(0);
    expect(dates[0] >= start).toBe(true);
  });

  it('MONTHLY: produces ~12 dates for a full year', () => {
    const dates = generateRebalanceDates(start, end, 'MONTHLY');
    expect(dates.length).toBeGreaterThanOrEqual(11);
    expect(dates.length).toBeLessThanOrEqual(13);
  });

  it('WEEKLY: produces ~52 dates for a full year', () => {
    const dates = generateRebalanceDates(start, end, 'WEEKLY');
    expect(dates.length).toBeGreaterThanOrEqual(50);
    expect(dates.length).toBeLessThanOrEqual(54);
  });

  it('WEEKLY: all dates are Mondays (day === 1)', () => {
    const dates = generateRebalanceDates(start, end, 'WEEKLY');
    dates.forEach(d => {
      expect(d.getDay()).toBe(1);
    });
  });

  it('dates are in ascending order', () => {
    const dates = generateRebalanceDates(start, end, 'MONTHLY');
    for (let i = 1; i < dates.length; i++) {
      expect(dates[i].getTime()).toBeGreaterThan(dates[i - 1].getTime());
    }
  });

  it('returns empty array when start === end', () => {
    const same = new Date('2023-06-01');
    expect(generateRebalanceDates(same, same, 'MONTHLY')).toHaveLength(0);
  });
});

// ── BacktestEngine.runBacktest ────────────────────────────────────────────────

const SHORT_CONFIG: BacktestConfig = {
  name:            'Test ALFA 3M',
  criteriaType:    'ALFA',
  startDate:       new Date('2023-01-01'),
  endDate:         new Date('2023-04-01'),
  rebalancePeriod: 'MONTHLY',
  market:          'BIST',
  initialCapital:  100_000,
  transactionCost: 0.001,
  slippage:        0.001,
};

describe('BacktestEngine.runBacktest', () => {
  let engine: BacktestEngine;
  beforeAll(() => { engine = new BacktestEngine(); });

  it('returns a result object without throwing', async () => {
    const result = await engine.runBacktest(SHORT_CONFIG);
    expect(result).toBeDefined();
  }, 30_000);

  it('result has required top-level fields', async () => {
    const result = await engine.runBacktest(SHORT_CONFIG);
    expect(typeof result.id).toBe('string');
    expect(result.config).toBeDefined();
    expect(result.performance).toBeDefined();
    expect(Array.isArray(result.portfolioHistory)).toBe(true);
    expect(Array.isArray(result.trades)).toBe(true);
  }, 30_000);

  it('performance metrics are finite numbers', async () => {
    const result = await engine.runBacktest(SHORT_CONFIG);
    const m = result.performance;
    [m.totalReturn, m.annualizedReturn, m.maxDrawdown, m.sharpeRatio, m.winRate].forEach(v => {
      expect(Number.isFinite(v)).toBe(true);
    });
  }, 30_000);

  it('maxDrawdown is a finite number (absolute or negative convention)', async () => {
    const result = await engine.runBacktest(SHORT_CONFIG);
    expect(Number.isFinite(result.performance.maxDrawdown)).toBe(true);
    expect(Math.abs(result.performance.maxDrawdown)).toBeLessThanOrEqual(100);
  }, 30_000);

  it('winRate is between 0 and 100', async () => {
    const result = await engine.runBacktest(SHORT_CONFIG);
    expect(result.performance.winRate).toBeGreaterThanOrEqual(0);
    expect(result.performance.winRate).toBeLessThanOrEqual(100);
  }, 30_000);

  it('portfolio history is chronologically ordered', async () => {
    const result = await engine.runBacktest(SHORT_CONFIG);
    for (let i = 1; i < result.portfolioHistory.length; i++) {
      expect(new Date(result.portfolioHistory[i].date).getTime())
        .toBeGreaterThanOrEqual(new Date(result.portfolioHistory[i - 1].date).getTime());
    }
  }, 30_000);

  it('rejects when startDate >= endDate', async () => {
    const bad = { ...SHORT_CONFIG, startDate: new Date('2023-06-01'), endDate: new Date('2023-01-01') };
    await expect(engine.runBacktest(bad)).rejects.toThrow();
  }, 10_000);

  it('calls onProgress with increasing progress', async () => {
    const ticks: number[] = [];
    await engine.runBacktest(SHORT_CONFIG, p => ticks.push(p.progress));
    expect(ticks.length).toBeGreaterThan(0);
    expect(ticks[ticks.length - 1]).toBe(100);
    // Progress should never decrease
    for (let i = 1; i < ticks.length; i++) {
      expect(ticks[i]).toBeGreaterThanOrEqual(ticks[i - 1]);
    }
  }, 30_000);

  it('HYBRID mode completes without error', async () => {
    const hybrid = { ...SHORT_CONFIG, criteriaType: 'HYBRID' as const };
    const result = await engine.runBacktest(hybrid);
    expect(result.performance).toBeDefined();
  }, 30_000);
});
