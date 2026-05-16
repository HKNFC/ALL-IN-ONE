import { create } from 'zustand';
import type { Stock, PortfolioPosition, MarketData } from '../types';

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:4000';

// ---------- Mock data (stocks & portfolio) ----------

const MOCK_STOCKS: Stock[] = [
  { symbol: 'AAPL', name: 'Apple Inc.',       price: 189.30, change: 2.45,  changePct: 1.31,  volume: 58432100, marketCap: 2940000000000, sector: 'Technology' },
  { symbol: 'MSFT', name: 'Microsoft Corp.',  price: 415.20, change: -1.80, changePct: -0.43, volume: 22145600, marketCap: 3080000000000, sector: 'Technology' },
  { symbol: 'NVDA', name: 'NVIDIA Corp.',     price: 875.40, change: 18.60, changePct: 2.17,  volume: 43210500, marketCap: 2150000000000, sector: 'Technology' },
  { symbol: 'TSLA', name: 'Tesla Inc.',       price: 248.50, change: -5.30, changePct: -2.09, volume: 95430200, marketCap: 789000000000,  sector: 'Consumer Disc.' },
  { symbol: 'META', name: 'Meta Platforms',   price: 516.80, change: 7.20,  changePct: 1.41,  volume: 18923400, marketCap: 1320000000000, sector: 'Technology' },
  { symbol: 'GOOGL', name: 'Alphabet Inc.',   price: 175.60, change: 0.90,  changePct: 0.51,  volume: 24120800, marketCap: 2180000000000, sector: 'Technology' },
  { symbol: 'AMZN', name: 'Amazon.com',       price: 198.20, change: 3.10,  changePct: 1.59,  volume: 35670000, marketCap: 2060000000000, sector: 'Consumer Disc.' },
  { symbol: 'BRK.B', name: 'Berkshire Hath.', price: 408.70, change: -0.40, changePct: -0.10, volume: 4120300,  marketCap: 892000000000,  sector: 'Financials' },
  { symbol: 'JPM',  name: 'JPMorgan Chase',   price: 212.40, change: 1.80,  changePct: 0.86,  volume: 9845600,  marketCap: 612000000000,  sector: 'Financials' },
  { symbol: 'V',    name: 'Visa Inc.',        price: 278.90, change: 0.60,  changePct: 0.22,  volume: 7230500,  marketCap: 561000000000,  sector: 'Financials' },
];

const MOCK_PORTFOLIO: PortfolioPosition[] = [
  { id: '1', symbol: 'AAPL', name: 'Apple Inc.',     shares: 50,  avgCost: 165.20, currentPrice: 189.30, pnl: 1205.00,  pnlPct: 14.59,  value: 9465.00,  weight: 22.4 },
  { id: '2', symbol: 'NVDA', name: 'NVIDIA Corp.',   shares: 15,  avgCost: 620.00, currentPrice: 875.40, pnl: 3831.00,  pnlPct: 41.19,  value: 13131.00, weight: 31.1 },
  { id: '3', symbol: 'MSFT', name: 'Microsoft',      shares: 20,  avgCost: 390.00, currentPrice: 415.20, pnl: 504.00,   pnlPct: 6.46,   value: 8304.00,  weight: 19.7 },
  { id: '4', symbol: 'TSLA', name: 'Tesla Inc.',     shares: 30,  avgCost: 280.00, currentPrice: 248.50, pnl: -945.00,  pnlPct: -11.25, value: 7455.00,  weight: 17.7 },
  { id: '5', symbol: 'META', name: 'Meta Platforms', shares: 8,   avgCost: 470.00, currentPrice: 516.80, pnl: 374.40,   pnlPct: 9.96,   value: 4134.40,  weight: 9.8  },
];

// ---------- Store ----------

interface AppState {
  stocks:          Stock[];
  market:          MarketData[];
  portfolio:       PortfolioPosition[];
  watchlist:       string[];
  selectedSymbol:  string;
  isLive:          boolean;

  setSelectedSymbol: (symbol: string) => void;
  toggleWatchlist:   (symbol: string) => void;
  tickPrices:        () => void;
  toggleLive:        () => void;
  fetchMarketData:   () => Promise<void>;
}

export const useAppStore = create<AppState>((set, get) => ({
  stocks:         MOCK_STOCKS,
  market:         [],          // gerçek veri gelene kadar boş
  portfolio:      MOCK_PORTFOLIO,
  watchlist:      ['AAPL', 'NVDA', 'MSFT', 'TSLA'],
  selectedSymbol: 'AAPL',
  isLive:         true,

  setSelectedSymbol: (symbol) => set({ selectedSymbol: symbol }),

  toggleWatchlist: (symbol) => {
    const { watchlist } = get();
    set({
      watchlist: watchlist.includes(symbol)
        ? watchlist.filter(s => s !== symbol)
        : [...watchlist, symbol],
    });
  },

  // Sadece stocks ve portfolio için — market artık API'dan geliyor
  tickPrices: () => {
    set(state => ({
      stocks: state.stocks.map(s => {
        const delta    = (Math.random() - 0.5) * s.price * 0.006;
        const newPrice = parseFloat((s.price + delta).toFixed(2));
        const change   = parseFloat((s.change + delta).toFixed(2));
        return { ...s, price: newPrice, change, changePct: parseFloat((change / newPrice * 100).toFixed(2)) };
      }),
    }));
  },

  toggleLive: () => set(state => ({ isLive: !state.isLive })),

  // Gerçek piyasa verisini backend'den çek
  fetchMarketData: async () => {
    try {
      const res  = await fetch(`${API_BASE}/api/market/indices`);
      if (!res.ok) return;
      const json = await res.json() as { data: MarketData[] };
      if (json.data?.length) {
        set({ market: json.data });
      }
    } catch {
      // sessiz başarısız
    }
  },
}));
