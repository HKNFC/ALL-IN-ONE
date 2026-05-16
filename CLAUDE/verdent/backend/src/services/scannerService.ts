/**
 * ScannerService — Twelve Data Grown planı ile gerçek veriye dayalı tarama.
 *
 * Akış:
 *  1. Universe'den sembol listesini al (BIST100 | BIST100DISI | BISTTUM | US)
 *  2. Batch quote ile tüm sembollerin anlık fiyatını tek seferde çek
 *  3. Paralel (CONCURRENCY sınırıyla) her sembol için OHLCV + indikatörler
 *  4. criteriaEngine ile skorla
 *  5. Sonuçları sırala ve döndür
 */

import { DataService } from './dataService';
import {
  calculateScore, CRITERIA_CONFIGS,
  type CriteriaType, type StockData,
} from './criteriaEngine';
import {
  getUniverse, type UniverseType, type StockSector,
} from './stockUniverse';

// Grown plan sınırları: burst olmadan güvenli paralel istek sayısı
const CONCURRENCY = 8;

// Minimum bar sayısı — yetersiz geçmiş veri olan hisseler atlanır
const MIN_BARS = 60;

export interface ScanResult {
  symbol:       string;
  name:         string;
  sector:       StockSector;
  price:        number;
  change1d:     number;
  changePct1d:  number;
  volume:       number;
  score:        number;
  signal:       'BUY' | 'WATCH' | 'SELL' | 'NEUTRAL';
  pattern:      string;
  rsi:          number | null;
  adx:          number | null;
  ema50:        number | null;
  ema200:       number | null;
  aboveEma50:   boolean;
  aboveEma200:  boolean;
  distFrom52wHigh: number | null;
  volumeRatio:  number | null;
}

export interface ScanFilters {
  universe?:   UniverseType;     // 'BISTTUM' | 'BIST100' | 'BIST100DISI' | 'US'
  criteria?:   'ALFA' | 'BETA' | 'DELTA' | 'AUTO';
  signal?:     'BUY' | 'WATCH' | 'SELL' | 'ALL';
  sector?:     string;
  minScore?:   number;
  minStrength?: number;          // alias for minScore
  limit?:      number;
}

/** Skor aralığına göre sinyal üret */
function scoreToSignal(score: number): ScanResult['signal'] {
  if (score >= 75) return 'BUY';
  if (score >= 55) return 'WATCH';
  if (score >= 35) return 'SELL';
  return 'NEUTRAL';
}

/** Basit pattern tespiti (OHLCV + indikatörlerden) */
function detectPattern(params: {
  price: number; ema50: number | undefined; ema200: number | undefined;
  rsi: number | undefined; adx: number | undefined;
  bbUpper: number | undefined; bbLower: number | undefined;
}): string {
  const { price, ema50, ema200, rsi, adx, bbUpper, bbLower } = params;

  if (ema50 && ema200 && price > ema50 && ema50 > ema200 && adx && adx > 25)
    return 'Trend Kırılımı';
  if (bbUpper && bbLower && price >= bbUpper * 0.99)
    return 'BB Üst Bant Kırılımı';
  if (rsi && rsi >= 60 && rsi <= 70 && adx && adx > 20)
    return 'Momentum Yükseliş';
  if (rsi && rsi < 35)
    return 'Aşırı Satım Dönüşü';
  if (bbUpper && bbLower && (bbUpper - bbLower) / ((bbUpper + bbLower) / 2) < 0.05)
    return 'Bollinger Sıkışma';
  if (ema50 && Math.abs(price - ema50) / ema50 < 0.015)
    return 'EMA50 Destek';
  if (ema200 && Math.abs(price - ema200) / ema200 < 0.015)
    return 'EMA200 Destek';
  if (adx && adx > 30)
    return 'Güçlü Trend';
  return 'Konsolidasyon';
}

/** Promise concurrency pool */
async function pMap<T, R>(
  items: T[],
  fn: (item: T) => Promise<R>,
  concurrency: number,
): Promise<PromiseSettledResult<R>[]> {
  const results: PromiseSettledResult<R>[] = [];
  let idx = 0;

  async function worker() {
    while (idx < items.length) {
      const i = idx++;
      try {
        results[i] = { status: 'fulfilled', value: await fn(items[i]!) };
      } catch (err) {
        results[i] = { status: 'rejected', reason: err };
      }
    }
  }

  await Promise.all(Array.from({ length: concurrency }, worker));
  return results;
}

export class ScannerService {
  private ds: DataService;

  constructor(dataService?: DataService) {
    this.ds = dataService ?? new DataService();
  }

  async scan(filters: ScanFilters = {}): Promise<ScanResult[]> {
    const universe   = filters.universe  ?? 'BIST100';
    const criteria   = filters.criteria  ?? 'AUTO';
    const minScore   = filters.minScore  ?? filters.minStrength ?? 0;
    const limitCount = filters.limit     ?? 200;
    const market: 'BIST' | 'US' = universe === 'US' ? 'US' : 'BIST';

    const pool    = getUniverse(universe);
    const symbols = pool.map(s => s.symbol);

    console.log(`[Scanner] Tarama başlıyor — ${universe} (${symbols.length} hisse), criteria=${criteria}`);

    // ── 1. Batch anlık fiyat — tek API çağrısı ────────────────────────────────
    let batchQuotes: Record<string, { price: number; change: number; changePct: number; volume: number }> = {};
    try {
      batchQuotes = await this.ds.fetchBatchQuotes(symbols.slice(0, 120), market);
      console.log(`[Scanner] Batch quote: ${Object.keys(batchQuotes).length} sembol`);
    } catch (err) {
      console.warn('[Scanner] Batch quote başarısız, tekil çekime geçiliyor:', (err as Error).message);
    }

    // ── 2. Detaylı analiz — OHLCV + indikatörler ─────────────────────────────
    // Sonuçlarını bekleyen symbol listesi (tümü için değil — limitCount kadar işle)
    const toAnalyze = symbols.slice(0, limitCount);

    const analyzed = await pMap(toAnalyze, async (sym) => {
      const stock = pool.find(s => s.symbol === sym)!;
      const quote = batchQuotes[sym];

      // OHLCV + TD indikatörler paralel
      const end   = new Date();
      const start = new Date(end);
      start.setFullYear(start.getFullYear() - 1);

      const [barsResult, indicResult] = await Promise.allSettled([
        this.ds.fetchStockPrice(sym, start, end, '1d'),
        this.ds.fetchRealIndicators(sym, market),
      ]);

      const bars  = barsResult.status  === 'fulfilled' ? barsResult.value  : [];
      const indic = indicResult.status === 'fulfilled' ? indicResult.value : {};

      if (bars.length < MIN_BARS) return null;  // yetersiz geçmiş

      const lastBar  = bars[bars.length - 1]!;
      const prevBar  = bars[bars.length - 2];
      const price    = quote?.price    ?? lastBar.close;
      const change1d = quote?.change   ?? (prevBar ? lastBar.close - prevBar.close : 0);
      const changePct= quote?.changePct ?? (prevBar ? (change1d / prevBar.close) * 100 : 0);
      const volume   = quote?.volume   ?? lastBar.volume;

      // 52 hafta yüksek/düşük
      const high52w = Math.max(...bars.slice(-252).map(b => b.high));
      const distFrom52wHigh = high52w > 0 ? ((price - high52w) / high52w) * 100 : null;

      // Hacim ortalaması (20 gün)
      const vol20avg = bars.slice(-20).reduce((s, b) => s + b.volume, 0) / 20;
      const volumeRatio = vol20avg > 0 ? volume / vol20avg : null;

      // criteria scoring — StockData tipine uygun nesne oluştur
      const effectiveCriteria: CriteriaType =
        criteria === 'AUTO' ? 'ALFA' : criteria;

      const stockData: StockData = {
        symbol: sym, name: stock.name, sector: stock.sector as StockSector,
        market: market === 'BIST' ? 'BIST' : 'US',
        marketCap: 0,
        date: lastBar.date instanceof Date ? lastBar.date : new Date(lastBar.date),
        open: lastBar.open, high: lastBar.high, low: lastBar.low,
        close: price, volume,
        series: bars.map(b => ({
          date:   b.date instanceof Date ? b.date : new Date(b.date),
          open:   b.open, high: b.high, low: b.low, close: b.close, volume: b.volume,
        })),
        rsi14:    indic.rsi14     ?? null,
        macd:     indic.macd?.macd     ?? null,
        macdSignal: indic.macd?.signal ?? null,
        macdHist: indic.macd?.histogram ?? null,
        ema20:    indic.ema20     ?? null,
        ema50:    indic.ema50     ?? null,
        ema200:   indic.ema200    ?? null,
        atr14:    indic.atr14     ?? null,
        bbUpper:  indic.bollinger?.upper  ?? null,
        bbMiddle: indic.bollinger?.middle ?? null,
        bbLower:  indic.bollinger?.lower  ?? null,
        adx14:    indic.adx14 != null ? indic.adx14.adx : null,
        stochK:   indic.stochastic?.k ?? null,
        stochD:   indic.stochastic?.d ?? null,
        high52w,
        vol20Avg: vol20avg,
      };

      const scoreResult = calculateScore(stockData, CRITERIA_CONFIGS[effectiveCriteria]);

      const pattern = detectPattern({
        price,
        ema50:    indic.ema50   ?? undefined,
        ema200:   indic.ema200  ?? undefined,
        rsi:      indic.rsi14   ?? undefined,
        adx:      indic.adx14 != null ? indic.adx14.adx : undefined,
        bbUpper:  indic.bollinger?.upper  ?? undefined,
        bbLower:  indic.bollinger?.lower  ?? undefined,
      });

      return {
        symbol:      sym,
        name:        stock.name,
        sector:      stock.sector,
        price,
        change1d,
        changePct1d: changePct,
        volume,
        score:       scoreResult.score,
        signal:      scoreToSignal(scoreResult.score),
        pattern,
        rsi:         indic.rsi14   ?? null,
        adx:         indic.adx14 != null ? indic.adx14.adx : null,
        ema50:       indic.ema50   ?? null,
        ema200:      indic.ema200  ?? null,
        aboveEma50:  !!(indic.ema50  && price > indic.ema50),
        aboveEma200: !!(indic.ema200 && price > indic.ema200),
        distFrom52wHigh,
        volumeRatio,
      } satisfies ScanResult;

    }, CONCURRENCY);

    // ── 3. Filtrele, sırala, döndür ───────────────────────────────────────────
    let results = analyzed
      .filter((r): r is PromiseFulfilledResult<ScanResult | null> => r.status === 'fulfilled' && r.value !== null)
      .map(r => (r as PromiseFulfilledResult<ScanResult>).value);

    if (filters.signal && filters.signal !== 'ALL') {
      results = results.filter(r => r.signal === filters.signal);
    }
    if (filters.sector && filters.sector !== 'ALL') {
      results = results.filter(r => r.sector === filters.sector);
    }
    if (minScore > 0) {
      results = results.filter(r => r.score >= minScore);
    }

    results.sort((a, b) => b.score - a.score);

    console.log(`[Scanner] Tamamlandı: ${results.length} hisse skorlandı`);
    return results;
  }
}
