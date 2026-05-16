// MarketService — Twelve Data API ile gerçek piyasa verileri

import axios from 'axios';

const http    = axios.create({ timeout: 10_000 });

function getKey(): string {
  return process.env['TWELVE_DATA_API_KEY'] ?? '';
}

// TD sembol eşleşmeleri: label → TD symbol + exchange
const INDEX_MAP: { label: string; symbol: string; exchange?: string }[] = [
  { label: 'S&P 500',  symbol: 'SPY'       },   // ETF proxy (indeks fiyatı için)
  { label: 'NASDAQ',   symbol: 'QQQ'       },
  { label: 'DOW',      symbol: 'DIA'       },
  { label: 'VIX',      symbol: 'VIX',  exchange: 'CBOE' },
  { label: 'BTC/USD',  symbol: 'BTC/USD'   },
  { label: 'GOLD',     symbol: 'XAU/USD'   },
  { label: 'USD/TRY',  symbol: 'USD/TRY'   },
];

// Gerçek endeks fiyatları için (S&P, NASDAQ, DOW)
const REAL_INDEX_MAP: { label: string; symbol: string; exchange: string }[] = [
  { label: 'S&P 500', symbol: 'SPX',  exchange: 'NYSE' },
  { label: 'NASDAQ',  symbol: 'IXIC', exchange: 'NASDAQ' },
  { label: 'DOW',     symbol: 'DJI',  exchange: 'NYSE' },
];

interface IndexQuote {
  index:     string;
  value:     number;
  change:    number;
  changePct: number;
}

interface Quote {
  symbol:    string;
  price:     number;
  change:    number;
  changePct: number;
  volume:    number;
  marketCap: number;
  high52w:   number;
  low52w:    number;
}

interface OHLCVCandle {
  time:   number;
  open:   number;
  high:   number;
  low:    number;
  close:  number;
  volume: number;
}

/** TD /quote ile tek sembol çek */
async function tdQuote(symbol: string): Promise<{
  close: number; previous_close: number; change: number; percent_change: number; volume: number;
} | null> {
  if (!getKey()) return null;
  try {
    const { data } = await http.get('https://api.twelvedata.com/quote', {
      params: { symbol, apikey: getKey(), dp: 4 },
    });
    if (data?.status === 'error') return null;
    return {
      close:          parseFloat(data.close),
      previous_close: parseFloat(data.previous_close),
      change:         parseFloat(data.change),
      percent_change: parseFloat(data.percent_change),
      volume:         parseInt(data.volume ?? '0'),
    };
  } catch {
    return null;
  }
}

/** TD /price batch — birden fazla sembolü virgülle gönder */
async function tdBatchPrice(symbols: string[]): Promise<Record<string, number>> {
  if (!getKey() || symbols.length === 0) return {};
  try {
    const { data } = await http.get('https://api.twelvedata.com/price', {
      params: { symbol: symbols.join(','), apikey: getKey(), dp: 4 },
    });
    const out: Record<string, number> = {};
    for (const sym of symbols) {
      const entry = data[sym];
      if (entry?.price) out[sym] = parseFloat(entry.price);
    }
    return out;
  } catch {
    return {};
  }
}

export class MarketService {

  /** GET /api/market/indices — ticker band için piyasa verileri */
  async getIndices(): Promise<IndexQuote[]> {
    if (!getKey()) return this.fallbackIndices();

    // Paralel çek — çalışan TD sembolleri
    const symbols = ['SPY', 'QQQ', 'DIA', 'VIXY', 'BTC/USD', 'XAU/USD', 'USD/TRY'];
    const results = await Promise.allSettled(symbols.map(s => tdQuote(s)));

    const map: Record<string, { value: number; change: number; changePct: number }> = {};
    for (let i = 0; i < symbols.length; i++) {
      const r = results[i];
      if (r.status === 'fulfilled' && r.value) {
        map[symbols[i]!] = {
          value:     r.value.close,
          change:    r.value.change,
          changePct: r.value.percent_change,
        };
      }
    }

    const get = (sym: string) => map[sym] ?? { value: 0, change: 0, changePct: 0 };

    return [
      { index: 'S&P 500', ...get('SPY')     },
      { index: 'NASDAQ',  ...get('QQQ')     },
      { index: 'DOW',     ...get('DIA')     },
      { index: 'VIX',     ...get('VIXY')    },
      { index: 'BTC/USD', ...get('BTC/USD') },
      { index: 'GOLD',    ...get('XAU/USD') },
      { index: 'USD/TRY', ...get('USD/TRY') },
    ].filter(i => i.value > 0);
  }

  /** GET /api/market/quotes */
  async getQuotes(symbols: string[]): Promise<Quote[]> {
    const list   = symbols.length > 0 ? symbols : ['AAPL','MSFT','NVDA','TSLA','META'];
    const prices = await tdBatchPrice(list);

    return list.map(symbol => {
      const price = prices[symbol] ?? 0;
      return {
        symbol,
        price,
        change: 0,
        changePct: 0,
        volume: 0,
        marketCap: 0,
        high52w: 0,
        low52w:  0,
      };
    });
  }

  /** GET /api/market/ohlcv/:symbol */
  async getOHLCV(symbol: string, period: string): Promise<OHLCVCandle[]> {
    if (!getKey()) return this.generateMockOHLCV(symbol, period);
    try {
      const outputsize = period === '3M' ? 65 : period === '6M' ? 130 : period === '2Y' ? 504 : period === '5Y' ? 1260 : 252;
      const { data } = await http.get('https://api.twelvedata.com/time_series', {
        params: { symbol, interval: '1day', outputsize, apikey: getKey(), dp: 4 },
      });
      if (data?.status === 'error' || !data?.values?.length) return this.generateMockOHLCV(symbol, period);
      return (data.values as any[]).reverse().map((v: any) => ({
        time:   Math.floor(new Date(v.datetime).getTime() / 1000),
        open:   parseFloat(v.open),
        high:   parseFloat(v.high),
        low:    parseFloat(v.low),
        close:  parseFloat(v.close),
        volume: parseInt(v.volume ?? '0'),
      }));
    } catch {
      return this.generateMockOHLCV(symbol, period);
    }
  }

  async search(q: string) {
    if (!getKey() || q.length < 1) return [];
    try {
      const { data } = await http.get('https://api.twelvedata.com/symbol_search', {
        params: { symbol: q, apikey: getKey() },
      });
      return ((data.data ?? []) as any[]).slice(0, 10).map((s: any) => ({
        symbol: s.symbol,
        name:   s.instrument_name,
        sector: s.exchange,
      }));
    } catch {
      return [];
    }
  }

  // ── Fallback (API key yokken) ────────────────────────────────
  private fallbackIndices(): IndexQuote[] {
    return [
      { index: 'S&P 500',  value: 5234.18, change: 28.40,  changePct: 0.55 },
      { index: 'NASDAQ',   value: 16421.30, change: 96.20,  changePct: 0.59 },
      { index: 'DOW',      value: 39512.84, change: -45.60, changePct: -0.12 },
      { index: 'VIX',      value: 14.82,   change: -0.34,  changePct: -2.24 },
      { index: 'BTC/USD',  value: 68420.00, change: 1240.0, changePct: 1.85 },
      { index: 'GOLD',     value: 2348.50,  change: 12.30,  changePct: 0.53 },
      { index: 'USD/TRY',  value: 32.80,   change: 0.10,   changePct: 0.31 },
    ];
  }

  private generateMockOHLCV(symbol: string, period: string): OHLCVCandle[] {
    const MOCK_PRICES: Record<string, number> = {
      AAPL: 189.30, MSFT: 415.20, NVDA: 875.40, TSLA: 248.50,
      META: 516.80, GOOGL: 175.60, AMZN: 198.20,
    };
    const days  = period === '3M' ? 90 : period === '6M' ? 180 : period === '2Y' ? 504 : 252;
    const base  = MOCK_PRICES[symbol] ?? 100;
    const data: OHLCVCandle[] = [];
    let price = base * 0.75;
    const now = Date.now();
    for (let i = days; i >= 0; i--) {
      const time   = Math.floor((now - i * 86400000) / 1000);
      const open   = price;
      const change = (Math.random() - 0.47) * price * 0.025;
      const close  = Math.max(open + change, 1);
      const high   = Math.max(open, close) * (1 + Math.random() * 0.01);
      const low    = Math.min(open, close) * (1 - Math.random() * 0.01);
      const volume = Math.floor(Math.random() * 50_000_000 + 5_000_000);
      data.push({ time, open: +open.toFixed(2), high: +high.toFixed(2), low: +low.toFixed(2), close: +close.toFixed(2), volume });
      price = close;
    }
    return data;
  }
}
