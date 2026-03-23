import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error.response?.data || error.message)
    return Promise.reject(error)
  }
)

// ── Market ────────────────────────────────────────────────────────────────────
export const marketService = {
  getCondition:   (market: string) => api.get(`/market/condition/${market}`),
  getConditionAt: (market: string, date: string) => api.get(`/market/condition/${market}/${date}`),
  getIndicators:  (market: string) => api.get(`/market/indicators/${market}`),
  getHistory:     (market: string, params?: { startDate?: string; endDate?: string }) =>
    api.get(`/market/history/${market}`, { params }),

  // Legacy
  getQuote:          (symbol: string) => api.get(`/market/quote/${symbol}`),
  getMarketOverview: () => api.get('/market/overview'),
  getTopMovers:      () => api.get('/market/movers'),
}

// ── Scanner ───────────────────────────────────────────────────────────────────
export const scannerService = {
  scan: (body: { criteria: string; date?: string; market?: string }) =>
    api.post('/scanner/scan', body),
  getResults: (params?: { criteria?: string; market?: string; limit?: number; offset?: number }) =>
    api.get('/scanner/results', { params }),
  getResult:    (id: string)    => api.get(`/scanner/results/${id}`),
  deleteResult: (id: string)    => api.delete(`/scanner/results/${id}`),
}

// ── Backtest ──────────────────────────────────────────────────────────────────
export const backtestService = {
  run: (body: {
    name?: string
    criteriaType: string
    startDate: string
    endDate: string
    rebalancePeriod?: string
    market?: string
    initialCapital?: number
    transactionCost?: number
    slippage?: number
  }) => api.post('/backtest/run', body),
  getStatus:  (jobId: string) => api.get(`/backtest/status/${jobId}`),
  getList:    (params?: { market?: string; limit?: number; offset?: number }) =>
    api.get('/backtest/results', { params }),
  getById:    (id: string) => api.get(`/backtest/results/${id}`),
  diagnostic: (id: string) => api.get(`/backtest/${id}/diagnostic`),
  deleteById: (id: string) => api.delete(`/backtest/${id}`),
}

// ── Stocks ────────────────────────────────────────────────────────────────────
export const stockService = {
  search: (q: string, params?: { market?: string; limit?: number }) =>
    api.get('/stocks/search', { params: { q, ...params } }),
  getBySymbol:    (symbol: string)                                   => api.get(`/stocks/${symbol}`),
  getPrice:       (symbol: string, params?: { start?: string; end?: string; interval?: string }) =>
    api.get(`/stocks/${symbol}/price`, { params }),
  getIndicators:  (symbol: string) => api.get(`/stocks/${symbol}/indicators`),
  getFundamentals:(symbol: string) => api.get(`/stocks/${symbol}/fundamentals`),
  listByMarket:   (market: string) => api.get(`/stocks/list/${market}`),
}

// ── Consistency ───────────────────────────────────────────────────────────────
export const consistencyService = {
  check: (params: { criteria: string; date: string; market?: string }) =>
    api.get('/consistency/check', { params }),
}

// ── Portfolio (legacy) ────────────────────────────────────────────────────────
export const portfolioService = {
  getPositions:   ()                                         => api.get('/portfolio/positions'),
  getPerformance: ()                                         => api.get('/portfolio/performance'),
  addPosition:    (data: Record<string, unknown>)            => api.post('/portfolio/positions', data),
  removePosition: (id: string)                               => api.delete(`/portfolio/positions/${id}`),
}

export default api
