/**
 * Unit tests — criteriaEngine
 * Tests ALFA / BETA / DELTA scoring logic and filter application.
 */
import {
  screenStocksSync,
  generateMockStocks,
  type CriteriaType,
  type ScoredStock,
} from '../services/criteriaEngine';

// ── Helpers ──────────────────────────────────────────────────────────────────

function makeStock(overrides: Record<string, unknown> = {}) {
  const base = generateMockStocks(1, 'BIST')[0];
  return { ...base, ...overrides };
}

// ── screenStocksSync ──────────────────────────────────────────────────────────

describe('screenStocksSync', () => {
  const criteria: CriteriaType[] = ['ALFA', 'BETA', 'DELTA'];

  it.each(criteria)('%s: returns an array', (c) => {
    const stocks = generateMockStocks(20, 'BIST');
    const result = screenStocksSync(stocks, c);
    expect(Array.isArray(result)).toBe(true);
  });

  it.each(criteria)('%s: scores are in [0, 100]', (c) => {
    const stocks = generateMockStocks(30, 'BIST');
    const result = screenStocksSync(stocks, c);
    result.forEach(s => {
      expect(s.score).toBeGreaterThanOrEqual(0);
      expect(s.score).toBeLessThanOrEqual(100);
    });
  });

  it.each(criteria)('%s: results are sorted descending by score', (c) => {
    const stocks = generateMockStocks(40, 'BIST');
    const result = screenStocksSync(stocks, c);
    for (let i = 1; i < result.length; i++) {
      expect(result[i - 1].score).toBeGreaterThanOrEqual(result[i].score);
    }
  });

  it.each(criteria)('%s: rank field is sequential starting at 1', (c) => {
    const stocks = generateMockStocks(15, 'BIST');
    const result = screenStocksSync(stocks, c);
    result.forEach((s, i) => {
      expect(s.rank).toBe(i + 1);
    });
  });

  it('returns empty array for empty input', () => {
    expect(screenStocksSync([], 'ALFA')).toEqual([]);
  });

  it('each result has required fields', () => {
    const stocks = generateMockStocks(10, 'US');
    const result = screenStocksSync(stocks, 'ALFA');
    result.forEach((s: ScoredStock) => {
      expect(typeof s.symbol).toBe('string');
      expect(typeof s.score).toBe('number');
      expect(typeof s.rank).toBe('number');
      expect(typeof s.entryPrice).toBe('number');
      expect(s.signals).toBeDefined();
    });
  });

  it('US market returns results', () => {
    const stocks = generateMockStocks(50, 'US');
    const result = screenStocksSync(stocks, 'ALFA');
    expect(result.length).toBeGreaterThan(0);
  });
});

// ── Score determinism ─────────────────────────────────────────────────────────

describe('Score determinism', () => {
  it('same stock + same criteria always returns same score', () => {
    const stocks = generateMockStocks(5, 'BIST');
    const run1 = screenStocksSync(stocks, 'ALFA');
    const run2 = screenStocksSync(stocks, 'ALFA');
    run1.forEach((s, i) => {
      expect(s.score).toBe(run2[i].score);
    });
  });

  it('different criteria produce different ordering for same stock set', () => {
    const stocks = generateMockStocks(20, 'BIST');
    const alfa  = screenStocksSync(stocks, 'ALFA').map(s => s.symbol).join(',');
    const beta  = screenStocksSync(stocks, 'BETA').map(s => s.symbol).join(',');
    const delta = screenStocksSync(stocks, 'DELTA').map(s => s.symbol).join(',');
    // At least one pair must differ (criteria have different weights)
    const allSame = alfa === beta && beta === delta;
    expect(allSame).toBe(false);
  });
});

// ── Entry / Stop / Target ─────────────────────────────────────────────────────

describe('Trade levels', () => {
  it.each(['ALFA','BETA','DELTA'] as CriteriaType[])('%s: stopLoss < entryPrice', (c) => {
    const stocks = generateMockStocks(10, 'BIST');
    const result = screenStocksSync(stocks, c);
    result.forEach(s => {
      expect(s.suggestedStopLoss).toBeLessThan(s.entryPrice);
    });
  });

  it.each(['ALFA','BETA','DELTA'] as CriteriaType[])('%s: targetPrice > entryPrice', (c) => {
    const stocks = generateMockStocks(10, 'BIST');
    const result = screenStocksSync(stocks, c);
    result.forEach(s => {
      expect(s.targetPrice).toBeGreaterThan(s.entryPrice);
    });
  });

  it('risk-reward ratio is positive', () => {
    const stocks = generateMockStocks(10, 'BIST');
    const result = screenStocksSync(stocks, 'ALFA');
    result.forEach(s => {
      expect(s.riskRewardRatio).toBeGreaterThan(0);
    });
  });
});
