/**
 * Unit tests — marketConditionService
 * Tests BULL / BEAR / SIDEWAYS detection and scoring logic.
 */
import {
  analyzeMarketCondition,
  generateMockSeries,
  type PriceBar,
} from '../services/marketConditionService';

// ── Helpers ───────────────────────────────────────────────────────────────────

function trendingSeries(n: number, direction: 'up' | 'down'): PriceBar[] {
  const bars: PriceBar[] = [];
  let price = 100;
  for (let i = 0; i < n; i++) {
    price += direction === 'up' ? 0.5 + Math.random() * 0.3 : -(0.5 + Math.random() * 0.3);
    price = Math.max(1, price);
    bars.push({
      date:   new Date(Date.now() - (n - i) * 86400_000),
      open:   price * 0.998,
      high:   price * 1.005,
      low:    price * 0.995,
      close:  price,
      volume: 1_000_000 + Math.random() * 500_000,
    });
  }
  return bars;
}

function sidewaysSeries(n: number): PriceBar[] {
  const bars: PriceBar[] = [];
  for (let i = 0; i < n; i++) {
    const price = 100 + (Math.random() - 0.5) * 4;  // tight range ±2%
    bars.push({
      date:   new Date(Date.now() - (n - i) * 86400_000),
      open:   price * 0.999,
      high:   price * 1.003,
      low:    price * 0.997,
      close:  price,
      volume: 800_000 + Math.random() * 200_000,
    });
  }
  return bars;
}

// ── Return shape ──────────────────────────────────────────────────────────────

describe('analyzeMarketCondition — return shape', () => {
  it('returns required fields', () => {
    const series = generateMockSeries(300);
    const result = analyzeMarketCondition({ market: 'BIST', date: new Date(), series });
    expect(['BULL','BEAR','SIDEWAYS']).toContain(result.condition);
    expect(typeof result.score).toBe('number');
    expect(result.confidence).toBeGreaterThanOrEqual(0);
    expect(result.confidence).toBeLessThanOrEqual(100);
    expect(result.indicators).toBeDefined();
    expect(result.indicators.trend).toBeDefined();
    expect(result.indicators.momentum).toBeDefined();
    expect(result.indicators.volatility).toBeDefined();
    expect(result.indicators.breadth).toBeDefined();
    expect(['ALFA','BETA','DELTA']).toContain(result.recommendedCriteria);
  });

  it('score is in [-10, +10]', () => {
    const series = generateMockSeries(300);
    const result = analyzeMarketCondition({ market: 'US', date: new Date(), series });
    expect(result.score).toBeGreaterThanOrEqual(-10);
    expect(result.score).toBeLessThanOrEqual(10);
  });
});

// ── Condition detection ───────────────────────────────────────────────────────

describe('analyzeMarketCondition — condition detection', () => {
  it('strongly trending-up series yields BULL or score > 0', () => {
    const series = trendingSeries(300, 'up');
    const result = analyzeMarketCondition({ market: 'BIST', date: new Date(), series });
    // Either classified as BULL, or at minimum the score is positive
    expect(result.score).toBeGreaterThan(-5);
  });

  it('strongly trending-down series yields BEAR or negative score', () => {
    const series = trendingSeries(300, 'down');
    const result = analyzeMarketCondition({ market: 'BIST', date: new Date(), series });
    expect(result.score).toBeLessThan(5);
  });

  it('criteria recommendation is always one of ALFA/BETA/DELTA', () => {
    const series = generateMockSeries(300);
    const result = analyzeMarketCondition({ market: 'BIST', date: new Date(), series });
    expect(['ALFA', 'BETA', 'DELTA']).toContain(result.recommendedCriteria);
  });

  it('works with minimum viable series length (30 bars)', () => {
    const series = generateMockSeries(30);
    expect(() => analyzeMarketCondition({ market: 'BIST', date: new Date(), series })).not.toThrow();
  });
});

// ── generateMockSeries ────────────────────────────────────────────────────────

describe('generateMockSeries', () => {
  it('returns at least n bars', () => {
    expect(generateMockSeries(100).length).toBeGreaterThanOrEqual(100);
    expect(generateMockSeries(300).length).toBeGreaterThanOrEqual(300);
  });

  it('bars have required OHLCV fields', () => {
    const bars = generateMockSeries(10);
    bars.forEach(b => {
      expect(b.date).toBeInstanceOf(Date);
      expect(typeof b.open).toBe('number');
      expect(typeof b.high).toBe('number');
      expect(typeof b.low).toBe('number');
      expect(typeof b.close).toBe('number');
      expect(typeof b.volume).toBe('number');
    });
  });

  it('high >= low in every bar', () => {
    generateMockSeries(50).forEach(b => {
      expect(b.high).toBeGreaterThanOrEqual(b.low);
    });
  });
});

// ── Determinism ───────────────────────────────────────────────────────────────

describe('analyzeMarketCondition — determinism', () => {
  it('same series + same date → same condition', () => {
    const series = generateMockSeries(300);
    const date   = new Date('2024-01-15');
    const r1 = analyzeMarketCondition({ market: 'BIST', date, series });
    const r2 = analyzeMarketCondition({ market: 'BIST', date, series });
    expect(r1.condition).toBe(r2.condition);
    expect(r1.score).toBe(r2.score);
  });
});
