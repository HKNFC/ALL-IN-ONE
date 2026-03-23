import axios, { type AxiosInstance } from 'axios'
import Redis from 'ioredis'
import * as fs from 'fs'
import * as path from 'path'
import type {
  OHLCV,
  Fundamentals,
  IndexData,
  TechnicalIndicators,
  BreadthData,
} from '../types/market'
import { calculateAllIndicators } from '../utils/indicators'

// ---------------------------------------------------------------------------
// Disk Cache — .cache/prices/{symbol}_{start}_{end}.json
// ---------------------------------------------------------------------------
const DISK_CACHE_DIR = path.resolve(process.cwd(), '.cache', 'prices')
const DISK_CACHE_TTL_MS = 7 * 24 * 60 * 60 * 1000  // 7 gün

function ensureCacheDir(): void {
  if (!fs.existsSync(DISK_CACHE_DIR)) {
    fs.mkdirSync(DISK_CACHE_DIR, { recursive: true })
  }
}

function diskCacheKey(symbol: string, start: string, end: string): string {
  return path.join(DISK_CACHE_DIR, `${symbol}_${start}_${end}.json`)
}

function readDiskCache(symbol: string, start: string, end: string): OHLCV[] | null {
  try {
    ensureCacheDir()
    // First try exact match
    const exactFile = diskCacheKey(symbol, start, end)
    if (fs.existsSync(exactFile)) {
      const stat = fs.statSync(exactFile)
      if (Date.now() - stat.mtimeMs <= DISK_CACHE_TTL_MS) {
        const data = JSON.parse(fs.readFileSync(exactFile, 'utf8')) as OHLCV[]
        if (Array.isArray(data) && data.length > 0) return data
      }
    }
    // Fallback: find cache file(s) whose range overlaps with [start, end]
    // Prefer files that cover the most of the range (widest coverage first)
    const prefix = `${symbol.toUpperCase()}_`
    const files = fs.readdirSync(DISK_CACHE_DIR).filter(f => f.startsWith(prefix) && f.endsWith('.json'))
    let bestData: OHLCV[] | null = null
    let bestCoverage = 0
    for (const fname of files) {
      const parts = fname.replace('.json', '').split('_')
      if (parts.length < 3) continue
      const fileStart = parts[parts.length - 2]
      const fileEnd   = parts[parts.length - 1]
      // Check for any overlap with requested range
      if (fileStart > end || fileEnd < start) continue
      const fullPath = path.join(DISK_CACHE_DIR, fname)
      try {
        const stat = fs.statSync(fullPath)
        if (Date.now() - stat.mtimeMs > DISK_CACHE_TTL_MS) continue
        const data = JSON.parse(fs.readFileSync(fullPath, 'utf8')) as OHLCV[]
        if (!Array.isArray(data) || data.length === 0) continue
        // Filter to requested range
        const filtered = data.filter(d => {
          const ds = d.date instanceof Date ? d.date.toISOString().slice(0, 10) : String(d.date).slice(0, 10)
          return ds >= start && ds <= end
        })
        if (filtered.length > bestCoverage) {
          bestCoverage = filtered.length
          bestData = filtered
        }
      } catch { continue }
    }
    return bestData
  } catch {
    return null
  }
}

function writeDiskCache(symbol: string, start: string, end: string, data: OHLCV[]): void {
  try {
    ensureCacheDir()
    fs.writeFileSync(diskCacheKey(symbol, start, end), JSON.stringify(data))
  } catch { /* non-fatal */ }
}

// Diskte kaç dosya var / toplam boyut
export function diskCacheStats(): { files: number; sizeMB: number } {
  try {
    ensureCacheDir()
    const files = fs.readdirSync(DISK_CACHE_DIR).filter(f => f.endsWith('.json'))
    const size  = files.reduce((s, f) => {
      try { return s + fs.statSync(path.join(DISK_CACHE_DIR, f)).size } catch { return s }
    }, 0)
    return { files: files.length, sizeMB: parseFloat((size / 1_048_576).toFixed(1)) }
  } catch {
    return { files: 0, sizeMB: 0 }
  }
}

// ---------------------------------------------------------------------------
// Cache TTLs (seconds)
// ---------------------------------------------------------------------------
const TTL = {
  dailyPrice:   60 * 60 * 24 * 30,  // 30 days
  indicators:   60 * 60 * 24,        // 24 hours
  fundamentals: 60 * 60 * 24 * 7,   // 7 days
  index:        60 * 60,             // 1 hour
  breadth:      60 * 60 * 4,        // 4 hours
  constituents: 60 * 60 * 24,       // 24 hours
}

// ---------------------------------------------------------------------------
// Interval mapping: internal → Twelve Data interval string
// ---------------------------------------------------------------------------
const TD_INTERVAL: Record<string, string> = {
  '1d':  '1day',
  '1wk': '1week',
  '1mo': '1month',
}

// ---------------------------------------------------------------------------
// Static constituent lists
// ---------------------------------------------------------------------------
const SP500_SAMPLE = [
  'AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA','BRK.B','UNH','JPM',
  'V','XOM','LLY','JNJ','PG','MA','HD','CVX','MRK','ABBV','AVGO','PEP',
  'KO','COST','WMT','BAC','TMO','MCD','CSCO','ABT','ACN','NFLX','CRM',
  'DHR','LIN','AMD','TXN','ADBE','NEE','WFC','PM','DIS','BMY','RTX','AMGN',
  'QCOM','LOW','SPGI','HON','UNP','IBM','SBUX','GE','CAT','INTU','ISRG',
  'BLK','MDT','ELV','VRTX','PLD','REGN','GILD','CI','CB','SO','DUK','SYK',
  'ZTS','SCHW','MO','TJX','BSX','CME','EOG','PNC','ADP','NOC','ITW','CL',
  'MDLZ','MMC','ETN','KLAC','FCX','SLB','GD','USB','LRCX','HCA','FDX','EMR',
]

// BIST sembolleri için Twelve Data exchange parametresi: BIST
const BIST100_SAMPLE = [
  // BIST100 — Büyük Şirketler
  'THYAO','GARAN','AKBNK','YKBNK','SISE','BIMAS','TUPRS','EREGL','KCHOL',
  'SAHOL','TKFEN','ARCLK','TOASO','FROTO','TTKOM','HEKTS','ASELS','KOZAL',
  'PGSUS','MGROS','ULKER','AEFES','CCOLA','DOHOL','EKGYO','ENKAI','TAVHL',
  'TCELL','VAKBN','VESTL','PETKM','OTKAR','LOGO','NETAS','SELEC','SKBNK',
  'GUBRF','KORDS','BRSAN','TMSN','YATAS','ZOREN','AKSEN','ALGYO','ALTNY',
  'ANACM','ASUZU','AVISA','BAGFS','BANVT','BIOEN','BIZIM','BMEKS','BNTAS',
  'BSOKE','BUCIM','CEMTS','CIMSA','CLEBI','CNVRE','CRDFA','CUSAN','IPEKE',
  // BIST100 ek hisseler
  'ALARK','ALBRK','ALFAS','ALKIM','ALTIN','ALYAG','ANELE','ANHYT','APEKS',
  'ARSAN','ATAGY','ATAKP','ATLAS','AYGAZ','AYEN','BASGZ','BTCIM','CANTE',
  'CEMZY','CEOEM','CGCAM','CIMSA','COSMO','CZURI','DENGE','DEVA','DOAS',
  'DOKTA','DURDO','DYOBY','ECZYT','EGEEN','EGPRO','EMKEL','EREGL','ESCOM',
  'FADE','FMIZP','FONET','FORMT','FORTS','GEDZA','GESAN','GLBMD','GOLTS',
  'GSDHO','GSRAY','GUBRF','GWIND','HALKB','HATEK','INDES','ISBIR','ISFIN',
  'ISGSY','ISGYO','ISMEN','ISYAT','IZMDC','JANTS','KAPLM','KAREL','KARTN',
  'KATMR','KAYSE','KERVT','KLGYO','KLNMA','KONYA','KOPOL','KRDMD','KRSTL',
  'KUTPO','LKMNH','LRSHO','LUKSK','LYDHO','MAALT','MACKO','MAGEN','MAKTK',
  'MARKA','MEDTR','MEGMT','MEPET','MERIT','MERKO','METUR','MGROS','MIATK',
  'MMCAS','MNDRS','MNVMS','MOBTL','MPARK','MRGYO','MRSHL','MSGYO','MTRKS',
  'NBORU','NETAS','NTHOL','NUHCM','OBAMS','ODAS','ONCSM','ORCAY','ORGE',
  'OYAKC','OYLUM','OZGYO','OZKGY','PARSN','PCILT','PEKGY','PENGD','PETUN',
  'PGSUS','PINSU','PKART','PLTUR','POLHO','POLTK','PRKAB','PRKME','PRZMA',
  'QUAGR','RALYH','RAYSG','RGYAS','RNPOL','RODRG','ROYAL','RTALB','RUBNS',
  'RYSAS','SAFKR','SAGYO','SARKY','SAYAS','SDTTR','SEKFK','SEKUR','SELGD',
  'SERCE','SEYKM','SILVR','SISE','SKBNK','SMART','SNGYO','SOKM','SONME',
  'SRVGY','SUMAS','SURGY','SVGYO','TARKM','TATGD','TBORG','TDGYO','TEKTU',
  'TEZOL','TGSAS','THYAO','TKFEN','TLMAN','TMPOL','TMSN','TNZTP','TOASO',
  'TRCAS','TRGYO','TRILC','TSGYO','TSKB','TTKOM','TTRAK','TUCLK','TUPRS',
  'TURGG','TURSG','ULUFA','ULUSE','UMASS','UNLU','USAK','USDAU','UTPYA',
  'VAKBN','VAKFN','VAKKO','VERUS','VESBE','VESTL','VKFYO','VKGYO','YBTAS',
  'YEOTK','YESIL','YGGYO','YKBNK','YKSLN','ZOREN','ZRGYO',
]

// ---------------------------------------------------------------------------
// DataService
// ---------------------------------------------------------------------------
export class DataService {
  private tdClient: AxiosInstance       // Twelve Data – primary
  private yahooClient: AxiosInstance    // Yahoo Finance – fallback
  private redis: Redis | null = null
  private redisAvailable = false

  // In-memory prefetch store for backtesting (avoids repeated API calls)
  private prefetchStore: Map<string, OHLCV[]> = new Map()
  private prefetchActive = false

  constructor() {
    const tdKey = process.env.TWELVE_DATA_API_KEY ?? ''

    // Twelve Data REST API
    this.tdClient = axios.create({
      baseURL: 'https://api.twelvedata.com',
      timeout: 20000,
      params: { apikey: tdKey },
    })

    // Yahoo Finance (fallback – no key needed)
    this.yahooClient = axios.create({
      baseURL: 'https://query1.finance.yahoo.com/v8/finance',
      timeout: 15000,
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; VERDENT/1.0)',
        Accept: 'application/json',
      },
    })

    this.initRedis()
  }

  // -------------------------------------------------------------------------
  // Redis helpers
  // -------------------------------------------------------------------------
  private initRedis(): void {
    const redisUrl = process.env.REDIS_URL ?? 'redis://localhost:6379'
    try {
      this.redis = new Redis(redisUrl, { lazyConnect: true, enableOfflineQueue: false })
      this.redis.connect()
        .then(() => { this.redisAvailable = true })
        .catch(() => { this.redisAvailable = false })
      this.redis.on('error', () => { this.redisAvailable = false })
    } catch {
      this.redisAvailable = false
    }
  }

  private async cacheGet<T>(key: string): Promise<T | null> {
    if (!this.redisAvailable || !this.redis) return null
    try {
      const raw = await this.redis.get(key)
      return raw ? (JSON.parse(raw) as T) : null
    } catch {
      return null
    }
  }

  private async cacheSet(key: string, value: unknown, ttl: number): Promise<void> {
    if (!this.redisAvailable || !this.redis) return
    try {
      await this.redis.set(key, JSON.stringify(value), 'EX', ttl)
    } catch { /* ignore */ }
  }

  // -------------------------------------------------------------------------
  // isBISTSymbol
  // -------------------------------------------------------------------------
  isBISTSymbol(symbol: string): boolean {
    return BIST100_SAMPLE.includes(symbol.toUpperCase()) ||
           symbol.toUpperCase().endsWith('.IS')
  }

  // -------------------------------------------------------------------------
  // Prefetch all prices for a backtest (call once before backtest loop)
  // -------------------------------------------------------------------------
  async prefetchPrices(
    symbols: { symbol: string; market: string }[],
    startDate: Date,
    endDate: Date,
    onProgress?: (done: number, total: number) => void
  ): Promise<void> {
    this.prefetchStore.clear()
    this.prefetchActive = true

    const BATCH = 5
    let done = 0
    for (let i = 0; i < symbols.length; i += BATCH) {
      const batch = symbols.slice(i, i + BATCH)
      await Promise.allSettled(
        batch.map(async ({ symbol }) => {
          const sym      = symbol.toUpperCase()
          const startStr = startDate.toISOString().slice(0, 10)
          const endStr   = endDate.toISOString().slice(0, 10)

          // Check disk cache first — no API call needed
          const disk = readDiskCache(sym, startStr, endStr)
          if (disk) {
            this.prefetchStore.set(sym, disk)
            done++
            onProgress?.(done, symbols.length)
            return
          }

          try {
            const prices = await this.fetchTwelveDataPrices(symbol, startDate, endDate, '1d')
            if (prices.length > 0) {
              this.prefetchStore.set(sym, prices)
              writeDiskCache(sym, startStr, endStr, prices)
            }
          } catch { /* skip failed symbols */ }
          done++
          onProgress?.(done, symbols.length)
        })
      )
      if (i + BATCH < symbols.length) await new Promise((r) => setTimeout(r, 500))
    }
  }

  clearPrefetch(): void {
    this.prefetchStore.clear()
    this.prefetchActive = false
  }

  // -------------------------------------------------------------------------
  // fetchStockPrice — Twelve Data primary, Yahoo fallback
  // -------------------------------------------------------------------------
  async fetchStockPrice(
    symbol: string,
    startDate: Date,
    endDate: Date,
    interval: '1d' | '1wk' | '1mo' = '1d'
  ): Promise<OHLCV[]> {
    // Backtest prefetch store: return slice of full dataset (no API call)
    if (this.prefetchActive && interval === '1d') {
      const prefetched = this.prefetchStore.get(symbol.toUpperCase())
      if (prefetched) {
        const start = startDate.getTime()
        const end   = endDate.getTime()
        return prefetched.filter((b) => {
          const t = new Date(b.date).getTime()
          return t >= start && t <= end
        })
      }
      // During backtest, if symbol is not in prefetch store, return empty immediately
      // (avoids redundant live API calls for symbols that failed during prefetch)
      return []
    }

    const startStr = startDate.toISOString().slice(0, 10)
    const endStr   = endDate.toISOString().slice(0, 10)
    const cacheKey = `price:${symbol}:${interval}:${startStr}:${endStr}`

    // 1. Redis/memory cache
    const cached = await this.cacheGet<OHLCV[]>(cacheKey)
    if (cached) return cached

    // 2. Disk cache (survives server restarts)
    if (interval === '1d') {
      const disk = readDiskCache(symbol.toUpperCase(), startStr, endStr)
      if (disk) {
        await this.cacheSet(cacheKey, disk, TTL.dailyPrice)
        return disk
      }
    }

    // 3. API call
    let data: OHLCV[] = []
    data = await this.fetchTwelveDataPrices(symbol, startDate, endDate, interval)
      .catch(() => this.fetchYahooPrices(symbol, startDate, endDate, interval))

    if (data.length > 0) {
      await this.cacheSet(cacheKey, data, TTL.dailyPrice)
      if (interval === '1d') writeDiskCache(symbol.toUpperCase(), startStr, endStr, data)
    }
    return data
  }

  // -------------------------------------------------------------------------
  // Twelve Data — time_series
  // -------------------------------------------------------------------------
  private async fetchTwelveDataPrices(
    symbol: string,
    startDate: Date,
    endDate: Date,
    interval: '1d' | '1wk' | '1mo'
  ): Promise<OHLCV[]> {
    const tdInterval = TD_INTERVAL[interval] ?? '1day'
    const isBIST = this.isBISTSymbol(symbol)

    // Clean symbol: remove .IS suffix if present (TD uses exchange param instead)
    const cleanSymbol = symbol.replace(/\.IS$/i, '').toUpperCase()

    const params: Record<string, string | number> = {
      symbol:    cleanSymbol,
      interval:  tdInterval,
      start_date: startDate.toISOString().slice(0, 10),
      end_date:   endDate.toISOString().slice(0, 10),
      outputsize: 5000,
      format:    'JSON',
      order:     'ASC',
    }

    // BIST için exchange parametresi ekle
    if (isBIST) {
      params.exchange = 'BIST'
    }

    const res = await this.tdClient.get('/time_series', { params })

    if (res.data?.status === 'error') {
      throw new Error(`Twelve Data error for ${symbol}: ${res.data.message}`)
    }

    const values = res.data?.values as Array<{
      datetime: string
      open: string
      high: string
      low: string
      close: string
      volume: string
    }>

    if (!Array.isArray(values) || values.length === 0) {
      throw new Error(`No Twelve Data values for ${symbol}`)
    }

    return values.map((bar) => ({
      date:   new Date(bar.datetime),
      open:   parseFloat(bar.open),
      high:   parseFloat(bar.high),
      low:    parseFloat(bar.low),
      close:  parseFloat(bar.close),
      volume: parseFloat(bar.volume ?? '0'),
    })).filter((bar) => bar.close > 0)
  }

  // -------------------------------------------------------------------------
  // Yahoo Finance (fallback)
  // -------------------------------------------------------------------------
  private async fetchYahooPrices(
    symbol: string,
    startDate: Date,
    endDate: Date,
    interval: string
  ): Promise<OHLCV[]> {
    const period1 = Math.floor(startDate.getTime() / 1000)
    const period2 = Math.floor(endDate.getTime() / 1000)

    // BIST sembollerini Yahoo formatına çevir (THYAO → THYAO.IS)
    const yahooSymbol = this.isBISTSymbol(symbol) && !symbol.endsWith('.IS')
      ? `${symbol}.IS`
      : symbol

    const res = await this.yahooClient.get(`/chart/${yahooSymbol}`, {
      params: { period1, period2, interval, events: 'history' },
    })

    const result = res.data?.chart?.result?.[0]
    if (!result) throw new Error(`No Yahoo data for ${symbol}`)

    const timestamps: number[] = result.timestamp
    const { open, high, low, close, volume } = result.indicators.quote[0] as {
      open: number[]; high: number[]; low: number[]
      close: number[]; volume: number[]
    }

    return timestamps.map((ts, i) => ({
      date:   new Date(ts * 1000),
      open:   open[i]   ?? 0,
      high:   high[i]   ?? 0,
      low:    low[i]    ?? 0,
      close:  close[i]  ?? 0,
      volume: volume[i] ?? 0,
    })).filter((bar) => bar.close > 0)
  }

  // -------------------------------------------------------------------------
  // fetchFundamentals — Twelve Data statistics endpoint
  // -------------------------------------------------------------------------
  async fetchFundamentals(symbol: string): Promise<Fundamentals> {
    const cacheKey = `fundamentals:${symbol}`
    const cached = await this.cacheGet<Fundamentals>(cacheKey)
    if (cached) return cached

    const result = await this.fetchTwelveDataFundamentals(symbol)
      .catch(() => this.fetchYahooFundamentals(symbol))

    await this.cacheSet(cacheKey, result, TTL.fundamentals)
    return result
  }

  private async fetchTwelveDataFundamentals(symbol: string): Promise<Fundamentals> {
    const isBIST = this.isBISTSymbol(symbol)
    const cleanSymbol = symbol.replace(/\.IS$/i, '').toUpperCase()

    const params: Record<string, string> = { symbol: cleanSymbol }
    if (isBIST) params.exchange = 'BIST'

    const res = await this.tdClient.get('/statistics', { params })

    if (res.data?.status === 'error') {
      throw new Error(`TD fundamentals error: ${res.data.message}`)
    }

    const s = res.data?.statistics as Record<string, Record<string, number>> | undefined

    return {
      symbol,
      pe:             s?.valuations_metrics?.trailing_pe         ?? null,
      pb:             s?.valuations_metrics?.price_to_book_mrq   ?? null,
      roe:            s?.financial_highlights?.return_on_equity_ttm ?? null,
      debtEquity:     s?.balance_sheet?.total_debt_to_equity_mrq  ?? null,
      revenueGrowth:  s?.income_statement?.quarterly_revenue_growth_yoy ?? null,
      earningsGrowth: s?.income_statement?.quarterly_earnings_growth_yoy ?? null,
      freeCashFlow:   s?.cash_flow_statement?.levered_free_cash_flow_ttm ?? null,
      marketCap:      s?.valuations_metrics?.market_capitalization ?? null,
      updatedAt:      new Date(),
    }
  }

  private async fetchYahooFundamentals(symbol: string): Promise<Fundamentals> {
    const yahooSymbol = this.isBISTSymbol(symbol) && !symbol.endsWith('.IS')
      ? `${symbol}.IS`
      : symbol

    const res = await this.yahooClient.get(`/quote/${yahooSymbol}`)
    const q = res.data?.quoteResponse?.result?.[0] as Record<string, number | string> | undefined

    return {
      symbol,
      pe:             (q?.trailingPE       as number) ?? null,
      pb:             (q?.priceToBook      as number) ?? null,
      roe:            null,
      debtEquity:     null,
      revenueGrowth:  (q?.revenueGrowth   as number) ?? null,
      earningsGrowth: (q?.earningsGrowth  as number) ?? null,
      freeCashFlow:   (q?.freeCashflow    as number) ?? null,
      marketCap:      (q?.marketCap       as number) ?? null,
      updatedAt:      new Date(),
    }
  }

  // -------------------------------------------------------------------------
  // fetchMarketIndex — Twelve Data primary
  // -------------------------------------------------------------------------
  async fetchMarketIndex(
    index: 'BIST100' | 'SP500' | 'VIX',
    date?: Date
  ): Promise<IndexData> {
    const cacheKey = `index:${index}:${date?.toISOString().slice(0, 10) ?? 'latest'}`
    const cached = await this.cacheGet<IndexData>(cacheKey)
    if (cached) return cached

    // Twelve Data sembol eşlemesi
    const tdSymbolMap: Record<string, { symbol: string; exchange?: string }> = {
      BIST100: { symbol: 'XU100', exchange: 'BIST' },
      SP500:   { symbol: 'SPX' },
      VIX:     { symbol: 'VIX' },
    }

    const { symbol: tdSym, exchange } = tdSymbolMap[index]
    const endDate   = date ?? new Date()
    const startDate = new Date(endDate)
    startDate.setDate(startDate.getDate() - 10)

    const params: Record<string, string | number> = {
      symbol:    tdSym,
      interval:  '1day',
      start_date: startDate.toISOString().slice(0, 10),
      end_date:   endDate.toISOString().slice(0, 10),
      outputsize: 10,
      order:     'ASC',
    }
    if (exchange) params.exchange = exchange

    let prices: OHLCV[] = []
    try {
      const res = await this.tdClient.get('/time_series', { params })
      if (res.data?.status !== 'error') {
        prices = (res.data?.values ?? []).map((bar: {
          datetime: string; open: string; high: string
          low: string; close: string; volume?: string
        }) => ({
          date:   new Date(bar.datetime),
          open:   parseFloat(bar.open),
          high:   parseFloat(bar.high),
          low:    parseFloat(bar.low),
          close:  parseFloat(bar.close),
          volume: parseFloat(bar.volume ?? '0'),
        }))
      }
    } catch { /* fallback below */ }

    // Yahoo fallback for index
    if (prices.length === 0) {
      const yahooSymbolMap: Record<string, string> = {
        BIST100: 'XU100.IS', SP500: '^GSPC', VIX: '^VIX',
      }
      prices = await this.fetchYahooPrices(yahooSymbolMap[index], startDate, endDate, '1d')
        .catch(() => [])
    }

    const latest = prices[prices.length - 1]
    const prev   = prices[prices.length - 2]

    const result: IndexData = {
      index,
      value:     latest?.close ?? 0,
      change:    latest && prev ? latest.close - prev.close : 0,
      changePct: latest && prev ? ((latest.close - prev.close) / prev.close) * 100 : 0,
      date:      latest?.date ?? new Date(),
    }

    await this.cacheSet(cacheKey, result, TTL.index)
    return result
  }

  // -------------------------------------------------------------------------
  // calculateTechnicalIndicators
  // -------------------------------------------------------------------------
  async calculateTechnicalIndicators(prices: OHLCV[]): Promise<TechnicalIndicators> {
    return calculateAllIndicators(prices)
  }

  // -------------------------------------------------------------------------
  // getBIST100Constituents
  // -------------------------------------------------------------------------
  async getBIST100Constituents(): Promise<string[]> {
    return this.getAllBISTStocks()
  }

  // -------------------------------------------------------------------------
  // getAllBISTStocks — Twelve Data /stocks?exchange=BIST (tüm BIST hisseleri)
  // -------------------------------------------------------------------------
  async getAllBISTStocks(): Promise<string[]> {
    const cacheKey = 'constituents:bist_all'
    const cached = await this.cacheGet<string[]>(cacheKey)
    if (cached && cached.length > 100) return cached

    try {
      const res = await this.tdClient.get('/stocks', {
        params: { exchange: 'BIST', outputsize: 5000 },
      })
      if (Array.isArray(res.data?.data) && res.data.data.length > 0) {
        const symbols: string[] = res.data.data
          .map((s: { symbol: string }) => s.symbol.toUpperCase())
          .filter((s: string) => /^[A-Z0-9]+$/.test(s))
        await this.cacheSet(cacheKey, symbols, TTL.constituents)
        console.log(`[DataService] BIST: ${symbols.length} hisse yüklendi`)
        return symbols
      }
    } catch (e) {
      console.error('[DataService] getAllBISTStocks error:', e)
    }

    // Fallback: static BIST100 list
    await this.cacheSet(cacheKey, BIST100_SAMPLE, TTL.constituents)
    return BIST100_SAMPLE
  }

  // -------------------------------------------------------------------------
  // getSP500Constituents
  // -------------------------------------------------------------------------
  async getSP500Constituents(): Promise<string[]> {
    const cacheKey = 'constituents:sp500'
    const cached = await this.cacheGet<string[]>(cacheKey)
    if (cached) return cached

    // Twelve Data'dan S&P500 bileşenleri çek
    try {
      const res = await this.tdClient.get('/indices/components', {
        params: { symbol: 'SPX' },
      })
      if (Array.isArray(res.data?.components)) {
        const symbols: string[] = res.data.components.map((c: { symbol: string }) => c.symbol)
        if (symbols.length > 0) {
          await this.cacheSet(cacheKey, symbols, TTL.constituents)
          return symbols
        }
      }
    } catch { /* fallback */ }

    await this.cacheSet(cacheKey, SP500_SAMPLE, TTL.constituents)
    return SP500_SAMPLE
  }

  // -------------------------------------------------------------------------
  // calculate52WeekHighLow
  // -------------------------------------------------------------------------
  async calculate52WeekHighLow(symbol: string): Promise<{ high: number; low: number }> {
    const endDate   = new Date()
    const startDate = new Date()
    startDate.setFullYear(startDate.getFullYear() - 1)

    const prices = await this.fetchStockPrice(symbol, startDate, endDate, '1d')

    if (prices.length === 0) return { high: 0, low: 0 }

    const high = Math.max(...prices.map((p) => p.high))
    const low  = Math.min(...prices.map((p) => p.low))
    return { high, low }
  }

  // -------------------------------------------------------------------------
  // getMarketBreadth
  // -------------------------------------------------------------------------
  async getMarketBreadth(market: 'BIST' | 'US'): Promise<BreadthData> {
    const cacheKey = `breadth:${market}`
    const cached = await this.cacheGet<BreadthData>(cacheKey)
    if (cached) return cached

    const constituents = market === 'BIST'
      ? await this.getBIST100Constituents()
      : await this.getSP500Constituents()

    const sample = constituents.slice(0, 30) // limit API calls
    const endDate = new Date()
    const startDate = new Date()
    startDate.setDate(startDate.getDate() - 210) // ~200 trading-day lookback

    let advances = 0
    let declines = 0
    let above200sma = 0
    let newHighs = 0
    let newLows = 0

    await Promise.allSettled(
      sample.map(async (sym) => {
        try {
          const prices = await this.fetchStockPrice(sym, startDate, endDate, '1d')
          if (prices.length < 2) return

          const latest = prices[prices.length - 1]
          const prev   = prices[prices.length - 2]

          if (latest.close > prev.close) advances++
          else declines++

          if (prices.length >= 200) {
            const sma200 = prices.slice(-200).reduce((s, p) => s + p.close, 0) / 200
            if (latest.close > sma200) above200sma++
          }

          const high52w = Math.max(...prices.slice(-252).map((p) => p.high))
          const low52w  = Math.min(...prices.slice(-252).map((p) => p.low))
          if (latest.high >= high52w * 0.98) newHighs++
          if (latest.low  <= low52w  * 1.02) newLows++
        } catch { /* skip failed symbols */ }
      })
    )

    const total = advances + declines || 1
    const result: BreadthData = {
      market,
      advanceDeclineRatio: advances / (declines || 1),
      advancingStocks:     advances,
      decliningStocks:     declines,
      unchangedStocks:     sample.length - advances - declines,
      pctAbove200SMA:      above200sma / sample.length,
      newHighs,
      newLows,
      newHighLowRatio:     newHighs / (newLows || 1),
      date: new Date(),
    }

    await this.cacheSet(cacheKey, result, TTL.breadth)
    return result
  }
}

export const dataService = new DataService()
