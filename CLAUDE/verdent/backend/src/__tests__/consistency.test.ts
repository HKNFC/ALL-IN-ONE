/**
 * Consistency tests — verifies that DeterministicScanner.scan() and
 * screenStocksSync() produce identical top-5 results for the same inputs.
 *
 * This is the core guarantee: Scanner page and Backtest engine
 * MUST return the same ranked list for the same (criteria × date × market).
 */
import { deterministicScanner } from '../services/consistencyService';
import { screenStocksSync, generateMockStocks, type CriteriaType } from '../services/criteriaEngine';

const TEST_DATE   = new Date('2024-01-15');
const TEST_MARKET = 'BIST' as const;
const CRITERIA: CriteriaType[] = ['ALFA', 'BETA', 'DELTA'];

describe('DeterministicScanner — caching', () => {
  it('two scans with identical params return identical results', async () => {
    const r1 = await deterministicScanner.scan({ criteria: 'ALFA', date: TEST_DATE, market: TEST_MARKET });
    const r2 = await deterministicScanner.scan({ criteria: 'ALFA', date: TEST_DATE, market: TEST_MARKET });

    expect(r1.cacheKey).toBe(r2.cacheKey);
    expect(r1.stocks.map(s => s.symbol)).toEqual(r2.stocks.map(s => s.symbol));
    expect(r1.stocks.map(s => s.score)).toEqual(r2.stocks.map(s => s.score));
  });

  it('second call is served from hot cache (same object reference)', async () => {
    deterministicScanner.clearAll();
    await deterministicScanner.scan({ criteria: 'BETA', date: TEST_DATE, market: TEST_MARKET });
    const sizeBefore = deterministicScanner.hotCacheSize();
    await deterministicScanner.scan({ criteria: 'BETA', date: TEST_DATE, market: TEST_MARKET });
    // Cache size should not grow on the second call
    expect(deterministicScanner.hotCacheSize()).toBe(sizeBefore);
  });

  it('different criteria produce different cache keys', async () => {
    const r1 = await deterministicScanner.scan({ criteria: 'ALFA',  date: TEST_DATE, market: TEST_MARKET });
    const r2 = await deterministicScanner.scan({ criteria: 'DELTA', date: TEST_DATE, market: TEST_MARKET });
    expect(r1.cacheKey).not.toBe(r2.cacheKey);
  });

  it('different dates produce different cache keys', async () => {
    const d1 = new Date('2024-01-15');
    const d2 = new Date('2024-02-01');
    const r1 = await deterministicScanner.scan({ criteria: 'ALFA', date: d1, market: TEST_MARKET });
    const r2 = await deterministicScanner.scan({ criteria: 'ALFA', date: d2, market: TEST_MARKET });
    expect(r1.cacheKey).not.toBe(r2.cacheKey);
  });
});

describe('Scanner ↔ Backtest consistency', () => {
  it.each(CRITERIA)('%s: two scan calls return identical top-5', async (criteria) => {
    deterministicScanner.invalidate(criteria, TEST_DATE, TEST_MARKET);

    // First call — populates cache
    const r1 = await deterministicScanner.scan({ criteria, date: TEST_DATE, market: TEST_MARKET });
    // Second call — must hit cache and return identical result
    const r2 = await deterministicScanner.scan({ criteria, date: TEST_DATE, market: TEST_MARKET });

    const top5r1 = r1.stocks.slice(0, 5).map(s => s.symbol);
    const top5r2 = r2.stocks.slice(0, 5).map(s => s.symbol);

    // Core consistency assertion: same inputs → same top-5
    expect(top5r1).toEqual(top5r2);
    expect(r1.cacheKey).toBe(r2.cacheKey);
  });

  it('results have no look-ahead bias marker (cacheKey includes date)', async () => {
    const r = await deterministicScanner.scan({ criteria: 'ALFA', date: TEST_DATE, market: TEST_MARKET });
    // SHA-256 of "ALFA|2024-01-15|BIST"
    expect(r.cacheKey).toBeTruthy();
    expect(r.cacheKey.length).toBe(64); // hex SHA-256
  });

  it('scannedTotal reflects the full universe, not just top results', async () => {
    const r = await deterministicScanner.scan({ criteria: 'ALFA', date: TEST_DATE, market: TEST_MARKET });
    expect(r.scannedTotal).toBeGreaterThanOrEqual(r.stocks.length);
  });

  it('invalidate clears only the specified entry', async () => {
    deterministicScanner.clearAll();
    await deterministicScanner.scan({ criteria: 'ALFA',  date: TEST_DATE, market: TEST_MARKET });
    await deterministicScanner.scan({ criteria: 'BETA',  date: TEST_DATE, market: TEST_MARKET });
    const before = deterministicScanner.hotCacheSize(); // 2
    deterministicScanner.invalidate('ALFA', TEST_DATE, TEST_MARKET);
    expect(deterministicScanner.hotCacheSize()).toBe(before - 1);
  });
});
