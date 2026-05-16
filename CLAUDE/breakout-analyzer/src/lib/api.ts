import axios from 'axios';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
});

// Interceptor for error handling
api.interceptors.response.use(
  res => res,
  err => {
    console.error('[API Error]', err.message);
    return Promise.reject(err);
  }
);

// API methods
export const apiClient = {
  // Market Overview
  getMarketOverview: () => api.get('/api/market/overview'),
  getMarketBreadth: () => api.get('/api/market/breadth'),

  // Breakout Analyzer
  getBreakouts: (params?: { market?: string; minScore?: number; limit?: number }) =>
    api.get('/api/breakouts', { params }),
  getBreakoutDetail: (symbol: string) => api.get(`/api/breakouts/${symbol}`),
  analyzeStock: (symbol: string) => api.post('/api/analyze', { symbol }),

  // Scanner
  runScan: (criteria: object) => api.post('/api/scan', criteria),
  getScanHistory: () => api.get('/api/scan/history'),

  // Watchlist
  getWatchlist: () => api.get('/api/watchlist'),
  addToWatchlist: (symbol: string) => api.post('/api/watchlist', { symbol }),
  removeFromWatchlist: (symbol: string) => api.delete(`/api/watchlist/${symbol}`),

  // Stock data
  getStockPrice: (symbol: string, period: string = '6mo') =>
    api.get(`/api/stocks/${symbol}/price`, { params: { period } }),
  getStockIndicators: (symbol: string) =>
    api.get(`/api/stocks/${symbol}/indicators`),
};
